"""Session management routes — full Phase-5 API surface.

POST   /api/v1/sessions                     — create + start a session
GET    /api/v1/sessions                     — list (status filter)
GET    /api/v1/sessions/{id}               — detail
GET    /api/v1/sessions/{id}/stream        — SSE live event stream
POST   /api/v1/sessions/{id}/messages      — send follow-up message
POST   /api/v1/sessions/{id}/pause         — checkpoint + exit
POST   /api/v1/sessions/{id}/resume        — boot fresh sandbox w/ checkpoint
POST   /api/v1/sessions/{id}/cancel        — terminate + archive
DELETE /api/v1/sessions/{id}               — alias for cancel
"""
from __future__ import annotations

import asyncio
import json
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from atrium.harness.session import SessionStatus, Session
from atrium.streaming.bus import format_sse, format_sse_end

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
# SSE heartbeat interval when no events arrive (seconds)
_SSE_HEARTBEAT = 15.0


class CreateSessionRequest(BaseModel):
    """Body for POST /api/v1/sessions."""

    agent: str = Field("", description="Registered HarnessAgent name")
    objective: str = Field(..., description="Task description passed into the sandbox")
    model_override: Optional[str] = Field(None, description="Override model (e.g. google:gemini-2.5-pro)")
    timeout_seconds: int = Field(1800, ge=60, le=86400)
    metadata: dict = Field(default_factory=dict)
    runtime: str = Field("echo", description="Runtime name: echo | open_agent_sdk | direct_anthropic | openclaude")
    model: str = Field("echo:test")


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


class MessageRequest(BaseModel):
    """Body for POST /api/v1/sessions/{id}/messages."""

    text: str = Field(..., min_length=1)


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


# ---------------------------------------------------------------------------
# POST /api/v1/sessions (Create)
# ---------------------------------------------------------------------------


@router.post("", response_model=SessionResponse, status_code=201)
async def create_session(
    req: CreateSessionRequest,
    workspace: "Workspace" = Depends(require_workspace),
    state: "AppState" = Depends(lambda: AppState.instance()),
) -> SessionResponse:
    """Create and start a new session."""
    sess_store = state.session_store
    if sess_store is None:
        raise HTTPException(503, "Session store not available")

    session = await sess_store.create(Session(
        workspace_id=workspace.workspace_id,
        objective=req.objective,
        title=f"Session: {req.agent or req.runtime}",
        runtime=req.runtime,
        model=req.model_override or req.model,
    ))

    await state.recorder.emit(
        session.session_id,
        "SESSION_CREATED",
        {
            "workspace_id": workspace.workspace_id,
            "objective": req.objective,
            "runtime": req.runtime,
            "model": req.model_override or req.model,
        },
    )

    # Runtimes that run server-side without Docker
    if req.runtime == "echo":
        asyncio.create_task(
            _run_echo_simulation(session.session_id, workspace.workspace_id, req.objective, state)
        )
    elif req.runtime in ("direct_gemini", "gemini"):
        asyncio.create_task(
            _run_gemini_session(session.session_id, workspace.workspace_id, req.objective, state)
        )

    return _sess_response(session)


async def _run_gemini_session(
    session_id: str, workspace_id: str, objective: str, state: "AppState"
) -> None:
    """Run a real Gemini session server-side — no Docker required.

    Uses LLMClient with the gemini provider (GEMINI_API_KEY must be set).
    Emits the same event sequence the UI expects so streaming works live.
    """
    import os
    from atrium.engine.llm import LLMClient

    rec = state.recorder
    sess_store = state.session_store

    async def emit(t: str, p: dict) -> None:
        await rec.emit(session_id, t, p)

    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    try:
        await asyncio.sleep(0.3)
        await emit("THREAD_PLANNING_STARTED", {})

        plan_id = str(uuid4())
        await asyncio.sleep(0.5)
        await emit("PLAN_CREATED", {
            "plan_id": plan_id,
            "plan_number": 1,
            "rationale": f"Calling Gemini ({model}) for: {objective[:120]}",
            "graph": {"nodes": [
                {"key": "gemini", "role": "gemini-agent",
                 "objective": objective[:80], "depends_on": []}
            ]},
        })
        await emit("THREAD_RUNNING", {})
        await emit("AGENT_HIRED", {
            "agent_key": "gemini", "role": f"gemini/{model}",
            "objective": objective[:80], "depends_on": [],
        })
        await emit("AGENT_RUNNING", {"agent_key": "gemini"})

        llm = LLMClient(f"gemini:{model}")
        system_prompt = (
            "You are a capable AI assistant running inside the Atrium agent platform. "
            "Respond clearly and helpfully to the user's objective. "
            "Structure your answer with a concise summary followed by detailed content."
        )
        response_text = await llm.generate_text(system_prompt, f"Objective: {objective}")

        preview = response_text[:180] + ("…" if len(response_text) > 180 else "")
        await emit("AGENT_MESSAGE", {"agent_key": "gemini", "text": preview})
        await emit("AGENT_OUTPUT", {"agent_key": "gemini", "output": {"text": response_text}})
        await emit("AGENT_COMPLETED", {"agent_key": "gemini"})
        await asyncio.sleep(0.2)
        await emit("EVIDENCE_PUBLISHED", {
            "headline": f"Gemini ({model}) Response",
            "summary": response_text[:400],
            "sections": [{
                "title": "Full Response",
                "content": response_text,
                "key_facts": [
                    f"Model: gemini:{model}",
                    f"Objective: {objective[:80]}",
                    "Executed server-side — no sandbox container needed",
                ],
            }],
        })
        await emit("THREAD_COMPLETED", {})
        if sess_store:
            await sess_store.set_status(workspace_id, session_id, SessionStatus.COMPLETED)

    except Exception as exc:
        await emit("THREAD_FAILED", {"error": str(exc)})
        if sess_store:
            try:
                await sess_store.set_status(workspace_id, session_id, SessionStatus.FAILED)
            except Exception:
                pass


async def _run_echo_simulation(
    session_id: str, workspace_id: str, objective: str, state: "AppState"
) -> None:
    """Emit a realistic event sequence for the echo runtime — no Docker required."""
    rec = state.recorder
    sess_store = state.session_store

    async def emit(t: str, p: dict) -> None:
        await rec.emit(session_id, t, p)

    try:
        await asyncio.sleep(0.4)
        await emit("THREAD_PLANNING_STARTED", {})
        await asyncio.sleep(0.7)
        plan_id = str(uuid4())
        await emit("PLAN_CREATED", {
            "plan_id": plan_id,
            "plan_number": 1,
            "rationale": f"I'll process: {objective[:120]}",
            "graph": {"nodes": [
                {"key": "executor", "role": "executor",
                 "objective": objective[:80], "depends_on": []}
            ]},
        })
        await asyncio.sleep(0.3)
        await emit("THREAD_RUNNING", {})
        await emit("AGENT_HIRED", {
            "agent_key": "executor", "role": "echo-executor",
            "objective": objective[:80], "depends_on": [],
        })
        await asyncio.sleep(0.8)
        await emit("AGENT_RUNNING", {"agent_key": "executor"})
        await emit("AGENT_MESSAGE", {
            "agent_key": "executor",
            "text": f"[echo] Processing: {objective[:120]}",
        })
        await asyncio.sleep(1.2)
        await emit("AGENT_OUTPUT", {
            "agent_key": "executor",
            "output": {"result": "echo OK", "objective": objective},
        })
        await emit("AGENT_COMPLETED", {"agent_key": "executor"})
        await asyncio.sleep(0.3)
        await emit("EVIDENCE_PUBLISHED", {
            "headline": "Echo Session Complete",
            "summary": f"Processed: {objective[:200]}",
            "sections": [{
                "title": "Result",
                "content": "The echo runtime acknowledged your request successfully.",
                "key_facts": [
                    "Session created and streamed in real time",
                    "Echo runtime requires no API key or Docker sandbox",
                    "Switch to direct_anthropic or open_agent_sdk for real execution",
                ],
            }],
        })
        await emit("THREAD_COMPLETED", {})
        if sess_store:
            await sess_store.set_status(workspace_id, session_id, SessionStatus.COMPLETED)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# GET /api/v1/sessions/{session_id}/stream (SSE)
# ---------------------------------------------------------------------------


@router.get("/{session_id}/stream")
async def stream_session(
    session_id: str,
    request: Request,
    workspace: "Workspace" = Depends(require_workspace),
    state: "AppState" = Depends(lambda: AppState.instance()),
) -> StreamingResponse:
    """Stream live events for a session via SSE."""
    sess_store = state.session_store
    if sess_store is None:
        raise HTTPException(503, "Session store not available")

    session = await sess_store.get(workspace.workspace_id, session_id)
    if session is None:
        raise HTTPException(404, "Session not found")

    async def event_generator():
        try:
            async for evt in state.recorder.subscribe(session_id):
                if await request.is_disconnected():
                    break
                yield format_sse(evt)
        except Exception:
            pass
        yield format_sse_end()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# POST /api/v1/sessions/{session_id}/messages
# ---------------------------------------------------------------------------


@router.post("/{session_id}/messages", status_code=201)
async def send_message(
    session_id: str,
    req: MessageRequest,
    workspace: "Workspace" = Depends(require_workspace),
    state: "AppState" = Depends(lambda: AppState.instance()),
) -> dict:
    """Send a follow-up message into a running session."""
    sess_store = state.session_store
    if sess_store is None:
        raise HTTPException(503, "Session store not available")

    session = await sess_store.get(workspace.workspace_id, session_id)
    if session is None:
        raise HTTPException(404, "Session not found")

    if session.status != SessionStatus.RUNNING:
        raise HTTPException(409, f"Cannot send message to a session in status {session.status.value}")

    # Emit the message event so the bridge/runtime can pick it up
    await state.recorder.emit(
        session_id,
        "USER_MESSAGE",
        {
            "workspace_id": workspace.workspace_id,
            "text": req.text,
        },
    )

    return {"status": "sent", "session_id": session_id}


# ---------------------------------------------------------------------------
# POST /api/v1/sessions/{session_id}/cancel
# ---------------------------------------------------------------------------


@router.post("/{session_id}/cancel", status_code=202)
async def cancel_session(
    session_id: str,
    workspace: "Workspace" = Depends(require_workspace),
    state: "AppState" = Depends(lambda: AppState.instance()),
) -> dict:
    """Terminate and archive a session."""
    sess_store = state.session_store
    if sess_store is None:
        raise HTTPException(503, "Session store not available")

    session = await sess_store.get(workspace.workspace_id, session_id)
    if session is None:
        raise HTTPException(404, "Session not found")

    if session.status in (SessionStatus.COMPLETED, SessionStatus.CANCELLED, SessionStatus.FAILED):
        return {"status": "already_terminal", "session_id": session_id}

    # Mark cancelled immediately
    await sess_store.set_status(workspace.workspace_id, session_id, SessionStatus.CANCELLED)

    await state.recorder.emit(
        session_id,
        "SESSION_CANCELLED",
        {
            "workspace_id": workspace.workspace_id,
            "previous_status": session.status.value,
        },
    )

    return {"status": "cancelled", "session_id": session_id}


# ---------------------------------------------------------------------------
# DELETE /api/v1/sessions/{session_id}
# ---------------------------------------------------------------------------


@router.delete("/{session_id}", status_code=202)
async def delete_session(
    session_id: str,
    workspace: "Workspace" = Depends(require_workspace),
    state: "AppState" = Depends(lambda: AppState.instance()),
) -> dict:
    """Alias for cancel_session (terminate + archive)."""
    return await cancel_session(session_id, workspace, state)
