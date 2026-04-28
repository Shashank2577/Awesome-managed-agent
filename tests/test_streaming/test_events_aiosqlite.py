"""Phase 0 acceptance tests — EventRecorder with aiosqlite."""
from __future__ import annotations

import pytest

from atrium.streaming.events import EventRecorder


@pytest.fixture
async def recorder(tmp_path):
    r = EventRecorder(db_path=str(tmp_path / "events.db"))
    await r.open()
    yield r
    await r.close()


async def test_emit_stores_event_in_memory(recorder):
    event = await recorder.emit("thread-1", "TEST_EVENT", {"key": "val"})
    assert event.thread_id == "thread-1"
    assert event.type == "TEST_EVENT"
    assert event.sequence == 1


async def test_replay_returns_emitted_events(recorder):
    await recorder.emit("t1", "EVT_A", {})
    await recorder.emit("t1", "EVT_B", {})
    events = recorder.replay("t1")
    types = [e.type for e in events]
    assert types == ["EVT_A", "EVT_B"]


async def test_replay_from_db_returns_persisted_events(tmp_path):
    db = str(tmp_path / "events.db")
    r1 = EventRecorder(db_path=db)
    await r1.open()
    await r1.emit("t1", "PING", {"n": 1})
    await r1.emit("t1", "PONG", {"n": 2})
    await r1.close()

    r2 = EventRecorder(db_path=db)
    await r2.open()
    events = await r2.replay_from_db("t1")
    await r2.close()

    assert len(events) == 2
    assert events[0].type == "PING"
    assert events[1].type == "PONG"


async def test_sequence_increments_per_thread(recorder):
    await recorder.emit("t1", "A", {})
    await recorder.emit("t1", "B", {})
    await recorder.emit("t2", "C", {})
    t1_events = recorder.replay("t1")
    t2_events = recorder.replay("t2")
    assert t1_events[-1].sequence == 2
    assert t2_events[-1].sequence == 1


async def test_subscribe_yields_historical_then_live(recorder):
    await recorder.emit("t1", "HIST", {})
    received = []

    async def consumer():
        async for event in recorder.subscribe("t1"):
            received.append(event.type)

    import asyncio
    task = asyncio.create_task(consumer())
    await asyncio.sleep(0)
    await recorder.emit("t1", "LIVE", {})
    await recorder.complete("t1")
    await task

    assert received == ["HIST", "LIVE"]
