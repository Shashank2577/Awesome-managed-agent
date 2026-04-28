"""Persistent storage for dynamically-created agent configs (SQLite)."""

from __future__ import annotations

import json
import sqlite3


class AgentStore:
    """Read/write agent config dicts to a local SQLite database.

    Each config is stored as a JSON blob keyed by the agent ``name``.
    The ``category`` and ``agent_type`` columns are index-only; the JSON blob
    is always the source of truth.
    """

    def __init__(self, db_path: str = "atrium_agents.db") -> None:
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_configs (
                name       TEXT PRIMARY KEY,
                config     TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self._db.commit()
        self._run_migrations()

    # ------------------------------------------------------------------
    # Migrations
    # ------------------------------------------------------------------

    def _run_migrations(self) -> None:
        """Additive schema migrations — safe to run on every startup."""
        cursor = self._db.execute("PRAGMA table_info(agent_configs)")
        existing_columns = {row[1] for row in cursor.fetchall()}

        if "category" not in existing_columns:
            self._db.execute(
                "ALTER TABLE agent_configs ADD COLUMN category TEXT"
            )
        if "agent_type" not in existing_columns:
            self._db.execute(
                "ALTER TABLE agent_configs ADD COLUMN agent_type TEXT NOT NULL DEFAULT 'http'"
            )
        self._db.commit()

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def save(self, config: dict) -> None:
        """Persist *config*, replacing any existing entry with the same name."""
        category = config.get("category")
        agent_type = config.get("agent_type", "http")
        self._db.execute(
            "INSERT OR REPLACE INTO agent_configs "
            "(name, config, created_at, category, agent_type) "
            "VALUES (?, ?, datetime('now'), ?, ?)",
            (config["name"], json.dumps(config), category, agent_type),
        )
        self._db.commit()

    def delete(self, name: str) -> None:
        """Remove the config for *name* (no-op if it doesn't exist)."""
        self._db.execute("DELETE FROM agent_configs WHERE name = ?", (name,))
        self._db.commit()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def count(self) -> int:
        """Return the number of stored agent configs."""
        cursor = self._db.execute("SELECT COUNT(*) FROM agent_configs")
        return cursor.fetchone()[0]

    def load_all(self) -> list[dict]:
        """Return every stored config as a list of dicts."""
        cursor = self._db.execute("SELECT config FROM agent_configs")
        return [json.loads(row[0]) for row in cursor]

    def load(self, name: str) -> dict | None:
        """Return a single config by name, or ``None``."""
        cursor = self._db.execute(
            "SELECT config FROM agent_configs WHERE name = ?", (name,)
        )
        row = cursor.fetchone()
        return json.loads(row[0]) if row else None
