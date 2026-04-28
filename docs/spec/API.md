# API Reference

FastAPI auto-generates interactive OpenAPI docs at `/docs` when the server is running.

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

### Agent Registry (read)
`GET /agents` — List all registered agents with capabilities.
`GET /agents/{name}` — Agent detail (name, description, capabilities, schemas).

### Agent Builder (create/edit/delete)
`POST /agents/create` — Create a config-driven agent at runtime. Returns 201.

```json
{
  "name": "wiki_search",
  "description": "Searches Wikipedia for articles",
  "capabilities": ["search", "research"],
  "api_url": "https://en.wikipedia.org/w/api.php",
  "method": "GET",
  "headers": {"User-Agent": "Atrium/0.1"},
  "query_params": {"action": "query", "list": "search", "srsearch": "{query}", "format": "json"},
  "response_path": "query.search"
}
```

`GET /agents/{name}/config` — Get the full persisted config for a UI-created agent.
`DELETE /agents/{name}` — Remove agent from registry and storage.

### Dashboard
`GET /dashboard` — Built-in web console.
`GET /` — Redirects to `/dashboard`.

## Response Schemas

See `src/atrium/api/schemas.py` for full Pydantic models:
- ThreadResponse: thread_id, title, objective, status, created_at, stream_url
- AgentInfoResponse: name, description, capabilities, input_schema, output_schema
- CreateAgentRequest: name, description, capabilities, api_url, method, headers, query_params, response_path
- ActionResponse: thread_id, accepted
- HealthResponse: status, version, agents_registered
