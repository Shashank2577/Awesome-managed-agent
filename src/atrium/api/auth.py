"""API key authentication for FastAPI dependencies."""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request

from atrium.api.state import AppState, get_app_state
from atrium.core.auth import ApiKey, ApiKeyKind, Workspace


async def require_api_key(
    request: Request,
    state: AppState = Depends(get_app_state),
    x_atrium_key: str | None = Header(default=None, alias="X-Atrium-Key"),
) -> ApiKey:
    """Resolve an ApiKey from X-Atrium-Key. 401 if missing or invalid."""
    if not x_atrium_key:
        raise HTTPException(401, detail="missing X-Atrium-Key header")
    key = await state.workspace_store.lookup_by_secret(x_atrium_key)
    if key is None or key.revoked_at is not None:
        raise HTTPException(401, detail="invalid api key")
    request.state.api_key = key
    return key


async def require_workspace(
    state: AppState = Depends(get_app_state),
    api_key: ApiKey = Depends(require_api_key),
) -> Workspace:
    """For routes scoped to a single workspace. 401 if the key is admin-only."""
    if api_key.kind == ApiKeyKind.ADMIN:
        raise HTTPException(401, detail="admin keys cannot access workspace routes")
    if api_key.workspace_id is None:
        raise HTTPException(401, detail="key is not bound to a workspace")
    ws = await state.workspace_store.get_workspace(api_key.workspace_id)
    if ws is None:
        raise HTTPException(401, detail="workspace not found")
    return ws


async def require_admin(api_key: ApiKey = Depends(require_api_key)) -> ApiKey:
    """For /api/v1/admin/* routes."""
    if api_key.kind != ApiKeyKind.ADMIN:
        raise HTTPException(403, detail="admin access required")
    return api_key
