"""Phase 2 session lifecycle acceptance tests."""
import os
import pytest
from atrium.harness.session import Session, SessionStatus, SessionStore
from atrium.core.errors import ConflictError


@pytest.fixture
async def store(tmp_path):
    db_path = str(tmp_path / "sessions.db")
    s = SessionStore(db_path=db_path, sessions_root=str(tmp_path / "sessions"))
    await s.open()
    yield s
    await s.close()


async def test_create_session_creates_workspace_dir_with_mode_0700(store, tmp_path):
    session = Session(workspace_id="ws1", objective="do something", runtime="echo", model="")
    created = await store.create(session)
    workspace = created.workspace_dir
    assert workspace.exists()
    mode = os.stat(str(workspace)).st_mode & 0o777
    assert mode == 0o700


async def test_set_status_validates_transition(store):
    session = Session(workspace_id="ws1", objective="test", runtime="echo", model="")
    created = await store.create(session)
    await store.set_status("ws1", created.session_id, SessionStatus.RUNNING)
    fetched = await store.get("ws1", created.session_id)
    assert fetched.status == SessionStatus.RUNNING


async def test_set_status_rejects_invalid_transition(store):
    session = Session(workspace_id="ws1", objective="test", runtime="echo", model="")
    created = await store.create(session)
    # CREATED → COMPLETED is invalid
    with pytest.raises(ConflictError):
        await store.set_status("ws1", created.session_id, SessionStatus.COMPLETED)


async def test_get_returns_none_for_unknown_session(store):
    result = await store.get("ws1", "no-such-id")
    assert result is None


async def test_list_by_workspace_filters_by_status(store):
    for i in range(3):
        s = Session(workspace_id="ws1", objective=f"obj{i}", runtime="echo", model="")
        created = await store.create(s)
        if i < 2:
            await store.set_status("ws1", created.session_id, SessionStatus.RUNNING)

    running = await store.list_by_workspace("ws1", status=SessionStatus.RUNNING)
    created_sessions = await store.list_by_workspace("ws1", status=SessionStatus.CREATED)
    assert len(running) == 2
    assert len(created_sessions) == 1


async def test_session_isolated_across_workspaces(store):
    s1 = Session(workspace_id="ws1", objective="x", runtime="echo", model="")
    await store.create(s1)
    # ws2 should see nothing
    sessions = await store.list_by_workspace("ws2")
    assert sessions == []


async def test_workspace_dir_is_deleted_on_session_delete(store):
    s = Session(workspace_id="ws1", objective="del", runtime="echo", model="")
    created = await store.create(s)
    workspace_path = str(created.workspace_dir)
    assert os.path.exists(workspace_path)
    await store.delete("ws1", created.session_id)
    assert not os.path.exists(workspace_path)
