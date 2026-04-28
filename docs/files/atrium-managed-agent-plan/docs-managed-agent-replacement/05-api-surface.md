# 05 — API Surface

The full external API for the v1 Managed Agents replacement. All routes are
under `/api/v1`. All routes require an `X-Atrium-Key` header except the
health route. Workspace is resolved from the API key.

## Health & metadata

- `GET /api/v1/health` — liveness, no auth.
- `GET /api/v1/version` — build metadata.
- `GET /api/v1/workspaces/me` — workspace info for the calling key.

## Agents

The existing routes, made workspace-aware. Adds harness-kind support.

- `GET /api/v1/agents` — list agents in this workspace.
- `GET /api/v1/agents/{name}` — agent manifest.
- `GET /api/v1/agents/{name}/config` — the stored config (if config-driven).
- `POST /api/v1/agents/create` — create an HTTP or harness agent.
  Body `kind: "http"` or `kind: "harness"`.
- `DELETE /api/v1/agents/{name}` — delete a stored agent config.

## Threads (multi-agent DAG runs)

Existing concept, kept. Workspace-scoped now.

- `POST /api/v1/threads` — create a thread, kick off orchestration.
  Body: `{objective, require_approval, guardrails_overrides?}`.
- `GET /api/v1/threads` — list threads in workspace.
- `GET /api/v1/threads/{id}` — thread detail with all events.
- `GET /api/v1/threads/{id}/stream` — SSE event stream.
- `DELETE /api/v1/threads/{id}` — cancel.
- `POST /api/v1/threads/{id}/pause` / `/resume` / `/approve` / `/reject` /
  `/input` — HITL control.

## Sessions (long-running harness)

NEW. The Managed-Agents-equivalent surface. A session is owned by exactly
one harness agent and represents a long-running tool-using execution.

- `POST /api/v1/sessions` — create and start a session.
  ```json
  {
    "agent": "code_research",
    "objective": "Investigate why X is failing",
    "model_override": "google:gemini-2.5-pro",
    "timeout_seconds": 1800,
    "metadata": {"project": "PLC-Direct"}
  }
  ```
  Returns `{session_id, stream_url, ...}`.
- `GET /api/v1/sessions` — list sessions in workspace, with status filter.
- `GET /api/v1/sessions/{id}` — session detail (status, runtime, model,
  budget consumed, last activity, all events).
- `GET /api/v1/sessions/{id}/stream` — SSE event stream (mirrors thread
  stream — same event types, different source).
- `POST /api/v1/sessions/{id}/messages` — send a follow-up message into
  a running session. Body: `{text}`.
- `POST /api/v1/sessions/{id}/pause` / `/resume` / `/cancel`.
- `POST /api/v1/sessions/{id}/resume` — resume a session whose container
  was killed (different from /resume after pause). Boots a fresh
  container, mounts the existing workspace, replays the last checkpoint.
- `DELETE /api/v1/sessions/{id}` — terminate and archive (workspace
  files retained for `retention_days`, then GC'd).

## Artifacts (files produced inside a session)

NEW. Lets external systems read what the harness wrote.

- `GET /api/v1/sessions/{id}/artifacts` — list files in the session
  workspace, with size and sha256.
- `GET /api/v1/artifacts/{artifact_id}` — download a single artifact.
  Streamed. Auth-checked against workspace.
- `GET /api/v1/artifacts/{artifact_id}/preview` — text preview for
  text-like files (capped to 1MB).
- `DELETE /api/v1/artifacts/{artifact_id}` — delete (only if session
  is terminal).

## Webhooks

NEW. Push-based delivery for systems that don't want to poll SSE.

- `POST /api/v1/webhooks` — register a webhook.
  ```json
  {
    "url": "https://internal.taazaa.com/atrium-hook",
    "events": ["THREAD_COMPLETED", "SESSION_COMPLETED", "BUDGET_EXCEEDED"],
    "filter": {"workspace_id": "..."},
    "secret": "..."
  }
  ```
- `GET /api/v1/webhooks` — list.
- `DELETE /api/v1/webhooks/{id}`.

Delivery is at-least-once with HMAC signing on `X-Atrium-Signature`.
A delivery worker reads the events table, matches webhooks, posts with
exponential backoff, marks delivered.

## Widgets (embeddable read-only views)

NEW. These return HTML that can be loaded inside an `<iframe>` in another
product (CIVI dashboard, Master CRM, internal Slack). Same data as the
dashboard, scoped to a single thread / session.

- `GET /widgets/feed?session_id=...&theme=light` — live event feed.
- `GET /widgets/plan?thread_id=...` — DAG visualization.
- `GET /widgets/budget?session_id=...` — cost bar.
- `GET /widgets/report?thread_id=...` — final EVIDENCE_PUBLISHED summary.

Widgets:
- Take a workspace-scoped read-only token via `?token=...` (separate from
  the main API key, scoped to a single thread/session, time-limited).
- Set `X-Frame-Options: ALLOWALL` and a permissive but explicit CSP for
  the configured embed domain.
- Re-use the same SSE backend; the widget HTML is just a thin client.

## Workspaces (multi-tenant admin)

NEW. Admin surface for managing tenancy. Requires an admin key.

- `POST /api/v1/admin/workspaces` — create.
- `GET /api/v1/admin/workspaces` — list.
- `POST /api/v1/admin/workspaces/{id}/keys` — issue a new API key.
- `DELETE /api/v1/admin/workspaces/{id}/keys/{key_id}` — revoke.
- `PATCH /api/v1/admin/workspaces/{id}/quota` — update quotas.

## OpenAPI

FastAPI generates `/openapi.json` automatically. The schemas in
`api/schemas.py` need to be expanded to cover the new routes; for the
public docs we publish the OpenAPI document at `/docs` (Swagger UI is
already set up by FastAPI's defaults).

## SDK clients

For external consumers, two thin SDKs:
- `atrium-client-py` — wraps the API in a Pythonic client. Useful for
  Engineering Core's internal scripts.
- `atrium-client-ts` — wraps the API in TypeScript. Useful for embedding
  into Master CRM and similar Node / browser code.

Both are auto-generated from the OpenAPI document and lightly hand-edited
for ergonomics. They live in separate repositories so they can be
versioned independently.

## Eventing schema (cross-cutting)

All SSE streams emit events with this envelope:

```json
{
  "event_id": "uuid",
  "type": "HARNESS_TOOL_CALLED",
  "thread_id": "uuid | null",
  "session_id": "uuid | null",
  "payload": {...},
  "sequence": 42,
  "timestamp": "2026-04-28T12:34:56Z",
  "causation_id": "uuid | null"
}
```

New event types added by the harness layer:
- `SESSION_CREATED`, `SESSION_RUNNING`, `SESSION_PAUSED`, `SESSION_RESUMED`,
  `SESSION_COMPLETED`, `SESSION_FAILED`, `SESSION_CANCELLED`.
- `HARNESS_TOOL_CALLED` — bash / file / web_fetch invocation.
- `HARNESS_TOOL_RESULT` — tool output.
- `HARNESS_MESSAGE` — assistant text content.
- `HARNESS_MCP_CALLED` — MCP server request via the gateway.
- `HARNESS_COMPACTION` — context compaction occurred.
- `HARNESS_CHECKPOINT` — checkpoint persisted (for resume).
- `ARTIFACT_CREATED` — file written to workspace.
- `ARTIFACT_UPDATED`, `ARTIFACT_DELETED`.

The existing event types (`THREAD_*`, `PLAN_*`, `AGENT_*`, `BUDGET_*`,
`PIVOT_*`, `EVIDENCE_PUBLISHED`, `HUMAN_*`) keep their current semantics.
