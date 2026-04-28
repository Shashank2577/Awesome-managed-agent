"""Tests for AgentStore schema migration (category and agent_type columns)."""

from __future__ import annotations

import json
import sqlite3

import pytest

from atrium.core.agent_store import AgentStore


def test_migration_adds_columns_to_existing_table():
    """Columns category and agent_type are added when they don't exist."""
    # Build a db with the OLD schema (no category/agent_type columns)
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE agent_configs (
            name       TEXT PRIMARY KEY,
            config     TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    # Insert a legacy row without the new columns
    legacy_config = {"name": "legacy_agent", "description": "Old agent", "api_url": "https://x.com"}
    conn.execute(
        "INSERT INTO agent_configs (name, config, created_at) VALUES (?, ?, datetime('now'))",
        ("legacy_agent", json.dumps(legacy_config)),
    )
    conn.commit()

    # Patch AgentStore to reuse the same in-memory connection
    store = AgentStore.__new__(AgentStore)
    store._db = conn
    store._run_migrations()

    # Verify both new columns now exist
    cursor = conn.execute("PRAGMA table_info(agent_configs)")
    columns = {row[1] for row in cursor.fetchall()}
    assert "category" in columns
    assert "agent_type" in columns

    # Legacy row should have agent_type defaulted to 'http' and category NULL
    row = conn.execute(
        "SELECT agent_type, category FROM agent_configs WHERE name = 'legacy_agent'"
    ).fetchone()
    assert row is not None
    assert row[0] == "http"
    assert row[1] is None


def test_migration_is_idempotent():
    """Running migrations twice on a fully-migrated db raises no errors."""
    store = AgentStore(db_path=":memory:")
    # Call migration again — should not raise
    store._run_migrations()

    cursor = store._db.execute("PRAGMA table_info(agent_configs)")
    columns = {row[1] for row in cursor.fetchall()}
    assert "category" in columns
    assert "agent_type" in columns


def test_count_empty_store():
    """count() returns 0 for a fresh store."""
    store = AgentStore(db_path=":memory:")
    assert store.count() == 0


def test_count_after_saves():
    """count() reflects the number of stored rows."""
    store = AgentStore(db_path=":memory:")
    store.save({"name": "a", "description": "A", "api_url": "https://a.com"})
    assert store.count() == 1
    store.save({"name": "b", "description": "B", "api_url": "https://b.com"})
    assert store.count() == 2


def test_count_after_replace():
    """Replacing an existing row does not increase count."""
    store = AgentStore(db_path=":memory:")
    store.save({"name": "a", "description": "v1", "api_url": "https://a.com"})
    store.save({"name": "a", "description": "v2", "api_url": "https://a.com"})
    assert store.count() == 1


def test_count_after_delete():
    """count() decreases after a delete."""
    store = AgentStore(db_path=":memory:")
    store.save({"name": "a", "description": "A", "api_url": "https://a.com"})
    store.save({"name": "b", "description": "B", "api_url": "https://b.com"})
    store.delete("a")
    assert store.count() == 1


def test_save_writes_category_and_agent_type_columns():
    """save() stores category and agent_type in dedicated columns."""
    store = AgentStore(db_path=":memory:")
    config = {
        "name": "cat_agent",
        "description": "Categorised agent",
        "api_url": "https://x.com",
        "category": "research",
        "agent_type": "http",
    }
    store.save(config)

    row = store._db.execute(
        "SELECT category, agent_type FROM agent_configs WHERE name = 'cat_agent'"
    ).fetchone()
    assert row is not None
    assert row[0] == "research"
    assert row[1] == "http"


def test_save_without_category_stores_null():
    """A config without category saves NULL in the category column."""
    store = AgentStore(db_path=":memory:")
    store.save({"name": "no_cat", "description": "No cat", "api_url": "https://x.com"})

    row = store._db.execute(
        "SELECT category, agent_type FROM agent_configs WHERE name = 'no_cat'"
    ).fetchone()
    assert row is not None
    assert row[0] is None
    assert row[1] == "http"


def test_load_all_returns_full_json():
    """load_all() returns full config dicts (JSON blob is source of truth)."""
    store = AgentStore(db_path=":memory:")
    config = {
        "name": "full",
        "description": "Full config",
        "api_url": "https://x.com",
        "category": "coding",
        "agent_type": "http",
        "extra_field": "preserved",
    }
    store.save(config)
    loaded = store.load_all()
    assert len(loaded) == 1
    assert loaded[0]["extra_field"] == "preserved"
    assert loaded[0]["category"] == "coding"
