"""Per-workspace MCP server registry."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

import aiosqlite


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS mcp_servers (
    mcp_server_id   TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL,
    name            TEXT NOT NULL,
    transport       TEXT NOT NULL,
    upstream        TEXT NOT NULL,
    credentials_ref TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    UNIQUE(workspace_id, name)
);
CREATE INDEX IF NOT EXISTS idx_mcp_servers_workspace ON mcp_servers(workspace_id);
"""

TransportType = Literal["stdio", "sse", "http"]


@dataclass
class MCPServer:
    mcp_server_id: str
    workspace_id: str
    name: str
    transport: str
    upstream: str
    credentials_ref: str
    created_at: datetime


class MCPServerStore:
    """SQLite-backed MCP server registry."""

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

    async def register(
        self,
        workspace_id: str,
        name: str,
        transport: str,
        upstream: str,
        credentials_ref: str = "",
    ) -> MCPServer:
        mcp_server_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            await self._db.execute(
                "INSERT INTO mcp_servers "
                "(mcp_server_id, workspace_id, name, transport, upstream, credentials_ref, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (mcp_server_id, workspace_id, name, transport, upstream, credentials_ref, now),
            )
            await self._db.commit()
        return MCPServer(
            mcp_server_id=mcp_server_id,
            workspace_id=workspace_id,
            name=name,
            transport=transport,
            upstream=upstream,
            credentials_ref=credentials_ref,
            created_at=datetime.fromisoformat(now),
        )

    async def list_for_workspace(self, workspace_id: str) -> list[MCPServer]:
        cursor = await self._db.execute(
            "SELECT mcp_server_id, workspace_id, name, transport, upstream, credentials_ref, created_at "
            "FROM mcp_servers WHERE workspace_id = ?",
            (workspace_id,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_server(r) for r in rows]

    async def get_by_name(self, workspace_id: str, name: str) -> MCPServer | None:
        cursor = await self._db.execute(
            "SELECT mcp_server_id, workspace_id, name, transport, upstream, credentials_ref, created_at "
            "FROM mcp_servers WHERE workspace_id = ? AND name = ?",
            (workspace_id, name),
        )
        row = await cursor.fetchone()
        return self._row_to_server(row) if row else None

    async def delete(self, workspace_id: str, name: str) -> bool:
        existing = await self.get_by_name(workspace_id, name)
        if existing is None:
            return False
        async with self._lock:
            await self._db.execute(
                "DELETE FROM mcp_servers WHERE workspace_id = ? AND name = ?",
                (workspace_id, name),
            )
            await self._db.commit()
        return True

    async def names_for_workspace(self, workspace_id: str) -> set[str]:
        """Return the set of server names registered for this workspace."""
        servers = await self.list_for_workspace(workspace_id)
        return {s.name for s in servers}

    @staticmethod
    def _row_to_server(row: tuple) -> MCPServer:
        mcp_server_id, workspace_id, name, transport, upstream, credentials_ref, created_at = row
        return MCPServer(
            mcp_server_id=mcp_server_id,
            workspace_id=workspace_id,
            name=name,
            transport=transport,
            upstream=upstream,
            credentials_ref=credentials_ref or "",
            created_at=datetime.fromisoformat(created_at),
        )
