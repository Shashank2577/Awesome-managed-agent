from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from backend.app.models.domain import Event


@dataclass(slots=True)
class EventCursor:
    sequence: int = 0


class InMemoryEventBus:
    """Simple per-thread event stream for runtime wiring and tests."""

    def __init__(self):
        self._events: list[Event] = []
        self._cursor_by_thread: dict[UUID, EventCursor] = {}

    def emit(
        self,
        *,
        org_id: UUID,
        thread_id: UUID,
        event_type: str,
        payload: dict[str, Any],
        causation_id: UUID | None = None,
        correlation_id: UUID | None = None,
    ) -> Event:
        cursor = self._cursor_by_thread.setdefault(thread_id, EventCursor(sequence=0))
        cursor.sequence += 1

        event = Event(
            event_id=uuid4(),
            org_id=org_id,
            thread_id=thread_id,
            type=event_type,
            payload={
                "sequence": cursor.sequence,
                **payload,
            },
            timestamp=datetime.now(timezone.utc),
            causation_id=causation_id,
            correlation_id=correlation_id,
        )
        self._events.append(event)
        return event

    def list_events(self, thread_id: UUID) -> list[Event]:
        return [event for event in self._events if event.thread_id == thread_id]
