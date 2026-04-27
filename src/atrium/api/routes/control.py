"""HITL control routes — pause, resume, cancel, approve, reject, input."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from atrium.api.schemas import ActionResponse, HumanInputRequest

router = APIRouter()


def _require_thread(thread_id: str) -> None:
    from atrium.api.routes.threads import _threads

    if thread_id not in _threads:
        raise HTTPException(status_code=404, detail="Thread not found")


@router.post("/threads/{thread_id}/pause", response_model=ActionResponse)
async def pause_thread(thread_id: str) -> ActionResponse:
    """Pause a running thread (stub for v1)."""
    _require_thread(thread_id)
    return ActionResponse(thread_id=thread_id, accepted=True)


@router.post("/threads/{thread_id}/resume", response_model=ActionResponse)
async def resume_thread(thread_id: str) -> ActionResponse:
    """Resume a paused thread (stub for v1)."""
    _require_thread(thread_id)
    return ActionResponse(thread_id=thread_id, accepted=True)


@router.post("/threads/{thread_id}/cancel", response_model=ActionResponse)
async def cancel_thread(thread_id: str) -> ActionResponse:
    """Cancel a thread (stub for v1)."""
    _require_thread(thread_id)
    return ActionResponse(thread_id=thread_id, accepted=True)


@router.post("/threads/{thread_id}/approve", response_model=ActionResponse)
async def approve_thread(thread_id: str) -> ActionResponse:
    """Approve a pending HITL checkpoint (stub for v1)."""
    _require_thread(thread_id)
    return ActionResponse(thread_id=thread_id, accepted=True)


@router.post("/threads/{thread_id}/reject", response_model=ActionResponse)
async def reject_thread(thread_id: str) -> ActionResponse:
    """Reject a pending HITL checkpoint (stub for v1)."""
    _require_thread(thread_id)
    return ActionResponse(thread_id=thread_id, accepted=False)


@router.post("/threads/{thread_id}/input", response_model=ActionResponse)
async def human_input(thread_id: str, body: HumanInputRequest) -> ActionResponse:
    """Accept human input for a waiting thread (stub for v1)."""
    _require_thread(thread_id)
    return ActionResponse(thread_id=thread_id, accepted=True)
