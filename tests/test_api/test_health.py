"""Tests for the /health endpoint."""
import pytest
from httpx import AsyncClient, ASGITransport

from atrium.api.app import create_app
from atrium.core.registry import AgentRegistry


@pytest.fixture
def app():
    return create_app(registry=AgentRegistry(), db_path=":memory:")


async def test_health(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


async def test_health_agents_registered(app):
    """Health reports 0 agents when no agents registered."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health")
    data = resp.json()
    assert data["agents_registered"] == 0
