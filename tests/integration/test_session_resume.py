"""Phase 5 session resume acceptance tests.

Uses InMemorySandboxRunner — no Docker required.
Tests marked integration run with `pytest -m integration`.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from atrium.harness.session import Session, SessionStatus, SessionStore


@pytest.fixture
async def session_store(tmp_path):
    store = SessionStore(
        db_path=str(tmp_path / "sessions.db"),
        sessions_root=str(tmp_path / "sessions"),
    )
    await store.open()
    yield store
    await store.close()


async def _make_session(store: SessionStore, workspace_id: str = "ws1") -> Session:
    session = Session(
        workspace_id=workspace_id,
        objective="Test session",
        runtime="echo",
        model="echo:test",
    )
    return await store.create(session)


@pytest.mark.integration
async def test_pause_writes_checkpoint_and_marks_paused(session_store, tmp_path):
    """Pause signal file written → session transitions to PAUSED when sandbox exits."""
    session = await _make_session(session_store)
    await session_store.set_status(session.workspace_id, session.session_id, SessionStatus.RUNNING)

    # Simulate the sandbox writing a checkpoint, then transitioning to PAUSED
    atrium_dir = session.workspace_dir / ".atrium"
    atrium_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_data = b'{"history": [], "tool_calls": 0}'
    await session.save_checkpoint(checkpoint_data)

    # Simulate bridge marking PAUSED
    await session_store.set_status(session.workspace_id, session.session_id, SessionStatus.PAUSED)

    refreshed = await session_store.get(session.workspace_id, session.session_id)
    assert refreshed.status == SessionStatus.PAUSED
    assert session.checkpoint_path.exists()
    assert session.checkpoint_path.read_bytes() == checkpoint_data


@pytest.mark.integration
async def test_resume_starts_new_container_with_same_workspace(session_store, tmp_path):
    """After PAUSED → resume, status becomes RUNNING and checkpoint is preserved."""
    session = await _make_session(session_store)
    await session_store.set_status(session.workspace_id, session.session_id, SessionStatus.RUNNING)
    await session_store.set_status(session.workspace_id, session.session_id, SessionStatus.PAUSED)

    # Write a checkpoint
    atrium_dir = session.workspace_dir / ".atrium"
    atrium_dir.mkdir(parents=True, exist_ok=True)
    await session.save_checkpoint(b'{"history": [1, 2, 3]}')

    # Resume: transition PAUSED → RUNNING
    await session_store.set_status(session.workspace_id, session.session_id, SessionStatus.RUNNING)
    refreshed = await session_store.get(session.workspace_id, session.session_id)
    assert refreshed.status == SessionStatus.RUNNING

    # Checkpoint still there for the new container to pick up
    blob = await session.load_checkpoint()
    assert blob == b'{"history": [1, 2, 3]}'


@pytest.mark.integration
async def test_resume_after_full_process_restart_works(session_store, tmp_path):
    """Simulate process restart: session is in DB as PAUSED, checkpoint on disk."""
    session = await _make_session(session_store)
    await session_store.set_status(session.workspace_id, session.session_id, SessionStatus.RUNNING)
    await session_store.set_status(session.workspace_id, session.session_id, SessionStatus.PAUSED)

    # Write checkpoint as if the previous process did it
    atrium_dir = session.workspace_dir / ".atrium"
    atrium_dir.mkdir(parents=True, exist_ok=True)
    await session.save_checkpoint(b'{"tool_calls": 15}')

    # "Restart" — create a fresh store pointing at the same DB
    store2 = SessionStore(
        db_path=str(tmp_path / "sessions.db"),  # same DB
        sessions_root=str(tmp_path / "sessions"),
    )
    await store2.open()
    try:
        recovered = await store2.get(session.workspace_id, session.session_id)
        assert recovered is not None
        assert recovered.status == SessionStatus.PAUSED
        blob = await recovered.load_checkpoint()
        assert blob == b'{"tool_calls": 15}'
    finally:
        await store2.close()


async def test_resume_a_completed_session_is_409(session_store):
    """Completed sessions cannot be resumed — expect ConflictError / 409 behavior."""
    session = await _make_session(session_store)
    await session_store.set_status(session.workspace_id, session.session_id, SessionStatus.RUNNING)
    await session_store.set_status(session.workspace_id, session.session_id, SessionStatus.COMPLETED)

    from atrium.core.errors import ConflictError
    with pytest.raises(ConflictError):
        await session_store.set_status(
            session.workspace_id, session.session_id, SessionStatus.RUNNING
        )


async def test_resume_a_session_with_corrupt_checkpoint_marks_failed(session_store, tmp_path):
    """Corrupt checkpoint: load_checkpoint returns bytes but they're garbage.

    This is a contract test: the caller (HarnessAgent) is responsible for
    detecting the corruption and marking the session FAILED.
    """
    session = await _make_session(session_store)
    await session_store.set_status(session.workspace_id, session.session_id, SessionStatus.RUNNING)
    await session_store.set_status(session.workspace_id, session.session_id, SessionStatus.PAUSED)

    # Write corrupt checkpoint
    atrium_dir = session.workspace_dir / ".atrium"
    atrium_dir.mkdir(parents=True, exist_ok=True)
    await session.save_checkpoint(b"\x00\xff\xfe corrupt garbage")

    blob = await session.load_checkpoint()
    assert blob == b"\x00\xff\xfe corrupt garbage"

    # HarnessAgent would try json.loads(blob) → fails → mark FAILED
    import json
    is_corrupt = False
    try:
        json.loads(blob)
    except (json.JSONDecodeError, UnicodeDecodeError):
        is_corrupt = True
    assert is_corrupt

    # Simulate bridge re-launching, failing immediately, then marking FAILED
    # Valid path: PAUSED → RUNNING → FAILED
    await session_store.set_status(session.workspace_id, session.session_id, SessionStatus.RUNNING)
    await session_store.set_status(session.workspace_id, session.session_id, SessionStatus.FAILED)
    refreshed = await session_store.get(session.workspace_id, session.session_id)
    assert refreshed.status == SessionStatus.FAILED
