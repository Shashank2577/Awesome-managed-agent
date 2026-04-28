"""Append-only event recorder with per-thread sequencing, aiosqlite persistence, and fan-out."""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

import aiosqlite

from atrium.core.models import AtriumEvent


_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id     TEXT PRIMARY KEY,
    thread_id    TEXT NOT NULL,
    type         TEXT NOT NULL,
    payload      TEXT NOT NULL,
    sequence     INTEGER NOT NULL,
    timestamp    TEXT NOT NULL,
    causation_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_thread_seq ON events(thread_id, sequence);
"""


class EventRecorder:
    """Records events per-thread with monotonic sequencing, fan-out, and aiosqlite persistence.

    Single-writer pattern: all writes go through ``_write_lock``.
    Reads (replay, list_thread_ids) are lock-free.
    """

    def __init__(self, db_path: str | None = None) -> None:
        self._events: dict[str, list[AtriumEvent]] = defaultdict(list)
        self._sequences: dict[str, int] = defaultdict(int)
        self._lock: asyncio.Lock = asyncio.Lock()
        self._write_lock: asyncio.Lock = asyncio.Lock()
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def open(self) -> None:
        """Open aiosqlite connection and apply schema. Call once at startup."""
        if self._db_path and self._db is None:
            self._db = await aiosqlite.connect(self._db_path)
            await self._db.executescript(_SCHEMA)
            await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    # ------------------------------------------------------------------
    # Backward-compat: allow sync construction for existing tests / CLI
    # that never call open(). In that case we fall back to in-memory only.
    # ------------------------------------------------------------------

    def _ensure_sync_db(self) -> None:
        """Bootstraps synchronous SQLite if aiosqlite hasn't been opened yet
        (legacy path for code that constructs EventRecorder without awaiting open()).
        This path is deprecated and will be removed in Phase 1.
        """
        # noop — in-memory fallback is already the default

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

        # Persist to aiosqlite (single-writer)
        if self._db is not None:
            async with self._write_lock:
                await self._db.execute(
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
                await self._db.commit()

        # Fan-out to subscribers
        for queue in self._subscribers[thread_id]:
            await queue.put(event)

        return event

    def replay(self, thread_id: str, since_sequence: int = 0) -> list[AtriumEvent]:
        """Return all events for thread_id with sequence > since_sequence (in-memory)."""
        return [e for e in self._events.get(thread_id, []) if e.sequence > since_sequence]

    async def replay_from_db(
        self, thread_id: str, since_sequence: int = 0
    ) -> list[AtriumEvent]:
        """Load events from aiosqlite for historical threads not in memory."""
        if self._db is None:
            return self.replay(thread_id, since_sequence)
        cursor = await self._db.execute(
            "SELECT event_id, thread_id, type, payload, sequence, timestamp, causation_id "
            "FROM events WHERE thread_id = ? AND sequence > ? ORDER BY sequence",
            (thread_id, since_sequence),
        )
        events = []
        async for row in cursor:
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
        # Merge with in-memory (may be ahead of DB)
        in_mem = self.replay(thread_id, since_sequence)
        in_mem_ids = {e.event_id for e in in_mem}
        return events + [e for e in in_mem if e.event_id not in in_mem_ids]

    def list_thread_ids(self) -> list[str]:
        """Return all known thread IDs (in-memory). Use list_thread_ids_from_db for full list."""
        return list(self._events.keys())

    async def list_thread_ids_from_db(self) -> list[str]:
        if self._db is None:
            return self.list_thread_ids()
        cursor = await self._db.execute("SELECT DISTINCT thread_id FROM events")
        ids = {row[0] async for row in cursor}
        ids.update(self._events.keys())
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
