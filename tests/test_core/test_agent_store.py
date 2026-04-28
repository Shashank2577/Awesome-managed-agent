"""Tests for AgentStore (SQLite persistence for agent configs)."""

import os
import tempfile

import pytest

from atrium.core.agent_store import AgentStore


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = AgentStore(db_path=path)
    yield s
    os.unlink(path)


def test_save_and_load(store):
    config = {"name": "test", "description": "Test agent", "api_url": "https://example.com"}
    store.save(config)
    loaded = store.load_all()
    assert len(loaded) == 1
    assert loaded[0]["name"] == "test"
    assert loaded[0]["api_url"] == "https://example.com"


def test_load_single(store):
    config = {"name": "alpha", "description": "Alpha", "api_url": "https://a.com"}
    store.save(config)
    result = store.load("alpha")
    assert result is not None
    assert result["name"] == "alpha"


def test_load_missing_returns_none(store):
    assert store.load("nope") is None


def test_save_replaces_existing(store):
    store.save({"name": "a", "description": "v1", "api_url": "x"})
    store.save({"name": "a", "description": "v2", "api_url": "y"})
    loaded = store.load_all()
    assert len(loaded) == 1
    assert loaded[0]["description"] == "v2"


def test_delete(store):
    store.save({"name": "a", "description": "A", "api_url": "x"})
    store.save({"name": "b", "description": "B", "api_url": "y"})
    store.delete("a")
    loaded = store.load_all()
    assert len(loaded) == 1
    assert loaded[0]["name"] == "b"


def test_delete_nonexistent_is_noop(store):
    store.delete("ghost")
    assert store.load_all() == []


def test_empty_store(store):
    assert store.load_all() == []
