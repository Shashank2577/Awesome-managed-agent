# API.md

## 1. API Principles

- Resource-oriented HTTP JSON API.
- `snake_case` fields only.
- Tenant boundary enforced by auth context and `org_id`.
- Long-running operations return accepted + stream references.

Base path: `/api/v1`

---

## 2. Authentication and Headers

Required headers:
- `Authorization: Bearer <token>`
- `X-Org-Id: <uuidv7>`
- `X-Request-Id: <uuid>` (recommended)

---

## 3. Thread APIs

### 3.1 Create Thread
`POST /threads`

Request:
```json
{
  "project_id": "uuidv7",
  "title": "Market analysis",
  "objective": "Compare Q2 trends",
  "priority": "normal",
  "budget": {
    "currency": "USD",
    "allocated": "25.00",
    "hard_limit": "30.00"
  }
}
```

Response `201`:
```json
{
  "thread_id": "uuidv7",
  "status": "CREATED"
}
```

### 3.2 Get Thread
`GET /threads/{thread_id}`

### 3.3 List Threads
`GET /threads?project_id=<id>&status=<status>&limit=50&cursor=...`

### 3.4 Execute Thread
`POST /threads/{thread_id}/execute`

Response `202`:
```json
{
  "thread_id": "uuidv7",
  "status": "RUNNING",
  "stream_url": "/api/v1/threads/{thread_id}/events/stream"
}
```

### 3.5 Pause/Resume/Cancel Thread
- `POST /threads/{thread_id}/pause`
- `POST /threads/{thread_id}/resume`
- `POST /threads/{thread_id}/cancel`

---

## 4. Plan APIs

- `POST /threads/{thread_id}/plans/generate`
- `GET /threads/{thread_id}/plans`
- `GET /threads/{thread_id}/plans/{plan_id}`
- `POST /threads/{thread_id}/plans/{plan_id}/approve`
- `POST /threads/{thread_id}/plans/{plan_id}/reject`

---

## 5. Agent Registry APIs

- `POST /agents/register`
- `GET /agents`
- `GET /agents/{agent_type}`
- `PATCH /agents/{agent_type}`

Registration request fields follow `SPEC.md` contract with validation from `DATA_MODEL.md`.

---

## 6. Events API

### 6.1 Stream Events (SSE)
`GET /threads/{thread_id}/events/stream`

SSE event:
```json
{
  "event_id": "uuidv7",
  "type": "AGENT_RUNNING",
  "sequence": 42,
  "timestamp": "2026-04-26T00:00:00.000Z",
  "payload": {}
}
```

### 6.2 List Events (historical)
`GET /threads/{thread_id}/events?after_sequence=100&limit=200`

---

## 7. Budget APIs

- `GET /threads/{thread_id}/budget`
- `POST /threads/{thread_id}/budget/reserve`
- `POST /threads/{thread_id}/budget/release`

---

## 8. Error Model

Error shape:
```json
{
  "error": {
    "code": "string",
    "message": "string",
    "retryable": false,
    "details": {}
  },
  "request_id": "uuid"
}
```

Common status codes:
- `400` validation
- `401` unauthenticated
- `403` forbidden
- `404` not found
- `409` state conflict/version mismatch
- `422` guardrail violation
- `429` rate/concurrency limit
- `500` internal

---

END
