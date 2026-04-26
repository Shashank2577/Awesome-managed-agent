# STATE_MACHINE.md

## 1. Scope

Defines allowed lifecycle transitions and guards for:
- Thread
- Plan
- PlanNode
- AgentInstance
- WorkerJob
- ToolInvocation

All transitions are event-driven and MUST emit corresponding events.

---

## 2. AgentInstance State Machine (Canonical)

`CREATED -> REGISTERED -> READY -> QUEUED -> RUNNING -> WAITING -> RUNNING -> COMPLETED|FAILED|TERMINATED`

Allowed transitions:
- `CREATED -> REGISTERED`
- `REGISTERED -> READY`
- `READY -> QUEUED`
- `QUEUED -> RUNNING`
- `RUNNING -> WAITING`
- `WAITING -> RUNNING`
- `RUNNING -> COMPLETED`
- `RUNNING -> FAILED`
- `RUNNING -> TERMINATED`
- `WAITING -> TERMINATED`
- `QUEUED -> TERMINATED`

Forbidden:
- any skip over intermediate non-terminal states
- any transition from terminal to non-terminal

---

## 3. Thread State Machine

`CREATED -> PLANNING -> READY -> RUNNING -> WAITING|PAUSED|COMPLETED|FAILED|CANCELLED|TERMINATED`

Allowed transitions:
- `CREATED -> PLANNING`
- `PLANNING -> READY`
- `READY -> RUNNING`
- `RUNNING -> WAITING`
- `WAITING -> RUNNING`
- `RUNNING -> PAUSED`
- `PAUSED -> RUNNING`
- `RUNNING -> COMPLETED|FAILED|CANCELLED|TERMINATED`
- `WAITING -> FAILED|CANCELLED|TERMINATED`
- `PAUSED -> CANCELLED|TERMINATED`

---

## 4. Plan State Machine

`DRAFT -> APPROVED|REJECTED`
`APPROVED -> EXECUTING -> COMPLETED|FAILED|SUPERSEDED`

Rules:
- only approved plans can execute
- a new approved plan may supersede the active plan

---

## 5. PlanNode State Machine

`PENDING -> READY -> QUEUED -> RUNNING -> WAITING|RETRYING|SUCCEEDED|FAILED|CANCELLED`

Rules:
- node enters `READY` only when dependencies are terminal-success (`SUCCEEDED|SKIPPED`)
- `RETRYING` returns to `QUEUED`

---

## 6. WorkerJob State Machine

`QUEUED -> CLAIMED -> RUNNING -> SUCCEEDED|FAILED|RETRY_WAIT|CANCELLED`

Rules:
- `RETRY_WAIT -> QUEUED` after backoff
- max retry bound is enforced by job policy

---

## 7. ToolInvocation State Machine

`QUEUED -> RUNNING -> SUCCEEDED|FAILED|TIMED_OUT|CANCELLED`

Rules:
- timeout transitions MUST include timeout metadata in payload

---

## 8. Transition Guard Conditions

Global guards:
- tenant parity across all referenced entities
- optimistic version check passes
- actor has permission for command
- budget guard passes for execution transitions
- max parallelism guard passes before queue claim

---

## 9. Required Event Emission

Each accepted transition MUST emit:
- `*_STATE_TRANSITIONED` event with `{from, to, reason, actor, timestamp}`

Each rejected transition MUST emit:
- `STATE_TRANSITION_REJECTED` with violation details

---

END
