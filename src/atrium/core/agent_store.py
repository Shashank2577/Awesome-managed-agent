"""Persistent storage for dynamically-created agent configs (SQLite).

Phase 1 adds workspace_id column. The class keeps full backward-compat:
all legacy methods (save, delete, load_all, load) default to
workspace_id="default" so existing code keeps working unmodified.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from typing import Iterable

logger = logging.getLogger(__name__)

_DEFAULT_WS = "default"


class AgentStore:
    """Read/write agent config dicts to a local SQLite database.

    Each config is stored as a JSON blob keyed by (workspace_id, name).
    """

    def __init__(self, db_path: str = "atrium_agents.db") -> None:
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_configs (
                name         TEXT NOT NULL,
                config       TEXT NOT NULL,
                created_at   TEXT NOT NULL,
                category     TEXT,
                agent_type   TEXT NOT NULL DEFAULT 'http',
                workspace_id TEXT NOT NULL DEFAULT 'default',
                PRIMARY KEY (workspace_id, name)
            )
            """
        )
        self._db.commit()
        self._run_migrations()

    # ------------------------------------------------------------------
    # Migrations
    # ------------------------------------------------------------------

    def _run_migrations(self) -> None:
        cursor = self._db.execute("PRAGMA table_info(agent_configs)")
        existing_columns = {row[1] for row in cursor.fetchall()}

        if "category" not in existing_columns:
            self._db.execute("ALTER TABLE agent_configs ADD COLUMN category TEXT")
        if "agent_type" not in existing_columns:
            self._db.execute(
                "ALTER TABLE agent_configs ADD COLUMN agent_type TEXT NOT NULL DEFAULT 'http'"
            )
        if "workspace_id" not in existing_columns:
            self._db.execute(
                "ALTER TABLE agent_configs ADD COLUMN workspace_id TEXT NOT NULL DEFAULT 'default'"
            )
        self._db.commit()

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def save(self, config: dict, workspace_id: str = _DEFAULT_WS) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO agent_configs "
            "(name, config, created_at, category, agent_type, workspace_id) "
            "VALUES (?, ?, datetime('now'), ?, ?, ?)",
            (
                config["name"],
                json.dumps(config),
                config.get("category"),
                config.get("agent_type", "http"),
                workspace_id,
            ),
        )
        self._db.commit()

    def delete(self, name: str, workspace_id: str = _DEFAULT_WS) -> None:
        self._db.execute(
            "DELETE FROM agent_configs WHERE name = ? AND workspace_id = ?",
            (name, workspace_id),
        )
        self._db.commit()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def count(self, workspace_id: str = _DEFAULT_WS) -> int:
        cursor = self._db.execute(
            "SELECT COUNT(*) FROM agent_configs WHERE workspace_id = ?", (workspace_id,)
        )
        return cursor.fetchone()[0]

    def load_all(self, workspace_id: str = _DEFAULT_WS) -> list[dict]:
        """Return every stored config for a workspace."""
        cursor = self._db.execute(
            "SELECT config FROM agent_configs WHERE workspace_id = ?", (workspace_id,)
        )
        return [json.loads(row[0]) for row in cursor]

    def load_all_for_workspace(self, workspace_id: str) -> list[dict]:
        """Alias for load_all with explicit workspace_id (used by AppState)."""
        return self.load_all(workspace_id)

    def load(self, name: str, workspace_id: str = _DEFAULT_WS) -> dict | None:
        cursor = self._db.execute(
            "SELECT config FROM agent_configs WHERE name = ? AND workspace_id = ?",
            (name, workspace_id),
        )
        row = cursor.fetchone()
        return json.loads(row[0]) if row else None

    # ------------------------------------------------------------------
    # Seeding
    # ------------------------------------------------------------------

    def seed_if_empty(self, seeds: Iterable[dict], workspace_id: str = _DEFAULT_WS) -> int:
        """Populate the store from *seeds* if — and only if — it is empty."""
        from atrium.api.routes.agent_builder import CreateAgentRequest  # noqa: PLC0415

        if self.count(workspace_id) > 0:
            return 0

        saved = 0
        for raw in seeds:
            try:
                req = CreateAgentRequest.model_validate(raw)
                self.save(req.model_dump(), workspace_id=workspace_id)
                saved += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("Skipping invalid seed %r: %s", raw.get("name", "<unknown>"), exc)
        return saved
