"""Tests for POST /api/v1/agents/bulk."""

from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport

from atrium.api.app import create_app
from atrium.core.registry import AgentRegistry


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    return create_app(registry=AgentRegistry(), llm_config="openai:gpt-4o-mini", db_path=":memory:")


def _http_agent(name: str, **overrides) -> dict:
    payload = {
        "name": name,
        "description": f"{name} description",
        "agent_type": "http",
        "api_url": "https://example.com/api",
    }
    payload.update(overrides)
    return payload


def _llm_agent(name: str, **overrides) -> dict:
    payload = {
        "name": name,
        "description": f"{name} description",
        "agent_type": "llm",
        "system_prompt": "You are helpful.",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_bulk_create_three_valid_agents(app):
    """Posting 3 valid agents should return 3 'created' results."""
    body = {
        "agents": [
            _http_agent("bulk_a"),
            _http_agent("bulk_b"),
            _llm_agent("bulk_c"),
        ],
        "mode": "skip",
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/agents/bulk", json=body)

    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 3
    statuses = {r["name"]: r["status"] for r in results}
    assert statuses["bulk_a"] == "created"
    assert statuses["bulk_b"] == "created"
    assert statuses["bulk_c"] == "created"


async def test_bulk_mode_skip_marks_duplicate_as_skipped(app):
    """With mode='skip', a pre-existing agent should be reported as 'skipped'."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create one agent first
        await client.post("/api/v1/agents/create", json=_http_agent("existing_x"))

        body = {
            "agents": [
                _http_agent("existing_x"),  # duplicate
                _http_agent("new_y"),
            ],
            "mode": "skip",
        }
        resp = await client.post("/api/v1/agents/bulk", json=body)

    assert resp.status_code == 200
    results = {r["name"]: r["status"] for r in resp.json()["results"]}
    assert results["existing_x"] == "skipped"
    assert results["new_y"] == "created"


async def test_bulk_mode_replace_recreates_existing_agent(app):
    """With mode='replace', an existing agent is deleted and re-created."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create the agent first
        await client.post("/api/v1/agents/create", json=_http_agent("replaceable"))

        body = {
            "agents": [_http_agent("replaceable")],
            "mode": "replace",
        }
        resp = await client.post("/api/v1/agents/bulk", json=body)

    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 1
    assert results[0]["name"] == "replaceable"
    assert results[0]["status"] == "created"


async def test_bulk_invalid_agent_skipped_batch_continues(app):
    """An invalid agent (missing description) is reported as 'error'; the rest succeed."""
    body = {
        "agents": [
            _http_agent("valid_1"),
            # missing description — per-item validation will catch this
            {"name": "invalid_no_desc", "agent_type": "http", "api_url": "https://x.com"},
            _http_agent("valid_2"),
        ],
        "mode": "skip",
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/agents/bulk", json=body)

    # The batch never aborts — invalid items get status="error", valid items get status="created"
    assert resp.status_code == 200
    results = {r["name"]: r for r in resp.json()["results"]}
    assert results["valid_1"]["status"] == "created"
    assert results["invalid_no_desc"]["status"] == "error"
    assert results["valid_2"]["status"] == "created"


async def test_bulk_invalid_agent_soft_error_in_valid_batch(app):
    """Two valid + one invalid (bad category) — batch returns 200 with per-item error."""
    body = {
        "agents": [
            _http_agent("val_a"),
            {**_http_agent("bad_cat"), "category": "not_a_real_category"},
            _http_agent("val_b"),
        ],
        "mode": "skip",
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/agents/bulk", json=body)

    # Invalid category is caught per-item — batch still returns 200
    assert resp.status_code == 200
    results = {r["name"]: r for r in resp.json()["results"]}
    assert results["val_a"]["status"] == "created"
    assert results["bad_cat"]["status"] == "error"
    assert results["val_b"]["status"] == "created"


async def test_bulk_empty_list_returns_empty_results(app):
    """Posting an empty agents list should return an empty results list."""
    body = {"agents": [], "mode": "skip"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/agents/bulk", json=body)

    assert resp.status_code == 200
    assert resp.json()["results"] == []


async def test_bulk_default_mode_is_skip(app):
    """Omitting mode should default to 'skip' behaviour."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/agents/create", json=_http_agent("dup_agent"))

        body = {"agents": [_http_agent("dup_agent"), _http_agent("fresh_agent")]}
        resp = await client.post("/api/v1/agents/bulk", json=body)

    assert resp.status_code == 200
    results = {r["name"]: r["status"] for r in resp.json()["results"]}
    assert results["dup_agent"] == "skipped"
    assert results["fresh_agent"] == "created"
