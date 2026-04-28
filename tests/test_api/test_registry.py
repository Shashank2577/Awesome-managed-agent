"""Tests for registry API endpoints — categories and category filtering."""

from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport

from atrium.api.app import create_app
from atrium.core.registry import AgentRegistry

EXPECTED_CATEGORIES = {
    "research",
    "coding",
    "writing",
    "data",
    "security",
    "ops",
    "design",
    "communication",
    "analysis",
    "creative",
    "productivity",
}


@pytest.fixture
def app():
    return create_app(registry=AgentRegistry(), db_path=":memory:")


# ---------------------------------------------------------------------------
# Issue 2: GET /agents/categories
# ---------------------------------------------------------------------------


async def test_categories_returns_200(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/agents/categories")
    assert resp.status_code == 200


async def test_categories_response_shape(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/agents/categories")
    data = resp.json()
    assert "categories" in data
    assert isinstance(data["categories"], list)


async def test_categories_contains_all_11(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/agents/categories")
    returned = set(resp.json()["categories"])
    assert returned == EXPECTED_CATEGORIES


async def test_categories_is_list_not_set(app):
    """The response value must be a JSON array, not a set literal."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/agents/categories")
    data = resp.json()
    # JSON arrays deserialise to Python lists
    assert isinstance(data["categories"], list)
    # No duplicate entries
    assert len(data["categories"]) == len(set(data["categories"]))


# ---------------------------------------------------------------------------
# Issue 3: GET /agents?category= filter
# ---------------------------------------------------------------------------

_CODING_AGENT = {
    "name": "coding_helper",
    "description": "Helps with coding",
    "capabilities": ["code"],
    "api_url": "https://example.com/code",
    "category": "coding",
}

_RESEARCH_AGENT = {
    "name": "research_helper",
    "description": "Helps with research",
    "capabilities": ["search"],
    "api_url": "https://example.com/research",
    "category": "research",
}


async def test_category_filter_returns_matching_agent(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/agents/create", json=_CODING_AGENT)
        await client.post("/api/v1/agents/create", json=_RESEARCH_AGENT)
        resp = await client.get("/api/v1/agents?category=coding")
    assert resp.status_code == 200
    agents = resp.json()["agents"]
    names = [a["name"] for a in agents]
    assert "coding_helper" in names
    assert "research_helper" not in names


async def test_category_filter_excludes_other_categories(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/agents/create", json=_CODING_AGENT)
        await client.post("/api/v1/agents/create", json=_RESEARCH_AGENT)
        resp = await client.get("/api/v1/agents?category=research")
    agents = resp.json()["agents"]
    names = [a["name"] for a in agents]
    assert "research_helper" in names
    assert "coding_helper" not in names


async def test_nonexistent_category_returns_empty_list(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/agents/create", json=_CODING_AGENT)
        resp = await client.get("/api/v1/agents?category=nonexistent_category_xyz")
    assert resp.status_code == 200
    assert resp.json()["agents"] == []
