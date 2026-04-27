# Constitution

## Core Laws

### 1. Event-Driven Execution ✅ ENFORCED
All agent lifecycle transitions emit events. EventRecorder captures everything.

### 2. Explicit Execution Graph ✅ ENFORCED
Commander generates plans as DAGs. Graph Builder compiles to LangGraph StateGraphs.

### 3. Ephemeral Agents ✅ ENFORCED
Agents are instantiated per-execution, stateless, isolated. No shared state between runs.

### 4. Deterministic Guardrails ✅ ENFORCED
GuardrailEnforcer checks cost, time, parallelism, and pivot limits. Violations halt execution.

### 5. Observable Execution ✅ ENFORCED
All events persisted to SQLite with sequence numbers. SSE streaming to dashboard.

### 6. Human-in-the-Loop ✅ ENFORCED
ThreadController supports pause, resume, cancel, approve, reject. Optional per-thread.

### 7. Separation of Concerns ✅ ENFORCED
Core, Engine, Streaming, API, Dashboard are independent layers with clear interfaces.

### 8. Extensibility ✅ ENFORCED
Agents are pluggable (subclass Agent). LLM providers are pluggable (openai/anthropic/google). Storage is pluggable (SQLite default).

### 9. Fault Tolerance ⚠️ PARTIAL
Orchestrator catches exceptions and emits THREAD_FAILED. No retry/backoff yet.

### 10. Cost Awareness ⚠️ PARTIAL
Budget events emitted. Guardrail checks cost limits. Actual token-level tracking not yet implemented.
