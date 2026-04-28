"""HITL control routes — pause, resume, cancel, approve, reject, input."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from atrium.api.schemas import ActionResponse, HumanInputRequest

router = APIRouter()


def _get_controller(thread_id: str):
    """Get the ThreadController from the orchestrator instance."""
    from atrium.api.app import get_orchestrator
    orchestrator = get_orchestrator()
    if orchestrator is None:
        return None
    return orchestrator.get_controller(thread_id)


async def _require_thread(thread_id: str) -> None:
    from atrium.api.app import get_thread_store
    thread_store = get_thread_store()
    if thread_store is None:
        raise HTTPException(status_code=503, detail="Thread store not available")
    thread = await thread_store.get(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")


@router.post("/threads/{thread_id}/pause", response_model=ActionResponse)
async def pause_thread(thread_id: str) -> ActionResponse:
    """Pause a running thread."""
    await _require_thread(thread_id)
    controller = _get_controller(thread_id)
    if controller:
        controller.pause()
        from atrium.api.app import get_recorder
        recorder = get_recorder()
        if recorder:
            await recorder.emit(thread_id, "THREAD_PAUSED", {"by": "operator"})
    return ActionResponse(thread_id=thread_id, accepted=controller is not None)


@router.post("/threads/{thread_id}/resume", response_model=ActionResponse)
async def resume_thread(thread_id: str) -> ActionResponse:
    """Resume a paused thread."""
    await _require_thread(thread_id)
    controller = _get_controller(thread_id)
    if controller:
        controller.resume()
        from atrium.api.app import get_recorder
        recorder = get_recorder()
        if recorder:
            await recorder.emit(thread_id, "THREAD_RUNNING", {"resumed_by": "operator"})
    return ActionResponse(thread_id=thread_id, accepted=controller is not None)


@router.post("/threads/{thread_id}/cancel", response_model=ActionResponse)
async def cancel_thread(thread_id: str) -> ActionResponse:
    """Cancel a running or paused thread."""
    await _require_thread(thread_id)
    controller = _get_controller(thread_id)
    if controller:
        controller.cancel()
    return ActionResponse(thread_id=thread_id, accepted=controller is not None)


@router.post("/threads/{thread_id}/approve", response_model=ActionResponse)
async def approve_thread(thread_id: str) -> ActionResponse:
    """Approve a pending HITL checkpoint."""
    await _require_thread(thread_id)
    controller = _get_controller(thread_id)
    if controller:
        controller.approve()
    return ActionResponse(thread_id=thread_id, accepted=controller is not None)


@router.post("/threads/{thread_id}/reject", response_model=ActionResponse)
async def reject_thread(thread_id: str) -> ActionResponse:
    """Reject a pending HITL checkpoint."""
    await _require_thread(thread_id)
    controller = _get_controller(thread_id)
    if controller:
        controller.reject()
    return ActionResponse(thread_id=thread_id, accepted=controller is not None)


@router.post("/threads/{thread_id}/input", response_model=ActionResponse)
async def human_input(thread_id: str, body: HumanInputRequest) -> ActionResponse:
    """Accept human input for a waiting thread."""
    await _require_thread(thread_id)
    controller = _get_controller(thread_id)
    if controller:
        controller.submit_input(body.input)
    return ActionResponse(thread_id=thread_id, accepted=controller is not None)
