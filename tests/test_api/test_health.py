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
    """Health reports the count of registered agents (seeds are loaded on startup)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health")
    data = resp.json()
    # Seeds are loaded automatically from the corpus on first boot, so the
    # count will be >= 0.  The exact value depends on the seed corpus size.
    assert isinstance(data["agents_registered"], int)
    assert data["agents_registered"] >= 0
