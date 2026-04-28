"""Persistent artifact index. Tracks files produced by sandbox sessions."""
from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import aiosqlite


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id  TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    session_id   TEXT NOT NULL,
    path         TEXT NOT NULL,
    size_bytes   INTEGER NOT NULL,
    sha256       TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
    created_at   TEXT NOT NULL,
    UNIQUE(session_id, path)
);
CREATE INDEX IF NOT EXISTS idx_artifacts_session   ON artifacts(session_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_workspace ON artifacts(workspace_id);
"""


@dataclass
class Artifact:
    artifact_id: str
    workspace_id: str
    session_id: str
    path: str           # relative to /workspace
    size_bytes: int
    sha256: str
    content_type: str
    created_at: datetime


def _sha256_file(file_path: str) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class ArtifactStore:
    """SQLite-backed artifact store."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def open(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.executescript(_SCHEMA_SQL)
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def index_file(
        self,
        workspace_id: str,
        session_id: str,
        workspace_dir: Path,
        relative_path: str,
    ) -> Artifact:
        """Hash and insert (or replace) a file artifact row."""
        abs_path = workspace_dir / relative_path
        size = abs_path.stat().st_size
        sha = _sha256_file(str(abs_path))
        content_type = mimetypes.guess_type(str(abs_path))[0] or "application/octet-stream"
        now = _utcnow()

        # Check if exists (for UPSERT)
        existing = await self.get_by_path(workspace_id, session_id, relative_path)
        if existing:
            artifact_id = existing.artifact_id
        else:
            artifact_id = str(uuid4())

        async with self._lock:
            await self._db.execute(
                "INSERT OR REPLACE INTO artifacts "
                "(artifact_id, workspace_id, session_id, path, size_bytes, sha256, content_type, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (artifact_id, workspace_id, session_id, relative_path,
                 size, sha, content_type,
                 existing.created_at.isoformat() if existing else now),
            )
            await self._db.commit()

        return Artifact(
            artifact_id=artifact_id,
            workspace_id=workspace_id,
            session_id=session_id,
            path=relative_path,
            size_bytes=size,
            sha256=sha,
            content_type=content_type,
            created_at=datetime.fromisoformat(existing.created_at.isoformat() if existing else now),
        )

    async def index_workspace(
        self,
        workspace_id: str,
        session_id: str,
        workspace_dir: Path,
        prioritize_files: list[str] | None = None,
    ) -> list[Artifact]:
        """Walk workspace dir and index all non-hidden files."""
        artifacts = []
        skip_dirs = {".atrium"}
        for root, dirs, files in os.walk(workspace_dir):
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
            for fname in files:
                if fname.startswith("."):
                    continue
                abs_path = Path(root) / fname
                rel = str(abs_path.relative_to(workspace_dir))
                try:
                    a = await self.index_file(workspace_id, session_id, workspace_dir, rel)
                    artifacts.append(a)
                except OSError:
                    pass
        return artifacts

    async def get(self, artifact_id: str) -> Artifact | None:
        cursor = await self._db.execute(
            "SELECT artifact_id, workspace_id, session_id, path, size_bytes, sha256, content_type, created_at "
            "FROM artifacts WHERE artifact_id = ?",
            (artifact_id,),
        )
        row = await cursor.fetchone()
        return self._row_to_artifact(row) if row else None

    async def get_by_path(
        self, workspace_id: str, session_id: str, path: str
    ) -> Artifact | None:
        cursor = await self._db.execute(
            "SELECT artifact_id, workspace_id, session_id, path, size_bytes, sha256, content_type, created_at "
            "FROM artifacts WHERE session_id = ? AND path = ?",
            (session_id, path),
        )
        row = await cursor.fetchone()
        return self._row_to_artifact(row) if row else None

    async def list_for_session(self, session_id: str) -> list[Artifact]:
        cursor = await self._db.execute(
            "SELECT artifact_id, workspace_id, session_id, path, size_bytes, sha256, content_type, created_at "
            "FROM artifacts WHERE session_id = ?",
            (session_id,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_artifact(r) for r in rows]

    async def delete(self, artifact_id: str) -> bool:
        """Returns True if the row existed."""
        existing = await self.get(artifact_id)
        if existing is None:
            return False
        async with self._lock:
            await self._db.execute(
                "DELETE FROM artifacts WHERE artifact_id = ?", (artifact_id,)
            )
            await self._db.commit()
        return True

    @staticmethod
    def _row_to_artifact(row: tuple) -> Artifact:
        artifact_id, workspace_id, session_id, path, size_bytes, sha256, content_type, created_at = row
        return Artifact(
            artifact_id=artifact_id,
            workspace_id=workspace_id,
            session_id=session_id,
            path=path,
            size_bytes=size_bytes,
            sha256=sha256,
            content_type=content_type,
            created_at=datetime.fromisoformat(created_at),
        )
