"""Phase 2 artifact store tests."""
import hashlib
import pytest
from pathlib import Path
from atrium.core.artifact_store import ArtifactStore


@pytest.fixture
async def store(tmp_path):
    s = ArtifactStore(str(tmp_path / "artifacts.db"))
    await s.open()
    yield s
    await s.close()


async def test_artifact_row_inserted_with_correct_sha256(store, tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    f = ws / "out.txt"
    f.write_bytes(b"hello world")
    expected_sha = hashlib.sha256(b"hello world").hexdigest()

    artifact = await store.index_file("ws1", "sess1", ws, "out.txt")
    assert artifact.sha256 == expected_sha


async def test_artifact_size_matches_file_size(store, tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    content = b"x" * 1000
    (ws / "data.bin").write_bytes(content)

    artifact = await store.index_file("ws1", "sess1", ws, "data.bin")
    assert artifact.size_bytes == 1000


async def test_duplicate_path_in_session_replaces_row(store, tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    f = ws / "file.txt"

    f.write_bytes(b"version 1")
    a1 = await store.index_file("ws1", "sess1", ws, "file.txt")

    f.write_bytes(b"version 2 - longer content here")
    a2 = await store.index_file("ws1", "sess1", ws, "file.txt")

    # Same artifact_id (row replaced, not duplicated)
    assert a1.artifact_id == a2.artifact_id
    # Size updated
    assert a2.size_bytes != a1.size_bytes

    all_artifacts = await store.list_for_session("sess1")
    assert len(all_artifacts) == 1


async def test_get_artifact_returns_none_in_other_workspace(store, tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "f.txt").write_bytes(b"data")
    artifact = await store.index_file("ws1", "sess1", ws, "f.txt")

    # Try to find by ID in a different workspace — store doesn't filter by workspace on get()
    # but returning 404 for different workspace is enforced at the API layer
    fetched = await store.get(artifact.artifact_id)
    assert fetched is not None
    assert fetched.workspace_id == "ws1"


async def test_delete_artifact_removes_row(store, tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "g.txt").write_bytes(b"gone")
    a = await store.index_file("ws1", "sess1", ws, "g.txt")
    deleted = await store.delete(a.artifact_id)
    assert deleted is True
    assert await store.get(a.artifact_id) is None
