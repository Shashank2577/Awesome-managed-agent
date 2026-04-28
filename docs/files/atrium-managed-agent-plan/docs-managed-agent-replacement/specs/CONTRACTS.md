# CONTRACTS — Cross-Cutting Specifications

Shared types, error model, naming conventions, and testing patterns that
apply to every phase. Read this once before any phase spec. Every phase
spec assumes you've read this.

## 1. Identifier conventions

All identifiers are UUID v4 strings unless noted otherwise. Identifiers
are immutable once issued. A `*_id` field is always a string.

| Entity | ID prefix in UI | Storage |
|--------|-----------------|---------|
| Workspace | `ws_` | UUID v4, stored as TEXT/UUID |
| API Key | `ak_` | hex(32) random, stored hashed (sha256) |
| Thread | none | UUID v4 |
| Session | none | UUID v4 |
| Plan | none | UUID v4 |
| Event | none | UUID v4 |
| Artifact | `art_` | UUID v4 |
| Webhook | `wh_` | UUID v4 |
| Agent | `{workspace_id}/{name}` is the storage key; `{name}` is the public identifier |

The prefixes (`ws_`, `ak_`, `art_`, `wh_`) MUST be added by the API layer
when serializing to clients, MUST be stripped before storage. This is so
operators can recognize an ID's type at a glance in logs and dashboards.

## 2. Time conventions

All timestamps:

- Stored as UTC.
- Serialized as ISO-8601 with the `Z` suffix.
- Generated via `datetime.now(timezone.utc)` — never `datetime.utcnow()`,
  which is naive.

Use the existing helper at `src/atrium/core/models.py:_utcnow()` and
add a copy of the same function to any new module that needs it. Do not
import private helpers across modules.

## 3. Workspace scoping (introduced in Phase 1)

After Phase 1, every persisted row in every table MUST have a
`workspace_id` column. Every API endpoint except `/api/v1/health` and
`/api/v1/version` MUST resolve a workspace from the API key and reject
requests for resources outside that workspace with HTTP 404 (not 403 —
hiding existence is more useful for tenancy).

The workspace is injected into the request via FastAPI dependency
injection. Phase 1 introduces:

```python
# src/atrium/api/auth.py
async def require_workspace(request: Request) -> Workspace:
    """Resolve the workspace from X-Atrium-Key. Raises 401 if missing/invalid."""
    ...
```

All routes added in Phase 1 onwards MUST include this dependency:

```python
@router.get("/things")
async def list_things(workspace: Workspace = Depends(require_workspace)):
    ...
```

## 4. Error model

The single error response shape used across all routes:

```python
class ErrorResponse(BaseModel):
    error: str          # short machine-readable code, e.g. "session_not_found"
    message: str        # human-readable description
    details: dict | None = None
```

HTTP status codes:

| Code | When |
|------|------|
| 400 | Validation failure on request body |
| 401 | Missing or invalid API key |
| 403 | Authenticated but not authorized for this action (admin endpoints) |
| 404 | Resource not in this workspace, or genuinely doesn't exist |
| 409 | State conflict (e.g. resuming a session that's still RUNNING) |
| 422 | Semantically valid but business-logic-rejected (FastAPI default for Pydantic errors) |
| 429 | Rate limited |
| 500 | Internal error — never leak stack trace to client |
| 503 | Sandbox capacity exhausted, or downstream provider unavailable |

The existing `setup_middleware` in `src/atrium/api/middleware.py` has a
catch-all 500 handler. Phase 0 modifies it to return the `ErrorResponse`
shape and to log the stack trace (not return it).

## 5. Event taxonomy (cross-phase)

Events are append-only, immutable, monotonically sequenced per scope.

A scope is either a `thread_id` or a `session_id`. Events for a thread
share a sequence numbering; events for a session share a separate
sequence numbering. A session that's spawned by a thread step has BOTH
its own session events AND emits a small set of bridging events into
the parent thread's stream.

### Existing event types (preserved as-is)

```
THREAD_CREATED        THREAD_PLANNING       THREAD_RUNNING
THREAD_PAUSED         THREAD_COMPLETED      THREAD_FAILED
THREAD_CANCELLED
PLAN_CREATED          PLAN_APPROVED         PLAN_REJECTED
PLAN_EXECUTION_STARTED                      PLAN_COMPLETED
PIVOT_REQUESTED       PIVOT_APPLIED
AGENT_HIRED           AGENT_RUNNING         AGENT_COMPLETED
AGENT_FAILED          AGENT_MESSAGE
COMMANDER_MESSAGE
BUDGET_RESERVED       BUDGET_CONSUMED       BUDGET_EXCEEDED
HUMAN_APPROVAL_REQUESTED                    EVIDENCE_PUBLISHED
```

### New event types added by phase

| Phase | Event types |
|-------|-------------|
| 2 | `SESSION_CREATED`, `SESSION_RUNNING`, `SESSION_PAUSED`, `SESSION_RESUMED`, `SESSION_COMPLETED`, `SESSION_FAILED`, `SESSION_CANCELLED`, `ARTIFACT_CREATED`, `ARTIFACT_UPDATED`, `ARTIFACT_DELETED`, `SANDBOX_STARTED`, `SANDBOX_STOPPED`, `SANDBOX_KILLED` |
| 3 | `HARNESS_TOOL_CALLED`, `HARNESS_TOOL_RESULT`, `HARNESS_MESSAGE`, `HARNESS_THINKING` |
| 4 | `HARNESS_MCP_CALLED`, `HARNESS_MCP_REJECTED` |
| 5 | `HARNESS_COMPACTION`, `HARNESS_CHECKPOINT`, `WEBHOOK_DELIVERED`, `WEBHOOK_FAILED` |

### Payload schemas

Every payload is a JSON object. Schemas are defined in the spec for the
phase that introduces the event. Once defined, a payload schema is
versioned only by adding optional fields — never by removing or
renaming fields.

The full payload schema reference for new events is in the
corresponding phase spec. For example, `HARNESS_TOOL_CALLED`'s payload
is defined in `PHASE-3-real-runtimes.md` § "Bridge translation table".

## 6. Database conventions

### Phase 0 (SQLite only)

All new tables added in Phase 0 use SQLite. Connection: a single
`sqlite3.Connection` opened with `check_same_thread=False`. All writes
go through a single asyncio task that owns the connection — no shared
connection across tasks. This replaces the current pattern in
`src/atrium/streaming/events.py` and `src/atrium/core/agent_store.py`.

### Phase 1 onwards (Postgres optional)

Phase 1 introduces a `Storage` abstraction that has both a SQLite and
a Postgres implementation. Selection via `ATRIUM_DB_URL`:
- `sqlite:///path/to/db.sqlite` → SQLite (default, dev)
- `postgresql+asyncpg://user:pw@host/db` → Postgres

All migrations are managed by Alembic from Phase 1 onward. Migration
files live in `migrations/versions/`.

### Naming conventions

- Tables: `snake_case`, plural (`events`, `threads`, `sessions`).
- Columns: `snake_case`. Foreign keys end in `_id`. Timestamps use
  `_at` (`created_at`, `last_active_at`).
- Indexes: `idx_<table>_<columns_with_underscores>`.
- The `id` column on every table is named after the entity:
  `event_id`, `thread_id`, etc. Never just `id`.

### Standard columns

Every table has these columns:

```sql
{entity}_id      TEXT PRIMARY KEY
created_at       TEXT NOT NULL  -- ISO-8601 UTC
```

After Phase 1, every table additionally has:

```sql
workspace_id     TEXT NOT NULL
```

with an index on `workspace_id` and a foreign key to `workspaces`.

## 7. Async conventions

- All I/O is async. There is no `requests`-style sync HTTP. All HTTP
  calls go through `httpx.AsyncClient`.
- Long-running tasks are `asyncio.create_task` and stored on a
  per-scope `set` so the orchestrator can cancel them on shutdown.
- Subprocess management uses `asyncio.create_subprocess_exec`. Never
  `subprocess.Popen`.
- File I/O for small files (config, manifests) uses sync `open()` —
  it's not a hot path. File I/O for artifacts uses `aiofiles`
  (introduced in Phase 2).

## 8. Logging conventions

- All log lines are JSON, single line per record.
- Levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`. No `CRITICAL`.
- Required fields on every log line: `ts`, `level`, `msg`, `module`.
- Optional but conventional: `workspace_id`, `thread_id`, `session_id`,
  `event_id` whenever available.
- No PII or API keys ever appear in logs. The auth module logs the
  hashed key prefix only.
- Use the existing `print(..., flush=True)` pattern only inside
  Docker entrypoints. Everywhere else uses `logging.getLogger(__name__)`.

Phase 0 introduces a structured logging helper at
`src/atrium/core/logging.py` that all later phases use.

## 9. Testing conventions

- Tests live in `tests/test_<package>/test_<module>.py`.
- Test functions are async (the project already uses `asyncio_mode=auto`).
- Unit tests MUST NOT make real HTTP calls. Mock with `pytest-httpx`.
- Unit tests MUST NOT spin up real Docker containers. The sandbox
  runner has an `InMemorySandboxRunner` for tests, introduced in Phase 2.
- Integration tests that DO use Docker live in `tests/integration/` and
  are gated behind `pytest -m integration`. They run in CI but not in
  the default `pytest` invocation.
- Every public function added by a spec MUST have at least one unit
  test. Tests are listed by name in each phase spec under "Acceptance
  tests".

### Standard fixtures

Phase 0 introduces these fixtures in `tests/conftest.py`:

```python
@pytest.fixture
def temp_db_path(tmp_path) -> str:
    return str(tmp_path / "test.sqlite")

@pytest.fixture
async def recorder(temp_db_path):
    return EventRecorder(db_path=temp_db_path)

@pytest.fixture
async def registry():
    return AgentRegistry()
```

Phase 1 adds:

```python
@pytest.fixture
async def workspace(workspace_store):
    return await workspace_store.create(name="test-workspace")

@pytest.fixture
async def api_key(workspace, workspace_store):
    return await workspace_store.issue_key(workspace.workspace_id)
```

Phase 2 adds:

```python
@pytest.fixture
async def in_memory_sandbox():
    return InMemorySandboxRunner()
```

## 10. Configuration conventions

All configuration is read from environment variables, parsed once at
startup into a frozen dataclass. New configuration in Phase 1+:

```python
# src/atrium/core/config.py
@dataclass(frozen=True)
class AtriumConfig:
    db_url: str
    sandbox_backend: Literal["docker", "kubernetes", "in_memory"]
    sandbox_image_registry: str
    sessions_root: str          # /var/atrium/sessions on host
    artifact_root: str          # /var/atrium/artifacts on host (or s3://...)
    mcp_socket_path: str        # /run/atrium/mcp.sock
    max_concurrent_sessions: int
    log_level: str
    # secrets
    admin_api_key: str          # for /api/v1/admin/* endpoints
    webhook_signing_secret: str
```

Each spec lists which env vars its phase introduces. Defaults are set
inside the dataclass; environment variables override.

## 11. Versioning and stability

- API routes use `/api/v1/`. Breaking changes go to `/api/v2/`. Until
  Phase 6, all routes are pre-1.0 and may change without notice — but
  document changes in `CHANGELOG.md`.
- Event types and payload field names are NEVER renamed once shipped.
  New fields are always optional.
- Database migrations are forward-only. Rollback is by restoring from
  backup, not by running a down-migration.

## 12. Naming the harness layer publicly

In documentation, dashboards, API responses, and external comms, refer
to harness sessions as **"sessions"** and to the long-running container
as the **"sandbox"**. Never "harness" — that's an internal term for the
package and the integration layer.

Acceptable: "Create a session", "Pause this session", "View the
sandbox logs".

Avoid: "Create a harness", "Spawn a harness agent".

The internal Python class is still `HarnessAgent` because that's what
distinguishes it from `HTTPAgent` in the registry.

## 13. Spec compliance checklist

For every phase, the implementer MUST be able to answer "yes" to all
of these before declaring the phase complete:

- [ ] Every file listed in "Files to create/modify" exists with the
      content shown or as specified.
- [ ] Every function, class, and method signature matches the spec
      exactly.
- [ ] Every new database table matches the schema shown.
- [ ] Every new API route is reachable and returns the schema shown
      for the success case.
- [ ] Every new event type is emitted at the points described and
      its payload matches the schema shown.
- [ ] Every acceptance test in the spec is present in the test suite
      and passing.
- [ ] No new public functions or classes exist that aren't in the spec.
- [ ] `ruff check` and `mypy` are clean on the new code.

If any answer is "no", the phase is not done. Fix or remove the
deviation.
