"""Tests for the threads routes."""
import pytest
from httpx import AsyncClient, ASGITransport

from atrium.api.app import create_app
from atrium.core.agent import Agent
from atrium.core.registry import AgentRegistry


class StubAgent(Agent):
    name = "stub"
    description = "Stub"
    capabilities = ["test"]

    async def run(self, input_data: dict) -> dict:
        return {"ok": True}


@pytest.fixture
def registry():
    reg = AgentRegistry()
    reg.register(StubAgent)
    return reg


@pytest.fixture
async def app(registry):
    from httpx import ASGITransport
    application = create_app(
        registry=registry,
        llm_config="openai:gpt-4o-mini",
        db_path=":memory:",
        events_db_path=":memory:",
        threads_db_path=":memory:",
    )
    # Trigger lifespan manually by using async with lifespan context
    async with application.router.lifespan_context(application):
        yield application



async def test_create_thread(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/threads", json={"objective": "test goal"})
    assert resp.status_code == 201
    data = resp.json()
    assert "thread_id" in data
    assert data["objective"] == "test goal"
    assert "stream_url" in data


async def test_list_threads(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/threads")
    assert resp.status_code == 200
    assert "threads" in resp.json()


async def test_list_threads_includes_created(app):
    """Created threads appear in the list response."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/threads", json={"objective": "list me"})
        resp = await client.get("/api/v1/threads")
    data = resp.json()
    objectives = [t["objective"] for t in data["threads"]]
    assert "list me" in objectives


async def test_get_thread_not_found(app):
    """Unknown thread_id returns 404."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/threads/nonexistent-id")
    assert resp.status_code == 404


async def test_get_thread(app):
    """Created thread can be retrieved by ID."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post("/api/v1/threads", json={"objective": "fetch me"})
        thread_id = create_resp.json()["thread_id"]
        resp = await client.get(f"/api/v1/threads/{thread_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["thread_id"] == thread_id
    assert data["objective"] == "fetch me"
    assert "events" in data


async def test_delete_thread(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create a thread first
        resp = await client.post("/api/v1/threads", json={"objective": "to delete"})
        tid = resp.json()["thread_id"]
        # Delete it
        resp = await client.delete(f"/api/v1/threads/{tid}")
        assert resp.status_code == 204
        # Verify it's gone
        resp = await client.get(f"/api/v1/threads/{tid}")
        assert resp.status_code == 404


async def test_delete_nonexistent_thread(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.delete("/api/v1/threads/nonexistent")
        assert resp.status_code == 404
