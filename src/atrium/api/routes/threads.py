"""Thread CRUD + SSE streaming routes — backed by persistent ThreadStore."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from atrium.api.schemas import (
    CreateThreadRequest,
    EventResponse,
    ThreadListResponse,
    ThreadResponse,
)
from atrium.core.models import Thread, ThreadStatus
from atrium.streaming.bus import format_sse, format_sse_end

router = APIRouter()


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
    """Background task: run the orchestrator and persist status changes via ThreadStore."""
    from atrium.api.app import get_orchestrator, get_thread_store

    orchestrator = get_orchestrator()
    thread_store = get_thread_store()
    if orchestrator is None:
        return

    if thread_store:
        await thread_store.set_status(thread_id, ThreadStatus.RUNNING)

    try:
        result = await orchestrator.run(objective=objective, thread_id=thread_id)
        if thread_store:
            new_status = (
                ThreadStatus.FAILED
                if result.get("status") == "FAILED"
                else ThreadStatus.COMPLETED
            )
            await thread_store.set_status(thread_id, new_status)
    except Exception:
        if thread_store:
            await thread_store.set_status(thread_id, ThreadStatus.FAILED)


@router.post("/threads", response_model=ThreadResponse, status_code=201)
async def create_thread(body: CreateThreadRequest) -> ThreadResponse:
    """Create a new thread, kick off orchestration in the background, return immediately."""
    from atrium.api.app import get_thread_store

    thread = Thread(objective=body.objective)
    thread_store = get_thread_store()
    if thread_store:
        await thread_store.create(thread)
    asyncio.create_task(_run_orchestrator(thread.thread_id, body.objective))
    return _thread_to_response(thread)


@router.get("/threads", response_model=ThreadListResponse)
async def list_threads() -> ThreadListResponse:
    """Return all known threads (from persistent store)."""
    from atrium.api.app import get_thread_store

    thread_store = get_thread_store()
    if thread_store is None:
        return ThreadListResponse(threads=[])
    threads = await thread_store.list_all()
    return ThreadListResponse(threads=[_thread_to_response(t) for t in threads])


@router.get("/threads/{thread_id}", response_model=dict)
async def get_thread(thread_id: str) -> dict[str, Any]:
    """Return thread detail including all recorded events."""
    from atrium.api.app import get_recorder, get_thread_store

    thread_store = get_thread_store()
    thread = None
    if thread_store:
        thread = await thread_store.get(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    recorder = get_recorder()
    events: list[dict] = []
    if recorder is not None:
        raw_events = await recorder.replay_from_db(thread_id)
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
    from atrium.api.app import get_recorder, get_thread_store

    thread_store = get_thread_store()
    exists = False
    if thread_store:
        exists = (await thread_store.get(thread_id)) is not None
    if not exists:
        raise HTTPException(status_code=404, detail="Thread not found")

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


@router.delete("/threads/{thread_id}", status_code=204)
async def delete_thread(thread_id: str):
    """Cancel and archive a thread."""
    from atrium.api.app import get_thread_store

    thread_store = get_thread_store()
    if thread_store:
        thread = await thread_store.get(thread_id)
        if thread is None:
            raise HTTPException(status_code=404, detail="Thread not found")
        await thread_store.set_status(thread_id, ThreadStatus.CANCELLED)
        await thread_store.delete(thread_id)
    return None
