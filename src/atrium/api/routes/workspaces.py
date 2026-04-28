"""Admin workspace and API key management routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atrium.api.auth import require_admin
from atrium.api.state import AppState, get_app_state
from atrium.core.auth import ApiKey, ApiKeyKind, Workspace, WorkspaceQuota

router = APIRouter(prefix="/admin", tags=["admin"])


class CreateWorkspaceRequest(BaseModel):
    name: str
    quota: WorkspaceQuota | None = None


class IssueKeyRequest(BaseModel):
    kind: ApiKeyKind = ApiKeyKind.WORKSPACE
    name: str = ""


class WorkspaceResponse(BaseModel):
    workspace_id: str
    name: str
    quota: WorkspaceQuota
    created_at: str
    metadata: dict[str, Any]


def _ws_to_resp(ws: Workspace) -> WorkspaceResponse:
    return WorkspaceResponse(
        workspace_id=ws.workspace_id,
        name=ws.name,
        quota=ws.quota,
        created_at=ws.created_at.isoformat(),
        metadata=ws.metadata,
    )


@router.post("/workspaces", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(
    body: CreateWorkspaceRequest,
    state: AppState = Depends(get_app_state),
    _admin: ApiKey = Depends(require_admin),
) -> WorkspaceResponse:
    ws = await state.workspace_store.create_workspace(body.name, body.quota)
    return _ws_to_resp(ws)


@router.get("/workspaces", response_model=dict)
async def list_workspaces(
    state: AppState = Depends(get_app_state),
    _admin: ApiKey = Depends(require_admin),
) -> dict:
    workspaces = await state.workspace_store.list_workspaces()
    return {"workspaces": [_ws_to_resp(w).model_dump() for w in workspaces]}


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: str,
    state: AppState = Depends(get_app_state),
    _admin: ApiKey = Depends(require_admin),
) -> WorkspaceResponse:
    ws = await state.workspace_store.get_workspace(workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return _ws_to_resp(ws)


@router.patch("/workspaces/{workspace_id}/quota", response_model=WorkspaceResponse)
async def update_quota(
    workspace_id: str,
    quota: WorkspaceQuota,
    state: AppState = Depends(get_app_state),
    _admin: ApiKey = Depends(require_admin),
) -> WorkspaceResponse:
    ws = await state.workspace_store.get_workspace(workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    await state.workspace_store.update_quota(workspace_id, quota)
    ws.quota = quota
    return _ws_to_resp(ws)


@router.delete("/workspaces/{workspace_id}", status_code=204)
async def delete_workspace(
    workspace_id: str,
    state: AppState = Depends(get_app_state),
    _admin: ApiKey = Depends(require_admin),
):
    ws = await state.workspace_store.get_workspace(workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    await state.workspace_store.delete_workspace(workspace_id)
    return None


@router.post("/workspaces/{workspace_id}/keys", status_code=201)
async def issue_key(
    workspace_id: str,
    body: IssueKeyRequest,
    state: AppState = Depends(get_app_state),
    _admin: ApiKey = Depends(require_admin),
) -> dict:
    """Returns the secret ONE TIME — it is not stored."""
    ws = await state.workspace_store.get_workspace(workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    key, secret = await state.workspace_store.issue_key(workspace_id, body.kind, body.name)
    return {
        "api_key": {
            "api_key_id": key.api_key_id,
            "workspace_id": key.workspace_id,
            "kind": key.kind.value,
            "name": key.name,
            "created_at": key.created_at.isoformat(),
        },
        "secret": secret,
        "_note": "This secret is shown ONCE and cannot be retrieved again.",
    }


@router.get("/workspaces/{workspace_id}/keys")
async def list_keys(
    workspace_id: str,
    state: AppState = Depends(get_app_state),
    _admin: ApiKey = Depends(require_admin),
) -> dict:
    keys = await state.workspace_store.list_keys(workspace_id)
    return {
        "keys": [
            {
                "api_key_id": k.api_key_id,
                "workspace_id": k.workspace_id,
                "kind": k.kind.value,
                "name": k.name,
                "created_at": k.created_at.isoformat(),
                "revoked_at": k.revoked_at.isoformat() if k.revoked_at else None,
            }
            for k in keys
        ]
    }


@router.delete("/keys/{api_key_id}", status_code=204)
async def revoke_key(
    api_key_id: str,
    state: AppState = Depends(get_app_state),
    _admin: ApiKey = Depends(require_admin),
):
    await state.workspace_store.revoke_key(api_key_id)
    return None
