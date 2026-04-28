"""Tests for CLI cmd_agents_seed — normal, force, category, and invalid seed paths."""

from __future__ import annotations

import argparse
from io import StringIO
from unittest.mock import patch

import pytest

from atrium.core.agent_store import AgentStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_store() -> AgentStore:
    """Return an in-memory AgentStore."""
    return AgentStore(db_path=":memory:")


def _valid_http_seed(**overrides) -> dict:
    base = {
        "name": "http-agent",
        "description": "An HTTP agent",
        "agent_type": "http",
        "api_url": "https://example.com/api",
    }
    base.update(overrides)
    return base


def _valid_llm_seed(**overrides) -> dict:
    base = {
        "name": "llm-agent",
        "description": "An LLM agent",
        "agent_type": "llm",
        "system_prompt": "You are helpful.",
    }
    base.update(overrides)
    return base


def _make_args(**kwargs) -> argparse.Namespace:
    """Build a minimal Namespace that cmd_agents_seed expects."""
    defaults = {
        "db": ":memory:",
        "force": False,
        "category": None,
        "source": None,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _run_seed(store: AgentStore, seeds: list[dict], **args_overrides) -> str:
    """Call cmd_agents_seed with a patched AgentStore and iter_seeds, return stdout."""
    from atrium.cli import cmd_agents_seed

    args = _make_args(**args_overrides)

    # AgentStore and iter_seeds are imported lazily inside cmd_agents_seed, so
    # we patch them at their source module locations.
    with patch("atrium.core.agent_store.AgentStore", return_value=store), \
         patch("atrium.seeds.iter_seeds", return_value=iter(seeds)), \
         patch("builtins.print") as mock_print:
        cmd_agents_seed(args)
        # Collect all print calls into a single string
        output = "\n".join(str(call.args[0]) for call in mock_print.call_args_list)

    return output


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestCmdAgentsSeedNormal:
    def test_empty_store_seeds_both_agents(self):
        """Normal seed into an empty store creates 2 agents."""
        store = _make_store()
        seeds = [
            _valid_http_seed(name="http-one"),
            _valid_llm_seed(name="llm-one"),
        ]

        output = _run_seed(store, seeds)

        assert store.count() == 2
        assert "2" in output  # "Seeded 2 agent(s)."

    def test_non_empty_store_skips_seeding(self):
        """Normal seed when store already has agents is a no-op."""
        store = _make_store()
        store.save(_valid_http_seed(name="existing"))

        seeds = [_valid_http_seed(name="new-one")]
        output = _run_seed(store, seeds)

        assert store.count() == 1  # unchanged
        assert "already populated" in output.lower() or "nothing seeded" in output.lower()


class TestCmdAgentsSeedForce:
    def test_force_replaces_existing_agent(self):
        """--force replaces an existing agent with updated description."""
        store = _make_store()
        store.save(_valid_http_seed(name="test-agent", description="old description"))

        updated_seed = _valid_http_seed(name="test-agent", description="new description")
        output = _run_seed(store, [updated_seed], force=True)

        assert store.count() == 1
        loaded = store.load("test-agent")
        assert loaded["description"] == "new description"
        assert "replaced: 1" in output

    def test_force_creates_new_agent(self):
        """--force creates an agent when it does not yet exist."""
        store = _make_store()
        seeds = [_valid_http_seed(name="brand-new")]

        output = _run_seed(store, seeds, force=True)

        assert store.count() == 1
        assert "created: 1" in output


class TestCmdAgentsSeedCategory:
    def test_category_filter_seeds_only_matching_agents(self):
        """--category filters seeds to only those with the matching category."""
        store = _make_store()
        seeds = [
            _valid_http_seed(name="coding-agent", category="coding"),
            _valid_http_seed(name="research-agent", category="research"),
        ]

        output = _run_seed(store, seeds, force=True, category="coding")

        assert store.count() == 1
        assert store.load("coding-agent") is not None
        assert store.load("research-agent") is None

    def test_category_filter_no_match_seeds_nothing(self):
        """--category with no matching seeds results in 0 created."""
        store = _make_store()
        seeds = [_valid_http_seed(name="other-agent", category="research")]

        output = _run_seed(store, seeds, force=True, category="coding")

        assert store.count() == 0
        assert "created: 0" in output


class TestCmdAgentsSeedInvalid:
    def test_invalid_seed_skipped_valid_seed_created(self):
        """An invalid seed is skipped and the valid one is still created."""
        store = _make_store()
        seeds = [
            _valid_http_seed(name="valid-agent"),
            # llm agent missing system_prompt — invalid
            {
                "name": "invalid-agent",
                "description": "Missing system_prompt",
                "agent_type": "llm",
            },
        ]

        output = _run_seed(store, seeds, force=True)

        assert store.count() == 1
        assert store.load("valid-agent") is not None
        assert store.load("invalid-agent") is None
        assert "invalid: 1" in output
        assert "created: 1" in output
