"""Phase 0 acceptance tests — ThreadStore persistence."""
from __future__ import annotations

import pytest

from atrium.core.models import Thread, ThreadStatus
from atrium.core.thread_store import ThreadStore


@pytest.fixture
async def store(tmp_path):
    s = ThreadStore(db_path=str(tmp_path / "threads.db"))
    await s.open()
    yield s
    await s.close()


async def test_create_thread_persists_to_db(store):
    t = Thread(objective="test objective")
    await store.create(t)
    fetched = await store.get(t.thread_id)
    assert fetched is not None
    assert fetched.thread_id == t.thread_id
    assert fetched.objective == "test objective"
    assert fetched.status == ThreadStatus.CREATED


async def test_thread_survives_store_reopen(tmp_path):
    db = str(tmp_path / "threads.db")
    t = Thread(objective="survive reopen")

    s1 = ThreadStore(db_path=db)
    await s1.open()
    await s1.create(t)
    await s1.close()

    s2 = ThreadStore(db_path=db)
    await s2.open()
    fetched = await s2.get(t.thread_id)
    await s2.close()

    assert fetched is not None
    assert fetched.objective == "survive reopen"


async def test_set_status_updates_persisted_thread(store):
    t = Thread(objective="status update test")
    await store.create(t)
    await store.set_status(t.thread_id, ThreadStatus.RUNNING)
    fetched = await store.get(t.thread_id)
    assert fetched.status == ThreadStatus.RUNNING


async def test_list_all_returns_all_threads(store):
    t1 = Thread(objective="first")
    t2 = Thread(objective="second")
    await store.create(t1)
    await store.create(t2)
    threads = await store.list_all()
    ids = {t.thread_id for t in threads}
    assert t1.thread_id in ids
    assert t2.thread_id in ids


async def test_delete_thread_removes_from_store(store):
    t = Thread(objective="delete me")
    await store.create(t)
    await store.delete(t.thread_id)
    assert (await store.get(t.thread_id)) is None


async def test_get_returns_none_for_missing_thread(store):
    assert (await store.get("does-not-exist")) is None
