"""Storage backend abstraction. Concrete impls: SQLiteStorage, PostgresStorage."""
from __future__ import annotations

from typing import Any, Protocol


class Storage(Protocol):
    """Minimal async DB interface used by all stores."""

    async def execute(self, sql: str, params: tuple = ()) -> None: ...
    async def execute_many(self, sql: str, params_list: list[tuple]) -> None: ...
    async def fetch_one(self, sql: str, params: tuple = ()) -> tuple | None: ...
    async def fetch_all(self, sql: str, params: tuple = ()) -> list[tuple]: ...

    async def init(self) -> None: ...
    async def close(self) -> None: ...


def open_storage(db_url: str) -> Storage:
    """Factory that picks SQLite or Postgres based on URL scheme."""
    if db_url.startswith("sqlite:") or db_url == ":memory:":
        from atrium.core.storage.sqlite import SQLiteStorage
        return SQLiteStorage(db_url)
    if db_url.startswith("postgresql") or db_url.startswith("postgres"):
        from atrium.core.storage.postgres import PostgresStorage
        return PostgresStorage(db_url)
    raise ValueError(f"unsupported db_url: {db_url!r}")
