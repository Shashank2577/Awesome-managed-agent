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
