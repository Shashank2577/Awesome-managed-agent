# PHASE 0 — Stabilization

**Goal:** fix the issues from `01-code-review.md` that block everything else.
No new features. After this phase, Atrium is the same shape it is today but
with the bugs fixed and the foundations strengthened.

**Estimated effort:** 5 days (1 engineer).

**Depends on:** nothing.

**Unblocks:** all later phases.

## 0.1 Files to create or modify

| Action | Path | What |
|--------|------|------|
| MODIFY | `src/atrium/api/routes/threads.py` | Replace `_threads` dict with `ThreadStore`. |
| CREATE | `src/atrium/core/thread_store.py` | New persistent thread store. |
| MODIFY | `src/atrium/engine/orchestrator.py` | Real guardrail enforcement; fail policy; remove `_controllers` module-level dict. |
| MODIFY | `src/atrium/engine/graph_builder.py` | Fail policy on agent errors; runtime guardrail checks. |
| MODIFY | `src/atrium/engine/llm.py` | Retry/backoff; structured output where supported; real token accounting. |
| MODIFY | `src/atrium/engine/commander.py` | Plan validation: registry check, cycle check, dup check. |
| MODIFY | `src/atrium/streaming/events.py` | Single-writer SQLite; aiosqlite. |
| MODIFY | `src/atrium/core/agent_store.py` | Same single-writer pattern. |
| MODIFY | `src/atrium/api/middleware.py` | Structured error responses; CORS unchanged but documented. |
| CREATE | `src/atrium/core/logging.py` | JSON logger helper. |
| CREATE | `src/atrium/core/retry.py` | `async_retry` decorator. |
| CREATE | `src/atrium/core/errors.py` | Error response envelope and exception hierarchy. |
| MODIFY | `tests/conftest.py` | Add the standard fixtures from CONTRACTS.md §9. |
| CREATE | `tests/test_core/test_thread_store.py` | New tests. |
| CREATE | `tests/test_core/test_retry.py` | New tests. |
| CREATE | `tests/test_engine/test_guardrails_runtime.py` | New tests. |
| CREATE | `tests/test_engine/test_plan_validation.py` | New tests. |
| MODIFY | `tests/test_engine/test_orchestrator.py` | Update for new fail-policy + persistent threads. |

## 0.2 New module: `core/errors.py`

```python
# verbatim
"""Error response envelope and exception hierarchy."""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel


class ErrorResponse(BaseModel):
    error: str
    message: str
    details: dict[str, Any] | None = None


class AtriumError(Exception):
    """Base for all Atrium-specific exceptions. Each carries an error_code."""
    error_code: str = "internal_error"
    http_status: int = 500

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        self.message = message
        self.details = details
        super().__init__(message)

    def to_response(self) -> ErrorResponse:
        return ErrorResponse(
            error=self.error_code, message=self.message, details=self.details
        )


class ValidationError(AtriumError):
    error_code = "validation_error"
    http_status = 400


class NotFoundError(AtriumError):
    error_code = "not_found"
    http_status = 404


class ConflictError(AtriumError):
    error_code = "conflict"
    http_status = 409


class GuardrailViolation(AtriumError):
    error_code = "guardrail_violation"
    http_status = 422
```

The existing `core/guardrails.py:GuardrailViolation` is moved here in
Phase 0; update its imports throughout the codebase. The existing
behaviour (carries `code` + `message`) is preserved by keeping a
backward-compatible `code` property.

## 0.3 New module: `core/retry.py`

```python
# verbatim
"""Async retry helper with exponential backoff and jitter."""
from __future__ import annotations

import asyncio
import random
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


async def async_retry(
    fn: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    initial_delay: float = 0.5,
    max_delay: float = 8.0,
    backoff_factor: float = 2.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    """Retry an async callable with exponential backoff + jitter.

    Args:
        fn: zero-arg async function to call.
        max_attempts: total attempts including the first.
        initial_delay: seconds before the second attempt.
        max_delay: cap on per-attempt delay.
        backoff_factor: multiplier per attempt.
        retry_on: exception types that trigger a retry. Other exceptions
            propagate immediately.

    Raises:
        The last exception if all attempts fail.
    """
    delay = initial_delay
    last_exc: BaseException | None = None
    for attempt in range(max_attempts):
        try:
            return await fn()
        except retry_on as exc:
            last_exc = exc
            if attempt == max_attempts - 1:
                raise
            jitter = random.uniform(0, delay * 0.25)
            await asyncio.sleep(min(delay + jitter, max_delay))
            delay *= backoff_factor
    assert last_exc is not None
    raise last_exc
```

## 0.4 New module: `core/logging.py`

```python
# verbatim
"""JSON structured logging helper."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "msg": record.getMessage(),
            "module": record.name,
        }
        # Surface common context fields if attached via `extra=`
        for key in ("workspace_id", "thread_id", "session_id", "event_id"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exc_type"] = record.exc_info[0].__name__
            payload["exc_msg"] = str(record.exc_info[1])
        return json.dumps(payload, default=str)


def configure(level: str = "INFO") -> None:
    """Configure root logger to emit JSON lines to stdout. Idempotent."""
    root = logging.getLogger()
    if any(isinstance(h, logging.StreamHandler) and isinstance(h.formatter, JSONFormatter)
           for h in root.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root.handlers = [handler]
    root.setLevel(level.upper())
```

## 0.5 New module: `core/thread_store.py`

```python
# template — replace _threads dict in api/routes/threads.py
"""Persistent thread store. SQLite-backed via aiosqlite."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import aiosqlite

from atrium.core.models import Thread, ThreadStatus


_SCHEMA = """
CREATE TABLE IF NOT EXISTS threads (
    thread_id   TEXT PRIMARY KEY,
    objective   TEXT NOT NULL,
    title       TEXT NOT NULL,
    status      TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    metadata    TEXT NOT NULL  -- JSON blob
);
CREATE INDEX IF NOT EXISTS idx_threads_status ON threads(status);
CREATE INDEX IF NOT EXISTS idx_threads_created_at ON threads(created_at);
"""


class ThreadStore:
    """Async persistent store for Thread records.

    Single-writer pattern: all writes serialize through a single asyncio
    Lock. Reads are concurrent. Connection is held for the lifetime of
    the store.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None
        self._write_lock = asyncio.Lock()  # add `import asyncio` above

    async def open(self) -> None:
        """Open connection and apply schema. Call once at startup."""
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    async def create(self, thread: Thread) -> None:
        async with self._write_lock:
            assert self._db is not None
            await self._db.execute(
                "INSERT INTO threads (thread_id, objective, title, status, "
                "created_at, metadata) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    thread.thread_id,
                    thread.objective,
                    thread.title,
                    thread.status.value,
                    thread.created_at.isoformat(),
                    json.dumps({}),
                ),
            )
            await self._db.commit()

    async def set_status(self, thread_id: str, status: ThreadStatus) -> None:
        async with self._write_lock:
            assert self._db is not None
            cursor = await self._db.execute(
                "UPDATE threads SET status = ? WHERE thread_id = ?",
                (status.value, thread_id),
            )
            if cursor.rowcount == 0:
                raise NotFoundError(f"thread {thread_id} not found")
            await self._db.commit()

    async def delete(self, thread_id: str) -> None:
        async with self._write_lock:
            assert self._db is not None
            await self._db.execute(
                "DELETE FROM threads WHERE thread_id = ?", (thread_id,),
            )
            await self._db.commit()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    async def get(self, thread_id: str) -> Thread | None:
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT thread_id, objective, title, status, created_at "
            "FROM threads WHERE thread_id = ?",
            (thread_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return Thread(
            thread_id=row[0],
            objective=row[1],
            title=row[2],
            status=ThreadStatus(row[3]),
            created_at=datetime.fromisoformat(row[4]),
        )

    async def list_all(self) -> list[Thread]:
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT thread_id, objective, title, status, created_at "
            "FROM threads ORDER BY created_at DESC"
        )
        return [
            Thread(
                thread_id=row[0],
                objective=row[1],
                title=row[2],
                status=ThreadStatus(row[3]),
                created_at=datetime.fromisoformat(row[4]),
            )
            async for row in cursor
        ]
```

The `_threads` dict in `api/routes/threads.py` is replaced. The store is
constructed in `api/app.py:create_app()` and held in the app's
dependency container (replacing the module-level globals — see Phase 1).
For Phase 0 only, the simplest path is: add the store as a module-level
global next to the existing `_recorder`, then Phase 1 cleans both up.

## 0.6 Modifications to `engine/graph_builder.py`

The current node function silently swallows exceptions. Change it to
respect a per-step **fail policy**, defaulting to `stop_thread`.

```python
# template — replace build_agent_node
from enum import Enum

class FailPolicy(str, Enum):
    STOP_THREAD = "stop_thread"   # raise; the orchestrator marks thread FAILED
    CONTINUE = "continue"         # current behaviour: return {"error": ...}
    RETRY_STEP = "retry_step"     # retry up to max_attempts, then stop_thread


def build_agent_node(
    agent_name: str,
    registry: AgentRegistry,
    recorder: EventRecorder,
    thread_id: str,
    guardrails: GuardrailEnforcer,
    fail_policy: FailPolicy = FailPolicy.STOP_THREAD,
    max_attempts: int = 3,
):
    async def node_fn(state: ThreadState) -> dict:
        # ... existing setup unchanged ...

        async def run_once() -> dict:
            return await agent.run(agent_input)

        await emit_agent_running(recorder, thread_id, agent_name)

        try:
            if fail_policy == FailPolicy.RETRY_STEP:
                output = await async_retry(
                    run_once, max_attempts=max_attempts,
                )
            else:
                output = await run_once()
            await emit_agent_completed(recorder, thread_id, agent_name, output)
        except Exception as exc:
            await emit_agent_failed(recorder, thread_id, agent_name, str(exc))
            if fail_policy == FailPolicy.STOP_THREAD:
                raise   # caller (orchestrator) will catch and mark thread FAILED
            output = {"error": str(exc)}

        # Guardrail: parallel + spawn at runtime. The graph itself bounds
        # parallelism, but we re-check here for symmetry with the others.
        new_outputs = dict(state.get("agent_outputs", {}))
        new_outputs[agent_name] = output
        return {"agent_outputs": new_outputs}

    return node_fn
```

The `build_graph_from_plan` signature gains an optional
`fail_policy: FailPolicy = FailPolicy.STOP_THREAD` and an optional
`guardrails: GuardrailEnforcer`. Callers (orchestrator) pass these.

## 0.7 Modifications to `engine/orchestrator.py`

Three concrete changes:

1. **Real budget tracking** — replace the hardcoded `0.10` and `0.20`
   strings with the LLM's reported usage. `LLMClient.generate_json` is
   modified to return both the parsed payload and a `usage` dict. The
   orchestrator accumulates and emits `BUDGET_CONSUMED` with real
   numbers.

2. **Real time guardrail** — at the top of `run()`, capture
   `started_at = time.monotonic()`. Spawn a background task that ticks
   every 1s and calls `self._guardrails.check_time(elapsed)`. On
   violation, emit `BUDGET_EXCEEDED` and cancel the orchestrator task.

3. **Remove module-level `_controllers`** — turn it into an instance
   attribute of `ThreadOrchestrator`. The HITL routes (`api/routes/control.py`)
   currently `from atrium.engine.orchestrator import get_controller`.
   Change them to read from the orchestrator passed via
   `get_orchestrator()` in `api/app.py`. Add an
   `orchestrator.get_controller(thread_id)` instance method.

```python
# template — orchestrator.run with real time guardrail
import time, asyncio

async def run(self, objective: str, thread_id: str | None = None) -> dict:
    # ... existing setup ...
    started_at = time.monotonic()
    cancel_event = asyncio.Event()

    async def time_watchdog() -> None:
        while not cancel_event.is_set():
            await asyncio.sleep(1.0)
            elapsed = time.monotonic() - started_at
            try:
                self._guardrails.check_time(elapsed)
            except GuardrailViolation as exc:
                await self._recorder.emit(
                    tid, "BUDGET_EXCEEDED",
                    {"code": exc.code, "message": exc.message},
                )
                cancel_event.set()

    watchdog_task = asyncio.create_task(time_watchdog())
    try:
        # ... existing body ...
    finally:
        cancel_event.set()
        watchdog_task.cancel()
        try:
            await watchdog_task
        except asyncio.CancelledError:
            pass
        self._controllers.pop(tid, None)
```

## 0.8 Modifications to `engine/commander.py`

Add **plan validation** between `await self._client.generate_json(...)`
and returning the `Plan`. Three checks, in order:

```python
# verbatim — drop into commander.plan() before returning Plan
def _validate_plan(steps: list[PlanStep], registry: AgentRegistry) -> None:
    """Validate a plan against the registry. Raises ValidationError on issues."""
    # 1. Every agent name exists.
    available = {cls.name for cls in registry.list_all()}
    for step in steps:
        if step.agent not in available:
            raise ValidationError(
                f"plan references unknown agent: {step.agent}",
                {"available": sorted(available)},
            )

    # 2. No duplicates.
    seen: set[str] = set()
    for step in steps:
        if step.agent in seen:
            raise ValidationError(
                f"plan uses agent '{step.agent}' more than once"
            )
        seen.add(step.agent)

    # 3. depends_on references real steps and is acyclic.
    step_names = {s.agent for s in steps}
    for step in steps:
        for dep in step.depends_on:
            if dep not in step_names:
                raise ValidationError(
                    f"step '{step.agent}' depends on missing step '{dep}'"
                )

    # Cycle detection — DFS with white/gray/black colours.
    WHITE, GRAY, BLACK = 0, 1, 2
    colour: dict[str, int] = {s.agent: WHITE for s in steps}
    deps: dict[str, list[str]] = {s.agent: list(s.depends_on) for s in steps}

    def dfs(node: str) -> None:
        colour[node] = GRAY
        for d in deps[node]:
            if colour[d] == GRAY:
                raise ValidationError(f"plan has a cycle involving '{node}' and '{d}'")
            if colour[d] == WHITE:
                dfs(d)
        colour[node] = BLACK

    for s in steps:
        if colour[s.agent] == WHITE:
            dfs(s.agent)
```

Call it: `_validate_plan(plan.steps, self._registry)` before returning
the `Plan` from `Commander.plan()`. Validation failures raise
`ValidationError`, which the orchestrator catches and emits as
`THREAD_FAILED` with the validation reason.

## 0.9 Modifications to `engine/llm.py`

Three changes:

1. **Wrap `ainvoke` in `async_retry`** with `retry_on=(Exception,)` and
   3 attempts. Most provider SDKs raise specific rate-limit exceptions;
   for now we retry on broad `Exception` and refine later.

2. **Use provider-native structured output where supported.** For
   OpenAI, pass `response_format={"type": "json_object"}` to
   `ChatOpenAI`. For Anthropic, leave as-is (their tool-use is more
   complex; structured output via tool-use is a phase 3 enhancement).
   For Gemini, pass `response_mime_type="application/json"`.

3. **Return usage**:

```python
# template — replace LLMClient.generate_json
async def generate_json(
    self, system_prompt: str, user_prompt: str
) -> tuple[dict[str, Any], dict[str, int]]:
    """Returns (parsed_payload, usage_dict).

    usage_dict has keys: 'input_tokens', 'output_tokens', 'total_tokens'.
    Empty dict if the provider didn't return usage.
    """
    model = self._get_chat_model()
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    async def _call():
        return await model.ainvoke(messages)

    response = await async_retry(_call, max_attempts=3)
    text = _strip_markdown_fence(response.content)
    payload = json.loads(text)
    usage = self._extract_usage(response)
    return payload, usage

def _extract_usage(self, response: Any) -> dict[str, int]:
    """LangChain v0.3 standardizes usage_metadata on the AIMessage."""
    meta = getattr(response, "usage_metadata", None)
    if not meta:
        return {}
    return {
        "input_tokens": int(meta.get("input_tokens", 0)),
        "output_tokens": int(meta.get("output_tokens", 0)),
        "total_tokens": int(meta.get("total_tokens", 0)),
    }
```

Update every caller in `engine/commander.py` to unpack the tuple. The
orchestrator emits `BUDGET_CONSUMED` with the real token counts and a
USD estimate based on a per-model pricing table:

```python
# verbatim — src/atrium/engine/pricing.py (NEW FILE)
"""Per-model token pricing table. Update when providers change pricing."""
from decimal import Decimal

# Prices per 1M tokens, USD. Conservative values; trim quarterly.
PRICING_PER_MILLION: dict[str, tuple[Decimal, Decimal]] = {
    # provider:model              (input,         output)
    "anthropic:claude-sonnet-4-6": (Decimal("3"),  Decimal("15")),
    "anthropic:claude-opus-4-7":   (Decimal("15"), Decimal("75")),
    "openai:gpt-4o-mini":          (Decimal("0.15"), Decimal("0.60")),
    "openai:gpt-4o":               (Decimal("2.50"), Decimal("10")),
    "gemini:gemini-2.5-flash":     (Decimal("0.075"), Decimal("0.30")),
    "gemini:gemini-2.5-pro":       (Decimal("1.25"), Decimal("5")),
}

def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    """Return USD cost estimate. Returns 0 if the model isn't priced yet."""
    pricing = PRICING_PER_MILLION.get(model)
    if not pricing:
        return Decimal("0")
    in_price, out_price = pricing
    return (in_price * input_tokens + out_price * output_tokens) / Decimal("1000000")
```

## 0.10 Modifications to `streaming/events.py` and `core/agent_store.py`

Both currently use sync `sqlite3.connect(..., check_same_thread=False)`.
Replace with `aiosqlite` and a single-writer `asyncio.Lock`. The migration
is mechanical:

- `self._db = sqlite3.connect(...)` → `self._db: aiosqlite.Connection | None = None`
- Add `async def open(self)` that does `await aiosqlite.connect(...)` and
  `await self._db.executescript(_SCHEMA)`.
- Wrap every write with `async with self._write_lock:`.
- The synchronous `replay()` becomes async; callers must `await` it.
  Update all callers in `api/routes/threads.py` and the dashboard
  endpoints.

## 0.11 Modifications to `api/middleware.py`

The `global_error_handler` currently returns `{"error": str(exc), "type": ...}`.
Change to use `ErrorResponse` from `core/errors.py`:

```python
# verbatim
@app.exception_handler(AtriumError)
async def atrium_error_handler(request: Request, exc: AtriumError) -> JSONResponse:
    logger.warning(
        f"AtriumError: {exc.error_code}",
        extra={"error_code": exc.error_code, "path": request.url.path},
    )
    return JSONResponse(
        status_code=exc.http_status,
        content=exc.to_response().model_dump(),
    )

@app.exception_handler(Exception)
async def global_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(f"unhandled exception on {request.url.path}")
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="internal_error",
            message="An internal error occurred. The team has been notified.",
        ).model_dump(),
    )
```

CORS configuration is left as-is (currently allows all origins) — Phase 1
will tighten it once auth is in place.

## 0.12 Acceptance tests

Each test below MUST exist and pass. Test names are exact.

### `tests/test_core/test_thread_store.py`

```
test_create_thread_persists_to_db
test_get_returns_none_for_unknown_id
test_set_status_updates_row
test_set_status_raises_for_unknown_id
test_list_all_returns_in_creation_order_desc
test_delete_removes_row
test_thread_survives_store_reopen   # close + reopen + get → returns thread
```

### `tests/test_core/test_retry.py`

```
test_async_retry_returns_on_first_success
test_async_retry_succeeds_after_two_failures
test_async_retry_raises_after_max_attempts
test_async_retry_does_not_retry_on_non_matching_exception
test_async_retry_respects_backoff_factor   # uses freezegun or mock sleep
```

### `tests/test_engine/test_guardrails_runtime.py`

```
test_max_time_kills_long_running_thread          # 1s limit, agent sleeps 5s
test_max_cost_emits_budget_exceeded_and_aborts
test_max_pivots_already_enforced_still_works     # regression
test_max_agents_check_runs_at_plan_validation    # plan with 26 steps when limit=25
```

### `tests/test_engine/test_plan_validation.py`

```
test_unknown_agent_raises_validation_error
test_duplicate_agent_raises_validation_error
test_missing_dependency_raises_validation_error
test_cycle_in_dependencies_raises_validation_error
test_valid_plan_passes
```

### `tests/test_engine/test_orchestrator.py` (extended)

```
test_thread_persists_across_restart
test_failed_agent_with_default_policy_stops_thread
test_failed_agent_with_continue_policy_runs_downstream
test_real_token_usage_appears_in_budget_consumed
```

## 0.13 Non-goals for Phase 0

The following are NOT in this phase, regardless of how easy they look:

- API authentication. (Phase 1.)
- Postgres backend. (Phase 1.)
- Workspace concept. (Phase 1.)
- Any new feature surface. (No new routes added.)
- Renaming existing event types or tables. (Backward compatibility.)
- Dashboard changes. (Dashboard reads through the same recorder; should
  keep working without modification.)

If during implementation a tempting refactor surfaces (e.g. "while I'm
here let me clean up X"), file it as a follow-up issue and do not do it
in Phase 0.

## 0.14 Definition of done

- [ ] All files in §0.1 created or modified per spec.
- [ ] All acceptance tests in §0.12 present and passing.
- [ ] `pytest` shows the existing test count plus the new tests, all green.
- [ ] `ruff check src/ tests/` clean.
- [ ] Manual smoke test: `python -m atrium.examples.hello_world.app`,
      submit a goal, observe a real BUDGET_CONSUMED with non-zero token
      counts in the SSE stream.
- [ ] Manual smoke test: kill the server mid-thread, restart, GET
      `/api/v1/threads` returns the thread (status RUNNING — Phase 1
      will recover stuck threads).
