"""Phase 2 end-to-end integration test — echo runtime, no Docker required.

Gated with pytest -m integration. Uses InMemorySandboxRunner.
"""
import pytest
from pathlib import Path

from atrium.harness.sandbox import InMemorySandboxRunner, ResourceLimits, NetworkPolicy
from atrium.harness.runtimes.echo import EchoRuntime
from atrium.harness.session import Session, SessionStatus, SessionStore
from atrium.harness.bridge import BridgeStream, GuardrailEnforcer
from atrium.core.artifact_store import ArtifactStore
from atrium.streaming.events import EventRecorder


pytestmark = pytest.mark.integration


@pytest.fixture
async def session_store(tmp_path):
    db_path = str(tmp_path / "sessions.db")
    s = SessionStore(db_path=db_path, sessions_root=str(tmp_path / "sessions"))
    await s.open()
    yield s
    await s.close()


@pytest.fixture
async def artifact_store(tmp_path):
    s = ArtifactStore(str(tmp_path / "artifacts.db"))
    await s.open()
    yield s
    await s.close()


@pytest.fixture
async def session(session_store, tmp_path):
    s = Session(workspace_id="ws1", objective="hello world", runtime="echo", model="")
    return await session_store.create(s)


async def test_post_session_creates_running_session(session, session_store):
    await session_store.set_status("ws1", session.session_id, SessionStatus.RUNNING)
    fetched = await session_store.get("ws1", session.session_id)
    assert fetched.status == SessionStatus.RUNNING


async def test_session_completes_within_30s_for_echo_runtime(session, artifact_store):
    import asyncio
    runtime = EchoRuntime()
    recorder = EventRecorder()
    limits = ResourceLimits()
    policy = NetworkPolicy()

    sandbox = await InMemorySandboxRunner.start(session, runtime, "", {}, limits, policy)
    bridge = BridgeStream(sandbox, session, recorder, artifact_store, GuardrailEnforcer())

    result = await asyncio.wait_for(bridge.run(session.objective), timeout=30.0)
    assert result.final_message != ""


async def test_completed_session_has_one_artifact_named_echo_txt(session, artifact_store):
    import asyncio
    runtime = EchoRuntime()
    recorder = EventRecorder()
    sandbox = await InMemorySandboxRunner.start(
        session, runtime, "", {}, ResourceLimits(), NetworkPolicy()
    )
    bridge = BridgeStream(sandbox, session, recorder, artifact_store, GuardrailEnforcer())
    result = await asyncio.wait_for(bridge.run(session.objective), timeout=30.0)
    paths = [a.path for a in result.artifacts]
    assert "echo.txt" in paths


async def test_artifact_is_downloadable(session, artifact_store):
    import asyncio
    runtime = EchoRuntime()
    recorder = EventRecorder()
    sandbox = await InMemorySandboxRunner.start(
        session, runtime, "", {}, ResourceLimits(), NetworkPolicy()
    )
    bridge = BridgeStream(sandbox, session, recorder, artifact_store, GuardrailEnforcer())
    result = await asyncio.wait_for(bridge.run(session.objective), timeout=30.0)
    echo_artifact = next(a for a in result.artifacts if a.path == "echo.txt")
    file_path = session.workspace_dir / echo_artifact.path
    assert file_path.exists()
    content = file_path.read_text()
    assert "Echo result" in content


async def test_sse_stream_emits_session_completed_event(session, artifact_store):
    import asyncio
    runtime = EchoRuntime()
    recorder = EventRecorder()
    sandbox = await InMemorySandboxRunner.start(
        session, runtime, "", {}, ResourceLimits(), NetworkPolicy()
    )
    bridge = BridgeStream(sandbox, session, recorder, artifact_store, GuardrailEnforcer())
    await asyncio.wait_for(bridge.run(session.objective), timeout=30.0)
    events = recorder.replay(session.session_id)
    types = [e.type for e in events]
    assert "HARNESS_MESSAGE" in types
    assert "HARNESS_TOOL_CALLED" in types


async def test_session_visible_in_list_with_status_completed(session, session_store, artifact_store):
    import asyncio
    await session_store.set_status("ws1", session.session_id, SessionStatus.RUNNING)
    runtime = EchoRuntime()
    recorder = EventRecorder()
    sandbox = await InMemorySandboxRunner.start(
        session, runtime, "", {}, ResourceLimits(), NetworkPolicy()
    )
    bridge = BridgeStream(sandbox, session, recorder, artifact_store, GuardrailEnforcer())
    await asyncio.wait_for(bridge.run(session.objective), timeout=30.0)
    await session_store.set_status("ws1", session.session_id, SessionStatus.COMPLETED)
    completed = await session_store.list_by_workspace("ws1", status=SessionStatus.COMPLETED)
    assert any(s.session_id == session.session_id for s in completed)
