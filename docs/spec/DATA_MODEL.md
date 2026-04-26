# DATA_MODEL.md

## 1. Overview

Defines canonical entities, relationships, identifiers, and ownership model for Agent OS.

---

## 2. Identifier Rules

- All IDs are UUID v7 (time-sortable)
- Scoped by tenant unless specified

Fields:
- org_id (tenant boundary)
- project_id (logical grouping)
- thread_id (execution unit)

---

## 3. Core Entities

### 3.1 Thread

Represents a single execution workflow.

Fields:
- thread_id
- org_id
- project_id
- status
- budget
- created_at
- updated_at

Relations:
- 1 Thread → many Plans
- 1 Thread → many AgentInstances
- 1 Thread → many Events

---

### 3.2 Plan

Execution graph.

Fields:
- plan_id
- thread_id
- version
- graph (nodes + edges)

Relations:
- 1 Plan → many Nodes

---

### 3.3 Node

Unit of execution in graph.

Fields:
- node_id
- plan_id
- type (agent | tool | decision)
- dependencies
- status

---

### 3.4 AgentInstance

Runtime instance of agent.

Fields:
- instance_id
- thread_id
- agent_type
- status
- cost
- started_at
- completed_at

---

### 3.5 WorkerJob

Execution job assigned to worker.

Fields:
- job_id
- instance_id
- status
- retry_count

---

### 3.6 ToolInvocation

Tool execution instance.

Fields:
- invocation_id
- instance_id
- tool_id
- input
- output
- status

---

### 3.7 Event

System event.

Fields:
- event_id
- thread_id
- type
- payload
- timestamp
- causation_id
- correlation_id

---

### 3.8 Checkpoint

Execution recovery snapshot.

Fields:
- checkpoint_id
- thread_id
- state_blob
- created_at

---

### 3.9 Budget

Cost tracking entity.

Fields:
- budget_id
- thread_id
- allocated
- consumed

---

## 4. Cardinality Summary

- Thread → Plans (1:N)
- Plan → Nodes (1:N)
- Thread → AgentInstances (1:N)
- AgentInstance → ToolInvocation (1:N)
- Thread → Events (1:N)

---

## 5. Ownership Model

- org_id → tenant boundary
- project_id → logical grouping
- thread_id → execution scope

---

## 6. Constraints

- All entities must include org_id
- Cross-tenant access is forbidden
- Event must always reference thread_id

---

END
