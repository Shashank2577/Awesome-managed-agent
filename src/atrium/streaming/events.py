"""Append-only event recorder with per-thread sequencing and optional SQLite persistence."""
from __future__ import annotations

import asyncio
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from atrium.core.models import AtriumEvent


class EventRecorder:
    """Records events per-thread with monotonic sequencing, fan-out, and SQLite persistence."""

    def __init__(self, db_path: str | None = None) -> None:
        self._events: dict[str, list[AtriumEvent]] = defaultdict(list)
        self._sequences: dict[str, int] = defaultdict(int)
        self._lock: asyncio.Lock = asyncio.Lock()
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)

        # SQLite persistence
        self._db_path = db_path
        self._db: sqlite3.Connection | None = None
        if db_path:
            self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite database and create tables if needed."""
        self._db = sqlite3.connect(self._db_path, check_same_thread=False)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                type TEXT NOT NULL,
                payload TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                causation_id TEXT
            )
        """)
        self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_thread_seq
            ON events(thread_id, sequence)
        """)
        self._db.commit()

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

        # Persist to SQLite
        if self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO events "
                "(event_id, thread_id, type, payload, sequence, timestamp, causation_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event.event_id,
                    event.thread_id,
                    event.type,
                    json.dumps(event.payload),
                    event.sequence,
                    event.timestamp.isoformat(),
                    event.causation_id,
                ),
            )
            self._db.commit()

        # Fan-out to subscribers
        for queue in self._subscribers[thread_id]:
            await queue.put(event)

        return event

    def replay(self, thread_id: str, since_sequence: int = 0) -> list[AtriumEvent]:
        """Return all events for thread_id with sequence > since_sequence."""
        in_mem = [e for e in self._events.get(thread_id, []) if e.sequence > since_sequence]
        if in_mem:
            return in_mem

        # Fall back to SQLite for historical threads not in memory
        if self._db:
            return self._load_from_db(thread_id, since_sequence)
        return []

    def _load_from_db(self, thread_id: str, since_sequence: int = 0) -> list[AtriumEvent]:
        """Load events from SQLite for a given thread."""
        if not self._db:
            return []
        cursor = self._db.execute(
            "SELECT event_id, thread_id, type, payload, sequence, timestamp, causation_id "
            "FROM events WHERE thread_id = ? AND sequence > ? ORDER BY sequence",
            (thread_id, since_sequence),
        )
        events = []
        for row in cursor:
            events.append(
                AtriumEvent(
                    event_id=row[0],
                    thread_id=row[1],
                    type=row[2],
                    payload=json.loads(row[3]),
                    sequence=row[4],
                    timestamp=datetime.fromisoformat(row[5]),
                    causation_id=row[6],
                )
            )
        return events

    def list_thread_ids(self) -> list[str]:
        """Return all known thread IDs (in-memory + SQLite)."""
        ids = set(self._events.keys())
        if self._db:
            cursor = self._db.execute("SELECT DISTINCT thread_id FROM events")
            for row in cursor:
                ids.add(row[0])
        return list(ids)

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
