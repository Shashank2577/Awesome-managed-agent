"""Docker + live Anthropic API integration tests for DirectAnthropicRuntime.

Gated with -m docker. Same shape as test_oas_session.py.

Run with:
  pytest -m docker tests/integration/docker/test_anthropic_session.py
"""
import asyncio
import os
import pytest

from atrium.harness.runtimes.direct_anthropic import DirectAnthropicRuntime
from atrium.harness.sandbox import DockerSandboxRunner, ResourceLimits, NetworkPolicy
from atrium.harness.bridge import BridgeStream, GuardrailEnforcer
from atrium.harness.session import Session
from atrium.core.artifact_store import ArtifactStore
from atrium.streaming.events import EventRecorder

pytestmark = [pytest.mark.docker]

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
REGISTRY = os.environ.get("ATRIUM_REGISTRY", "atrium")
MODEL = "anthropic:claude-sonnet-4-6"


@pytest.fixture
async def session(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir(mode=0o700)
    return Session(
        workspace_id="docker_anthropic_test",
        objective="List files in /workspace and return the list.",
        runtime="direct_anthropic",
        model=MODEL,
        workspace_path=str(ws),
    )


@pytest.fixture
async def artifact_store(tmp_path):
    s = ArtifactStore(str(tmp_path / "artifacts.db"))
    await s.open()
    yield s
    await s.close()


@pytest.fixture
async def sandbox(session):
    runtime = DirectAnthropicRuntime()
    env = {"ANTHROPIC_API_KEY": API_KEY} if API_KEY else {}
    s = await DockerSandboxRunner.start(
        session=session,
        runtime=runtime,
        model=MODEL,
        env=env,
        limits=ResourceLimits(wall_clock_seconds=120),
        network_policy=NetworkPolicy(allow_egress=["https://api.anthropic.com"]),
        registry=REGISTRY,
    )
    yield s
    await s.stop()


async def test_anthropic_session_completes_and_returns_message(session, sandbox, artifact_store):
    recorder = EventRecorder()
    bridge = BridgeStream(sandbox, session, recorder, artifact_store, GuardrailEnforcer(max_tool_calls=50))
    result = await asyncio.wait_for(bridge.run(session.objective), timeout=120)
    assert result.final_message != ""


async def test_anthropic_session_emits_at_least_one_tool_called_event(session, sandbox, artifact_store):
    recorder = EventRecorder()
    bridge = BridgeStream(sandbox, session, recorder, artifact_store, GuardrailEnforcer(max_tool_calls=50))
    await asyncio.wait_for(bridge.run(session.objective), timeout=120)
    events = recorder.replay(session.session_id)
    types = [e.type for e in events]
    assert "HARNESS_TOOL_CALLED" in types


async def test_anthropic_session_artifact_count_matches_files_written(session, sandbox, artifact_store):
    recorder = EventRecorder()
    bridge = BridgeStream(sandbox, session, recorder, artifact_store, GuardrailEnforcer(max_tool_calls=50))
    result = await asyncio.wait_for(bridge.run(session.objective), timeout=120)
    db_artifacts = await artifact_store.list_for_session(session.session_id)
    assert len(result.artifacts) == len(db_artifacts)


async def test_anthropic_session_budget_consumed_reported(session, sandbox, artifact_store):
    recorder = EventRecorder()
    bridge = BridgeStream(sandbox, session, recorder, artifact_store, GuardrailEnforcer(max_tool_calls=50))
    result = await asyncio.wait_for(bridge.run(session.objective), timeout=120)
    events = recorder.replay(session.session_id)
    types = [e.type for e in events]
    assert "BUDGET_CONSUMED" in types
    assert result.tokens_used > 0


async def test_anthropic_session_killed_on_max_tool_calls_violation(session, tmp_path, artifact_store):
    from atrium.core.errors import GuardrailViolation
    runtime = DirectAnthropicRuntime()
    env = {"ANTHROPIC_API_KEY": API_KEY} if API_KEY else {}
    s = await DockerSandboxRunner.start(
        session=session,
        runtime=runtime,
        model=MODEL,
        env=env,
        limits=ResourceLimits(wall_clock_seconds=60),
        network_policy=NetworkPolicy(allow_egress=["https://api.anthropic.com"]),
        registry=REGISTRY,
    )
    try:
        recorder = EventRecorder()
        bridge = BridgeStream(s, session, recorder, artifact_store, GuardrailEnforcer(max_tool_calls=1))
        with pytest.raises(GuardrailViolation):
            await asyncio.wait_for(bridge.run("Write many files"), timeout=60)
    finally:
        await s.stop()
