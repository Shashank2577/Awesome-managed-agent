# API Reference

FastAPI auto-generates OpenAPI docs at `/docs` when the server is running.

## Base URL

`http://localhost:8080/api/v1`

## Endpoints

### Health
`GET /health` → `{"status": "ok", "version": "0.1.0", "agents_registered": N}`

### Threads
`POST /threads` — Create thread. Body: `{"objective": "string"}`. Returns 201 + ThreadResponse.
`GET /threads` — List all threads.
`GET /threads/{id}` — Thread detail with event history.
`GET /threads/{id}/stream` — SSE event stream.
`DELETE /threads/{id}` — Cancel and remove thread. Returns 204.

### HITL Controls
`POST /threads/{id}/pause` — Pause execution.
`POST /threads/{id}/resume` — Resume execution.
`POST /threads/{id}/cancel` — Cancel execution.
`POST /threads/{id}/approve` — Approve pending plan.
`POST /threads/{id}/reject` — Reject pending plan.
`POST /threads/{id}/input` — Submit human input. Body: `{"input": "string"}`.

### Agent Registry
`GET /agents` — List all registered agents with capabilities.
`GET /agents/{name}` — Agent detail.

## Response Schemas

See `src/atrium/api/schemas.py` for full Pydantic models:
- ThreadResponse: thread_id, title, objective, status, created_at, stream_url
- AgentInfoResponse: name, description, capabilities, input_schema, output_schema
- ActionResponse: thread_id, accepted
- HealthResponse: status, version, agents_registered
