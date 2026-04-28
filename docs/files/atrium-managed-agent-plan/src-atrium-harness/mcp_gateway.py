"""MCPGateway — workspace-scoped MCP proxy with audit and allow-listing.

The gateway sits between sandboxed agents and external MCP servers. The
sandbox talks to the gateway over a Unix socket (mounted into the
container at /run/atrium/mcp.sock); the gateway forwards approved
requests to the upstream MCP server and emits an audit event for every
call.

Why a gateway and not direct sandbox→MCP?

  * Audit trail — CIVI compliance needs every MCP call logged.
  * Allow-listing — multi-tenant sessions can't be allowed to call
    arbitrary MCP servers.
  * Auth — the upstream MCP server's credentials live in the gateway,
    not in the sandbox. The sandbox never sees the GitHub PAT.
  * Rate limiting — coalesced across all sessions for a workspace.

This file is a SCAFFOLD. Real implementation lands in roadmap phase 4.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MCPServerConfig:
    name: str             # logical name, e.g. "github"
    transport: str        # "stdio" | "sse" | "http"
    upstream: str         # command or URL
    credentials_env: dict[str, str]  # env vars to inject from secret store


class MCPGateway:
    """A per-Atrium-instance gateway that fronts MCP traffic from sandboxes."""

    def __init__(self, workspace_servers: dict[str, list[MCPServerConfig]]) -> None:
        # workspace_servers maps workspace_id -> list of allowed server configs
        self._workspace_servers = workspace_servers

    async def serve(self, socket_path: str) -> None:
        """Listen on the given Unix socket and route requests."""
        # Phase 4:
        # accept() loop -> for each conn read MCP frame -> auth via env
        # marker injected at sandbox start -> look up workspace -> check
        # allow-list -> forward to upstream -> emit HARNESS_MCP_CALLED
        raise NotImplementedError
