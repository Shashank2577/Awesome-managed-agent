"""Session — long-running state and per-session workspace filesystem.

A Session owns:
  * a unique ``session_id``
  * a workspace_id for tenancy
  * a directory at ``/var/atrium/sessions/{session_id}/`` mounted into the
    sandbox as ``/workspace``
  * its position in the lifecycle state machine (CREATED → RUNNING →
    PAUSED/COMPLETED/FAILED/CANCELLED)
  * a checkpoint blob (compaction snapshot) so it can be resumed in a
    fresh container

This file is a SCAFFOLD. Real implementation lands in roadmap phase 2.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SessionStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Session(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    workspace_id: str
    title: str = ""
    objective: str = ""
    status: SessionStatus = SessionStatus.CREATED
    runtime: str = ""               # "open_agent_sdk" | "openclaude" | ...
    model: str = ""                 # "anthropic:claude-sonnet-4-6" | ...
    container_id: str | None = None
    workspace_path: str = ""        # filled in by create()
    parent_thread_id: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    last_active_at: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    # ------------------------------------------------------------------
    # Lifecycle (stubs)
    # ------------------------------------------------------------------

    @classmethod
    async def create_or_resume(
        cls,
        workspace_id: str,
        session_id: str | None = None,
        parent_thread_id: str | None = None,
    ) -> "Session":
        """Create a new session, or resume an existing one by id."""
        # Phase 2:
        #   if session_id is provided, load from sessions table; ensure
        #   workspace_id matches; fail if status is COMPLETED/FAILED/CANCELLED.
        #
        #   if session_id is None, create a new row and create the workspace
        #   directory at /var/atrium/sessions/{new_id}/ with mode 0700.
        raise NotImplementedError

    async def mark_running(self, container_id: str) -> None:
        """Persist transition to RUNNING with the given container id."""
        raise NotImplementedError

    async def mark_completed(self) -> None:
        raise NotImplementedError

    async def mark_failed(self, reason: str) -> None:
        raise NotImplementedError

    async def mark_cancelled(self) -> None:
        raise NotImplementedError

    async def save_checkpoint(self, blob: bytes) -> None:
        """Persist a checkpoint blob (compaction snapshot) to durable storage.

        The blob is written to ``{workspace_path}/.atrium/checkpoint`` and
        backed up to S3 (or equivalent) so the session can resume in a fresh
        container after a process restart.
        """
        raise NotImplementedError

    async def load_checkpoint(self) -> bytes | None:
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Workspace filesystem
    # ------------------------------------------------------------------

    @property
    def workspace_dir(self) -> Path:
        """The host-side directory mounted into the sandbox as /workspace."""
        return Path(self.workspace_path)
