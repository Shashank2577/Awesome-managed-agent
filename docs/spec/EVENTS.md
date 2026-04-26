# EVENTS.md

## 1. Principles

- Events are the sole communication primitive.
- Events are immutable and append-only.
- Every event type has a schema and validation contract.

---

## 2. Envelope

All events use the canonical envelope from `DATA_MODEL.md` Event entity.

Required envelope fields:
- `event_id`
- `org_id`
- `thread_id`
- `type`
- `source`
- `target` (optional)
- `payload`
- `causation_id` (optional)
- `correlation_id` (optional)
- `sequence`
- `timestamp`

---

## 3. Event Type Taxonomy

## 3.1 Thread Events
- `THREAD_CREATED`
- `THREAD_PLANNING_STARTED`
- `THREAD_READY`
- `THREAD_RUNNING`
- `THREAD_WAITING`
- `THREAD_PAUSED`
- `THREAD_COMPLETED`
- `THREAD_FAILED`
- `THREAD_CANCELLED`
- `THREAD_TERMINATED`

## 3.2 Plan Events
- `PLAN_CREATED`
- `PLAN_APPROVED`
- `PLAN_REJECTED`
- `PLAN_EXECUTION_STARTED`
- `PLAN_COMPLETED`
- `PLAN_FAILED`
- `PLAN_SUPERSEDED`

## 3.3 Node Events
- `NODE_READY`
- `NODE_QUEUED`
- `NODE_RUNNING`
- `NODE_WAITING`
- `NODE_RETRYING`
- `NODE_SUCCEEDED`
- `NODE_FAILED`
- `NODE_SKIPPED`
- `NODE_CANCELLED`

## 3.4 Agent Events
- `AGENT_CREATED`
- `AGENT_REGISTERED`
- `AGENT_READY`
- `AGENT_QUEUED`
- `AGENT_RUNNING`
- `AGENT_WAITING`
- `AGENT_COMPLETED`
- `AGENT_FAILED`
- `AGENT_TERMINATED`

## 3.5 Tool Events
- `TOOL_INVOCATION_QUEUED`
- `TOOL_INVOCATION_STARTED`
- `TOOL_INVOCATION_SUCCEEDED`
- `TOOL_INVOCATION_FAILED`
- `TOOL_INVOCATION_TIMED_OUT`

## 3.6 Budget & Guardrail Events
- `BUDGET_RESERVED`
- `BUDGET_CONSUMED`
- `BUDGET_WARNING`
- `BUDGET_EXHAUSTED`
- `GUARDRAIL_VIOLATION`

## 3.7 Control Plane Events
- `COMMAND_RECEIVED`
- `PLAN_GENERATION_STARTED`
- `PLAN_GENERATION_COMPLETED`
- `PIVOT_REQUESTED`
- `PIVOT_APPLIED`

## 3.8 Human-in-the-Loop Events
- `HUMAN_APPROVAL_REQUESTED`
- `HUMAN_APPROVED`
- `HUMAN_REJECTED`
- `HUMAN_INPUT_RECEIVED`

## 3.9 System Events
- `CHECKPOINT_CREATED`
- `RESUME_REQUESTED`
- `RESUME_COMPLETED`
- `STATE_TRANSITION_REJECTED`
- `DEAD_LETTER_ENQUEUED`

---

## 4. Ordering and Delivery

- Per-thread ordering: strict by `sequence`.
- Delivery semantics: at-least-once.
- Consumers must implement idempotency using `event_id`.

---

## 5. Validation Rules

- Unknown event type is rejected.
- Payload schema mismatch is rejected.
- Missing causation in derived events is warned (not fatal for root events).

---

END
