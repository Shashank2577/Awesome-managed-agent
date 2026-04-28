"""REST routes for workspace MCP server registry.

All routes require an authenticated workspace (require_workspace dep).

POST   /api/v1/mcp-servers        — register an MCP server
GET    /api/v1/mcp-servers        — list servers in this workspace
DELETE /api/v1/mcp-servers/{name} — remove a server
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

# Lazy imports — avoids hard dep on full AppState at module load
try:
    from atrium.api.auth import require_workspace
    from atrium.api.state import AppState
    from atrium.core.workspace_store import Workspace
except ImportError:
    require_workspace = None  # type: ignore[assignment]
    AppState = None  # type: ignore[assignment]
    Workspace = None  # type: ignore[assignment]

router = APIRouter(prefix="/api/v1/mcp-servers", tags=["mcp"])


class RegisterMCPServerRequest(BaseModel):
    name: str = Field(..., description="Logical name, e.g. 'github'")
    transport: Literal["stdio", "sse", "http"] = "stdio"
    upstream: str = Field(..., description="Command (stdio) or URL (sse/http)")
    credentials_ref: str = Field(
        default="",
        description="Name of secret in secret store that holds credentials",
    )


class MCPServerResponse(BaseModel):
    mcp_server_id: str
    name: str
    transport: str
    upstream: str
    credentials_ref: str
    created_at: str


def _to_response(server) -> MCPServerResponse:
    return MCPServerResponse(
        mcp_server_id=server.mcp_server_id,
        name=server.name,
        transport=server.transport,
        upstream=server.upstream,
        credentials_ref=server.credentials_ref,
        created_at=server.created_at.isoformat(),
    )


@router.post("", response_model=MCPServerResponse, status_code=201)
async def register_mcp_server(
    body: RegisterMCPServerRequest,
    workspace: "Workspace" = Depends(require_workspace),
    state: "AppState" = Depends(lambda: AppState.instance()),
) -> MCPServerResponse:
    existing = await state.mcp_server_store.get_by_name(workspace.workspace_id, body.name)
    if existing is not None:
        raise HTTPException(409, detail=f"MCP server '{body.name}' already registered")
    server = await state.mcp_server_store.register(
        workspace_id=workspace.workspace_id,
        name=body.name,
        transport=body.transport,
        upstream=body.upstream,
        credentials_ref=body.credentials_ref,
    )
    return _to_response(server)


@router.get("", response_model=list[MCPServerResponse])
async def list_mcp_servers(
    workspace: "Workspace" = Depends(require_workspace),
    state: "AppState" = Depends(lambda: AppState.instance()),
) -> list[MCPServerResponse]:
    servers = await state.mcp_server_store.list_for_workspace(workspace.workspace_id)
    return [_to_response(s) for s in servers]


@router.delete("/{name}", status_code=204)
async def delete_mcp_server(
    name: str,
    workspace: "Workspace" = Depends(require_workspace),
    state: "AppState" = Depends(lambda: AppState.instance()),
) -> None:
    deleted = await state.mcp_server_store.delete(workspace.workspace_id, name)
    if not deleted:
        raise HTTPException(404, detail=f"MCP server '{name}' not found")
