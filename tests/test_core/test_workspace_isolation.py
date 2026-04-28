"""Phase 1 acceptance tests — WorkspaceStore, auth helpers."""
import pytest
from atrium.core.auth import (
    ApiKeyKind,
    Workspace,
    WorkspaceQuota,
    generate_secret,
    hash_secret,
    verify_secret,
)
from atrium.core.workspace_store import WorkspaceStore
from atrium.core.storage.sqlite import SQLiteStorage


@pytest.fixture
async def store(tmp_path):
    s = SQLiteStorage(f"sqlite:///{tmp_path}/ws.db")
    await s.init()
    ws = WorkspaceStore(s)
    await ws.init_schema()
    yield ws
    await s.close()


async def test_create_workspace_returns_workspace_with_quota_defaults(store):
    ws = await store.create_workspace("acme")
    assert ws.workspace_id.startswith("ws_")
    assert ws.name == "acme"
    assert ws.quota.max_concurrent_sessions == 10


async def test_get_workspace_round_trips(store):
    ws = await store.create_workspace("acme")
    fetched = await store.get_workspace(ws.workspace_id)
    assert fetched is not None
    assert fetched.workspace_id == ws.workspace_id
    assert fetched.name == "acme"


async def test_list_workspaces(store):
    await store.create_workspace("a")
    await store.create_workspace("b")
    wss = await store.list_workspaces()
    names = {w.name for w in wss}
    assert "a" in names and "b" in names


async def test_update_quota_persists(store):
    ws = await store.create_workspace("acme")
    new_quota = WorkspaceQuota(max_monthly_spend_usd=500.0)
    await store.update_quota(ws.workspace_id, new_quota)
    fetched = await store.get_workspace(ws.workspace_id)
    assert fetched.quota.max_monthly_spend_usd == 500.0


async def test_delete_workspace(store):
    ws = await store.create_workspace("bye")
    await store.delete_workspace(ws.workspace_id)
    assert await store.get_workspace(ws.workspace_id) is None


async def test_issue_key_returns_secret_only_once(store):
    ws = await store.create_workspace("k")
    key, secret = await store.issue_key(ws.workspace_id, ApiKeyKind.WORKSPACE, "my key")
    assert len(secret) == 64  # 32 hex bytes
    assert key.hash == hash_secret(secret)
    # The secret is not stored; looking up again requires the secret
    found = await store.lookup_by_secret(secret)
    assert found is not None
    assert found.api_key_id == key.api_key_id


async def test_lookup_by_secret_returns_none_for_wrong_secret(store):
    ws = await store.create_workspace("k")
    await store.issue_key(ws.workspace_id, ApiKeyKind.WORKSPACE)
    assert await store.lookup_by_secret("bad_secret") is None


async def test_revoke_key_blocks_subsequent_requests(store):
    ws = await store.create_workspace("k")
    key, secret = await store.issue_key(ws.workspace_id, ApiKeyKind.WORKSPACE)
    await store.revoke_key(key.api_key_id)
    found = await store.lookup_by_secret(secret)
    # The key row exists but revoked_at is set
    assert found is not None
    assert found.revoked_at is not None


async def test_list_keys_does_not_return_secrets(store):
    ws = await store.create_workspace("k")
    await store.issue_key(ws.workspace_id, ApiKeyKind.WORKSPACE, "k1")
    await store.issue_key(ws.workspace_id, ApiKeyKind.READ_ONLY, "k2")
    keys = await store.list_keys(ws.workspace_id)
    assert len(keys) == 2
    # Keys have hashes, not plaintext secrets
    for k in keys:
        assert len(k.hash) == 64


async def test_admin_key_has_no_workspace_id(store):
    ws = await store.create_workspace("k")
    key, _ = await store.issue_key(None, ApiKeyKind.ADMIN, "admin")
    assert key.workspace_id is None
    assert key.kind == ApiKeyKind.ADMIN


async def test_generate_secret_length():
    s = generate_secret()
    assert len(s) == 64


async def test_verify_secret_correct():
    s = generate_secret()
    h = hash_secret(s)
    assert verify_secret(s, h) is True


async def test_verify_secret_wrong():
    assert verify_secret("wrong", hash_secret("right")) is False
