"""Webhook CRUD + test delivery + delivery history endpoints.

POST   /api/v1/webhooks
GET    /api/v1/webhooks
DELETE /api/v1/webhooks/{id}
POST   /api/v1/webhooks/{id}/test
GET    /api/v1/webhooks/{id}/deliveries
"""
from __future__ import annotations

import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

try:
    from atrium.api.auth import require_workspace
    from atrium.api.state import AppState
    from atrium.core.workspace_store import Workspace
except ImportError:
    require_workspace = None  # type: ignore[assignment]
    AppState = None  # type: ignore[assignment]
    Workspace = None  # type: ignore[assignment]

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


class RegisterWebhookRequest(BaseModel):
    url: str
    events: list[str] = Field(default_factory=lambda: ["SESSION_COMPLETED"])
    secret: Optional[str] = None  # auto-generated if omitted


class WebhookResponse(BaseModel):
    webhook_id: str
    url: str
    events: list[str]
    created_at: str
    disabled: bool


class DeliveryResponse(BaseModel):
    delivery_id: str
    event_id: str
    attempt: int
    status: str
    response_code: Optional[int]
    error: Optional[str]
    delivered_at: Optional[str]
    next_attempt_at: str
    created_at: str


def _wh_response(wh) -> WebhookResponse:
    return WebhookResponse(
        webhook_id=f"wh_{wh.webhook_id}",
        url=wh.url,
        events=wh.events,
        created_at=wh.created_at.isoformat(),
        disabled=wh.disabled_at is not None,
    )


@router.post("", response_model=WebhookResponse, status_code=201)
async def register_webhook(
    body: RegisterWebhookRequest,
    workspace: "Workspace" = Depends(require_workspace),
    state: "AppState" = Depends(lambda: AppState.instance()),
) -> WebhookResponse:
    wh = await state.webhook_store.register(
        workspace_id=workspace.workspace_id,
        url=body.url,
        events=body.events,
        secret=body.secret,
    )
    return _wh_response(wh)


@router.get("", response_model=list[WebhookResponse])
async def list_webhooks(
    workspace: "Workspace" = Depends(require_workspace),
    state: "AppState" = Depends(lambda: AppState.instance()),
) -> list[WebhookResponse]:
    webhooks = await state.webhook_store.list_for_workspace(workspace.workspace_id)
    return [_wh_response(wh) for wh in webhooks]


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: str,
    workspace: "Workspace" = Depends(require_workspace),
    state: "AppState" = Depends(lambda: AppState.instance()),
) -> None:
    bare_id = webhook_id.removeprefix("wh_")
    deleted = await state.webhook_store.delete(bare_id)
    if not deleted:
        raise HTTPException(404, detail="Webhook not found")


@router.post("/{webhook_id}/test", status_code=202)
async def test_webhook(
    webhook_id: str,
    workspace: "Workspace" = Depends(require_workspace),
    state: "AppState" = Depends(lambda: AppState.instance()),
) -> dict:
    import json
    import datetime
    bare_id = webhook_id.removeprefix("wh_")
    wh = await state.webhook_store.get(bare_id)
    if not wh or wh.workspace_id != workspace.workspace_id:
        raise HTTPException(404, detail="Webhook not found")
    # Synthesize a test event delivery
    event_id = f"test-{secrets.token_hex(8)}"
    delivery = await state.webhook_store.create_delivery(
        webhook_id=bare_id,
        event_id=event_id,
    )
    # Store full event body for the worker
    body = json.dumps({
        "event_id": event_id,
        "type": "WEBHOOK_TEST",
        "thread_id": "test",
        "session_id": "test",
        "workspace_id": workspace.workspace_id,
        "payload": {"message": "Test webhook delivery"},
        "sequence": 1,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }).encode()
    object.__setattr__(delivery, "_body_cache", body)
    return {"delivery_id": delivery.delivery_id, "status": "queued"}


@router.get("/{webhook_id}/deliveries", response_model=list[DeliveryResponse])
async def list_deliveries(
    webhook_id: str,
    workspace: "Workspace" = Depends(require_workspace),
    state: "AppState" = Depends(lambda: AppState.instance()),
) -> list[DeliveryResponse]:
    bare_id = webhook_id.removeprefix("wh_")
    wh = await state.webhook_store.get(bare_id)
    if not wh or wh.workspace_id != workspace.workspace_id:
        raise HTTPException(404, detail="Webhook not found")
    deliveries = await state.webhook_store.list_deliveries_for_webhook(bare_id)
    return [
        DeliveryResponse(
            delivery_id=d.delivery_id,
            event_id=d.event_id,
            attempt=d.attempt,
            status=d.status,
            response_code=d.response_code,
            error=d.error,
            delivered_at=d.delivered_at.isoformat() if d.delivered_at else None,
            next_attempt_at=d.next_attempt_at.isoformat(),
            created_at=d.created_at.isoformat(),
        )
        for d in deliveries
    ]
