# SPEC.md

## 1. Overview

Agent OS is a stateful, event-driven system that orchestrates dynamic multi-agent teams to execute complex workflows.

---

## 2. Actors

### User
Initiates workflows via prompt or event.

### Commander
Responsible for planning, orchestration, and decision-making.

### Agent
Executes specialized tasks.

### Worker
Executes agent instances asynchronously.

---

## 3. Core Entities

### Thread
```
{
  "thread_id": "string",
  "status": "CREATED | RUNNING | PAUSED | COMPLETED | FAILED",
  "budget": number,
  "created_at": timestamp,
  "updated_at": timestamp
}
```

---

### AgentInstance
```
{
  "instance_id": "string",
  "agent_type": "string",
  "thread_id": "string",
  "status": "CREATED | QUEUED | RUNNING | COMPLETED | FAILED | TERMINATED",
  "input": {},
  "output": {},
  "cost": number
}
```

---

### Plan
```
{
  "plan_id": "string",
  "thread_id": "string",
  "graph": {
    "nodes": [],
    "edges": []
  },
  "version": number
}
```

---

### Event
```
{
  "event_id": "string",
  "thread_id": "string",
  "type": "string",
  "payload": {},
  "timestamp": "ISO8601"
}
```

---

## 4. API Contracts

### 4.1 Create Thread
POST /threads

Request:
```
{
  "input": "string",
  "context": {},
  "budget": number
}
```

Response:
```
{
  "thread_id": "string"
}
```

---

### 4.2 Get Thread
GET /threads/{thread_id}

Response:
```
{
  "thread": {},
  "plan": {},
  "agents": []
}
```

---

### 4.3 Stream Events
GET /threads/{thread_id}/events (SSE)

Event:
```
data: {
  "type": "AGENT_STARTED",
  "payload": {}
}
```

---

## 5. Event Types

- THREAD_CREATED
- PLAN_CREATED
- AGENT_SPAWNED
- AGENT_STARTED
- AGENT_COMPLETED
- AGENT_FAILED
- COMMANDER_PIVOT
- THREAD_COMPLETED

---

## 6. Execution Semantics

### 6.1 State Transitions

Thread:
CREATED → RUNNING → PAUSED → RUNNING → COMPLETED | FAILED

Agent:
CREATED → QUEUED → RUNNING → COMPLETED
                      → FAILED → RETRY → RUNNING

Invalid transitions MUST be rejected.

---

### 6.2 Retry Policy

- max_retries = 3
- exponential backoff

---

### 6.3 Idempotency

Agent executions MUST be idempotent.

---

### 6.4 Budget Enforcement

- Each thread has a budget
- Each agent execution consumes cost
- Execution terminates when budget exceeded

---

## 7. Agent Capability System

### Capability
```
{
  "name": "string",
  "input_schema": {},
  "cost_profile": "low | medium | high"
}
```

---

### Agent Registry
```
{
  "agent_type": "string",
  "capabilities": ["string"],
  "tools": [],
  "cost_profile": "string"
}
```

---

### Selection Algorithm

Steps:
1. Decompose task into capabilities
2. Match capabilities to agents
3. Rank by cost and availability
4. Spawn N instances if required

---

## 8. Functional Requirements

FR-1 Trigger Handling
FR-2 Plan Generation
FR-3 Agent Selection
FR-4 Parallel Execution
FR-5 Result Aggregation
FR-6 Pivoting
FR-7 Observability
FR-8 Checkpointing
FR-9 Guardrails

---

## 9. Non-Functional Requirements

NFR-1 Scalability
NFR-2 Reliability
NFR-3 Performance
NFR-4 Extensibility

---

## 10. Scenarios

### Scenario 1: Basic Execution

1. User creates thread
2. Commander generates plan
3. Agents spawned
4. Agents execute in parallel
5. Results aggregated
6. Thread completes

---

### Scenario 2: Pivot

1. Agents return conflicting results
2. Commander evaluates
3. Commander updates plan
4. New agents spawned

---

### Scenario 3: Failure Handling

1. Agent fails
2. Retry triggered
3. If retries exceed → commander decides next step

---

END
