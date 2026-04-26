# EXECUTION_SEMANTICS.md

## 1. Execution Guarantees

- Event delivery semantics: at-least-once.
- Job processing semantics: at-least-once.
- State transitions are idempotent.

---

## 2. Planning Loop

Commander loop:
1. ingest objective
2. generate plan DAG
3. validate constraints
4. request approval (if configured)
5. execute nodes
6. evaluate outcomes
7. pivot if needed and allowed
8. finalize thread

---

## 3. DAG Scheduling Rules

- Node eligible when all dependencies terminal and successful.
- Nodes with no dependencies are initial frontier.
- Scheduler respects `max_parallel` guardrail.
- Deterministic tie-breaker: `(priority DESC, created_at ASC, node_key ASC)`.

---

## 4. Retry Semantics

- Retry policy per node/job: max attempts + backoff strategy.
- Retryable failures move node/job to `RETRYING/RETRY_WAIT`.
- Non-retryable failures propagate failure to thread according to policy.

Backoff default:
- exponential with jitter
- base 500ms
- cap 30s

---

## 5. Waiting Semantics

`WAITING` represents blocked progress due to:
- tool response pending
- human input required
- external dependency signal

Unblock is event-driven only.

---

## 6. Checkpoint & Resume

Checkpoint triggers:
- before risky fan-out
- before pivot
- periodic interval (configurable)
- manual pause

Resume behavior:
- load latest valid checkpoint
- replay events after checkpoint sequence
- recompute ready frontier idempotently

---

## 7. Failure Propagation

- Node failure can be local or terminal according to fail policy.
- Thread fails when no viable path to completion exists.
- Commander may pivot instead of failing if within max pivots.

---

## 8. Idempotency Requirements

Idempotency keys:
- event dedupe by `event_id`
- tool dedupe by `(instance_id, tool_id, attempt)`
- job dedupe by `job_id`

---

## 9. Deterministic Guardrail Enforcement

Guards checked at plan validation and runtime dispatch:
- max agents
- max parallel
- max time
- max cost
- max pivots

On violation:
- emit `GUARDRAIL_VIOLATION`
- halt affected scope
- move thread to `FAILED` or `TERMINATED` per policy

---

END
