# Atrium Specification

## 1. System Model

Atrium wraps LangGraph as the execution engine. The system is composed of:

- **Agent Layer** — User-defined Agent subclasses with name, description, capabilities, run()
- **Registry** — Holds registered agents, exposes manifests for the Commander
- **Commander** — LLM-powered planner that reads the registry and generates execution plans
- **Graph Builder** — Compiles Commander plans into LangGraph StateGraphs
- **Event Recorder** — Append-only event log with per-thread sequencing, SSE fan-out, SQLite persistence
- **Guardrails** — Enforces cost, time, parallelism, and pivot limits
- **API Layer** — FastAPI with 14 REST endpoints + SSE streaming
- **Dashboard** — Built-in web UI for real-time execution visualization
- **HITL Controller** — Pause, resume, cancel, approve, reject via ThreadController

## 2. Agent Lifecycle

The Commander plans which agents to run. The framework manages lifecycle automatically:

1. Commander generates a Plan (list of steps with agents, inputs, dependencies)
2. Graph Builder compiles the Plan into a LangGraph StateGraph
3. LangGraph executes the graph — parallel fan-out for independent steps
4. Each agent node: create instance → wire emitter → call run() → emit events
5. Commander evaluates outputs — finalize or pivot
6. On pivot: generate new plan, execute, evaluate again (capped by max_pivots guardrail)

## 3. Event Taxonomy

All events are typed, sequenced per-thread, and persisted to SQLite:

- Thread: THREAD_CREATED, THREAD_PLANNING, THREAD_RUNNING, THREAD_COMPLETED, THREAD_FAILED, THREAD_CANCELLED, THREAD_PAUSED
- Plan: PLAN_CREATED, PLAN_APPROVED, PLAN_REJECTED, PLAN_EXECUTION_STARTED, PLAN_COMPLETED
- Agent: AGENT_HIRED, AGENT_RUNNING, AGENT_COMPLETED, AGENT_FAILED, AGENT_MESSAGE, AGENT_OUTPUT
- Commander: COMMANDER_MESSAGE, PIVOT_REQUESTED, PIVOT_APPLIED
- HITL: HUMAN_APPROVAL_REQUESTED, HUMAN_INPUT_RECEIVED
- Budget: BUDGET_RESERVED, BUDGET_CONSUMED, BUDGET_EXCEEDED
- Evidence: EVIDENCE_PUBLISHED

## 4. API Endpoints

```
GET  /api/v1/health
POST /api/v1/threads
GET  /api/v1/threads
GET  /api/v1/threads/{id}
GET  /api/v1/threads/{id}/stream    (SSE)
DELETE /api/v1/threads/{id}
POST /api/v1/threads/{id}/pause
POST /api/v1/threads/{id}/resume
POST /api/v1/threads/{id}/cancel
POST /api/v1/threads/{id}/approve
POST /api/v1/threads/{id}/reject
POST /api/v1/threads/{id}/input
GET  /api/v1/agents
GET  /api/v1/agents/{name}
```

## 5. Guardrails

Configurable limits enforced during execution:
- max_agents (default: 25)
- max_parallel (default: 5)
- max_time_seconds (default: 600)
- max_cost_usd (default: $10.00)
- max_pivots (default: 2)

## 6. Dependencies

langgraph, langchain-core, langgraph-checkpoint-sqlite, fastapi, uvicorn, httpx, pydantic, aiosqlite

Optional: langchain-openai, langchain-anthropic, langchain-google-genai
