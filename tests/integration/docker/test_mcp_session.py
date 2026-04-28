"""Docker + live API + MCP gateway integration tests.

Gated with -m docker. Requires:
  - Running Docker daemon
  - ANTHROPIC_API_KEY env var
  - OpenClaude image pre-built

Run with:
  pytest -m docker tests/integration/docker/test_mcp_session.py
"""
import asyncio
import os
import pytest

from atrium.harness.runtimes.openclaude import OpenClaudeRuntime
from atrium.harness.sandbox import DockerSandboxRunner, ResourceLimits, NetworkPolicy
from atrium.harness.bridge import BridgeStream, GuardrailEnforcer
from atrium.harness.mcp_gateway import MCPGateway
from atrium.harness.session import Session
from atrium.core.artifact_store import ArtifactStore
from atrium.core.mcp_server_store import MCPServerStore
from atrium.streaming.events import EventRecorder

pytestmark = [pytest.mark.docker]

REGISTRY = os.environ.get("ATRIUM_REGISTRY", "atrium")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = "anthropic:claude-sonnet-4-6"
GITHUB_MCP_CMD = "npx -y @modelcontextprotocol/server-github"


@pytest.fixture
async def mcp_store(tmp_path):
    s = MCPServerStore(str(tmp_path / "mcp.db"))
    await s.open()
    yield s
    await s.close()


@pytest.fixture
async def gateway(tmp_path, mcp_store):
    sock = str(tmp_path / "mcp.sock")
    recorder = EventRecorder()
    gw = MCPGateway(
        socket_path=sock,
        session_store=None,  # type: ignore
        mcp_server_store=mcp_store,
        recorder=recorder,
    )
    task = asyncio.create_task(gw.serve())
    for _ in range(50):
        if os.path.exists(sock):
            break
        await asyncio.sleep(0.05)
    yield gw, recorder, sock
    await gw.stop()
    task.cancel()


async def test_session_lists_repos_via_github_mcp(tmp_path, mcp_store, gateway):
    gw, recorder, sock = gateway
    workspace_id = "ws_mcp1"
    await mcp_store.register(workspace_id, "github", "stdio", GITHUB_MCP_CMD)

    session = Session(
        workspace_id=workspace_id,
        objective="List the first 3 repositories for the 'octocat' GitHub user via the GitHub MCP tool.",
        runtime="openclaude", model=MODEL,
    )
    import secrets
    token = secrets.token_hex(16)
    gw.register_token(token, session.session_id, workspace_id)

    runtime = OpenClaudeRuntime()
    env = {"ANTHROPIC_API_KEY": ANTHROPIC_API_KEY}
    sandbox = await DockerSandboxRunner.start(
        session=session, runtime=runtime, model=MODEL, env=env,
        limits=ResourceLimits(wall_clock_seconds=120),
        network_policy=NetworkPolicy(allow_egress=["https://api.anthropic.com"], allow_mcp=True),
        registry=REGISTRY,
        mcp_socket_path=sock, session_token=token,
    )
    artifact_store = ArtifactStore(":memory:")
    await artifact_store.open()
    bridge = BridgeStream(sandbox, session, recorder, artifact_store, GuardrailEnforcer(max_tool_calls=30))
    result = await asyncio.wait_for(bridge.run(session.objective), timeout=120)
    await sandbox.stop()
    events = recorder.replay(session.session_id)
    assert any(e.type == "HARNESS_MCP_CALLED" for e in events)


async def test_session_with_no_allowed_mcp_cannot_call_anything(tmp_path, mcp_store, gateway):
    """Workspace with no MCP servers registered → all calls rejected."""
    gw, recorder, sock = gateway
    workspace_id = "ws_mcp_empty"
    # No servers registered for this workspace

    session = Session(
        workspace_id=workspace_id,
        objective="Try to call the github MCP server.",
        runtime="openclaude", model=MODEL,
    )
    import secrets
    token = secrets.token_hex(16)
    gw.register_token(token, session.session_id, workspace_id)

    runtime = OpenClaudeRuntime()
    env = {"ANTHROPIC_API_KEY": ANTHROPIC_API_KEY}
    sandbox = await DockerSandboxRunner.start(
        session=session, runtime=runtime, model=MODEL, env=env,
        limits=ResourceLimits(wall_clock_seconds=60),
        network_policy=NetworkPolicy(allow_egress=["https://api.anthropic.com"], allow_mcp=True),
        registry=REGISTRY,
        mcp_socket_path=sock, session_token=token,
    )
    artifact_store = ArtifactStore(":memory:")
    await artifact_store.open()
    bridge = BridgeStream(sandbox, session, recorder, artifact_store, GuardrailEnforcer(max_tool_calls=10))
    await asyncio.wait_for(bridge.run(session.objective), timeout=60)
    await sandbox.stop()
    # No MCP_CALLED — possibly MCP_REJECTED or no MCP events at all
    events = recorder.replay(session.session_id)
    assert not any(e.type == "HARNESS_MCP_CALLED" for e in events)


async def test_attempt_to_call_disallowed_server_logged_as_rejected(tmp_path, mcp_store, gateway):
    gw, recorder, sock = gateway
    workspace_id = "ws_mcp_rejected"
    # Register github but NOT linear
    await mcp_store.register(workspace_id, "github", "stdio", GITHUB_MCP_CMD)

    session = Session(
        workspace_id=workspace_id,
        objective="Call the 'linear' MCP server to list my issues.",
        runtime="openclaude", model=MODEL,
    )
    import secrets
    token = secrets.token_hex(16)
    gw.register_token(token, session.session_id, workspace_id)

    runtime = OpenClaudeRuntime()
    env = {"ANTHROPIC_API_KEY": ANTHROPIC_API_KEY}
    sandbox = await DockerSandboxRunner.start(
        session=session, runtime=runtime, model=MODEL, env=env,
        limits=ResourceLimits(wall_clock_seconds=60),
        network_policy=NetworkPolicy(allow_egress=["https://api.anthropic.com"], allow_mcp=True),
        registry=REGISTRY,
        mcp_socket_path=sock, session_token=token,
    )
    artifact_store = ArtifactStore(":memory:")
    await artifact_store.open()
    bridge = BridgeStream(sandbox, session, recorder, artifact_store, GuardrailEnforcer(max_tool_calls=20))
    await asyncio.wait_for(bridge.run(session.objective), timeout=60)
    await sandbox.stop()
    events = recorder.replay(session.session_id)
    assert any(e.type == "HARNESS_MCP_REJECTED" for e in events)
