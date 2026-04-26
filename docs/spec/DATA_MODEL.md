# DATA_MODEL.md

## 1. Overview

This document defines the canonical domain model for Agent OS, including:
- entity fields and types,
- invariants and constraints,
- lifecycle coupling,
- storage/index recommendations,
- serialization and versioning rules.

This specification is normative for:
- backend persistence schemas,
- API contracts,
- event payloads,
- UI state derivation.

---

## 2. Global Modeling Rules

### 2.1 Identifier and Time Rules

- All primary IDs MUST be UUIDv7 strings.
- All timestamps MUST be UTC RFC3339/ISO-8601 with millisecond precision.
- IDs are immutable.
- `created_at` is immutable after creation.
- `updated_at` MUST be updated on every material state mutation.

### 2.2 Multi-Tenant Boundary

- Every persisted domain entity MUST include `org_id`.
- `project_id` is REQUIRED for user-owned execution entities.
- Cross-tenant references are forbidden.
- Foreign-key joins MUST include tenant checks (`org_id` parity).

### 2.3 Soft Deletion and Retention

- Mutable operational entities MAY support soft deletion with:
  - `deleted_at` (nullable timestamp)
  - `deleted_by` (actor id)
- Audit/event entities MUST NOT be hard-mutated except by retention policy.

### 2.4 Optimistic Concurrency

All mutable entities SHOULD include:
- `version` (monotonic integer, starts at 1)
- updates use compare-and-swap semantics where applicable.

---

## 3. Core Entity Definitions

## 3.1 Thread

A Thread is the top-level execution unit representing one orchestrated run.

Required fields:
- `thread_id: uuidv7`
- `org_id: uuidv7`
- `project_id: uuidv7`
- `status: ThreadStatus`
- `title: string(1..200)`
- `objective: string(1..4000)`
- `priority: enum(low|normal|high|urgent)`
- `budget_id: uuidv7`
- `active_plan_id: uuidv7?`
- `execution_started_at: timestamp?`
- `execution_completed_at: timestamp?`
- `created_at: timestamp`
- `updated_at: timestamp`
- `version: int`

Status enum (`ThreadStatus`):
- `CREATED`
- `PLANNING`
- `READY`
- `RUNNING`
- `WAITING`
- `PAUSED`
- `COMPLETED`
- `FAILED`
- `CANCELLED`
- `TERMINATED`

Invariants:
- terminal statuses: `COMPLETED|FAILED|CANCELLED|TERMINATED`
- terminal thread cannot transition to non-terminal
- exactly one active plan at a time when `RUNNING|WAITING|PAUSED`

Indexes:
- `(org_id, project_id, created_at DESC)`
- `(org_id, status, updated_at DESC)`

---

## 3.2 Plan

A Plan is a versioned DAG attached to a Thread.

Required fields:
- `plan_id: uuidv7`
- `thread_id: uuidv7`
- `org_id: uuidv7`
- `project_id: uuidv7`
- `plan_number: int` (1..N within thread)
- `status: PlanStatus`
- `graph: json` (normalized node and edge payloads)
- `created_by: ActorRef`
- `created_at: timestamp`
- `updated_at: timestamp`
- `version: int`

Status enum (`PlanStatus`):
- `DRAFT`
- `APPROVED`
- `REJECTED`
- `SUPERSEDED`
- `EXECUTING`
- `COMPLETED`
- `FAILED`

Invariants:
- `plan_number` unique per thread
- only one `EXECUTING` plan per thread
- `SUPERSEDED` plans are immutable

---

## 3.3 PlanNode

A PlanNode represents one executable unit in a plan DAG.

Required fields:
- `node_id: uuidv7`
- `plan_id: uuidv7`
- `thread_id: uuidv7`
- `org_id: uuidv7`
- `node_key: string` (stable unique key per plan)
- `node_type: enum(agent|tool|decision|join|human_gate)`
- `display_name: string`
- `depends_on: string[]` (array of `node_key`)
- `status: NodeStatus`
- `input_template: json?`
- `config: json`
- `output_schema: json?`
- `retry_policy: json`
- `timeout_ms: int`
- `created_at: timestamp`
- `updated_at: timestamp`
- `version: int`

Status enum (`NodeStatus`):
- `PENDING`
- `READY`
- `QUEUED`
- `RUNNING`
- `WAITING`
- `RETRYING`
- `SUCCEEDED`
- `FAILED`
- `SKIPPED`
- `CANCELLED`

Invariants:
- DAG acyclic at plan approval time
- `depends_on` must reference existing nodes in same plan
- node terminal statuses are immutable

---

## 3.4 AgentRegistration

Defines capability metadata for an agent type.

Required fields:
- `agent_type: string`
- `org_id: uuidv7?` (null => system/global)
- `display_name: string`
- `description: string`
- `capabilities: string[]`
- `supported_tools: string[]`
- `execution_mode: enum(sync|async)`
- `visibility: enum(public|private|system)`
- `runtime_constraints: json`
- `created_at: timestamp`
- `updated_at: timestamp`

Uniqueness:
- `(org_id, agent_type)` unique
- system/global agents use `org_id = null`

---

## 3.5 AgentInstance

A concrete runtime instance of an agent for a node execution.

Required fields:
- `instance_id: uuidv7`
- `thread_id: uuidv7`
- `plan_id: uuidv7`
- `node_id: uuidv7`
- `org_id: uuidv7`
- `agent_type: string`
- `status: AgentStatus`
- `attempt: int`
- `worker_affinity: string?`
- `input: json`
- `output: json?`
- `error: ErrorInfo?`
- `token_usage: TokenUsage`
- `cost: Money`
- `started_at: timestamp?`
- `completed_at: timestamp?`
- `created_at: timestamp`
- `updated_at: timestamp`
- `version: int`

Status enum (`AgentStatus`):
- `CREATED`
- `REGISTERED`
- `READY`
- `QUEUED`
- `RUNNING`
- `WAITING`
- `COMPLETED`
- `FAILED`
- `TERMINATED`

Invariants:
- lifecycle must follow `SPEC.md` state ordering
- completed/failed/terminated require `completed_at`

---

## 3.6 WorkerJob

Queue payload and execution state for a worker task.

Required fields:
- `job_id: uuidv7`
- `org_id: uuidv7`
- `thread_id: uuidv7`
- `instance_id: uuidv7`
- `job_type: enum(run_agent|invoke_tool|evaluate|checkpoint)`
- `status: JobStatus`
- `priority: int` (0..100)
- `retry_count: int`
- `max_retries: int`
- `scheduled_at: timestamp`
- `started_at: timestamp?`
- `completed_at: timestamp?`
- `last_error: ErrorInfo?`
- `created_at: timestamp`
- `updated_at: timestamp`

Status enum (`JobStatus`):
- `QUEUED`
- `CLAIMED`
- `RUNNING`
- `RETRY_WAIT`
- `SUCCEEDED`
- `FAILED`
- `CANCELLED`

---

## 3.7 ToolDefinition

Static metadata describing an invokable tool.

Required fields:
- `tool_id: string`
- `org_id: uuidv7?`
- `name: string`
- `description: string`
- `input_schema: jsonschema`
- `output_schema: jsonschema`
- `endpoint: string`
- `timeout_ms: int`
- `idempotent: bool`
- `enabled: bool`
- `created_at: timestamp`
- `updated_at: timestamp`

---

## 3.8 ToolInvocation

Execution record for a tool call.

Required fields:
- `invocation_id: uuidv7`
- `org_id: uuidv7`
- `thread_id: uuidv7`
- `instance_id: uuidv7`
- `tool_id: string`
- `status: ToolInvocationStatus`
- `input: json`
- `output: json?`
- `error: ErrorInfo?`
- `latency_ms: int?`
- `cost: Money`
- `started_at: timestamp?`
- `completed_at: timestamp?`
- `created_at: timestamp`
- `updated_at: timestamp`

Status enum (`ToolInvocationStatus`):
- `QUEUED`
- `RUNNING`
- `SUCCEEDED`
- `FAILED`
- `TIMED_OUT`
- `CANCELLED`

---

## 3.9 Event

Immutable event envelope for all inter-component communication.

Required fields:
- `event_id: uuidv7`
- `org_id: uuidv7`
- `thread_id: uuidv7`
- `type: string` (from `EVENTS.md` taxonomy)
- `source: EventActor`
- `target: EventActor?`
- `payload: json`
- `causation_id: uuidv7?`
- `correlation_id: uuidv7?`
- `sequence: int` (monotonic per thread)
- `timestamp: timestamp`

Invariants:
- events are append-only
- sequence unique per thread
- payload schema validated by event type

Indexes:
- `(org_id, thread_id, sequence)` unique
- `(org_id, type, timestamp DESC)`

---

## 3.10 Checkpoint

Snapshot to support resume and replay.

Required fields:
- `checkpoint_id: uuidv7`
- `org_id: uuidv7`
- `thread_id: uuidv7`
- `plan_id: uuidv7`
- `scope: enum(thread|plan|node)`
- `scope_ref: string`
- `state_blob: json|bytes`
- `event_sequence: int`
- `created_at: timestamp`

Invariants:
- immutable after creation
- `event_sequence` must exist in event stream

---

## 3.11 BudgetLedger

Thread-level budgeting and spend ledger.

Required fields:
- `budget_id: uuidv7`
- `org_id: uuidv7`
- `thread_id: uuidv7`
- `currency: string(ISO-4217)`
- `allocated: decimal(18,6)`
- `reserved: decimal(18,6)`
- `consumed: decimal(18,6)`
- `hard_limit: decimal(18,6)`
- `status: enum(active|warning|exhausted|closed)`
- `created_at: timestamp`
- `updated_at: timestamp`
- `version: int`

Invariant:
- `0 <= consumed <= hard_limit`
- reservation + consumed cannot exceed hard limit

---

## 4. Shared Value Objects

### 4.1 ActorRef
- `actor_type: enum(user|system|agent|worker|tool|commander|ui)`
- `actor_id: string`
- `display_name: string?`

### 4.2 Money
- `currency: string`
- `amount: decimal(18,6)`

### 4.3 TokenUsage
- `prompt_tokens: int`
- `completion_tokens: int`
- `total_tokens: int`
- `model: string?`

### 4.4 ErrorInfo
- `code: string`
- `message: string`
- `retryable: bool`
- `details: json?`

---

## 5. Cardinality Summary

- Thread `1:N` Plan
- Plan `1:N` PlanNode
- PlanNode `1:N` AgentInstance (retries)
- AgentInstance `1:N` ToolInvocation
- Thread `1:N` Event
- Thread `1:N` Checkpoint
- Thread `1:1` BudgetLedger

---

## 6. Serialization & Compatibility

- API serialization uses `snake_case`.
- Unknown JSON fields should be ignored on read and preserved where possible.
- Breaking changes require version bump in API namespace and migration spec.

---

## 7. Validation Matrix

- ID format validation at ingress and persistence boundaries.
- Enum validation in API and worker consumers.
- JSON schema validation for tool input/output.
- Event payload validation by event type registry.

---

END
