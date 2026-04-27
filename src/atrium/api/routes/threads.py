"""Thread CRUD + SSE streaming routes."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from atrium.streaming.bus import format_sse, format_sse_end

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from atrium.api.schemas import (
    CreateThreadRequest,
    EventResponse,
    ThreadListResponse,
    ThreadResponse,
)
from atrium.core.models import Thread

router = APIRouter()

# In-memory thread store: thread_id -> Thread
_threads: dict[str, Thread] = {}


def _thread_to_response(thread: Thread, request_base_url: str = "") -> ThreadResponse:
    return ThreadResponse(
        thread_id=thread.thread_id,
        title=thread.title or thread.objective[:60],
        objective=thread.objective,
        status=thread.status.value,
        created_at=thread.created_at,
        stream_url=f"/api/v1/threads/{thread.thread_id}/stream",
    )


async def _run_orchestrator(thread_id: str, objective: str) -> None:
    """Background task: run the orchestrator and update the stored thread."""
    from atrium.api.app import get_orchestrator

    orchestrator = get_orchestrator()
    if orchestrator is None:
        return
    try:
        await orchestrator.run(objective=objective, thread_id=thread_id)
    except Exception:
        pass  # errors are emitted as events; don't crash the background task


@router.post("/threads", response_model=ThreadResponse, status_code=201)
async def create_thread(body: CreateThreadRequest) -> ThreadResponse:
    """Create a new thread, kick off orchestration in the background, return immediately."""
    thread = Thread(objective=body.objective)
    _threads[thread.thread_id] = thread
    asyncio.create_task(_run_orchestrator(thread.thread_id, body.objective))
    return _thread_to_response(thread)


@router.get("/threads", response_model=ThreadListResponse)
async def list_threads() -> ThreadListResponse:
    """Return all known threads."""
    return ThreadListResponse(
        threads=[_thread_to_response(t) for t in _threads.values()]
    )


@router.get("/threads/{thread_id}", response_model=dict)
async def get_thread(thread_id: str) -> dict[str, Any]:
    """Return thread detail including all recorded events."""
    thread = _threads.get(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    from atrium.api.app import get_recorder

    recorder = get_recorder()
    events: list[dict] = []
    if recorder is not None:
        raw_events = recorder.replay(thread_id)
        events = [
            EventResponse(
                event_id=e.event_id,
                type=e.type,
                payload=e.payload,
                sequence=e.sequence,
                timestamp=e.timestamp,
                causation_id=e.causation_id,
            ).model_dump(mode="json")
            for e in raw_events
        ]

    resp = _thread_to_response(thread).model_dump(mode="json")
    resp["events"] = events
    return resp


@router.get("/threads/{thread_id}/stream")
async def stream_thread(thread_id: str) -> StreamingResponse:
    """SSE endpoint — streams events for a thread as they are emitted."""
    if thread_id not in _threads:
        raise HTTPException(status_code=404, detail="Thread not found")

    from atrium.api.app import get_recorder

    recorder = get_recorder()

    async def _event_generator():
        if recorder is None:
            yield format_sse_end()
            return
        async for event in recorder.subscribe(thread_id):
            yield format_sse(event)
        yield format_sse_end()

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
