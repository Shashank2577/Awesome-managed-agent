"""BridgeStream — drives the sandbox, translates events, enforces guardrails."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from atrium.core.errors import GuardrailViolation

if TYPE_CHECKING:
    from atrium.core.artifact_store import Artifact, ArtifactStore
    from atrium.harness.sandbox import SandboxRunner
    from atrium.harness.session import Session
    from atrium.streaming.events import EventRecorder

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class BridgeResult:
    final_message: str
    artifacts: list["Artifact"] = field(default_factory=list)
    tokens_used: int = 0


# ---------------------------------------------------------------------------
# Event draft (thin wrapper so translate() can return multiple events)
# ---------------------------------------------------------------------------

@dataclass
class AtriumEventDraft:
    type: str
    payload: dict


# ---------------------------------------------------------------------------
# Guardrail enforcer (thin for Phase 2 — just tool call counting)
# ---------------------------------------------------------------------------

class GuardrailEnforcer:
    def __init__(self, max_tool_calls: int = 200) -> None:
        self._max_tool_calls = max_tool_calls
        self._tool_calls = 0

    def on_event(self, event: dict) -> None:
        if event.get("type") == "tool_call":
            self._tool_calls += 1
            if self._tool_calls > self._max_tool_calls:
                raise GuardrailViolation(
                    "MAX_TOOL_CALLS",
                    f"tool call limit {self._max_tool_calls} exceeded",
                )


# ---------------------------------------------------------------------------
# Translation tables
# ---------------------------------------------------------------------------

def _translate_echo(event: dict) -> list[AtriumEventDraft]:
    """Translate Echo format events → Atrium event drafts."""
    t = event.get("type")
    if t == "ready":
        return []  # internal handshake — no Atrium event
    if t == "tool_call":
        return [AtriumEventDraft(
            type="HARNESS_TOOL_CALLED",
            payload={"tool": event.get("tool"), "input": event.get("input")},
        )]
    if t == "tool_result":
        return [AtriumEventDraft(
            type="HARNESS_TOOL_RESULT",
            payload={"tool": event.get("tool"), "output": event.get("output")},
        )]
    if t == "message":
        return [AtriumEventDraft(type="HARNESS_MESSAGE", payload={"text": event.get("text", "")})]
    if t == "result":
        return [AtriumEventDraft(type="HARNESS_MESSAGE", payload={"text": event.get("text", "")})]
    return []


_TRANSLATORS = {
    "echo": _translate_echo,
}


# ---------------------------------------------------------------------------
# BridgeStream
# ---------------------------------------------------------------------------

class BridgeStream:
    def __init__(
        self,
        sandbox: "SandboxRunner",
        session: "Session",
        recorder: "EventRecorder",
        artifact_store: "ArtifactStore",
        guardrails: GuardrailEnforcer,
    ) -> None:
        self._sandbox = sandbox
        self._session = session
        self._recorder = recorder
        self._artifact_store = artifact_store
        self._guardrails = guardrails
        self._tokens_used = 0
        # Pick translator based on session runtime's event_format
        self._translator = _TRANSLATORS.get(session.runtime, _translate_echo)

    async def run(
        self,
        objective: str,
        max_tool_calls: int = 200,
    ) -> BridgeResult:
        """Drive the sandbox to completion. Stream events. Apply guardrails."""
        # 1. Send objective on stdin.
        await self._sandbox.send_input(objective)

        # 2. Iterate the sandbox's stdout.
        result_event: dict | None = None
        async for raw_line in self._sandbox.stream_events():
            try:
                event = json.loads(raw_line.decode().strip() if isinstance(raw_line, bytes) else raw_line.strip())
            except (json.JSONDecodeError, UnicodeDecodeError):
                logger.debug("dropped non-json line", extra={"line": repr(raw_line[:200])})
                continue

            drafts = self._translator(event)
            for draft in drafts:
                await self._recorder.emit(
                    self._session.session_id,
                    draft.type,
                    draft.payload,
                )

            self._guardrails.on_event(event)

            if event.get("type") == "result":
                result_event = event
                break

        if result_event is None:
            result_event = {"text": "", "files": []}

        # 3. Index artifacts produced.
        artifacts = await self._index_artifacts(result_event.get("files", []))

        return BridgeResult(
            final_message=result_event.get("text", ""),
            artifacts=artifacts,
            tokens_used=self._tokens_used,
        )

    async def _index_artifacts(self, file_paths: list[str]) -> list["Artifact"]:
        """Walk the workspace and index all files. Emit ARTIFACT_CREATED per file."""
        workspace_dir = self._session.workspace_dir
        if not workspace_dir.exists():
            return []

        artifacts = await self._artifact_store.index_workspace(
            workspace_id=self._session.workspace_id,
            session_id=self._session.session_id,
            workspace_dir=workspace_dir,
        )

        for artifact in artifacts:
            await self._recorder.emit(
                self._session.session_id,
                "ARTIFACT_CREATED",
                {
                    "artifact_id": artifact.artifact_id,
                    "path": artifact.path,
                    "size_bytes": artifact.size_bytes,
                    "sha256": artifact.sha256,
                },
            )

        return artifacts
