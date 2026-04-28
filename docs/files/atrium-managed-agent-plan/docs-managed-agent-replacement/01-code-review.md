# 01 — Code Review

This is an honest review of the current Atrium codebase, performed by reading
every file in `src/atrium/`. The goal is not to produce a clean bill of health
— it's to surface the things that will bite us when we add the harness layer
and harden Atrium for production multi-tenant use.

The codebase is small (around 230KB of Python plus a static dashboard) and
generally well-organized. The separation into `core / engine / streaming / api
/ dashboard` is clean and the constitution.md document is honest about what's
fully implemented vs partial. What follows are the issues that actually matter.

## What's good

- **Module boundaries are real, not aspirational.** `core` has no engine
  imports, `engine` doesn't reach into the dashboard, the streaming bus is its
  own thing. This will make adding the harness package straightforward.
- **The Agent base class is minimal and correct.** A metaclass that enforces
  `name` and `description`, an abstract `run()`, an emitter for `say()`. Easy
  to subclass, hard to misuse.
- **`AgentMeta` is the right pattern.** Catching missing class attributes at
  instantiation time rather than runtime is the right call.
- **Event recorder is event-sourced and append-only.** Sequence numbers under a
  lock, SQLite persistence, replay-from-sequence — this is exactly what a
  durable session needs. The harness work can build on it directly.
- **The HITL ThreadController is well thought out.** Per-thread asyncio events
  for pause / approval / human input, with cancellation that unblocks every
  waiter. This pattern carries straight over to long-running harness sessions.
- **LLM provider abstraction.** `parse_llm_config` plus lazy chat-model loading
  in `LLMClient` means the Commander is already model-agnostic. Good.
- **Dashboard ships in the same package.** No separate frontend repo to keep in
  sync. For an integration tool this is the right call.

## What's broken or weak

### 1. Thread storage is in-memory only — `api/routes/threads.py:24`
```python
_threads: dict[str, Thread] = {}
```
Restart the API, every running thread is gone. Events survive in SQLite but the
Thread record itself doesn't. A long-running harness session (the entire point
of what we're building) cannot survive a deploy. This is a top-priority fix.

### 2. Budget consumption is hardcoded — `engine/orchestrator.py:155-158`
```python
await self._recorder.emit(tid, "BUDGET_CONSUMED", {
    "currency": "USD",
    "consumed": "0.10",  # estimated planning cost
    "hard_limit": str(self._guardrails.config.max_cost_usd),
})
```
The budget UI shows fake numbers. The constitution.md flags this as
"⚠️ PARTIAL". For v1 we need real per-call token counting from the LLM
responses. LangChain's `ainvoke` returns usage data; we ignore it.

### 3. Guardrails are defined but only `max_pivots` is enforced
`GuardrailEnforcer` has `check_spawn`, `check_parallel`, `check_time`,
`check_cost`, `check_pivots`. Searching the codebase, only `check_pivots` is
actually called (in `orchestrator.py:257`). `max_agents`, `max_parallel`,
`max_time_seconds`, and `max_cost_usd` are never checked at runtime.
The constitution claims "✅ ENFORCED" — it isn't.

### 4. Agents catch their own exceptions and swallow them — `engine/graph_builder.py:56-61`
```python
try:
    output = await agent.run(agent_input)
    await emit_agent_completed(recorder, thread_id, agent_name, output)
except Exception as exc:
    await emit_agent_failed(recorder, thread_id, agent_name, str(exc))
    output = {"error": str(exc)}
```
Failed agents return `{"error": "..."}` and downstream agents in the DAG
keep running with that as their `upstream`. A long pipeline will produce
garbage and the Commander will write a confident final report based on
errors. There needs to be a fail-policy: stop-thread, retry-step, or
continue. Right now it's silently the third.

### 5. `create_agent_class` closure leaks the config — `core/http_agent.py:32-41`
```python
class ConfiguredHTTPAgent(Agent):
    name = agent_name
    ...
    def __init__(self) -> None:
        super().__init__()
        self._config: dict[str, Any] = config
```
Two issues here. First, `config` is captured in a closure *and* assigned per
instance — pick one. Second, if a user creates 100 different HTTP agents
(which the user said they want to do for the agent marketplace work),
each lives forever in module memory because `AgentRegistry` holds the class.
There's no eviction. For 100+ agents, this is acceptable; for thousands,
it isn't.

### 6. Module-level state in the API — `api/app.py:25-28`
```python
_registry: Optional[AgentRegistry] = None
_recorder: Optional[EventRecorder] = None
_orchestrator: Optional[ThreadOrchestrator] = None
_agent_store: Optional[AgentStore] = None
```
These are mutated by `create_app()` and read by route handlers via
`get_registry()` etc. This works for a single FastAPI app but breaks under
testing (the tests have to import from `atrium.api.app` and reset state
between tests) and makes multi-tenant isolation impossible — there's
literally one global registry and one global recorder.

### 7. Module-level controller dict — `engine/orchestrator.py:77`
```python
_controllers: dict[str, ThreadController] = {}
```
Same problem at the engine layer. Acceptable for a single-process
single-tenant deploy. Not acceptable for what we're building.

### 8. SQLite connection without thread-safety — `core/agent_store.py:16`
```python
self._db = sqlite3.connect(db_path, check_same_thread=False)
```
`check_same_thread=False` plus no locking means concurrent writes will
race. SQLite is fine as a default, but writes need to be serialized
(either through a single asyncio queue or by switching to aiosqlite).
The same issue exists in `streaming/events.py:32`.

### 9. The dashboard `_threads` dict and the recorder's events drift
The thread status in `_threads` is updated by `_run_orchestrator` after
`orchestrator.run()` returns. But the recorder has emitted
`THREAD_COMPLETED` at that point. There are two sources of truth and they
can disagree. Make the recorder the only source of truth for status; the
thread record should be projected from events.

### 10. No retry / backoff anywhere
HTTP agents make a single request, no retry on 5xx. LLM calls in
`LLMClient.generate_json` make a single request, no retry on rate-limit.
The constitution flags this as "⚠️ PARTIAL". For a long-running harness
session this matters a lot — a single rate-limit error should not kill a
two-hour run.

### 11. JSON parsing of LLM output is fragile — `engine/llm.py:80-82`
```python
text = _strip_markdown_fence(response.content)
return json.loads(text)
```
If the model returns malformed JSON (which Gemini does occasionally),
this throws and the whole thread fails. Three improvements: ask the model
for structured output via the provider's native structured-output API
(OpenAI tool calling, Anthropic tool use, Gemini response_mime_type),
fall back to a JSON-fixing pass, and at minimum wrap this in retry.

### 12. No request-level auth / authz on the API
Every route is open. For a service running on EKS with multiple internal
clients (CIVI, PLC Direct, Master CRM), this is a non-starter. We need
at minimum API keys per consumer, ideally JWTs with workspace scoping.

### 13. `agent_input["upstream"]` is a string-key dump of all upstream outputs
When agent C depends on A and B, it gets `{"upstream": {"A": ..., "B":
...}}`. The agent has to know the names of its upstream dependencies and
pluck the right values out. This pushes coupling into the leaf agents.
A cleaner model is for the Plan to declare per-step input mappings:
`inputs: {"text": "$.A.summary"}` style. JSONPath or simple dotted
paths would do.

### 14. Single Commander prompt; no plan validation
The Commander asks the LLM for JSON, parses it, and trusts it. There's no
validation that the agent names exist in the registry, that the DAG is
acyclic, or that depends_on entries reference real plan steps. A bad LLM
response can produce a graph that LangGraph compiles and then crashes on.

### 15. The dashboard static files live inside the package — fine, but...
`src/atrium/dashboard/static` is 78KB and is mounted at runtime. If we want
to embed widgets in third-party UIs, the static assets need to be served
with proper CORS and from a stable URL pattern. Right now the routes are
mounted under `/dashboard/static/` with no CORS config visible. The
`api/middleware.py` file is only 1KB — very likely we don't have CORS
configured.

## What's missing (by category)

These aren't bugs, they're absent features. They are the gap between Atrium
and a real Managed Agents replacement.

| Category | Missing |
|----------|---------|
| Sandbox | No process isolation. Agents run in the API process. |
| Filesystem | No per-session workspace. Agents share `/tmp`. |
| Long-running execution | No checkpoint / resume. A killed worker loses everything. |
| Tool primitives | No bash, no file editor, no web_fetch, no code execution. HTTP only. |
| MCP support | None. |
| Token accounting | LLM calls don't return costs to the orchestrator. |
| Rate limiting | None on inbound API or outbound LLM. |
| Auth | None. |
| Multi-tenancy | None. Single registry, single recorder. |
| Resume | A thread can pause but not survive a process restart. |
| Artifact API | No way to read files produced by an agent. |
| Webhooks | No way to notify an external system on completion. |
| Widget mode | No embed-friendly read-only views. |

## Severity summary

| Issue | Severity | Blocks harness work? |
|-------|----------|----------------------|
| In-memory thread storage | High | Yes |
| Hardcoded budget | Medium | No, but breaks UX |
| Guardrails not enforced | High | Yes |
| Swallowed agent exceptions | High | Yes — masks harness failures |
| Module-level state | High | Yes — blocks multi-tenancy |
| SQLite concurrency | Medium | Probably not, until load |
| No retry / backoff | High | Yes — long sessions need it |
| Brittle JSON parsing | Medium | Yes for non-Claude models |
| No auth | High | Yes for production |
| No artifact API | High | Yes — harness produces files |

The "Yes" items in the right column are the prerequisites we'll address in
phase 1 of the roadmap before adding the harness package.
