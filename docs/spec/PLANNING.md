# PLANNING.md

## 1. Objective

Deliver a production-ready Agent OS that supports dynamic multi-agent team orchestration with observable, controllable execution.

---

## 2. Scope

In scope:
- Commander (planning, pivoting, guardrails)
- Graph orchestration runtime
- Agent runtime + worker pool
- Event backbone (durable + streaming)
- State layer (Postgres + Redis)
- Streaming UI integration

Out of scope (initial phases):
- Full enterprise IAM
- Billing systems (basic budget only in v1)

---

## 3. Milestones & Deliverables

### Phase 1 — Core Engine (Weeks 1–3)
Deliverables:
- Minimal Commander (plan → spawn → collect)
- 2 agent types (DummyAgent, SummaryAgent)
- Basic graph execution (parallel nodes)

Acceptance Criteria:
- Two agents execute in parallel
- Results aggregated and returned

---

### Phase 2 — Eventing & Streaming (Weeks 3–5)
Deliverables:
- Event model + emitter
- SSE/WebSocket endpoint
- Basic React viewer (event log)

Acceptance Criteria:
- AGENT_* events stream in real time
- UI shows live execution updates

---

### Phase 3 — Persistence & Checkpointing (Weeks 5–7)
Deliverables:
- Postgres schema (threads, plans, agents, checkpoints)
- Checkpointer integration with graph runtime
- Resume execution API

Acceptance Criteria:
- Execution can pause and resume from checkpoint
- Historical replay available

---

### Phase 4 — Adaptive Execution (Weeks 7–10)
Deliverables:
- Pivot engine (rule-based triggers)
- Dynamic agent spawning (N instances)
- Retry + failure policies

Acceptance Criteria:
- System pivots on low-confidence or failures
- New agents spawned mid-flight

---

### Phase 5 — Execution Plane Scaling (Weeks 9–12)
Deliverables:
- Worker pool (Celery/Temporal)
- Job queue (Kafka/SQS)
- Concurrency controls

Acceptance Criteria:
- Horizontal scaling of agent execution
- Backpressure handled via queue

---

### Phase 6 — Guardrails & Cost Control (Weeks 10–12)
Deliverables:
- Budget model (per thread)
- Cost accounting per agent
- Limits: max_agents, max_parallelism, max_pivots, max_time

Acceptance Criteria:
- Execution halts on budget breach
- Guardrails enforced across flows

---

### Phase 7 — UI (Generative + Graph) (Weeks 12–16)
Deliverables:
- Commander panel (plan, pivots)
- Agent timelines (collapsible)
- Execution graph (live DAG)
- Output renderers (JSON → components)

Acceptance Criteria:
- Users can follow execution and inspect nodes
- UI updates in real time from stream

---

### Phase 8 — Extensibility (Weeks 14–18)
Deliverables:
- Agent plugin interface
- Tool plugin interface
- Model provider abstraction
- Agent registry + capability matching

Acceptance Criteria:
- New agent types can be added without core changes
- Commander selects agents via capability matching

---

### Phase 9 — Production Readiness (Weeks 18–22)
Deliverables:
- Multi-tenancy (org_id, user_id isolation)
- AuthN/AuthZ (basic RBAC)
- Observability (metrics, tracing, logs)

Acceptance Criteria:
- Tenant isolation enforced
- System metrics available

---

## 4. Workstreams

- Control Plane: Commander, Planner, Pivot Engine
- Orchestration: Graph runtime, checkpointing
- Execution: Worker pool, job queue
- Data: Postgres schema, Redis streams
- UI: React widget, streaming client

---

## 5. Risks & Mitigation

Risk: Infinite loops / runaway planning
- Mitigation: max_pivots, max_agents, timeouts

Risk: Cost explosion
- Mitigation: budget per thread, model routing, caps

Risk: Concurrency bottlenecks
- Mitigation: worker pool + queue backpressure

Risk: Non-deterministic outputs
- Mitigation: validation, guardrails, retries

---

## 6. Success Metrics

- Parallelism: ≥ 3 agents executing concurrently (p95)
- Latency: < 2s to first event, streaming thereafter
- Reliability: ≥ 99% successful thread completion without manual intervention (controlled tests)
- Observability: 100% lifecycle events emitted for threads and agents
- Cost Control: 0 budget overruns beyond configured caps

---

## 7. Definition of Done

- All acceptance criteria for current phase met
- Events emitted for all state transitions
- APIs documented and tested
- Basic UI reflects execution accurately

---

END
