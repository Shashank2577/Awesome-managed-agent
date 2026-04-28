"""Artifact routes — list, download, preview, delete.

GET  /api/v1/sessions/{session_id}/artifacts
GET  /api/v1/artifacts/{artifact_id}
GET  /api/v1/artifacts/{artifact_id}/preview
DELETE /api/v1/artifacts/{artifact_id}
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import aiofiles
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, PlainTextResponse
from pydantic import BaseModel

try:
    from atrium.api.auth import require_workspace
    from atrium.api.state import AppState
    from atrium.core.workspace_store import Workspace
except ImportError:
    require_workspace = None  # type: ignore[assignment]
    AppState = None  # type: ignore[assignment]
    Workspace = None  # type: ignore[assignment]

from atrium.core.artifact_store import Artifact, ArtifactStore
from atrium.harness.session import SessionStatus

router = APIRouter(tags=["artifacts"])

# Maximum bytes returned by the preview endpoint (1 MiB per spec §5 API surface)
_PREVIEW_MAX_BYTES = 1 * 1024 * 1024

# Chunk size for streaming artifact downloads
_STREAM_CHUNK = 65536


class ArtifactResponse(BaseModel):
    """Wire representation of an Artifact, matching spec §5 API surface."""

    artifact_id: str
    session_id: str
    path: str
    size_bytes: int
    sha256: str
    content_type: str
    created_at: str


def _to_response(a: Artifact) -> ArtifactResponse:
    return ArtifactResponse(
        artifact_id=f"art_{a.artifact_id}",  # CONTRACTS.md §1: prefix added at API boundary
        session_id=a.session_id,
        path=a.path,
        size_bytes=a.size_bytes,
        sha256=a.sha256,
        content_type=a.content_type,
        created_at=a.created_at.isoformat(),
    )


def _get_artifact_store(state: "AppState") -> ArtifactStore:
    """Return the ArtifactStore from AppState, raising 503 if unavailable."""
    store = getattr(state, "artifact_store", None)
    if store is None:
        raise HTTPException(503, "Artifact store not available")
    return store


def _artifact_file_path(artifact: Artifact, state: "AppState") -> Path:
    """Resolve the absolute filesystem path for an artifact's file."""
    sessions_root = getattr(state, "sessions_root", None) or "/var/atrium/sessions"
    workspace_dir = Path(sessions_root) / artifact.session_id
    return workspace_dir / artifact.path


# ---------------------------------------------------------------------------
# GET /api/v1/sessions/{session_id}/artifacts
# ---------------------------------------------------------------------------


@router.get(
    "/api/v1/sessions/{session_id}/artifacts",
    response_model=list[ArtifactResponse],
    summary="List artifacts for a session",
)
async def list_artifacts(
    session_id: str,
    workspace: "Workspace" = Depends(require_workspace),
    state: "AppState" = Depends(lambda: AppState.instance()),
) -> list[ArtifactResponse]:
    """List all indexed artifacts for the given session.

    Scoped to the calling workspace — returns 404 if the session belongs
    to a different workspace (consistent with CONTRACTS.md §3 scoping).
    """
    store = _get_artifact_store(state)

    # Verify the session belongs to this workspace
    sess_store = getattr(state, "session_store", None)
    if sess_store:
        session = await sess_store.get(workspace.workspace_id, session_id)
        if session is None:
            raise HTTPException(404, "Session not found")

    artifacts = await store.list_for_session(session_id)
    return [_to_response(a) for a in artifacts]


# ---------------------------------------------------------------------------
# GET /api/v1/artifacts/{artifact_id}
# ---------------------------------------------------------------------------


@router.get(
    "/api/v1/artifacts/{artifact_id}",
    summary="Download an artifact (streamed)",
)
async def download_artifact(
    artifact_id: str,
    workspace: "Workspace" = Depends(require_workspace),
    state: "AppState" = Depends(lambda: AppState.instance()),
) -> StreamingResponse:
    """Stream-download an artifact file.

    The ``artifact_id`` may optionally include the ``art_`` prefix —
    both forms are accepted for ergonomic client use.
    """
    store = _get_artifact_store(state)
    # Strip API-layer prefix if present (CONTRACTS.md §1)
    bare_id = artifact_id.removeprefix("art_")
    artifact = await store.get(bare_id)
    if artifact is None:
        raise HTTPException(404, "Artifact not found")

    # Workspace check: 404, not 403 (CONTRACTS.md §3)
    if artifact.workspace_id != workspace.workspace_id:
        raise HTTPException(404, "Artifact not found")

    file_path = _artifact_file_path(artifact, state)
    if not file_path.exists():
        raise HTTPException(404, "Artifact file no longer present on disk")

    async def _iter_file():
        async with aiofiles.open(file_path, "rb") as fh:
            while True:
                chunk = await fh.read(_STREAM_CHUNK)
                if not chunk:
                    break
                yield chunk

    filename = Path(artifact.path).name
    return StreamingResponse(
        _iter_file(),
        media_type=artifact.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(artifact.size_bytes),
            "X-Artifact-SHA256": artifact.sha256,
        },
    )


# ---------------------------------------------------------------------------
# GET /api/v1/artifacts/{artifact_id}/preview
# ---------------------------------------------------------------------------


@router.get(
    "/api/v1/artifacts/{artifact_id}/preview",
    summary="Text preview of an artifact (max 1 MiB)",
)
async def preview_artifact(
    artifact_id: str,
    workspace: "Workspace" = Depends(require_workspace),
    state: "AppState" = Depends(lambda: AppState.instance()),
) -> PlainTextResponse:
    """Return a text preview of an artifact file, capped to 1 MiB.

    Returns 415 for binary (non-text-like) content types.
    Returns 404 if the file is not present or doesn't belong to the workspace.
    """
    store = _get_artifact_store(state)
    bare_id = artifact_id.removeprefix("art_")
    artifact = await store.get(bare_id)
    if artifact is None:
        raise HTTPException(404, "Artifact not found")

    if artifact.workspace_id != workspace.workspace_id:
        raise HTTPException(404, "Artifact not found")

    # Only serve preview for text-like content
    ct = artifact.content_type
    is_text = ct.startswith("text/") or ct in (
        "application/json",
        "application/xml",
        "application/javascript",
        "application/x-yaml",
        "application/x-sh",
    )
    if not is_text:
        raise HTTPException(415, f"Preview not available for content type {ct}")

    file_path = _artifact_file_path(artifact, state)
    if not file_path.exists():
        raise HTTPException(404, "Artifact file no longer present on disk")

    async with aiofiles.open(file_path, "rb") as fh:
        raw = await fh.read(_PREVIEW_MAX_BYTES)

    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        raise HTTPException(415, "File is not valid UTF-8")

    truncated = len(raw) >= _PREVIEW_MAX_BYTES
    headers = {}
    if truncated:
        headers["X-Preview-Truncated"] = "true"

    return PlainTextResponse(text, headers=headers)


# ---------------------------------------------------------------------------
# DELETE /api/v1/artifacts/{artifact_id}
# ---------------------------------------------------------------------------


@router.delete(
    "/api/v1/artifacts/{artifact_id}",
    status_code=204,
    summary="Delete an artifact (only if session is terminal)",
)
async def delete_artifact(
    artifact_id: str,
    workspace: "Workspace" = Depends(require_workspace),
    state: "AppState" = Depends(lambda: AppState.instance()),
) -> None:
    """Delete an artifact.

    Permitted only if the session is in a terminal state
    (COMPLETED, FAILED, or CANCELLED). Per spec §5 API surface.
    """
    store = _get_artifact_store(state)
    bare_id = artifact_id.removeprefix("art_")
    artifact = await store.get(bare_id)
    if artifact is None:
        raise HTTPException(404, "Artifact not found")

    if artifact.workspace_id != workspace.workspace_id:
        raise HTTPException(404, "Artifact not found")

    # Only allow deletion when session is terminal
    sess_store = getattr(state, "session_store", None)
    if sess_store:
        session = await sess_store.get(workspace.workspace_id, artifact.session_id)
        if session and session.status not in (
            SessionStatus.COMPLETED,
            SessionStatus.FAILED,
            SessionStatus.CANCELLED,
        ):
            raise HTTPException(
                409,
                f"Cannot delete artifact while session is {session.status.value}; "
                "wait for the session to reach a terminal state.",
            )

    deleted = await store.delete(bare_id)
    if not deleted:
        raise HTTPException(404, "Artifact not found")

    # Best-effort: remove the file from disk
    file_path = _artifact_file_path(artifact, state)
    try:
        if file_path.exists():
            file_path.unlink()
    except OSError:
        pass
