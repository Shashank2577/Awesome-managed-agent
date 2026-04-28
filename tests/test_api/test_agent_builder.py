"""Tests for the agent builder API endpoints."""

import pytest
from httpx import AsyncClient, ASGITransport

from atrium.api.app import create_app
from atrium.core.registry import AgentRegistry


@pytest.fixture
def app():
    return create_app(registry=AgentRegistry(), llm_config="openai:gpt-4o-mini")


_WIKI_PAYLOAD = {
    "name": "test_wiki",
    "description": "Searches Wikipedia",
    "capabilities": ["search"],
    "api_url": "https://en.wikipedia.org/w/api.php",
    "method": "GET",
    "query_params": {
        "action": "query",
        "list": "search",
        "srsearch": "{query}",
        "format": "json",
        "srlimit": "3",
    },
}


async def test_create_agent_returns_201(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/agents/create", json=_WIKI_PAYLOAD)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "test_wiki"
    assert data["status"] == "registered"


async def test_created_agent_appears_in_registry(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/agents/create", json=_WIKI_PAYLOAD)
        resp = await client.get("/api/v1/agents")
    agents = resp.json()["agents"]
    names = [a["name"] for a in agents]
    assert "test_wiki" in names


async def test_duplicate_name_returns_400(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/agents/create", json=_WIKI_PAYLOAD)
        resp = await client.post("/api/v1/agents/create", json=_WIKI_PAYLOAD)
    assert resp.status_code == 400


async def test_delete_agent(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/agents/create", json=_WIKI_PAYLOAD)
        resp = await client.delete("/api/v1/agents/test_wiki")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"


async def test_missing_fields_returns_422(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/agents/create", json={"name": "incomplete"})
    assert resp.status_code == 422
