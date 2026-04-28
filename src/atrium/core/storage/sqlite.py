"""SQLite storage backend — wraps aiosqlite with a single-writer lock."""
from __future__ import annotations

import asyncio
import re
from typing import Any

import aiosqlite


# Convert :name placeholders to ? (SQLite style)
_PLACEHOLDER_RE = re.compile(r":([a-zA-Z_][a-zA-Z0-9_]*)")


def _rewrite(sql: str, params: tuple) -> tuple[str, tuple]:
    """Pass-through for positional params; named params aren't used here."""
    return sql, params


class SQLiteStorage:
    """aiosqlite-backed storage. Serializes writes through a single lock."""

    def __init__(self, db_url: str) -> None:
        # Strip "sqlite:///" or "sqlite://" prefix
        if db_url == ":memory:":
            self._path = ":memory:"
        else:
            self._path = db_url.lstrip("sqlite:").lstrip("/")
            if db_url.startswith("sqlite:///"):
                self._path = db_url[len("sqlite:///"):]
            elif db_url.startswith("sqlite://"):
                self._path = db_url[len("sqlite://"):]
            elif db_url.startswith("sqlite:"):
                self._path = db_url[len("sqlite:"):]
        self._db: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def init(self) -> None:
        self._db = await aiosqlite.connect(self._path)
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    def _conn(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("SQLiteStorage not initialized — call await init() first")
        return self._db

    async def execute(self, sql: str, params: tuple = ()) -> None:
        async with self._lock:
            await self._conn().execute(sql, params)
            await self._conn().commit()

    async def execute_many(self, sql: str, params_list: list[tuple]) -> None:
        async with self._lock:
            await self._conn().executemany(sql, params_list)
            await self._conn().commit()

    async def executescript(self, script: str) -> None:
        async with self._lock:
            await self._conn().executescript(script)
            await self._conn().commit()

    async def fetch_one(self, sql: str, params: tuple = ()) -> tuple | None:
        cursor = await self._conn().execute(sql, params)
        return await cursor.fetchone()

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[tuple]:
        cursor = await self._conn().execute(sql, params)
        return await cursor.fetchall()
