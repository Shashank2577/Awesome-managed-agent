"""EventRecorder — sequenced event store with fan-out to subscribers."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import AsyncGenerator, Optional

from atrium.core.models import AtriumEvent


class EventRecorder:
    """Stores and fans-out AtriumEvents per thread with monotonic sequencing."""

    def __init__(self) -> None:
        self._events: dict[str, list[AtriumEvent]] = defaultdict(list)
        self._sequences: dict[str, int] = defaultdict(int)
        self._lock: asyncio.Lock = asyncio.Lock()
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)

    async def emit(
        self,
        thread_id: str,
        event_type: str,
        payload: dict,
        causation_id: Optional[str] = None,
    ) -> AtriumEvent:
        """Increment sequence under lock, create and store the event, fan-out to queues."""
        async with self._lock:
            self._sequences[thread_id] += 1
            seq = self._sequences[thread_id]
            event = AtriumEvent(
                thread_id=thread_id,
                type=event_type,
                payload=payload,
                sequence=seq,
                causation_id=causation_id,
            )
            self._events[thread_id].append(event)
            for queue in self._subscribers[thread_id]:
                await queue.put(event)
        return event

    def replay(self, thread_id: str, since_sequence: int = 0) -> list[AtriumEvent]:
        """Return all events for thread_id with sequence > since_sequence."""
        return [e for e in self._events.get(thread_id, []) if e.sequence > since_sequence]

    async def subscribe(
        self, thread_id: str, since_sequence: int = 0
    ) -> AsyncGenerator[AtriumEvent, None]:
        """Yield historical events then live events from a queue. None sentinel ends stream."""
        queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            historical = self.replay(thread_id, since_sequence=since_sequence)
            self._subscribers[thread_id].append(queue)

        for event in historical:
            yield event

        while True:
            item = await queue.get()
            if item is None:
                break
            yield item

    async def complete(self, thread_id: str) -> None:
        """Send None sentinel to all subscriber queues for this thread."""
        async with self._lock:
            for queue in self._subscribers[thread_id]:
                await queue.put(None)
