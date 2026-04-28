"""MCP Gateway — proxies JSON-RPC 2.0 MCP calls from sandboxed containers.

Architecture:
  - Listens on a Unix socket (config.mcp_socket_path, default /run/atrium/mcp.sock)
  - Containers bind-mount the socket and send MCP traffic through it
  - First frame from each connection must be a hello with session_token
  - Subsequent frames are forwarded to the named upstream MCP server
  - Disallowed server names → HARNESS_MCP_REJECTED event; no proxy
  - Allowed calls → proxied + HARNESS_MCP_CALLED event with redacted params

Wire format: one JSON object per line (newline-framed JSON-RPC 2.0).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atrium.core.mcp_server_store import MCPServerStore
    from atrium.harness.session import SessionStore
    from atrium.streaming.events import EventRecorder

logger = logging.getLogger(__name__)

# Fields to redact from MCP call params before logging
_SECRET_FIELD_NAMES = frozenset(
    {"password", "api_key", "apikey", "token", "secret", "authorization", "credential"}
)
_REDACTED = "***REDACTED***"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _redact(params: dict | None) -> dict:
    """Recursively redact obvious secrets from a params dict."""
    if not isinstance(params, dict):
        return {}
    out = {}
    for k, v in params.items():
        if k.lower() in _SECRET_FIELD_NAMES:
            out[k] = _REDACTED
        elif isinstance(v, dict):
            out[k] = _redact(v)
        else:
            out[k] = v
    return out


def _jsonrpc_error(id_: object, code: int, message: str) -> bytes:
    return (
        json.dumps({"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}})
        + "\n"
    ).encode()


# ---------------------------------------------------------------------------
# Upstream MCP connection (simplified: process stdio or HTTP; Phase 4 = stdio)
# ---------------------------------------------------------------------------

class _StdioUpstream:
    """Manages one upstream MCP server process per (workspace_id, server_name)."""

    def __init__(self, command: list[str]) -> None:
        self._command = command
        self._proc: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()

    async def call(self, frame: dict) -> dict:
        async with self._lock:
            if self._proc is None or self._proc.returncode is not None:
                self._proc = await asyncio.create_subprocess_exec(
                    *self._command,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
            assert self._proc.stdin and self._proc.stdout
            self._proc.stdin.write(json.dumps(frame).encode() + b"\n")
            await self._proc.stdin.drain()
            line = await self._proc.stdout.readline()
        try:
            return json.loads(line.decode())
        except json.JSONDecodeError:
            return {"jsonrpc": "2.0", "id": frame.get("id"), "error": {"code": -32603, "message": "upstream error"}}

    async def close(self) -> None:
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=3)
            except asyncio.TimeoutError:
                self._proc.kill()


class _HttpUpstream:
    """Simple HTTP upstream for SSE/HTTP MCP servers."""

    def __init__(self, url: str) -> None:
        self._url = url

    async def call(self, frame: dict) -> dict:
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    self._url,
                    json=frame,
                    headers={"Content-Type": "application/json"},
                    timeout=30,
                )
                return resp.json()
        except Exception as exc:
            return {"jsonrpc": "2.0", "id": frame.get("id"), "error": {"code": -32603, "message": str(exc)}}

    async def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# MCPGateway
# ---------------------------------------------------------------------------

class MCPGateway:
    """Async MCP gateway — owns the Unix socket lifecycle."""

    def __init__(
        self,
        socket_path: str,
        session_store: "SessionStore",
        mcp_server_store: "MCPServerStore",
        recorder: "EventRecorder",
    ) -> None:
        self._socket_path = socket_path
        self._session_store = session_store
        self._mcp_server_store = mcp_server_store
        self._recorder = recorder
        # Cache of open upstream connections: (workspace_id, server_name) → upstream
        self._upstreams: dict[tuple[str, str], _StdioUpstream | _HttpUpstream] = {}
        self._token_to_session_id: dict[str, str] = {}
        self._server: asyncio.Server | None = None

    def register_token(self, token: str, session_id: str, workspace_id: str) -> None:
        """Called by SandboxRunner when a session starts."""
        self._token_to_session_id[token] = (session_id, workspace_id)

    def unregister_token(self, token: str) -> None:
        self._token_to_session_id.pop(token, None)

    async def serve(self) -> None:
        """Start the Unix socket server. Run as a background task."""
        # Ensure socket dir exists
        socket_dir = os.path.dirname(self._socket_path)
        if socket_dir:
            os.makedirs(socket_dir, exist_ok=True)
        # Remove stale socket
        if os.path.exists(self._socket_path):
            os.unlink(self._socket_path)

        self._server = await asyncio.start_unix_server(
            self._handle_conn, path=self._socket_path
        )
        os.chmod(self._socket_path, 0o600)
        logger.info("MCPGateway listening on %s", self._socket_path)
        async with self._server:
            await self._server.serve_forever()

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        for up in self._upstreams.values():
            await up.close()

    # ------------------------------------------------------------------
    # Connection handler
    # ------------------------------------------------------------------

    async def _handle_conn(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        session_id: str | None = None
        workspace_id: str | None = None
        try:
            # 1. Read hello frame
            hello_line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            session_id, workspace_id = await self._authenticate(hello_line)
            if session_id is None:
                writer.write(_jsonrpc_error(None, -32600, "unauthenticated"))
                await writer.drain()
                return

            allowed = await self._resolve_allowed_servers(workspace_id)

            # 2. Proxy subsequent frames
            async for raw_line in reader:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    frame = json.loads(raw_line)
                except json.JSONDecodeError:
                    writer.write(_jsonrpc_error(None, -32700, "parse error"))
                    await writer.drain()
                    continue

                frame_id = frame.get("id")
                params = frame.get("params") or {}
                server_name = params.pop("server", None) if isinstance(params, dict) else None

                if server_name not in allowed:
                    await self._recorder.emit(
                        session_id,
                        "HARNESS_MCP_REJECTED",
                        {
                            "server": server_name,
                            "method": frame.get("method"),
                            "workspace_id": workspace_id,
                        },
                    )
                    writer.write(
                        _jsonrpc_error(frame_id, -32001, f"server '{server_name}' not in allow-list")
                    )
                    await writer.drain()
                    continue

                upstream = await self._get_upstream(workspace_id, server_name)  # type: ignore[arg-type]
                response = await upstream.call(frame)

                await self._recorder.emit(
                    session_id,
                    "HARNESS_MCP_CALLED",
                    {
                        "server": server_name,
                        "method": frame.get("method"),
                        "params": _redact(params),
                        "workspace_id": workspace_id,
                    },
                )
                writer.write(json.dumps(response).encode() + b"\n")
                await writer.drain()

        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        except Exception as exc:
            logger.exception("MCPGateway error for session %s: %s", session_id, exc)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _authenticate(self, hello_line: bytes) -> tuple[str | None, str | None]:
        try:
            frame = json.loads(hello_line.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None, None
        token = frame.get("params", {}).get("session_token")
        if not token:
            return None, None
        entry = self._token_to_session_id.get(token)
        if entry is None:
            return None, None
        return entry  # (session_id, workspace_id)

    async def _resolve_allowed_servers(self, workspace_id: str) -> set[str]:
        return await self._mcp_server_store.names_for_workspace(workspace_id)

    async def _get_upstream(
        self, workspace_id: str, server_name: str
    ) -> _StdioUpstream | _HttpUpstream:
        key = (workspace_id, server_name)
        if key not in self._upstreams:
            server = await self._mcp_server_store.get_by_name(workspace_id, server_name)
            if server is None:
                raise KeyError(f"MCP server {server_name!r} not found in workspace {workspace_id!r}")
            if server.transport in ("sse", "http"):
                self._upstreams[key] = _HttpUpstream(server.upstream)
            else:
                # stdio — split command string
                cmd = server.upstream.split()
                self._upstreams[key] = _StdioUpstream(cmd)
        return self._upstreams[key]
