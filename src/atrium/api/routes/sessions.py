"""Session management routes — list, get, pause, resume.

POST /api/v1/sessions/{id}/pause
POST /api/v1/sessions/{id}/resume
GET  /api/v1/sessions
GET  /api/v1/sessions/{id}
"""
from __future__ import annotations

import asyncio
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atrium.harness.session import SessionStatus, Session

try:
    from atrium.api.auth import require_workspace
    from atrium.api.state import AppState
    from atrium.core.workspace_store import Workspace
except ImportError:
    require_workspace = None  # type: ignore[assignment]
    AppState = None  # type: ignore[assignment]
    Workspace = None  # type: ignore[assignment]

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])

# Timeout for waiting for a clean pause (seconds)
_PAUSE_TIMEOUT = 30.0


class SessionResponse(BaseModel):
    session_id: str
    workspace_id: str
    title: str
    objective: str
    status: str
    runtime: str
    model: str
    container_id: Optional[str]
    created_at: str
    last_active_at: str


def _sess_response(s: Session) -> SessionResponse:
    return SessionResponse(
        session_id=s.session_id,
        workspace_id=s.workspace_id,
        title=s.title,
        objective=s.objective,
        status=s.status.value,
        runtime=s.runtime,
        model=s.model,
        container_id=s.container_id,
        created_at=s.created_at.isoformat(),
        last_active_at=s.last_active_at.isoformat(),
    )


@router.get("", response_model=list[SessionResponse])
async def list_sessions(
    status: Optional[str] = None,
    workspace: "Workspace" = Depends(require_workspace),
    state: "AppState" = Depends(lambda: AppState.instance()),
) -> list[SessionResponse]:
    sess_store = state.session_store
    if sess_store is None:
        return []
    status_filter = SessionStatus(status) if status else None
    sessions = await sess_store.list_by_workspace(workspace.workspace_id, status_filter)
    return [_sess_response(s) for s in sessions]


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    workspace: "Workspace" = Depends(require_workspace),
    state: "AppState" = Depends(lambda: AppState.instance()),
) -> SessionResponse:
    sess_store = state.session_store
    if sess_store is None:
        raise HTTPException(503, "Session store not available")
    session = await sess_store.get(workspace.workspace_id, session_id)
    if session is None:
        raise HTTPException(404, "Session not found")
    return _sess_response(session)


@router.post("/{session_id}/pause", status_code=202)
async def pause_session(
    session_id: str,
    workspace: "Workspace" = Depends(require_workspace),
    state: "AppState" = Depends(lambda: AppState.instance()),
) -> dict:
    """Signal the sandbox to checkpoint and exit, then mark PAUSED.

    Implementation: writes .atrium/please_pause inside the workspace.
    The entrypoint polls this file and checkpoints before exiting.
    """
    sess_store = state.session_store
    if sess_store is None:
        raise HTTPException(503, "Session store not available")
    session = await sess_store.get(workspace.workspace_id, session_id)
    if session is None:
        raise HTTPException(404, "Session not found")
    if session.status != SessionStatus.RUNNING:
        raise HTTPException(409, f"Cannot pause a session in status {session.status.value}")

    # Write the pause signal file
    try:
        pause_signal = session.pause_signal_path
        pause_signal.parent.mkdir(parents=True, exist_ok=True)
        pause_signal.write_text("pause\n")
    except OSError:
        pass  # best-effort

    # Wait for the session to transition to PAUSED (the container will exit)
    # In production, the bridge's run() loop detects HARNESS_CHECKPOINT + exit
    # and transitions status. For the API, we do a simple poll.
    deadline = asyncio.get_event_loop().time() + _PAUSE_TIMEOUT
    while asyncio.get_event_loop().time() < deadline:
        refreshed = await sess_store.get(workspace.workspace_id, session_id)
        if refreshed and refreshed.status in (SessionStatus.PAUSED, SessionStatus.FAILED, SessionStatus.COMPLETED):
            if refreshed.status == SessionStatus.PAUSED:
                await state.recorder.emit(
                    session_id, "SESSION_PAUSED", {"workspace_id": workspace.workspace_id}
                )
                return {"status": "paused", "session_id": session_id}
            break
        await asyncio.sleep(0.5)

    # Timeout — mark failed
    try:
        await sess_store.set_status(workspace.workspace_id, session_id, SessionStatus.FAILED)
        await sess_store.set_error_code(workspace.workspace_id, session_id, "pause_timeout")
        await state.recorder.emit(
            session_id, "SESSION_FAILED",
            {"error": "pause_timeout", "error_code": "pause_timeout"}
        )
    except Exception:
        pass
    raise HTTPException(504, "Session did not pause within timeout — marked FAILED")


@router.post("/{session_id}/resume", status_code=202)
async def resume_session(
    session_id: str,
    workspace: "Workspace" = Depends(require_workspace),
    state: "AppState" = Depends(lambda: AppState.instance()),
) -> dict:
    """Resume a PAUSED or FAILED session using its workspace checkpoint."""
    sess_store = state.session_store
    if sess_store is None:
        raise HTTPException(503, "Session store not available")
    session = await sess_store.get(workspace.workspace_id, session_id)
    if session is None:
        raise HTTPException(404, "Session not found")

    # Only PAUSED and FAILED can be resumed
    if session.status in (SessionStatus.COMPLETED, SessionStatus.CANCELLED):
        raise HTTPException(409, f"Cannot resume a session in status {session.status.value}")
    if session.status not in (SessionStatus.PAUSED, SessionStatus.FAILED):
        raise HTTPException(409, f"Session is not paused or failed (status: {session.status.value})")

    # Check workspace exists (or was restored from durable storage)
    if not session.workspace_dir.exists():
        raise HTTPException(
            422,
            "Workspace directory missing — cannot resume. "
            "Restore from S3 first or start a new session."
        )

    # Remove pause signal if present
    try:
        if session.pause_signal_path.exists():
            session.pause_signal_path.unlink()
    except OSError:
        pass

    # Transition to RUNNING
    try:
        await sess_store.set_status(workspace.workspace_id, session_id, SessionStatus.RUNNING)
    except Exception as exc:
        raise HTTPException(409, f"Cannot resume: {exc}")

    await state.recorder.emit(
        session_id,
        "SESSION_RESUMED",
        {
            "workspace_id": workspace.workspace_id,
            "previous_status": session.status.value,
            "checkpoint_exists": session.checkpoint_path.exists(),
        },
    )

    # Boot a fresh sandbox with ATRIUM_CHECKPOINT_PATH set
    # (actual sandbox start is delegated to a background task in production)
    checkpoint_path = str(session.checkpoint_path) if session.checkpoint_path.exists() else None

    return {
        "status": "resuming",
        "session_id": session_id,
        "checkpoint_available": checkpoint_path is not None,
    }
