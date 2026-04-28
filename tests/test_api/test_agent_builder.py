"""Tests for the agent builder API endpoints."""

import pytest
from httpx import AsyncClient, ASGITransport

from atrium.api.app import create_app
from atrium.core.registry import AgentRegistry


@pytest.fixture
def app():
    return create_app(registry=AgentRegistry(), llm_config="openai:gpt-4o-mini", db_path=":memory:")


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


# ---------------------------------------------------------------------------
# Issue 4: model_validator cross-field rules at HTTP layer
# ---------------------------------------------------------------------------


async def test_http_agent_without_api_url_returns_422(app):
    """agent_type='http' with no api_url should be rejected at validation time."""
    payload = {
        "name": "bad_http_agent",
        "description": "Missing api_url",
        "agent_type": "http",
        # api_url intentionally omitted
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/agents/create", json=payload)
    assert resp.status_code == 422


async def test_llm_agent_without_system_prompt_returns_422(app):
    """agent_type='llm' with no system_prompt should be rejected at validation time."""
    payload = {
        "name": "bad_llm_agent",
        "description": "Missing system_prompt",
        "agent_type": "llm",
        # system_prompt intentionally omitted
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/agents/create", json=payload)
    assert resp.status_code == 422


async def test_llm_agent_with_system_prompt_returns_201(app):
    """agent_type='llm' with a valid system_prompt creates the agent (HTTP 201)."""
    payload = {
        "name": "future_llm_agent",
        "description": "An LLM agent",
        "agent_type": "llm",
        "system_prompt": "You are a helpful assistant.",
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/agents/create", json=payload)
    assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Issue 6 (Suggestion): VALID_CATEGORIES enforced at request validation
# ---------------------------------------------------------------------------


async def test_invalid_category_returns_422(app):
    """A category value not in VALID_CATEGORIES must be rejected with 422."""
    payload = {
        "name": "agent_with_bad_category",
        "description": "Testing bad category",
        "api_url": "https://example.com/api",
        "category": "not_a_real_category",
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/agents/create", json=payload)
    assert resp.status_code == 422


async def test_valid_category_is_accepted(app):
    """A valid category should pass validation and return 201."""
    payload = {
        "name": "agent_with_good_category",
        "description": "Testing valid category",
        "api_url": "https://example.com/api",
        "category": "coding",
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/agents/create", json=payload)
    assert resp.status_code == 201


async def test_null_category_is_accepted(app):
    """category=None (omitted) should be accepted — it is optional."""
    payload = {
        "name": "agent_without_category",
        "description": "No category set",
        "api_url": "https://example.com/api",
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/agents/create", json=payload)
    assert resp.status_code == 201
