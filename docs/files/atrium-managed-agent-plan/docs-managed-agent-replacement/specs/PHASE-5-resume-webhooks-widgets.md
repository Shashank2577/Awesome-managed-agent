# PHASE 5 — Resume, Webhooks, Widgets

**Goal:** session checkpoint + resume across process restarts; outbound webhook
delivery; embeddable read-only widgets for other UIs to drop in.

**Estimated effort:** 6 days (1 engineer).

**Depends on:** Phase 4.

**Unblocks:** Phase 6.

## 5.1 Files to create or modify

| Action | Path | What |
|--------|------|------|
| MODIFY | `src/atrium/harness/session.py` | Checkpoint save/load. |
| MODIFY | `src/atrium/harness/agent.py` | Resume path. |
| MODIFY | `src/atrium/harness/dockerfiles/oas_entrypoint.js` | Read/write checkpoint. |
| MODIFY | `src/atrium/harness/dockerfiles/anthropic_entrypoint.py` | Same. |
| MODIFY | `src/atrium/api/routes/sessions.py` | `POST /sessions/{id}/resume`. |
| CREATE | `src/atrium/streaming/webhooks.py` | Delivery worker + signing. |
| CREATE | `src/atrium/api/routes/webhooks.py` | CRUD. |
| CREATE | `src/atrium/api/routes/widgets.py` | Widget endpoints. |
| CREATE | `src/atrium/dashboard/static/widgets/feed.html` | Live feed widget. |
| CREATE | `src/atrium/dashboard/static/widgets/plan.html` | Plan DAG widget. |
| CREATE | `src/atrium/dashboard/static/widgets/budget.html` | Budget bar widget. |
| CREATE | `src/atrium/dashboard/static/widgets/report.html` | Final report widget. |
| CREATE | `src/atrium/core/widget_tokens.py` | Short-lived embed tokens. |
| CREATE | `migrations/versions/0004_webhooks.py` |  |
| CREATE | `tests/test_streaming/test_webhook_delivery.py` |  |
| CREATE | `tests/test_api/test_widget_tokens.py` |  |
| CREATE | `tests/integration/test_session_resume.py` |  |

## 5.2 Checkpoint and resume

### Where the checkpoint lives

Inside the session workspace at
`{workspace_dir}/.atrium/checkpoint.json`. The directory `.atrium/` is
treated as runtime metadata and is excluded from artifact indexing.

The checkpoint is opaque to Atrium — it's whatever the inner runtime
chose to persist. Atrium just:

1. Tells the runtime the path to read from / write to.
2. Backs up the checkpoint to durable storage (S3 or another mounted
   volume) when SESSION_PAUSED fires.
3. Restores it before booting a new container on resume.

### Inner runtime contract

When the runtime sees an `ATRIUM_CHECKPOINT_PATH` env var, it MUST:

- On startup, if the file exists, load it and resume from that state.
- On every Nth tool call (recommended: every 5), write its current
  state to the path atomically (write to `.tmp`, rename).
- Emit a `HARNESS_CHECKPOINT` JSON-line event whenever it writes,
  with payload `{tokens_so_far, tool_calls_so_far}`.

For OAS and OpenClaude, the checkpoint contains the inner SDK's
serialized conversation history plus the tool-call counter. For the
Anthropic SDK, similar.

### `Session.save_checkpoint()` and `load_checkpoint()`

```python
# template
async def save_checkpoint(self, blob: bytes) -> None:
    """Persist a checkpoint blob to durable storage."""
    # Write to {workspace_dir}/.atrium/checkpoint.json (already there)
    # AND to s3://{config.checkpoint_bucket}/{workspace_id}/{session_id}/checkpoint.json
    ...

async def load_checkpoint(self) -> bytes | None:
    """Restore from durable storage if available."""
    # If workspace_dir has the file, return its bytes.
    # Otherwise pull from S3 into {workspace_dir}/.atrium/ and return.
    ...
```

For dev / single-host deployments, the "durable storage" is just the
local filesystem (the workspace_dir already survives across restarts
because it's on disk). For production EKS, it's S3.

### Resume route

`POST /api/v1/sessions/{id}/resume` does:

1. Load Session from store. Must be in PAUSED or FAILED status.
   (Reject for COMPLETED, CANCELLED, RUNNING.)
2. Verify the workspace directory exists; if not, restore from S3.
3. Boot a fresh sandbox with the same workspace mounted and the
   checkpoint path env var set.
4. Set status to RUNNING; emit `SESSION_RESUMED`.
5. Continue as before — the bridge picks up the live event stream.

If the resume fails (sandbox can't start, checkpoint is corrupt), set
status back to FAILED with `error_code: "resume_failed"`.

### Pause route

`POST /api/v1/sessions/{id}/pause` does:

1. Send a SIGTERM-equivalent signal to the inner runtime telling it to
   checkpoint and exit. (Implementation: write a signal file inside
   the workspace at `.atrium/please_pause` and the entrypoint polls
   for it; this is simpler than wiring a real signal through Docker.)
2. Wait up to 30s for the runtime to write its checkpoint and exit
   cleanly.
3. If timeout, kill the sandbox; mark FAILED with
   `error_code: "pause_timeout"`.
4. On clean exit, mark PAUSED; emit `SESSION_PAUSED`.

## 5.3 Webhook delivery

### Schema (migration 0004)

```sql
CREATE TABLE webhooks (
    webhook_id    TEXT PRIMARY KEY,
    workspace_id  TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    url           TEXT NOT NULL,
    events        TEXT NOT NULL,  -- JSON array of event types
    secret        TEXT NOT NULL,  -- per-webhook signing secret
    created_at    TEXT NOT NULL,
    disabled_at   TEXT
);
CREATE INDEX idx_webhooks_workspace ON webhooks(workspace_id);

CREATE TABLE webhook_deliveries (
    delivery_id   TEXT PRIMARY KEY,
    webhook_id    TEXT NOT NULL REFERENCES webhooks(webhook_id) ON DELETE CASCADE,
    event_id      TEXT NOT NULL,
    attempt       INTEGER NOT NULL DEFAULT 1,
    status        TEXT NOT NULL,  -- "pending" | "delivered" | "failed"
    response_code INTEGER,
    error         TEXT,
    delivered_at  TEXT,
    next_attempt_at TEXT,
    created_at    TEXT NOT NULL
);
CREATE INDEX idx_webhook_deliveries_pending
    ON webhook_deliveries(next_attempt_at) WHERE status = 'pending';
```

### Delivery worker

A single asyncio task started by `AppState`. Loop:

1. Query `webhook_deliveries` where `status='pending'` AND
   `next_attempt_at <= now()`. Limit 10 per tick.
2. For each, POST to the webhook's URL with body:
   ```json
   {
     "event_id": "...",
     "type": "SESSION_COMPLETED",
     "thread_id": null,
     "session_id": "...",
     "workspace_id": "...",
     "payload": {...},
     "sequence": 42,
     "timestamp": "2026-04-28T12:34:56Z"
   }
   ```
3. Headers:
   - `Content-Type: application/json`
   - `X-Atrium-Signature: sha256=<hex>` where the value is HMAC-SHA256
     of the body using the webhook's `secret`.
   - `X-Atrium-Delivery: {delivery_id}`
   - `X-Atrium-Event: {event_type}`
4. Timeout: 10s.
5. On 2xx: mark `delivered`, emit `WEBHOOK_DELIVERED`.
6. On 4xx (except 429): mark `failed`, do not retry, emit
   `WEBHOOK_FAILED`.
7. On 429 / 5xx / timeout: retry with backoff (1s → 30s → 5min →
   30min → 6hr → fail). Update `attempt` and `next_attempt_at`.
8. After 6 failed attempts: mark `failed` permanently.

### How events become deliveries

Whenever the recorder emits an event, after persisting, it queries:

```sql
SELECT webhook_id, secret FROM webhooks
WHERE workspace_id = :workspace_id
  AND disabled_at IS NULL
  AND :event_type IN UNJSON(events)
```

For each match, INSERT a `webhook_deliveries` row with `status="pending"`
and `next_attempt_at=now()`. The delivery worker picks it up.

The `IN UNJSON(events)` is pseudo-SQL; the real query expands the JSON
array client-side or uses a backend-specific JSON operator. SQLite uses
`json_each`; Postgres uses `jsonb ? :event_type`.

### Routes

| Method | Path | Body |
|--------|------|------|
| POST   | `/api/v1/webhooks` | `{url, events: [...], secret?}` (secret generated if omitted) |
| GET    | `/api/v1/webhooks` | — |
| DELETE | `/api/v1/webhooks/{id}` | — |
| POST   | `/api/v1/webhooks/{id}/test` | — (synthesizes a `webhook.test` event and delivers it) |
| GET    | `/api/v1/webhooks/{id}/deliveries` | — (last 50 deliveries with status) |

## 5.4 Widget tokens

Embeddable widgets need to render in third-party UIs without exposing
the workspace API key. Solution: short-lived signed tokens scoped to a
single thread or session, read-only, time-limited.

```python
# verbatim — src/atrium/core/widget_tokens.py
"""Short-lived signed tokens for embeddable widgets.

Token format: "v1.{base64(payload)}.{base64(hmac)}"
Payload JSON: {workspace_id, scope, scope_id, expires_at}
scope: "thread" | "session"
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Literal


class WidgetTokenError(Exception):
    pass


def issue_token(
    *,
    workspace_id: str,
    scope: Literal["thread", "session"],
    scope_id: str,
    ttl_seconds: int,
    signing_secret: str,
) -> str:
    payload = {
        "workspace_id": workspace_id,
        "scope": scope,
        "scope_id": scope_id,
        "expires_at": int(time.time()) + ttl_seconds,
    }
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=")
    sig = hmac.new(signing_secret.encode(), body, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=")
    return f"v1.{body.decode()}.{sig_b64.decode()}"


def verify_token(token: str, signing_secret: str) -> dict:
    try:
        version, body, sig_b64 = token.split(".", 2)
        if version != "v1":
            raise WidgetTokenError("unsupported version")
        body_bytes = base64.urlsafe_b64decode(body + "==")
        expected = hmac.new(signing_secret.encode(), body.encode(), hashlib.sha256).digest()
        actual = base64.urlsafe_b64decode(sig_b64 + "==")
        if not hmac.compare_digest(expected, actual):
            raise WidgetTokenError("bad signature")
        payload = json.loads(body_bytes)
        if payload["expires_at"] < int(time.time()):
            raise WidgetTokenError("expired")
        return payload
    except (ValueError, KeyError) as exc:
        raise WidgetTokenError(f"malformed: {exc}") from exc
```

### Issuing tokens

| Method | Path | Body |
|--------|------|------|
| POST | `/api/v1/threads/{id}/widget-token` | `{ttl_seconds: 3600}` → `{token, expires_at}` |
| POST | `/api/v1/sessions/{id}/widget-token` | same |

Default TTL: 1 hour. Max TTL: 24 hours.

## 5.5 Widget endpoints

All widgets accept `?token=...` and validate it via `verify_token`.
On validation failure: 401 with a small HTML error page.

### `GET /widgets/feed`

Query params: `token` (required), `theme=light|dark` (default light),
`compact=true` (smaller layout).

Returns a self-contained HTML document that:
- Loads minimal CSS and JS (no external CDN).
- Connects via `EventSource` to `/api/v1/widgets/stream?token=...`
  (a token-authorized SSE endpoint that streams the same events as
  the regular thread/session stream, scoped to the token's scope_id).
- Renders events as a vertical feed: tool calls, messages, status
  changes.
- Sets `X-Frame-Options: ALLOWALL` and `Content-Security-Policy:
  default-src 'self' 'unsafe-inline';` (inline JS is fine here; no
  third-party scripts).

### `GET /widgets/plan`

Same auth model. Renders the thread's plan as a DAG. SVG; no JS
animation library; uses the existing dashboard's plan-rendering code
extracted into a standalone bundle.

Static once the plan is final; refreshes via SSE if the plan changes
(pivot).

### `GET /widgets/budget`

Renders a budget bar showing `consumed / limit`, currency, and the
last few BUDGET_CONSUMED events. Live updates via SSE.

### `GET /widgets/report`

Renders the final EVIDENCE_PUBLISHED summary as Markdown-ish HTML.
Read-once (no SSE).

### Embed example

```html
<iframe
  src="https://atrium.taazaa.com/widgets/feed?token=v1.eyJ3..."
  width="600" height="400"
  sandbox="allow-scripts allow-same-origin"
></iframe>
```

CIVI dashboard or Master CRM embeds these in their own UIs.

## 5.6 Token-scoped SSE endpoint

```python
# template — api/routes/widgets.py
@router.get("/api/v1/widgets/stream")
async def widget_stream(
    token: str,
    state: AppState = Depends(get_app_state),
):
    payload = verify_token(token, state.config.webhook_signing_secret)
    workspace_id = payload["workspace_id"]
    scope = payload["scope"]
    scope_id = payload["scope_id"]

    async def gen():
        if scope == "thread":
            async for event in state.recorder.subscribe_thread(scope_id, workspace_id):
                yield format_sse(event)
        else:
            async for event in state.recorder.subscribe_session(scope_id, workspace_id):
                yield format_sse(event)

    return StreamingResponse(gen(), media_type="text/event-stream")
```

## 5.7 Acceptance tests

### `tests/test_streaming/test_webhook_delivery.py`

```
test_event_emission_creates_delivery_for_subscribed_webhook
test_event_emission_creates_no_delivery_for_unsubscribed_event_type
test_signature_header_is_hmac_sha256_of_body
test_2xx_response_marks_delivered
test_4xx_marks_failed_no_retry
test_5xx_schedules_retry_with_backoff
test_max_attempts_marks_permanent_failure
test_disabled_webhook_does_not_receive_events
test_test_endpoint_synthesizes_and_delivers
```

### `tests/test_api/test_widget_tokens.py`

```
test_issued_token_verifies
test_expired_token_rejected
test_tampered_payload_rejected
test_token_for_thread_a_not_valid_for_thread_b
test_widget_endpoint_404_for_resource_outside_scope
```

### `tests/integration/test_session_resume.py`

```
test_pause_writes_checkpoint_and_marks_paused
test_resume_starts_new_container_with_same_workspace
test_resume_after_full_process_restart_works         # restart pytest fixture mid-test
test_resume_a_completed_session_is_409
test_resume_a_session_with_corrupt_checkpoint_marks_failed
```

## 5.8 Non-goals for Phase 5

- Helm chart / Kubernetes runner — Phase 6.
- Webhook delivery from a separate worker process (multi-replica) —
  Phase 6.
- OAuth / SSO for widget tokens — out of scope; tokens stay HMAC.
- Server-side rendering of widgets in non-HTML formats (no PDF, no
  PNG snapshots) — out of scope.
- A reverse-proxy widget-only subdomain — deployment concern.

## 5.9 Definition of done

- [ ] All files in §5.1 created or modified per spec.
- [ ] All acceptance tests in §5.7 present and passing.
- [ ] Manual smoke: long session paused mid-execution, server killed,
      server restarted, session resumed, completes successfully.
- [ ] Manual smoke: webhook subscribed to SESSION_COMPLETED, completes
      a session, webhook receives signed delivery within 5 seconds.
- [ ] Manual smoke: feed widget embedded in a static HTML page renders
      live events from a running session.
- [ ] No `TODO(phase-5)` markers remain.
