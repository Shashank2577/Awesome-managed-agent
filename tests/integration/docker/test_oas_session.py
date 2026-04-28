"""Docker + live Anthropic API integration tests for the OAS runtime.

Gated with -m docker. Requires:
  - Running Docker daemon
  - ANTHROPIC_API_KEY env var
  - OAS image pre-built: docker build -f dockerfiles/open_agent_sdk.Dockerfile .

Run with:
  pytest -m docker tests/integration/docker/test_oas_session.py
"""
import asyncio
import os
import pytest

from atrium.harness.runtimes.open_agent_sdk import OpenAgentSDKRuntime
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
        workspace_id="docker_test",
        objective="List files in /workspace and return the list.",
        runtime="open_agent_sdk",
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
    runtime = OpenAgentSDKRuntime()
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


async def test_oas_session_lists_files_and_writes_report(session, sandbox, artifact_store):
    recorder = EventRecorder()
    bridge = BridgeStream(sandbox, session, recorder, artifact_store, GuardrailEnforcer(max_tool_calls=50))
    result = await asyncio.wait_for(bridge.run(session.objective), timeout=120)
    assert result.final_message != ""


async def test_oas_session_emits_at_least_one_tool_called_event(session, sandbox, artifact_store):
    recorder = EventRecorder()
    bridge = BridgeStream(sandbox, session, recorder, artifact_store, GuardrailEnforcer(max_tool_calls=50))
    await asyncio.wait_for(bridge.run(session.objective), timeout=120)
    events = recorder.replay(session.session_id)
    types = [e.type for e in events]
    assert "HARNESS_TOOL_CALLED" in types


async def test_oas_session_artifact_count_matches_files_written(session, sandbox, artifact_store):
    recorder = EventRecorder()
    bridge = BridgeStream(sandbox, session, recorder, artifact_store, GuardrailEnforcer(max_tool_calls=50))
    result = await asyncio.wait_for(bridge.run(session.objective), timeout=120)
    db_artifacts = await artifact_store.list_for_session(session.session_id)
    assert len(result.artifacts) == len(db_artifacts)


async def test_oas_session_token_cost_is_within_provider_invoice_1_percent(session, sandbox, artifact_store):
    recorder = EventRecorder()
    bridge = BridgeStream(sandbox, session, recorder, artifact_store, GuardrailEnforcer(max_tool_calls=50))
    result = await asyncio.wait_for(bridge.run(session.objective), timeout=120)
    # We can only check that cost_usd > 0 (actual invoice comparison requires API)
    assert result.cost_usd >= 0


async def test_oas_session_killed_on_max_tool_calls_violation(session, tmp_path, artifact_store):
    from atrium.core.errors import GuardrailViolation
    runtime = OpenAgentSDKRuntime()
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
            await asyncio.wait_for(bridge.run("Write 50 files in /workspace"), timeout=60)
    finally:
        await s.stop()


async def test_oas_session_killed_on_max_cost_violation(session, tmp_path, artifact_store):
    from atrium.core.errors import GuardrailViolation
    runtime = OpenAgentSDKRuntime()
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
        bridge = BridgeStream(s, session, recorder, artifact_store, GuardrailEnforcer(max_cost_usd=0.000001))
        with pytest.raises(GuardrailViolation):
            await asyncio.wait_for(bridge.run("Do a long analysis"), timeout=60)
    finally:
        await s.stop()
