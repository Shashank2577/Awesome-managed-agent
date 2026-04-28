# PHASE 1 — Multi-Tenancy and Production Foundations

**Goal:** workspaces, API-key auth, Postgres backend, dependency injection.
After this phase, multiple internal teams (CIVI, PLC Direct, Master CRM)
can share one Atrium deployment without seeing each other's data.

**Estimated effort:** 8 days (1 engineer).

**Depends on:** Phase 0.

**Unblocks:** Phases 2–6.

## 1.1 Files to create or modify

| Action | Path | What |
|--------|------|------|
| CREATE | `src/atrium/core/auth.py` | `Workspace`, `ApiKey`, key hashing. |
| CREATE | `src/atrium/core/workspace_store.py` | Persistent workspace + key store. |
| CREATE | `src/atrium/api/auth.py` | `require_workspace`, `require_admin` deps. |
| CREATE | `src/atrium/api/state.py` | `AppState` dependency container. |
| CREATE | `src/atrium/api/routes/workspaces.py` | Admin workspace endpoints. |
| CREATE | `src/atrium/core/storage/__init__.py` | Storage abstraction. |
| CREATE | `src/atrium/core/storage/sqlite.py` | SQLite backend. |
| CREATE | `src/atrium/core/storage/postgres.py` | Postgres backend (asyncpg). |
| CREATE | `src/atrium/core/config.py` | `AtriumConfig` env-var loader. |
| CREATE | `migrations/env.py` | Alembic env. |
| CREATE | `migrations/versions/0001_initial.py` | First migration. |
| MODIFY | `src/atrium/api/app.py` | Replace module-level state with AppState. |
| MODIFY | `src/atrium/core/registry.py` | Workspace-scoped. |
| MODIFY | `src/atrium/core/agent_store.py` | Workspace-scoped. |
| MODIFY | `src/atrium/core/thread_store.py` | Workspace-scoped. |
| MODIFY | `src/atrium/streaming/events.py` | Workspace-scoped. |
| MODIFY | `src/atrium/engine/orchestrator.py` | Workspace-aware. |
| MODIFY | every route file | Add `Depends(require_workspace)`. |
| CREATE | `src/atrium/core/sessions_store.py` | New `Session` table (used in Phase 2). |
| MODIFY | `pyproject.toml` | Add `asyncpg`, `alembic`, `sqlalchemy[asyncio]`. |
| CREATE | `tests/test_api/test_auth.py` | New tests. |
| CREATE | `tests/test_core/test_workspace_isolation.py` | New tests. |
| CREATE | `tests/test_core/test_storage.py` | New tests. |

## 1.2 New module: `core/auth.py`

```python
# verbatim
"""Workspace and API key models + hashing helpers."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WorkspaceQuota(BaseModel):
    max_concurrent_sessions: int = 10
    max_concurrent_threads: int = 50
    max_monthly_spend_usd: float = 1000.0
    max_agents_registered: int = 200


class Workspace(BaseModel):
    workspace_id: str = Field(default_factory=lambda: f"ws_{uuid4().hex}")
    name: str
    quota: WorkspaceQuota = Field(default_factory=WorkspaceQuota)
    created_at: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApiKeyKind(str, Enum):
    WORKSPACE = "workspace"  # full access to one workspace
    READ_ONLY = "read_only"  # read-only access to one workspace
    ADMIN = "admin"          # cross-workspace admin access


class ApiKey(BaseModel):
    api_key_id: str = Field(default_factory=lambda: f"ak_{uuid4().hex[:12]}")
    workspace_id: str | None  # None for ADMIN keys
    kind: ApiKeyKind = ApiKeyKind.WORKSPACE
    hash: str                 # sha256 hex of the secret
    name: str = ""            # human-readable label
    created_at: datetime = Field(default_factory=_utcnow)
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


def generate_secret() -> str:
    """Generate a new API key secret. 64 hex chars (256 bits)."""
    return secrets.token_hex(32)


def hash_secret(secret: str) -> str:
    """Hash a secret for storage. Constant-time-comparable via the hash itself."""
    return hashlib.sha256(secret.encode()).hexdigest()


def verify_secret(secret: str, expected_hash: str) -> bool:
    """Constant-time comparison of a secret against its stored hash."""
    return secrets.compare_digest(hash_secret(secret), expected_hash)
```

## 1.3 New module: `core/workspace_store.py`

```python
# template — full schema and methods
"""Persistent workspace and API key store. Storage-backend agnostic."""
from __future__ import annotations

from atrium.core.auth import ApiKey, ApiKeyKind, Workspace, WorkspaceQuota
from atrium.core.storage import Storage


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS workspaces (
    workspace_id TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    quota_json   TEXT NOT NULL,
    metadata     TEXT NOT NULL,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS api_keys (
    api_key_id   TEXT PRIMARY KEY,
    workspace_id TEXT,
    kind         TEXT NOT NULL,
    hash         TEXT NOT NULL UNIQUE,
    name         TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    last_used_at TEXT,
    revoked_at   TEXT,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_workspace ON api_keys(workspace_id);
"""


class WorkspaceStore:
    """Workspaces and API keys."""

    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    async def init_schema(self) -> None: ...
    async def create_workspace(self, name: str, quota: WorkspaceQuota | None = None) -> Workspace: ...
    async def get_workspace(self, workspace_id: str) -> Workspace | None: ...
    async def list_workspaces(self) -> list[Workspace]: ...
    async def update_quota(self, workspace_id: str, quota: WorkspaceQuota) -> None: ...
    async def delete_workspace(self, workspace_id: str) -> None: ...

    async def issue_key(
        self, workspace_id: str | None, kind: ApiKeyKind, name: str = ""
    ) -> tuple[ApiKey, str]:
        """Returns (record, plaintext_secret). The secret is shown ONCE; the
        store only persists the hash."""
        ...

    async def lookup_by_secret(self, secret: str) -> ApiKey | None:
        """Hash the secret, look up the record. Updates last_used_at on hit."""
        ...

    async def revoke_key(self, api_key_id: str) -> None: ...
    async def list_keys(self, workspace_id: str | None) -> list[ApiKey]: ...
```

Implementation detail: `lookup_by_secret` MUST hash the input first and
compare hashes — never compare plaintext to plaintext.

## 1.4 Storage abstraction

```python
# verbatim — src/atrium/core/storage/__init__.py
"""Storage backend abstraction. Concrete impls: SQLiteStorage, PostgresStorage."""
from __future__ import annotations

from typing import Any, Protocol


class Storage(Protocol):
    """Minimal async DB interface used by all stores."""

    async def execute(self, sql: str, params: tuple = ()) -> None: ...
    async def execute_many(self, sql: str, params_list: list[tuple]) -> None: ...
    async def fetch_one(self, sql: str, params: tuple = ()) -> tuple | None: ...
    async def fetch_all(self, sql: str, params: tuple = ()) -> list[tuple]: ...
    async def transaction(self) -> "TransactionContextManager": ...

    async def init(self) -> None: ...
    async def close(self) -> None: ...


def open_storage(db_url: str) -> Storage:
    """Factory that picks SQLite or Postgres based on URL scheme."""
    if db_url.startswith("sqlite:"):
        from atrium.core.storage.sqlite import SQLiteStorage
        return SQLiteStorage(db_url)
    if db_url.startswith("postgresql"):
        from atrium.core.storage.postgres import PostgresStorage
        return PostgresStorage(db_url)
    raise ValueError(f"unsupported db_url: {db_url}")
```

The two implementations:

- `SQLiteStorage` wraps `aiosqlite.Connection` and serializes writes
  through `asyncio.Lock`. Schema differences vs Postgres: TEXT instead
  of TIMESTAMP, no native JSON, no `RETURNING *`.
- `PostgresStorage` wraps `asyncpg.Pool`. Native JSON via JSONB. Native
  TIMESTAMPTZ. Concurrent writes; no app-level lock needed.

Both implementations expose `execute`, `fetch_one`, `fetch_all`,
`execute_many`, `transaction`. Param style is `?` for SQLite, `$1, $2`
for Postgres. The stores higher up MUST NOT use `?` or `$1` directly;
instead they use a placeholder `:name` and the storage layer rewrites:

```python
# Stores write:
"INSERT INTO foo (a, b) VALUES (:a, :b)"
# Storage layer rewrites to ? or $1 depending on backend.
```

This costs a tiny bit of complexity but lets stores be backend-agnostic.

## 1.5 New module: `core/config.py`

```python
# verbatim
"""Atrium runtime configuration. Read from environment, cached on first access."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal


@dataclass(frozen=True)
class AtriumConfig:
    db_url: str
    sandbox_backend: Literal["docker", "kubernetes", "in_memory"]
    sandbox_image_registry: str
    sessions_root: str
    artifact_root: str
    mcp_socket_path: str
    max_concurrent_sessions: int
    log_level: str
    admin_api_key_hash: str
    webhook_signing_secret: str
    cors_allowed_origins: tuple[str, ...]


@lru_cache(maxsize=1)
def get_config() -> AtriumConfig:
    return AtriumConfig(
        db_url=os.getenv("ATRIUM_DB_URL", "sqlite:///atrium.sqlite"),
        sandbox_backend=os.getenv("ATRIUM_SANDBOX_BACKEND", "in_memory"),  # safe default
        sandbox_image_registry=os.getenv("ATRIUM_SANDBOX_REGISTRY", "atrium"),
        sessions_root=os.getenv("ATRIUM_SESSIONS_ROOT", "/var/atrium/sessions"),
        artifact_root=os.getenv("ATRIUM_ARTIFACT_ROOT", "/var/atrium/artifacts"),
        mcp_socket_path=os.getenv("ATRIUM_MCP_SOCKET", "/run/atrium/mcp.sock"),
        max_concurrent_sessions=int(os.getenv("ATRIUM_MAX_CONCURRENT_SESSIONS", "20")),
        log_level=os.getenv("ATRIUM_LOG_LEVEL", "INFO"),
        admin_api_key_hash=os.getenv("ATRIUM_ADMIN_KEY_HASH", ""),
        webhook_signing_secret=os.getenv("ATRIUM_WEBHOOK_SECRET", ""),
        cors_allowed_origins=tuple(
            o.strip() for o in os.getenv("ATRIUM_CORS_ORIGINS", "*").split(",") if o.strip()
        ),
    )
```

## 1.6 AppState dependency container

Replaces module-level globals in `api/app.py`.

```python
# verbatim — src/atrium/api/state.py
"""Per-app dependency container. Holds storage, stores, recorder, orchestrator."""
from __future__ import annotations

from dataclasses import dataclass

from atrium.core.config import AtriumConfig
from atrium.core.storage import Storage
from atrium.core.workspace_store import WorkspaceStore
from atrium.core.thread_store import ThreadStore
from atrium.core.agent_store import AgentStore
from atrium.streaming.events import EventRecorder


@dataclass
class AppState:
    config: AtriumConfig
    storage: Storage
    workspace_store: WorkspaceStore
    thread_store: ThreadStore
    agent_store: AgentStore
    recorder: EventRecorder
    # registries are workspace-scoped, indexed by workspace_id
    # (lazy-loaded on first access for that workspace)
    _registries: dict[str, "AgentRegistry"] = None  # filled in __post_init__

    def get_registry(self, workspace_id: str) -> "AgentRegistry":
        """Return the per-workspace agent registry, creating if needed."""
        ...

    def get_orchestrator(self, workspace_id: str) -> "ThreadOrchestrator":
        """Return the per-workspace orchestrator. Cached per workspace."""
        ...

    async def shutdown(self) -> None:
        """Close all open resources."""
        ...


def get_app_state(request) -> AppState:
    """FastAPI dependency that returns the AppState attached to the app."""
    return request.app.state.atrium
```

`api/app.py:create_app()` constructs `AppState`, runs `await
storage.init()` and `await *_store.init_schema()` in startup hooks, and
attaches `AppState` to `app.state.atrium`.

All routes that previously read from `_registry / _recorder /
_orchestrator` now use `Depends(get_app_state)`.

## 1.7 Auth middleware

```python
# verbatim — src/atrium/api/auth.py
"""API key authentication for FastAPI dependencies."""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request

from atrium.api.state import AppState, get_app_state
from atrium.core.auth import ApiKey, ApiKeyKind, Workspace
from atrium.core.errors import NotFoundError


async def require_api_key(
    request: Request,
    state: AppState = Depends(get_app_state),
    x_atrium_key: str | None = Header(default=None, alias="X-Atrium-Key"),
) -> ApiKey:
    """Resolve an ApiKey from X-Atrium-Key. 401 if missing or invalid."""
    if not x_atrium_key:
        raise HTTPException(401, detail="missing X-Atrium-Key header")
    key = await state.workspace_store.lookup_by_secret(x_atrium_key)
    if key is None or key.revoked_at is not None:
        raise HTTPException(401, detail="invalid api key")
    request.state.api_key = key
    return key


async def require_workspace(
    state: AppState = Depends(get_app_state),
    api_key: ApiKey = Depends(require_api_key),
) -> Workspace:
    """For routes scoped to a single workspace. 401 if the key is admin-only."""
    if api_key.kind == ApiKeyKind.ADMIN:
        raise HTTPException(401, detail="admin keys cannot access workspace routes")
    if api_key.workspace_id is None:
        raise HTTPException(401, detail="key is not bound to a workspace")
    ws = await state.workspace_store.get_workspace(api_key.workspace_id)
    if ws is None:
        raise HTTPException(401, detail="workspace not found")
    return ws


async def require_admin(api_key: ApiKey = Depends(require_api_key)) -> ApiKey:
    """For /api/v1/admin/* routes."""
    if api_key.kind != ApiKeyKind.ADMIN:
        raise HTTPException(403, detail="admin access required")
    return api_key
```

## 1.8 Workspace-scoping the existing stores

Every existing store gets `workspace_id` plumbed through. Concrete
changes:

### `core/registry.py`

`AgentRegistry` becomes per-workspace. The class itself stays the same;
it's just no longer a singleton. `AppState.get_registry(workspace_id)`
constructs and caches one per workspace.

### `core/agent_store.py`

The `agent_configs` table gets a `workspace_id` column added in
migration 0001. Every method takes `workspace_id` as the first
positional argument.

### `core/thread_store.py`

The `threads` table gets a `workspace_id` column. Every method takes
`workspace_id`. `list_all` becomes `list_by_workspace(workspace_id)`.

### `streaming/events.py`

The `events` table gets a `workspace_id` column. `EventRecorder.emit`
gains a `workspace_id` parameter (or reads it from the thread/session
the event belongs to). `replay()`, `subscribe()`, and
`list_thread_ids()` all gain `workspace_id`.

The orchestrator passes `workspace_id` whenever it emits.

## 1.9 New table: `sessions` (used in Phase 2)

Schema is added in migration 0001 even though Phase 1 doesn't write to
it. This avoids two migrations close together.

```sql
CREATE TABLE sessions (
    session_id        TEXT PRIMARY KEY,
    workspace_id      TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    title             TEXT NOT NULL DEFAULT '',
    objective         TEXT NOT NULL,
    status            TEXT NOT NULL,
    runtime           TEXT NOT NULL,
    model             TEXT NOT NULL,
    container_id      TEXT,
    workspace_path    TEXT NOT NULL,
    parent_thread_id  TEXT,
    metadata          TEXT NOT NULL DEFAULT '{}',
    created_at        TEXT NOT NULL,
    last_active_at    TEXT NOT NULL
);

CREATE INDEX idx_sessions_workspace_status ON sessions(workspace_id, status);
CREATE INDEX idx_sessions_parent_thread ON sessions(parent_thread_id);
CREATE INDEX idx_sessions_last_active ON sessions(last_active_at);
```

## 1.10 New routes: workspace admin

Mounted at `/api/v1/admin/`, all guarded by `Depends(require_admin)`.

| Method | Path | Body | Returns |
|--------|------|------|---------|
| POST   | `/api/v1/admin/workspaces` | `{name, quota?}` | `Workspace` |
| GET    | `/api/v1/admin/workspaces` | — | `{workspaces: [Workspace]}` |
| GET    | `/api/v1/admin/workspaces/{id}` | — | `Workspace` |
| PATCH  | `/api/v1/admin/workspaces/{id}/quota` | `WorkspaceQuota` | `Workspace` |
| DELETE | `/api/v1/admin/workspaces/{id}` | — | 204 |
| POST   | `/api/v1/admin/workspaces/{id}/keys` | `{kind, name?}` | `{api_key: ApiKey, secret: "...shown_once..."}` |
| GET    | `/api/v1/admin/workspaces/{id}/keys` | — | `{keys: [ApiKey]}` |
| DELETE | `/api/v1/admin/keys/{api_key_id}` | — | 204 |

The `secret` is returned ONCE on creation and never again. The DB only
stores the hash. This must be made obvious in the response shape and
documented in the OpenAPI description.

## 1.11 Existing routes: workspace scoping

Every existing route under `/api/v1/threads`, `/api/v1/agents`, and
`/api/v1/agents/create` adds `Depends(require_workspace)`. The
workspace's `workspace_id` is passed to the store call.

Cross-workspace reads MUST return 404 (not 403). Test:
```
ws_a creates thread T.
ws_b's key calls GET /api/v1/threads/{T} → 404.
```

## 1.12 Migration: `migrations/versions/0001_initial.py`

Captures the full schema as of end-of-Phase-1:

- `workspaces`
- `api_keys`
- `threads` (with workspace_id)
- `events` (with workspace_id)
- `agent_configs` (with workspace_id)
- `sessions` (defined in §1.9, unused yet)
- All indexes per CONTRACTS.md §6.

Migration runs against both SQLite and Postgres; Alembic detects from
the connection URL. CI runs the migration on a clean SQLite, runs the
test suite, then runs the same migration on Postgres in a Docker
sidecar container, and runs the same test suite again.

## 1.13 Acceptance tests

### `tests/test_api/test_auth.py`

```
test_request_without_key_returns_401
test_request_with_invalid_key_returns_401
test_request_with_valid_workspace_key_resolves_workspace
test_admin_key_can_call_admin_routes
test_workspace_key_cannot_call_admin_routes
test_revoked_key_returns_401
test_last_used_at_updates_on_successful_request
```

### `tests/test_core/test_workspace_isolation.py`

```
test_thread_created_in_ws_a_not_visible_to_ws_b           # 404
test_agent_registered_in_ws_a_not_visible_to_ws_b
test_events_for_ws_a_thread_not_streamed_to_ws_b
test_admin_can_list_workspaces_and_keys
test_workspace_b_cannot_create_thread_using_ws_a_agent_name
test_orchestrator_uses_ws_b_registry_when_called_with_ws_b_id
```

### `tests/test_core/test_storage.py`

```
test_sqlite_storage_executes_and_fetches
test_sqlite_storage_serializes_concurrent_writes
test_postgres_storage_executes_and_fetches  # gated behind ATRIUM_TEST_POSTGRES env
test_storage_factory_picks_sqlite_for_sqlite_url
test_storage_factory_picks_postgres_for_postgres_url
test_storage_factory_raises_for_unknown_scheme
```

### `tests/test_api/test_workspace_routes.py`

```
test_create_workspace_returns_workspace_with_quota_defaults
test_issue_key_returns_secret_only_once
test_list_keys_does_not_return_secrets
test_revoke_key_blocks_subsequent_requests
test_quota_update_persists
```

## 1.14 Non-goals for Phase 1

- Sandboxes, sessions, harness — Phase 2.
- Webhooks — Phase 5.
- Widgets — Phase 5.
- OAuth / SSO — out of scope for v1.
- Per-resource ACLs (within a workspace) — out of scope for v1; all
  workspace keys have full workspace access.
- Rate limiting — out of scope for v1; deploy with API gateway in front
  if needed.

## 1.15 Definition of done

- [ ] All files in §1.1 created or modified per spec.
- [ ] All acceptance tests in §1.13 present and passing on SQLite.
- [ ] CI runs the same tests against Postgres in a sidecar container,
      green.
- [ ] Manual smoke test: create two workspaces via admin, issue keys,
      run threads in each, confirm isolation.
- [ ] `ruff check` and `mypy --strict` clean on `src/atrium/core/auth.py`,
      `src/atrium/api/auth.py`, `src/atrium/core/storage/`.
- [ ] OpenAPI spec at `/openapi.json` shows all new routes with
      `X-Atrium-Key` security scheme.
- [ ] `migrations/versions/0001_initial.py` runs cleanly against both
      backends in CI.
