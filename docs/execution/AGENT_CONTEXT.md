# AGENT_CONTEXT.md

## System Overview

This system is an Agent Operating System (Agent OS).

It follows:
- Event-driven architecture
- Explicit orchestration (graph-based)
- Ephemeral agents
- Deterministic guardrails

---

## Mandatory Context Loading

Before any implementation or execution, the process MUST:

1. Read CONSTITUTION.md
2. Read SPEC.md
3. Read PLANNING.md
4. Read TASKS.md
5. Read HANDOFFS.md

---

## Execution Rules

- Do NOT deviate from defined spec
- Do NOT invent undefined behavior
- Always break work into tasks
- Always update TASKS.md after execution
- Always update HANDOFFS.md after execution

---

## Execution Handle

Each execution MUST define:

- execution_id
- session_id
- last_task
- next_task
- timestamp

---

## Current Focus

Derived from TASKS.md and HANDOFFS.md

---

END
