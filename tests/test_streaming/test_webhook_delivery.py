"""Phase 5 acceptance tests — webhook delivery worker."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import pytest

from atrium.streaming.webhooks import (
    WebhookStore,
    WebhookDeliveryWorker,
    _sign,
    enqueue_event,
)
from atrium.core.models import AtriumEvent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def store(tmp_path):
    s = WebhookStore(str(tmp_path / "webhooks.db"))
    await s.open()
    yield s
    await s.close()


def _make_event(workspace_id: str = "ws1", event_type: str = "SESSION_COMPLETED") -> AtriumEvent:
    return AtriumEvent(
        thread_id="t1",
        type=event_type,
        payload={"result": "done"},
        sequence=1,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_event_emission_creates_delivery_for_subscribed_webhook(store):
    wh = await store.register("ws1", "https://example.com/hook", ["SESSION_COMPLETED"])
    event = _make_event("ws1", "SESSION_COMPLETED")
    await enqueue_event(store, event, "ws1")
    deliveries = await store.list_deliveries_for_webhook(wh.webhook_id)
    assert len(deliveries) == 1
    assert deliveries[0].event_id == event.event_id


async def test_event_emission_creates_no_delivery_for_unsubscribed_event_type(store):
    wh = await store.register("ws1", "https://example.com/hook2", ["SESSION_COMPLETED"])
    event = _make_event("ws1", "HARNESS_TOOL_CALLED")
    await enqueue_event(store, event, "ws1")
    deliveries = await store.list_deliveries_for_webhook(wh.webhook_id)
    assert len(deliveries) == 0


async def test_signature_header_is_hmac_sha256_of_body(store):
    secret = "test-secret-abc"
    body = b'{"event_id": "test"}'
    sig = _sign(body, secret)
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert sig == expected


async def test_2xx_response_marks_delivered(store):
    import httpx
    wh = await store.register("ws1", "https://example.com/hook3", ["SESSION_COMPLETED"], secret="s")
    event = _make_event("ws1", "SESSION_COMPLETED")
    await enqueue_event(store, event, "ws1")
    deliveries = await store.list_deliveries_for_webhook(wh.webhook_id)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        worker = WebhookDeliveryWorker(store, poll_interval=0.05)
        await worker._tick()

    refreshed = await store.list_deliveries_for_webhook(wh.webhook_id)
    assert refreshed[0].status == "delivered"


async def test_4xx_marks_failed_no_retry(store):
    wh = await store.register("ws1", "https://example.com/hook4", ["SESSION_COMPLETED"], secret="s")
    event = _make_event("ws1", "SESSION_COMPLETED")
    await enqueue_event(store, event, "ws1")

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_resp = AsyncMock()
        mock_resp.status_code = 400
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        worker = WebhookDeliveryWorker(store, poll_interval=0.05)
        await worker._tick()

    refreshed = await store.list_deliveries_for_webhook(wh.webhook_id)
    assert refreshed[0].status == "failed"
    assert refreshed[0].attempt == 1  # no retry increment


async def test_5xx_schedules_retry_with_backoff(store):
    wh = await store.register("ws1", "https://example.com/hook5", ["SESSION_COMPLETED"], secret="s")
    event = _make_event("ws1", "SESSION_COMPLETED")
    await enqueue_event(store, event, "ws1")

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_resp = AsyncMock()
        mock_resp.status_code = 503
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        worker = WebhookDeliveryWorker(store, poll_interval=0.05)
        await worker._tick()

    refreshed = await store.list_deliveries_for_webhook(wh.webhook_id)
    assert refreshed[0].status == "pending"
    assert refreshed[0].attempt == 2


async def test_max_attempts_marks_permanent_failure(store):
    wh = await store.register("ws1", "https://example.com/hook6", ["SESSION_COMPLETED"], secret="s")
    event = _make_event("ws1", "SESSION_COMPLETED")
    delivery = await store.create_delivery(wh.webhook_id, event.event_id)

    # Advance the attempt counter to MAX so the next failure makes it permanent
    # Use internal DB update to set attempt=MAX and next_attempt_at=now (due immediately)
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()
    await store._db.execute(
        "UPDATE webhook_deliveries SET attempt=?, next_attempt_at=?, status='pending' WHERE delivery_id=?",
        (WebhookDeliveryWorker.MAX_ATTEMPTS, now_iso, delivery.delivery_id),
    )
    await store._db.commit()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_resp = AsyncMock()
        mock_resp.status_code = 503
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        worker = WebhookDeliveryWorker(store, poll_interval=0.05)
        await worker._tick()

    refreshed = await store.list_deliveries_for_webhook(wh.webhook_id)
    assert refreshed[0].status == "failed"



async def test_disabled_webhook_does_not_receive_events(store):
    wh = await store.register("ws1", "https://example.com/hook7", ["SESSION_COMPLETED"])
    await store.disable(wh.webhook_id)
    event = _make_event("ws1", "SESSION_COMPLETED")
    await enqueue_event(store, event, "ws1")
    deliveries = await store.list_deliveries_for_webhook(wh.webhook_id)
    assert len(deliveries) == 0


async def test_test_endpoint_synthesizes_and_delivers(store):
    """create_delivery with a test event_id works and creates a pending row."""
    wh = await store.register("ws1", "https://example.com/hook8", ["SESSION_COMPLETED"])
    delivery = await store.create_delivery(wh.webhook_id, "test-abc123")
    assert delivery.status == "pending"
    pending = await store.pending_deliveries()
    assert any(d.delivery_id == delivery.delivery_id for d, _ in pending)
