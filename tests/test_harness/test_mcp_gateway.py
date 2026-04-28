"""Phase 4 acceptance tests — MCPGateway."""
from __future__ import annotations

import asyncio
import json
import os
import socket
import secrets
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from atrium.harness.mcp_gateway import MCPGateway, _redact
from atrium.core.mcp_server_store import MCPServerStore
from atrium.streaming.events import EventRecorder


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_socket():
    """Use a short path under /tmp to avoid AF_UNIX path-length limits."""
    sock_path = f"/tmp/atm_{secrets.token_hex(6)}.sock"
    yield sock_path
    if os.path.exists(sock_path):
        os.unlink(sock_path)


@pytest.fixture
async def mcp_store(tmp_path):
    store = MCPServerStore(str(tmp_path / "mcp.db"))
    await store.open()
    yield store
    await store.close()


@pytest.fixture
async def gateway(tmp_socket, mcp_store):
    recorder = EventRecorder()
    gw = MCPGateway(
        socket_path=tmp_socket,
        session_store=MagicMock(),
        mcp_server_store=mcp_store,
        recorder=recorder,
    )
    yield gw, recorder
    await gw.stop()


async def _start_gateway(gw: MCPGateway, sock_path: str):
    """Start the gateway server in the background."""
    task = asyncio.create_task(gw.serve())
    # Wait for socket to appear
    for _ in range(50):
        if os.path.exists(sock_path):
            break
        await asyncio.sleep(0.05)
    return task


async def _connect_and_send(sock_path: str, frames: list[dict]) -> list[bytes]:
    """Connect to the gateway, send frames, collect responses."""
    reader, writer = await asyncio.open_unix_connection(sock_path)
    for f in frames:
        writer.write(json.dumps(f).encode() + b"\n")
        await writer.drain()
    # Read all available responses (up to len(frames))
    responses = []
    try:
        for _ in range(len(frames)):
            line = await asyncio.wait_for(reader.readline(), timeout=2.0)
            if line.strip():
                responses.append(line.strip())
    except asyncio.TimeoutError:
        pass
    writer.close()
    await writer.wait_closed()
    return responses


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_unauthenticated_connection_rejected(gateway, tmp_socket):
    gw, recorder = gateway
    task = await _start_gateway(gw, tmp_socket)

    responses = await _connect_and_send(
        tmp_socket,
        [{"jsonrpc": "2.0", "method": "$/atrium/hello", "params": {"session_token": "bad_token"}}],
    )
    task.cancel()
    assert len(responses) == 1
    resp = json.loads(responses[0])
    assert "error" in resp


async def test_socket_chmod_is_0600(gateway, tmp_socket):
    gw, _ = gateway
    task = await _start_gateway(gw, tmp_socket)
    mode = oct(os.stat(tmp_socket).st_mode)
    task.cancel()
    assert mode.endswith("600")


async def test_unknown_server_emits_mcp_rejected_event(gateway, tmp_socket):
    gw, recorder = gateway
    session_id = "sess1"
    workspace_id = "ws1"
    token = "tok1"
    gw.register_token(token, session_id, workspace_id)

    task = await _start_gateway(gw, tmp_socket)
    responses = await _connect_and_send(
        tmp_socket,
        [
            {"jsonrpc": "2.0", "method": "$/atrium/hello", "params": {"session_token": token}},
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list",
             "params": {"server": "unknown_server"}},
        ],
    )
    task.cancel()
    events = recorder.replay(session_id)
    types = [e.type for e in events]
    assert "HARNESS_MCP_REJECTED" in types


async def test_allowed_server_emits_mcp_called_event(gateway, tmp_socket, mcp_store, tmp_path):
    gw, recorder = gateway
    session_id = "sess2"
    workspace_id = "ws2"
    token = "tok2"
    gw.register_token(token, session_id, workspace_id)

    # Register a fake echo MCP server (stdio: python -c "...")
    echo_script = str(tmp_path / "fake_mcp.py")
    Path(echo_script).write_text(
        'import sys,json\n'
        'for line in sys.stdin:\n'
        '    req=json.loads(line)\n'
        '    sys.stdout.write(json.dumps({"jsonrpc":"2.0","id":req.get("id"),"result":{}})+"\\n")\n'
        '    sys.stdout.flush()\n'
    )
    import sys
    await mcp_store.register(workspace_id, "echo_mcp", "stdio", f"{sys.executable} {echo_script}")

    task = await _start_gateway(gw, tmp_socket)
    await _connect_and_send(
        tmp_socket,
        [
            {"jsonrpc": "2.0", "method": "$/atrium/hello", "params": {"session_token": token}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list",
             "params": {"server": "echo_mcp"}},
        ],
    )
    await asyncio.sleep(0.2)
    task.cancel()
    events = recorder.replay(session_id)
    types = [e.type for e in events]
    assert "HARNESS_MCP_CALLED" in types


async def test_credentials_redacted_from_event_payload(gateway, tmp_socket, mcp_store, tmp_path):
    gw, recorder = gateway
    session_id = "sess3"
    workspace_id = "ws3"
    token = "tok3"
    gw.register_token(token, session_id, workspace_id)

    echo_script = str(tmp_path / "fake_mcp2.py")
    Path(echo_script).write_text(
        'import sys,json\n'
        'for line in sys.stdin:\n'
        '    req=json.loads(line)\n'
        '    sys.stdout.write(json.dumps({"jsonrpc":"2.0","id":req.get("id"),"result":{}})+"\\n")\n'
        '    sys.stdout.flush()\n'
    )
    import sys
    await mcp_store.register(workspace_id, "secret_mcp", "stdio", f"{sys.executable} {echo_script}")

    task = await _start_gateway(gw, tmp_socket)
    await _connect_and_send(
        tmp_socket,
        [
            {"jsonrpc": "2.0", "method": "$/atrium/hello", "params": {"session_token": token}},
            {"jsonrpc": "2.0", "id": 3, "method": "auth",
             "params": {"server": "secret_mcp", "token": "super_secret", "api_key": "sk-123"}},
        ],
    )
    await asyncio.sleep(0.2)
    task.cancel()
    events = recorder.replay(session_id)
    mcp_called = [e for e in events if e.type == "HARNESS_MCP_CALLED"]
    assert len(mcp_called) >= 1
    payload = mcp_called[0].payload.get("params", {})
    if "token" in payload:
        assert payload["token"] == "***REDACTED***"
    if "api_key" in payload:
        assert payload["api_key"] == "***REDACTED***"


async def test_concurrent_connections_handled(gateway, tmp_socket):
    """Multiple concurrent connections don't deadlock or crash."""
    gw, recorder = gateway
    task = await _start_gateway(gw, tmp_socket)

    async def bad_conn():
        return await _connect_and_send(
            tmp_socket,
            [{"jsonrpc": "2.0", "method": "$/atrium/hello",
              "params": {"session_token": f"bad_{id(asyncio.current_task())}"}}],
        )

    results = await asyncio.gather(*[bad_conn() for _ in range(10)], return_exceptions=True)
    task.cancel()
    # All connections handled, no exceptions raised from gather
    for r in results:
        assert not isinstance(r, Exception) or isinstance(r, asyncio.CancelledError)


# ---------------------------------------------------------------------------
# _redact unit tests
# ---------------------------------------------------------------------------

def test_redact_strips_known_secret_fields():
    params = {"api_key": "sk-123", "normal": "value", "token": "abc"}
    redacted = _redact(params)
    assert redacted["api_key"] == "***REDACTED***"
    assert redacted["token"] == "***REDACTED***"
    assert redacted["normal"] == "value"


def test_redact_handles_nested_dicts():
    params = {"auth": {"password": "hunter2", "username": "admin"}}
    redacted = _redact(params)
    assert redacted["auth"]["password"] == "***REDACTED***"
    assert redacted["auth"]["username"] == "admin"


def test_redact_non_dict_returns_empty():
    assert _redact(None) == {}
    assert _redact("string") == {}  # type: ignore[arg-type]
