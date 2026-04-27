import os
import tempfile

import pytest
from atrium.streaming.events import EventRecorder


@pytest.fixture
def recorder():
    return EventRecorder()


@pytest.fixture
def sqlite_recorder():
    """Recorder with SQLite persistence in a temp file."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    recorder = EventRecorder(db_path=path)
    yield recorder
    os.unlink(path)


async def test_emit_creates_event(recorder):
    evt = await recorder.emit("t1", "THREAD_CREATED", {"objective": "test"})
    assert evt.thread_id == "t1"
    assert evt.type == "THREAD_CREATED"
    assert evt.sequence == 1
    assert evt.payload["objective"] == "test"


async def test_emit_increments_sequence(recorder):
    e1 = await recorder.emit("t1", "A", {})
    e2 = await recorder.emit("t1", "B", {})
    e3 = await recorder.emit("t1", "C", {})
    assert e1.sequence == 1
    assert e2.sequence == 2
    assert e3.sequence == 3


async def test_separate_threads_have_independent_sequences(recorder):
    await recorder.emit("t1", "A", {})
    await recorder.emit("t1", "B", {})
    e = await recorder.emit("t2", "A", {})
    assert e.sequence == 1


async def test_replay(recorder):
    await recorder.emit("t1", "A", {})
    await recorder.emit("t1", "B", {})
    await recorder.emit("t1", "C", {})
    events = recorder.replay("t1", since_sequence=1)
    assert len(events) == 2
    assert events[0].type == "B"
    assert events[1].type == "C"


async def test_replay_empty_thread(recorder):
    events = recorder.replay("nonexistent", since_sequence=0)
    assert events == []


async def test_causation_id(recorder):
    e1 = await recorder.emit("t1", "A", {})
    e2 = await recorder.emit("t1", "B", {}, causation_id=e1.event_id)
    assert e2.causation_id == e1.event_id


async def test_sqlite_persistence(sqlite_recorder):
    await sqlite_recorder.emit("t1", "A", {"key": "val"})
    await sqlite_recorder.emit("t1", "B", {"key": "val2"})

    # Create a NEW recorder pointing at same DB — simulates server restart
    new_recorder = EventRecorder(db_path=sqlite_recorder._db_path)
    events = new_recorder.replay("t1")
    assert len(events) == 2
    assert events[0].type == "A"
    assert events[1].type == "B"


async def test_sqlite_list_thread_ids(sqlite_recorder):
    await sqlite_recorder.emit("t1", "A", {})
    await sqlite_recorder.emit("t2", "B", {})
    ids = sqlite_recorder.list_thread_ids()
    assert set(ids) == {"t1", "t2"}


async def test_sqlite_payload_roundtrip(sqlite_recorder):
    """Payloads survive JSON serialization through SQLite."""
    await sqlite_recorder.emit("t1", "A", {"nested": {"x": 1}, "lst": [1, 2, 3]})

    new_recorder = EventRecorder(db_path=sqlite_recorder._db_path)
    events = new_recorder.replay("t1")
    assert events[0].payload == {"nested": {"x": 1}, "lst": [1, 2, 3]}


async def test_sqlite_causation_id_roundtrip(sqlite_recorder):
    """causation_id is persisted and restored correctly."""
    e1 = await sqlite_recorder.emit("t1", "A", {})
    await sqlite_recorder.emit("t1", "B", {}, causation_id=e1.event_id)

    new_recorder = EventRecorder(db_path=sqlite_recorder._db_path)
    events = new_recorder.replay("t1")
    assert events[1].causation_id == e1.event_id


async def test_in_memory_recorder_unaffected():
    """EventRecorder() with no db_path still works exactly as before."""
    recorder = EventRecorder()
    e = await recorder.emit("t1", "X", {"v": 1})
    assert e.sequence == 1
    assert recorder.replay("t1") == [e]
    assert recorder.list_thread_ids() == ["t1"]
