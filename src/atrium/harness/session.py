"""Session model, SessionStatus, and persistent SessionStore."""
from __future__ import annotations

import json
import os
import stat
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from atrium.core.errors import ConflictError


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SessionStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# Valid state transitions
_TRANSITIONS: dict[SessionStatus, set[SessionStatus]] = {
    SessionStatus.CREATED: {SessionStatus.RUNNING, SessionStatus.CANCELLED},
    SessionStatus.RUNNING: {
        SessionStatus.PAUSED,
        SessionStatus.COMPLETED,
        SessionStatus.FAILED,
        SessionStatus.CANCELLED,
    },
    SessionStatus.PAUSED: {SessionStatus.RUNNING, SessionStatus.CANCELLED},
    SessionStatus.COMPLETED: set(),
    SessionStatus.FAILED: set(),
    SessionStatus.CANCELLED: set(),
}


class Session(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    workspace_id: str
    title: str = ""
    objective: str = ""
    status: SessionStatus = SessionStatus.CREATED
    runtime: str = ""
    model: str = ""
    container_id: str | None = None
    workspace_path: str = ""
    parent_thread_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)
    last_active_at: datetime = Field(default_factory=_utcnow)

    @property
    def workspace_dir(self) -> Path:
        return Path(self.workspace_path)


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id       TEXT NOT NULL,
    workspace_id     TEXT NOT NULL,
    title            TEXT NOT NULL DEFAULT '',
    objective        TEXT NOT NULL,
    status           TEXT NOT NULL,
    runtime          TEXT NOT NULL,
    model            TEXT NOT NULL,
    container_id     TEXT,
    workspace_path   TEXT NOT NULL,
    parent_thread_id TEXT,
    metadata         TEXT NOT NULL DEFAULT '{}',
    created_at       TEXT NOT NULL,
    last_active_at   TEXT NOT NULL,
    PRIMARY KEY (session_id)
);
CREATE INDEX IF NOT EXISTS idx_sessions_workspace_status ON sessions(workspace_id, status);
CREATE INDEX IF NOT EXISTS idx_sessions_parent_thread ON sessions(parent_thread_id);
CREATE INDEX IF NOT EXISTS idx_sessions_last_active ON sessions(last_active_at);
"""


class SessionStore:
    """SQLite-backed session store following the same pattern as ThreadStore."""

    def __init__(self, db_path: str, sessions_root: str = "/var/atrium/sessions") -> None:
        import aiosqlite
        self._db_path = db_path
        self._sessions_root = sessions_root
        self._db: aiosqlite.Connection | None = None
        import asyncio
        self._lock = asyncio.Lock()

    async def open(self) -> None:
        import aiosqlite
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.executescript(_SCHEMA_SQL)
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    def _workspace_path_for(self, workspace_id: str, session_id: str) -> str:
        return os.path.join(self._sessions_root, workspace_id, session_id)

    async def create(self, session: Session) -> Session:
        """Persist the session and create its workspace directory (mode 0700)."""
        # Set workspace_path if not provided
        if not session.workspace_path:
            session = session.model_copy(update={
                "workspace_path": self._workspace_path_for(
                    session.workspace_id, session.session_id
                )
            })

        # Create workspace directory
        try:
            os.makedirs(session.workspace_path, mode=0o700, exist_ok=True)
        except OSError:
            pass  # best-effort; tests may use tmp dirs

        async with self._lock:
            await self._db.execute(
                "INSERT INTO sessions "
                "(session_id, workspace_id, title, objective, status, runtime, model, "
                "container_id, workspace_path, parent_thread_id, metadata, "
                "created_at, last_active_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    session.session_id,
                    session.workspace_id,
                    session.title,
                    session.objective,
                    session.status.value,
                    session.runtime,
                    session.model,
                    session.container_id,
                    session.workspace_path,
                    session.parent_thread_id,
                    json.dumps(session.metadata),
                    session.created_at.isoformat(),
                    session.last_active_at.isoformat(),
                ),
            )
            await self._db.commit()
        return session

    async def get(self, workspace_id: str, session_id: str) -> Session | None:
        cursor = await self._db.execute(
            "SELECT session_id, workspace_id, title, objective, status, runtime, model, "
            "container_id, workspace_path, parent_thread_id, metadata, created_at, last_active_at "
            "FROM sessions WHERE session_id = ? AND workspace_id = ?",
            (session_id, workspace_id),
        )
        row = await cursor.fetchone()
        return self._row_to_session(row) if row else None

    async def list_by_workspace(
        self, workspace_id: str, status: SessionStatus | None = None
    ) -> list[Session]:
        if status is not None:
            cursor = await self._db.execute(
                "SELECT session_id, workspace_id, title, objective, status, runtime, model, "
                "container_id, workspace_path, parent_thread_id, metadata, created_at, last_active_at "
                "FROM sessions WHERE workspace_id = ? AND status = ?",
                (workspace_id, status.value),
            )
        else:
            cursor = await self._db.execute(
                "SELECT session_id, workspace_id, title, objective, status, runtime, model, "
                "container_id, workspace_path, parent_thread_id, metadata, created_at, last_active_at "
                "FROM sessions WHERE workspace_id = ?",
                (workspace_id,),
            )
        rows = await cursor.fetchall()
        return [self._row_to_session(r) for r in rows]

    async def set_status(
        self, workspace_id: str, session_id: str, new_status: SessionStatus
    ) -> None:
        session = await self.get(workspace_id, session_id)
        if session is None:
            raise KeyError(f"session {session_id!r} not found in workspace {workspace_id!r}")
        allowed = _TRANSITIONS.get(session.status, set())
        if new_status not in allowed:
            raise ConflictError(
                f"Cannot transition session {session_id} from {session.status} to {new_status}"
            )
        async with self._lock:
            await self._db.execute(
                "UPDATE sessions SET status = ? WHERE session_id = ? AND workspace_id = ?",
                (new_status.value, session_id, workspace_id),
            )
            await self._db.commit()

    async def set_container_id(
        self, workspace_id: str, session_id: str, container_id: str | None
    ) -> None:
        async with self._lock:
            await self._db.execute(
                "UPDATE sessions SET container_id = ? WHERE session_id = ? AND workspace_id = ?",
                (container_id, session_id, workspace_id),
            )
            await self._db.commit()

    async def touch(self, workspace_id: str, session_id: str) -> None:
        """Update last_active_at to now."""
        async with self._lock:
            await self._db.execute(
                "UPDATE sessions SET last_active_at = ? WHERE session_id = ? AND workspace_id = ?",
                (_utcnow().isoformat(), session_id, workspace_id),
            )
            await self._db.commit()

    async def delete(self, workspace_id: str, session_id: str) -> None:
        session = await self.get(workspace_id, session_id)
        async with self._lock:
            await self._db.execute(
                "DELETE FROM sessions WHERE session_id = ? AND workspace_id = ?",
                (session_id, workspace_id),
            )
            await self._db.commit()
        # Remove workspace directory
        if session and session.workspace_path:
            import shutil
            try:
                shutil.rmtree(session.workspace_path, ignore_errors=True)
            except OSError:
                pass

    @staticmethod
    def _row_to_session(row: tuple) -> Session:
        (
            session_id, workspace_id, title, objective, status,
            runtime, model, container_id, workspace_path,
            parent_thread_id, metadata, created_at, last_active_at,
        ) = row
        return Session(
            session_id=session_id,
            workspace_id=workspace_id,
            title=title or "",
            objective=objective,
            status=SessionStatus(status),
            runtime=runtime or "",
            model=model or "",
            container_id=container_id,
            workspace_path=workspace_path or "",
            parent_thread_id=parent_thread_id,
            metadata=json.loads(metadata) if metadata else {},
            created_at=datetime.fromisoformat(created_at),
            last_active_at=datetime.fromisoformat(last_active_at),
        )
