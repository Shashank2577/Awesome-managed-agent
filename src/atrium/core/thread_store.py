"""Persistent thread store. SQLite-backed via aiosqlite."""
from __future__ import annotations

import asyncio
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
        self._write_lock = asyncio.Lock()

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
        from atrium.core.errors import NotFoundError
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
