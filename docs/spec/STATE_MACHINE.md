# State Machine

## Thread States

```
CREATED → PLANNING → RUNNING → COMPLETED
                   ↘ PAUSED → RUNNING (resume)
                   ↘ FAILED
                   ↘ CANCELLED
```

Thread status is updated by the API route handler based on orchestrator lifecycle:
- CREATED: thread created
- RUNNING: orchestrator started
- COMPLETED: orchestrator finished successfully
- FAILED: orchestrator caught exception
- CANCELLED: operator cancelled via HITL

## Agent States (managed by LangGraph)

Agent lifecycle is implicit — tracked via events, not explicit state machine.
The framework emits AGENT_RUNNING when an agent starts and AGENT_COMPLETED or AGENT_FAILED when it finishes.
