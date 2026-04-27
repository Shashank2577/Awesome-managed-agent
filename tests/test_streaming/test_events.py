import pytest
from atrium.streaming.events import EventRecorder


@pytest.fixture
def recorder():
    return EventRecorder()


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
