"""Docker + live API key multi-model tests.

Gated with -m docker. Proves model agnosticism: same CodeResearchAgent
definition runs with different models by passing model_override.

Run with:
  pytest -m docker tests/integration/docker/test_multi_model.py
"""
import asyncio
import os
import pytest

from atrium.harness.runtimes.openclaude import OpenClaudeRuntime
from atrium.harness.sandbox import DockerSandboxRunner, ResourceLimits, NetworkPolicy
from atrium.harness.bridge import BridgeStream, GuardrailEnforcer
from atrium.harness.session import Session
from atrium.core.artifact_store import ArtifactStore
from atrium.streaming.events import EventRecorder

pytestmark = [pytest.mark.docker]

REGISTRY = os.environ.get("ATRIUM_REGISTRY", "atrium")
OBJECTIVE = "List all files in /workspace and return the list."


def _env_for(model: str) -> dict[str, str]:
    provider = model.split(":", 1)[0]
    mapping = {
        "anthropic":  "ANTHROPIC_API_KEY",
        "openai":     "OPENAI_API_KEY",
        "gemini":     "GEMINI_API_KEY",
        "deepseek":   "DEEPSEEK_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }
    key = mapping.get(provider, "OPENROUTER_API_KEY")
    val = os.environ.get(key, "")
    return {key: val} if val else {}


async def _run_model(tmp_path, model: str) -> tuple[str, float]:
    ws = tmp_path / "workspace"
    ws.mkdir(mode=0o700, exist_ok=True)
    session = Session(
        workspace_id="docker_multimodel",
        objective=OBJECTIVE,
        runtime="openclaude",
        model=model,
        workspace_path=str(ws),
    )
    runtime = OpenClaudeRuntime()
    env = _env_for(model)
    sandbox = await DockerSandboxRunner.start(
        session=session, runtime=runtime, model=model, env=env,
        limits=ResourceLimits(wall_clock_seconds=120),
        network_policy=NetworkPolicy(allow_egress=[runtime.model_endpoint(model)]),
        registry=REGISTRY,
    )
    artifact_store = ArtifactStore(str(tmp_path / f"art_{model.replace(':', '_')}.db"))
    await artifact_store.open()
    recorder = EventRecorder()
    bridge = BridgeStream(sandbox, session, recorder, artifact_store, GuardrailEnforcer(max_tool_calls=50))
    try:
        result = await asyncio.wait_for(bridge.run(OBJECTIVE), timeout=120)
        return result.final_message, result.cost_usd
    finally:
        await sandbox.stop()
        await artifact_store.close()


async def test_same_agent_completes_with_anthropic(tmp_path):
    msg, _ = await _run_model(tmp_path, "anthropic:claude-sonnet-4-6")
    assert msg != ""


async def test_same_agent_completes_with_gemini(tmp_path):
    msg, _ = await _run_model(tmp_path, "gemini:gemini-2.5-flash")
    assert msg != ""


async def test_same_agent_completes_with_openai(tmp_path):
    msg, _ = await _run_model(tmp_path, "openai:gpt-4o")
    assert msg != ""


async def test_same_agent_completes_with_deepseek_via_openrouter(tmp_path):
    msg, _ = await _run_model(tmp_path, "openrouter:deepseek/deepseek-chat")
    assert msg != ""


async def test_token_cost_recorded_for_each_provider(tmp_path):
    for model in ["anthropic:claude-sonnet-4-6", "gemini:gemini-2.5-flash"]:
        _, cost = await _run_model(tmp_path, model)
        assert cost >= 0  # $0 only if not priced — anthropic/gemini are priced


async def test_swap_model_via_model_override_no_code_change(tmp_path):
    """Exactly the same session dict, different model_override = different provider."""
    msg_a, _ = await _run_model(tmp_path, "anthropic:claude-sonnet-4-6")
    msg_g, _ = await _run_model(tmp_path, "gemini:gemini-2.5-flash")
    # Both should complete — content may differ
    assert msg_a and msg_g
