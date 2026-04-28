"""Postgres storage backend — asyncpg connection pool.

Only imported when ATRIUM_DB_URL starts with postgresql:// or postgres://.
asyncpg is an optional dependency; CI with Postgres requires it.
"""
from __future__ import annotations

from typing import Any

try:
    import asyncpg
except ImportError:
    asyncpg = None  # type: ignore[assignment]


class PostgresStorage:
    """asyncpg-backed storage. Native concurrent writes — no app-level lock."""

    def __init__(self, db_url: str) -> None:
        self._db_url = db_url
        self._pool: Any = None

    async def init(self) -> None:
        if asyncpg is None:
            raise RuntimeError(
                "asyncpg is not installed. "
                "Install it with: pip install asyncpg"
            )
        self._pool = await asyncpg.create_pool(self._db_url)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    def _p(self) -> Any:
        if self._pool is None:
            raise RuntimeError("PostgresStorage not initialized — call await init() first")
        return self._pool

    async def execute(self, sql: str, params: tuple = ()) -> None:
        async with self._p().acquire() as conn:
            await conn.execute(sql, *params)

    async def execute_many(self, sql: str, params_list: list[tuple]) -> None:
        async with self._p().acquire() as conn:
            await conn.executemany(sql, params_list)

    async def fetch_one(self, sql: str, params: tuple = ()) -> tuple | None:
        async with self._p().acquire() as conn:
            row = await conn.fetchrow(sql, *params)
            return tuple(row) if row else None

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[tuple]:
        async with self._p().acquire() as conn:
            rows = await conn.fetch(sql, *params)
            return [tuple(r) for r in rows]
