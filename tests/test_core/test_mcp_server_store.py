"""MCPServerStore acceptance tests."""
import pytest
from atrium.core.mcp_server_store import MCPServerStore


@pytest.fixture
async def store(tmp_path):
    s = MCPServerStore(str(tmp_path / "mcp.db"))
    await s.open()
    yield s
    await s.close()


async def test_register_returns_server_with_id(store):
    s = await store.register("ws1", "github", "stdio", "npx -y @modelcontextprotocol/server-github")
    assert s.mcp_server_id
    assert s.name == "github"
    assert s.workspace_id == "ws1"


async def test_list_for_workspace_returns_registered(store):
    await store.register("ws1", "github", "stdio", "npx foo")
    await store.register("ws1", "linear", "http", "https://mcp.linear.app")
    servers = await store.list_for_workspace("ws1")
    names = {s.name for s in servers}
    assert "github" in names and "linear" in names


async def test_list_for_workspace_isolates_across_workspaces(store):
    await store.register("ws1", "github", "stdio", "cmd")
    servers = await store.list_for_workspace("ws2")
    assert servers == []


async def test_get_by_name_returns_correct_server(store):
    await store.register("ws1", "github", "stdio", "cmd")
    s = await store.get_by_name("ws1", "github")
    assert s is not None
    assert s.transport == "stdio"


async def test_delete_removes_server(store):
    await store.register("ws1", "github", "stdio", "cmd")
    deleted = await store.delete("ws1", "github")
    assert deleted is True
    assert await store.get_by_name("ws1", "github") is None


async def test_delete_returns_false_for_missing(store):
    deleted = await store.delete("ws1", "nonexistent")
    assert deleted is False


async def test_names_for_workspace_returns_set(store):
    await store.register("ws1", "a", "stdio", "cmd")
    await store.register("ws1", "b", "http", "http://example.com")
    names = await store.names_for_workspace("ws1")
    assert names == {"a", "b"}
