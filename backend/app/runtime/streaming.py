"""Async streaming bus for thread events.

Threads emit events into a `ThreadStream`. Each subscriber gets a queue with
its own cursor so the SSE handler can fan out without blocking the producer.
Events are kept on the thread for replay (`since_sequence`).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Optional
from uuid import UUID, uuid4


@dataclass(slots=True)
class StreamEvent:
    event_id: str
    thread_id: str
    org_id: str
    type: str
    payload: dict[str, Any]
    sequence: int
    timestamp: str
    causation_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "thread_id": self.thread_id,
            "org_id": self.org_id,
            "type": self.type,
            "payload": self.payload,
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "causation_id": self.causation_id,
        }


class ThreadStream:
    """Append-only event log per thread with fan-out pubsub."""

    def __init__(self, *, thread_id: UUID, org_id: UUID, objective: str, title: str):
        self.thread_id = thread_id
        self.org_id = org_id
        self.objective = objective
        self.title = title
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.status: str = "CREATED"
        self._events: list[StreamEvent] = []
        self._sequence = 0
        self._subscribers: set[asyncio.Queue[StreamEvent]] = set()
        self._lock = asyncio.Lock()
        self._completed = asyncio.Event()

    @property
    def latest_sequence(self) -> int:
        return self._sequence

    @property
    def is_complete(self) -> bool:
        return self._completed.is_set()

    def snapshot(self) -> dict[str, Any]:
        return {
            "thread_id": str(self.thread_id),
            "org_id": str(self.org_id),
            "title": self.title,
            "objective": self.objective,
            "status": self.status,
            "created_at": self.created_at,
            "latest_sequence": self._sequence,
            "is_complete": self.is_complete,
        }

    def events_after(self, sequence: int) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self._events if e.sequence > sequence]

    async def emit(
        self,
        event_type: str,
        payload: dict[str, Any],
        causation_id: Optional[UUID] = None,
    ) -> StreamEvent:
        async with self._lock:
            self._sequence += 1
            event = StreamEvent(
                event_id=str(uuid4()),
                thread_id=str(self.thread_id),
                org_id=str(self.org_id),
                type=event_type,
                payload=dict(payload),
                sequence=self._sequence,
                timestamp=datetime.now(timezone.utc).isoformat(),
                causation_id=str(causation_id) if causation_id else None,
            )
            self._events.append(event)
            # Update lifecycle hints from canonical events.
            if event_type == "THREAD_PLANNING_STARTED":
                self.status = "PLANNING"
            elif event_type == "THREAD_RUNNING":
                self.status = "RUNNING"
            elif event_type == "THREAD_COMPLETED":
                self.status = "COMPLETED"
            elif event_type == "THREAD_FAILED":
                self.status = "FAILED"
            elif event_type == "THREAD_CANCELLED":
                self.status = "CANCELLED"

        for queue in list(self._subscribers):
            await queue.put(event)
        return event

    async def mark_complete(self) -> None:
        self._completed.set()
        for queue in list(self._subscribers):
            await queue.put(_SENTINEL)

    async def subscribe(self, *, since_sequence: int = 0) -> AsyncIterator[StreamEvent]:
        queue: asyncio.Queue[StreamEvent] = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            for event in self._events:
                if event.sequence > since_sequence:
                    yield event
            if self.is_complete and queue.empty():
                return
            while True:
                event = await queue.get()
                if event is _SENTINEL:
                    return
                if event.sequence > since_sequence:
                    yield event
        finally:
            self._subscribers.discard(queue)


# Sentinel used to terminate subscribers when the stream completes.
class _Sentinel:
    pass


_SENTINEL: Any = _Sentinel()


@dataclass(slots=True)
class ThreadHandle:
    """Public, JSON-serializable handle returned to API clients."""

    thread_id: str
    title: str
    objective: str
    status: str
    created_at: str

    @classmethod
    def from_stream(cls, stream: ThreadStream) -> "ThreadHandle":
        return cls(
            thread_id=str(stream.thread_id),
            title=stream.title,
            objective=stream.objective,
            status=stream.status,
            created_at=stream.created_at,
        )


@dataclass(slots=True)
class StreamRegistry:
    """In-process registry of live thread streams."""

    streams: dict[str, ThreadStream] = field(default_factory=dict)

    def add(self, stream: ThreadStream) -> None:
        self.streams[str(stream.thread_id)] = stream

    def get(self, thread_id: str) -> Optional[ThreadStream]:
        return self.streams.get(thread_id)

    def list(self) -> list[dict[str, Any]]:
        return [stream.snapshot() for stream in self.streams.values()]
