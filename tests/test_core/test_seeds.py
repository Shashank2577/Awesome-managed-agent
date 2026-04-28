"""Tests for the seeds iterator and AgentStore.seed_if_empty."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

import pytest

from atrium.seeds import iter_seeds
from atrium.core.agent_store import AgentStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_store() -> AgentStore:
    """Return an in-memory AgentStore."""
    return AgentStore(db_path=":memory:")


def _valid_http_seed(**overrides) -> dict:
    base = {
        "name": "seed_agent",
        "description": "A seeded HTTP agent",
        "agent_type": "http",
        "api_url": "https://example.com/api",
    }
    base.update(overrides)
    return base


def _valid_llm_seed(**overrides) -> dict:
    base = {
        "name": "seed_llm",
        "description": "A seeded LLM agent",
        "agent_type": "llm",
        "system_prompt": "You are helpful.",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# iter_seeds tests
# ---------------------------------------------------------------------------

class TestIterSeeds:
    def test_returns_empty_when_directory_missing(self, tmp_path):
        """iter_seeds should yield nothing when the source dir doesn't exist."""
        result = list(iter_seeds(source=tmp_path / "nonexistent"))
        assert result == []

    def test_yields_dicts_for_valid_json_files(self, tmp_path):
        """All valid JSON files under the corpus dir should be yielded."""
        (tmp_path / "cat1").mkdir()
        (tmp_path / "cat1" / "a.json").write_text(json.dumps(_valid_http_seed(name="alpha")))
        (tmp_path / "cat1" / "b.json").write_text(json.dumps(_valid_llm_seed(name="beta")))

        seeds = list(iter_seeds(source=tmp_path))
        names = [s["name"] for s in seeds]
        assert "alpha" in names
        assert "beta" in names
        assert len(seeds) == 2

    def test_invalid_json_files_are_skipped(self, tmp_path, caplog):
        """Files with invalid JSON should be skipped with a warning, not raised."""
        (tmp_path / "good.json").write_text(json.dumps(_valid_http_seed(name="good")))
        (tmp_path / "bad.json").write_text("this is not valid json {{{")

        with caplog.at_level(logging.WARNING, logger="atrium.seeds"):
            seeds = list(iter_seeds(source=tmp_path))

        assert len(seeds) == 1
        assert seeds[0]["name"] == "good"
        assert any("bad.json" in r.message for r in caplog.records)

    def test_empty_corpus_directory_yields_nothing(self, tmp_path):
        """An existing but empty directory yields an empty iterator."""
        result = list(iter_seeds(source=tmp_path))
        assert result == []

    def test_non_object_json_is_skipped(self, tmp_path, caplog):
        """A JSON file whose top-level value is a list (not an object) is skipped."""
        (tmp_path / "list.json").write_text(json.dumps([1, 2, 3]))

        with caplog.at_level(logging.WARNING, logger="atrium.seeds"):
            seeds = list(iter_seeds(source=tmp_path))

        assert seeds == []

    def test_recursive_glob(self, tmp_path):
        """iter_seeds walks nested subdirectories."""
        nested = tmp_path / "a" / "b" / "c"
        nested.mkdir(parents=True)
        (nested / "deep.json").write_text(json.dumps(_valid_http_seed(name="deep")))

        seeds = list(iter_seeds(source=tmp_path))
        assert len(seeds) == 1
        assert seeds[0]["name"] == "deep"


# ---------------------------------------------------------------------------
# AgentStore.seed_if_empty tests
# ---------------------------------------------------------------------------

class TestSeedIfEmpty:
    def test_non_empty_store_returns_zero_and_writes_nothing(self):
        """seed_if_empty must be a no-op when the store already has content."""
        store = _make_store()
        store.save(_valid_http_seed(name="existing"))
        assert store.count() == 1

        seeds = [_valid_http_seed(name="new_one")]
        result = store.seed_if_empty(seeds)

        assert result == 0
        assert store.count() == 1  # no new entry written

    def test_empty_store_writes_seeds_and_returns_count(self):
        """seed_if_empty populates an empty store and returns the saved count."""
        store = _make_store()
        seeds = [
            _valid_http_seed(name="http_one"),
            _valid_llm_seed(name="llm_one"),
        ]
        result = store.seed_if_empty(seeds)

        assert result == 2
        assert store.count() == 2

    def test_invalid_seed_is_skipped_with_warning(self, caplog):
        """An invalid seed (missing required fields) is logged and skipped."""
        store = _make_store()
        # Missing 'description' and type-specific fields — will fail validation
        bad_seed = {"name": "bad_no_description"}
        good_seed = _valid_http_seed(name="good_one")

        with caplog.at_level(logging.WARNING, logger="atrium.core.agent_store"):
            result = store.seed_if_empty([bad_seed, good_seed])

        assert result == 1
        assert store.count() == 1
        assert store.load("good_one") is not None
        assert any("bad_no_description" in r.message for r in caplog.records)

    def test_idempotency_second_call_returns_zero(self):
        """Calling seed_if_empty twice: first call seeds, second is a no-op."""
        store = _make_store()
        seeds = [_valid_http_seed(name="agent_a")]

        first = store.seed_if_empty(seeds)
        second = store.seed_if_empty([_valid_http_seed(name="agent_b")])

        assert first == 1
        assert second == 0
        assert store.count() == 1  # only the first seeded agent exists

    def test_seed_if_empty_resilient_to_empty_iterator(self):
        """Passing an empty iterator to seed_if_empty returns 0 without errors."""
        store = _make_store()
        result = store.seed_if_empty(iter([]))
        assert result == 0
        assert store.count() == 0
