"""Persistent workspace and API key store. Storage-backend agnostic."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from atrium.core.auth import (
    ApiKey,
    ApiKeyKind,
    Workspace,
    WorkspaceQuota,
    generate_secret,
    hash_secret,
)
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


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(s: str | None) -> datetime | None:
    if s is None:
        return None
    return datetime.fromisoformat(s)


class WorkspaceStore:
    """Workspaces and API keys."""

    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    async def init_schema(self) -> None:
        for stmt in _SCHEMA_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                await self._storage.execute(stmt)

    # ------------------------------------------------------------------
    # Workspaces
    # ------------------------------------------------------------------

    async def create_workspace(self, name: str, quota: WorkspaceQuota | None = None) -> Workspace:
        ws = Workspace(name=name, quota=quota or WorkspaceQuota())
        await self._storage.execute(
            "INSERT INTO workspaces (workspace_id, name, quota_json, metadata, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                ws.workspace_id,
                ws.name,
                ws.quota.model_dump_json(),
                json.dumps(ws.metadata),
                ws.created_at.isoformat(),
            ),
        )
        return ws

    async def get_workspace(self, workspace_id: str) -> Workspace | None:
        row = await self._storage.fetch_one(
            "SELECT workspace_id, name, quota_json, metadata, created_at "
            "FROM workspaces WHERE workspace_id = ?",
            (workspace_id,),
        )
        if row is None:
            return None
        return self._row_to_workspace(row)

    async def list_workspaces(self) -> list[Workspace]:
        rows = await self._storage.fetch_all(
            "SELECT workspace_id, name, quota_json, metadata, created_at FROM workspaces"
        )
        return [self._row_to_workspace(r) for r in rows]

    async def update_quota(self, workspace_id: str, quota: WorkspaceQuota) -> None:
        await self._storage.execute(
            "UPDATE workspaces SET quota_json = ? WHERE workspace_id = ?",
            (quota.model_dump_json(), workspace_id),
        )

    async def delete_workspace(self, workspace_id: str) -> None:
        await self._storage.execute(
            "DELETE FROM workspaces WHERE workspace_id = ?",
            (workspace_id,),
        )

    # ------------------------------------------------------------------
    # API keys
    # ------------------------------------------------------------------

    async def issue_key(
        self, workspace_id: str | None, kind: ApiKeyKind, name: str = ""
    ) -> tuple[ApiKey, str]:
        """Returns (record, plaintext_secret). The secret is shown ONCE."""
        secret = generate_secret()
        key = ApiKey(
            workspace_id=workspace_id,
            kind=kind,
            hash=hash_secret(secret),
            name=name,
        )
        await self._storage.execute(
            "INSERT INTO api_keys (api_key_id, workspace_id, kind, hash, name, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                key.api_key_id,
                key.workspace_id,
                key.kind.value,
                key.hash,
                key.name,
                key.created_at.isoformat(),
            ),
        )
        return key, secret

    async def lookup_by_secret(self, secret: str) -> ApiKey | None:
        """Hash the secret, look up the record. Updates last_used_at on hit."""
        h = hash_secret(secret)
        row = await self._storage.fetch_one(
            "SELECT api_key_id, workspace_id, kind, hash, name, created_at, last_used_at, revoked_at "
            "FROM api_keys WHERE hash = ?",
            (h,),
        )
        if row is None:
            return None
        key = self._row_to_key(row)
        # Update last_used_at (fire-and-forget — don't fail request on error)
        now = _utcnow()
        try:
            await self._storage.execute(
                "UPDATE api_keys SET last_used_at = ? WHERE api_key_id = ?",
                (now, key.api_key_id),
            )
        except Exception:
            pass
        return key

    async def revoke_key(self, api_key_id: str) -> None:
        await self._storage.execute(
            "UPDATE api_keys SET revoked_at = ? WHERE api_key_id = ?",
            (_utcnow(), api_key_id),
        )

    async def list_keys(self, workspace_id: str | None) -> list[ApiKey]:
        if workspace_id is None:
            rows = await self._storage.fetch_all(
                "SELECT api_key_id, workspace_id, kind, hash, name, created_at, "
                "last_used_at, revoked_at FROM api_keys WHERE workspace_id IS NULL"
            )
        else:
            rows = await self._storage.fetch_all(
                "SELECT api_key_id, workspace_id, kind, hash, name, created_at, "
                "last_used_at, revoked_at FROM api_keys WHERE workspace_id = ?",
                (workspace_id,),
            )
        return [self._row_to_key(r) for r in rows]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_workspace(row: tuple) -> Workspace:
        workspace_id, name, quota_json, metadata_json, created_at = row
        return Workspace(
            workspace_id=workspace_id,
            name=name,
            quota=WorkspaceQuota.model_validate_json(quota_json),
            metadata=json.loads(metadata_json),
            created_at=datetime.fromisoformat(created_at),
        )

    @staticmethod
    def _row_to_key(row: tuple) -> ApiKey:
        api_key_id, workspace_id, kind, hash_, name, created_at, last_used_at, revoked_at = row
        return ApiKey(
            api_key_id=api_key_id,
            workspace_id=workspace_id,
            kind=ApiKeyKind(kind),
            hash=hash_,
            name=name or "",
            created_at=datetime.fromisoformat(created_at),
            last_used_at=_parse_dt(last_used_at),
            revoked_at=_parse_dt(revoked_at),
        )
