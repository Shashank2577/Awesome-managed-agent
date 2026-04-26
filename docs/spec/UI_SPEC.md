# UI_SPEC.md

## 1. Objective

Define minimum UI behaviors for observable and controllable execution.

---

## 2. Screens

- Thread List
- Thread Detail
- Live Event Timeline
- Execution Graph View
- Agent Instance Inspector
- Budget Panel

---

## 3. Thread Detail Requirements

Must show:
- current thread status
- active plan version
- node statuses (real time)
- budget consumed/reserved
- latest errors and guardrail violations

Controls:
- pause
- resume
- cancel
- provide human input
- approve/reject plan (when pending)

---

## 4. Event Timeline

- ordered by event sequence
- filter by type/source
- jump to causation chain
- highlight errors and retries

---

## 5. Execution Graph View

- render DAG nodes and edges
- node color by state
- display retries/attempt counts
- click node opens instance/tool details

---

## 6. Streaming Contract

UI consumes SSE/WebSocket stream from `/threads/{id}/events/stream`.

Client responsibilities:
- reconnect with last sequence
- dedupe by `event_id`
- preserve strict sequence ordering per thread

---

## 7. Human-in-the-Loop UX

On `HUMAN_APPROVAL_REQUESTED` or `HUMAN_INPUT_RECEIVED` waits:
- show blocking banner
- collect input with schema-aware form
- send response action event

---

## 8. Non-Functional Targets

- Time to first event < 2s (p95)
- Timeline render supports >= 10k events with virtualization
- Graph updates under 200ms from event arrival

---

END
