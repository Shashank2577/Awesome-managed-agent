# SPEC.md

## 1. System Model

Agent OS is composed of:
- Control Plane (Commander)
- Execution Plane (Workers)
- Agent Runtime
- Tool System
- Event Layer
- UI Layer

---

## 2. Agent Lifecycle

States:
CREATED → REGISTERED → READY → QUEUED → RUNNING → WAITING → COMPLETED | FAILED | TERMINATED

Rules:
- Agents MUST NOT skip states
- WAITING indicates dependency
- TERMINATED is final state

---

## 3. Agent Registration

POST /agents/register

```
{
  "agent_type": "string",
  "capabilities": ["string"],
  "tools": ["tool_id"],
  "execution_mode": "sync | async",
  "visibility": "public | private | system"
}
```

---

## 4. Tool System

Tool:
```
{
  "tool_id": "string",
  "input_schema": {},
  "endpoint": "url",
  "timeout": number
}
```

Flow:
Agent → Event → Worker → Tool → Result Event

---

## 5. Commander Model

Loop:
Input → Plan → Execute → Evaluate → Pivot or Finish

---

## 6. Communication Model

- Agents communicate only via events
- No direct calls allowed

---

## 7. UI Interaction

UI subscribes to event stream.

Actions:
- approve
- reject
- pause
- resume
- provide input

---

## 8. Visibility

Modes:
- public
- private
- system

---

## 9. Waiting vs Termination

WAITING:
- tool pending
- user input

TERMINATED:
- completed
- failed
- cancelled

---

## 10. Event Contract

```
{
  "event_id": "string",
  "type": "string",
  "source": "string",
  "target": "string",
  "payload": {},
  "timestamp": "ISO"
}
```

---

## 11. Execution Rules

- Idempotent agents required
- Retry with backoff
- At-least-once execution

---

## 12. Guardrails

- max_agents
- max_parallel
- max_time
- max_cost
- max_pivots

---

## 13. Extensibility

- Agent plugins
- Tool plugins
- UI plugins
- Model providers

---

END
