# Data Model

## Core Entities (Pydantic models in `src/atrium/core/models.py`)

### Thread
- thread_id: str (UUID)
- objective: str
- title: str
- status: ThreadStatus (CREATED | PLANNING | RUNNING | PAUSED | COMPLETED | FAILED | CANCELLED)
- created_at: datetime

### Plan
- plan_id: str (UUID)
- thread_id: str
- plan_number: int
- rationale: str
- steps: list[PlanStep]

### PlanStep
- agent: str (agent name)
- inputs: dict
- depends_on: list[str] (agent names)
- status: str

### AtriumEvent
- event_id: str (UUID)
- thread_id: str
- type: str
- payload: dict
- sequence: int (monotonic per-thread)
- timestamp: datetime
- causation_id: str | None

### BudgetSnapshot
- consumed: str
- limit: str
- currency: str

### Agent (config-driven)

Pydantic model: `CreateAgentRequest` / `AgentConfig` in `src/atrium/api/schemas.py`.
SQLite table: `agent_configs`. Indexed columns: `category`, `agent_type`.
Config is stored as a JSON blob; the row also has top-level `name`, `category`, and `agent_type` columns for filtered queries.

| Column | SQL Type | Notes |
|---|---|---|
| `name` | TEXT PK | Unique slug (e.g. `wiki_search`, `seed/error-detective`) |
| `description` | TEXT | Plain-English purpose |
| `agent_type` | TEXT | `"http"` or `"llm"` — indexed |
| `category` | TEXT | UI group (e.g. `research`, `coding`) — indexed |
| `capabilities` | JSON | List of capability tags |
| `system_prompt` | TEXT | LLM agents only |
| `model` | TEXT | LLM agents only — provider-qualified (`anthropic:claude-sonnet-4-6`) |
| `api_url` | TEXT | HTTP agents only |
| `method` | TEXT | HTTP agents only (`GET`, `POST`, …) |
| `headers` | JSON | HTTP agents only — static request headers |
| `query_params` | JSON | HTTP agents only — may use `{placeholder}` syntax |
| `response_path` | TEXT | HTTP agents only — dot-path into JSON response |
| `seeded` | BOOLEAN | `true` for agents from the built-in seed corpus |
| `seed_version` | INTEGER | Monotonic version for seed update detection |
