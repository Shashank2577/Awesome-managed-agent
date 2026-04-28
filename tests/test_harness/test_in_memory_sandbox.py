"""Phase 2 InMemorySandboxRunner tests."""
import asyncio
import pytest
from atrium.harness.sandbox import InMemorySandboxRunner, ResourceLimits, NetworkPolicy
from atrium.harness.runtimes.echo import EchoRuntime
from atrium.harness.session import Session


@pytest.fixture
def session(tmp_path):
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir(mode=0o700)
    return Session(
        workspace_id="ws1",
        objective="test",
        runtime="echo",
        model="",
        workspace_path=str(ws_dir),
    )


@pytest.fixture
def runtime():
    return EchoRuntime()


@pytest.fixture
def limits():
    return ResourceLimits()


@pytest.fixture
def policy():
    return NetworkPolicy()


async def test_in_memory_runner_starts_echo_subprocess(session, runtime, limits, policy):
    runner = await InMemorySandboxRunner.start(session, runtime, "", {}, limits, policy)
    assert runner._proc is not None
    assert runner._proc.returncode is None  # still alive
    await runner.kill()


async def test_stream_events_yields_one_event_per_line(session, runtime, limits, policy, tmp_path):
    runner = await InMemorySandboxRunner.start(session, runtime, "", {}, limits, policy)
    await runner.send_input("hello")
    events = []
    async for line in runner.stream_events():
        import json
        events.append(json.loads(line.decode() if isinstance(line, bytes) else line))
        if events and events[-1].get("type") == "result":
            break
    types = [e["type"] for e in events]
    assert "ready" in types
    assert "result" in types


async def test_send_input_writes_to_subprocess_stdin(session, runtime, limits, policy):
    runner = await InMemorySandboxRunner.start(session, runtime, "", {}, limits, policy)
    # Should not raise
    await runner.send_input("test objective")
    await runner.kill()


async def test_stop_terminates_subprocess(session, runtime, limits, policy):
    runner = await InMemorySandboxRunner.start(session, runtime, "", {}, limits, policy)
    await runner.stop(timeout_seconds=3.0)
    assert runner._proc.returncode is not None


async def test_kill_sigkills_subprocess(session, runtime, limits, policy):
    runner = await InMemorySandboxRunner.start(session, runtime, "", {}, limits, policy)
    await runner.kill()
    assert runner._proc.returncode is not None
