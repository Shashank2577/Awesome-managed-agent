"""BridgeStream — drives the sandbox, translates events, enforces guardrails.

Phase 2: echo translator
Phase 3: claude_code_stream_json translator + token-based budget enforcement
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

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
    cost_usd: float = 0.0


# ---------------------------------------------------------------------------
# Event draft (thin wrapper so translate() can return multiple events)
# ---------------------------------------------------------------------------

@dataclass
class AtriumEventDraft:
    type: str
    payload: dict


# ---------------------------------------------------------------------------
# Guardrail enforcer
# ---------------------------------------------------------------------------

class GuardrailEnforcer:
    def __init__(self, max_tool_calls: int = 200, max_cost_usd: float | None = None) -> None:
        self._max_tool_calls = max_tool_calls
        self._max_cost_usd = max_cost_usd
        self._tool_calls = 0

    def on_event(self, event: dict) -> None:
        """Called for every raw inner event — only counts tool_call (echo format)."""
        if event.get("type") == "tool_call":
            self._tool_calls += 1
            if self._tool_calls > self._max_tool_calls:
                raise GuardrailViolation(
                    "MAX_TOOL_CALLS",
                    f"tool call limit {self._max_tool_calls} exceeded",
                )

    def on_tool_use(self) -> None:
        """Incremented for claude_code_stream_json tool_use blocks."""
        self._tool_calls += 1
        if self._tool_calls > self._max_tool_calls:
            raise GuardrailViolation(
                "MAX_TOOL_CALLS",
                f"tool call limit {self._max_tool_calls} exceeded",
            )

    def check_cost(self, cost_usd: float) -> None:
        if self._max_cost_usd is not None and cost_usd > self._max_cost_usd:
            raise GuardrailViolation(
                "MAX_COST",
                f"cost ${cost_usd:.4f} exceeds limit ${self._max_cost_usd:.2f}",
            )


# ---------------------------------------------------------------------------
# Translation: Echo format (Phase 2)
# ---------------------------------------------------------------------------

def translate_echo(event: dict) -> list[AtriumEventDraft]:
    """Translate Echo format events → Atrium event drafts."""
    t = event.get("type")
    if t == "ready":
        return []
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


# ---------------------------------------------------------------------------
# Translation: claude_code_stream_json format (Phase 3)
# ---------------------------------------------------------------------------

def translate_claude_code(event: dict) -> list[AtriumEventDraft]:
    """Translate claude_code_stream_json events → Atrium event drafts.

    For assistant messages with multiple content blocks, returns one draft
    per block in order.
    """
    t = event.get("type")
    drafts: list[AtriumEventDraft] = []

    if t == "system":
        # Internal handshake — not user-facing
        return []

    if t == "assistant":
        message = event.get("message", {})
        content = message.get("content", [])
        usage = message.get("usage")

        for block in content:
            btype = block.get("type")
            if btype == "text":
                drafts.append(AtriumEventDraft(
                    type="HARNESS_MESSAGE",
                    payload={"text": block.get("text", "")},
                ))
            elif btype == "thinking":
                drafts.append(AtriumEventDraft(
                    type="HARNESS_THINKING",
                    payload={"text": block.get("thinking", "")},
                ))
            elif btype == "tool_use":
                drafts.append(AtriumEventDraft(
                    type="HARNESS_TOOL_CALLED",
                    payload={"tool": block.get("name"), "input": block.get("input", {})},
                ))

        if usage:
            drafts.append(_budget_draft(usage, event.get("_model", "")))

        return drafts

    if t == "user":
        message = event.get("message", {})
        content = message.get("content", [])
        for block in content:
            if block.get("type") == "tool_result":
                # tool_result may be a list or a string
                output = block.get("content", "")
                if isinstance(output, list):
                    output = " ".join(
                        p.get("text", "") for p in output if isinstance(p, dict)
                    )
                drafts.append(AtriumEventDraft(
                    type="HARNESS_TOOL_RESULT",
                    payload={"tool": block.get("tool_use_id", ""), "output": output},
                ))
        return drafts

    if t == "result":
        subtype = event.get("subtype", "success")
        if subtype == "success":
            return [AtriumEventDraft(
                type="HARNESS_MESSAGE",
                payload={"text": event.get("result", "")},
            )]
        # error subtypes — SESSION_FAILED is emitted by HarnessAgent, not here
        return []

    # Unknown event type — drop gracefully
    logger.debug("claude_code translator: dropping unknown event type %r", t)
    return []


def _budget_draft(usage: dict, model: str) -> AtriumEventDraft:
    """Build a BUDGET_CONSUMED draft from a usage dict."""
    tokens_in = usage.get("input_tokens", 0)
    tokens_out = usage.get("output_tokens", 0)
    cost_usd = 0.0
    try:
        from atrium.engine.pricing import estimate_cost
        cost_usd = float(estimate_cost(model, tokens_in, tokens_out))
    except Exception:
        pass
    return AtriumEventDraft(
        type="BUDGET_CONSUMED",
        payload={
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": cost_usd,
        },
    )


def _extract_usage(event: dict) -> dict | None:
    """Pull usage dict from an assistant message, if present."""
    return event.get("message", {}).get("usage")


# ---------------------------------------------------------------------------
# Translator registry
# ---------------------------------------------------------------------------

_TRANSLATORS: dict[str, Callable[[dict], list[AtriumEventDraft]]] = {
    "echo": translate_echo,
    "claude_code_stream_json": translate_claude_code,
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
        self._tokens_in = 0
        self._tokens_out = 0
        self._tokens_used = 0
        self._cost_usd = 0.0
        # Pick translator from session runtime name → event_format
        fmt = getattr(session, "runtime", "echo")
        # Allow the runtime object to declare its format if available
        self._translator = _TRANSLATORS.get(fmt, translate_echo)

    def _translate(self, event: dict) -> list[AtriumEventDraft]:
        translator = self._translator
        if translator is None:
            raise ValueError(f"no translator for event_format={self._session.runtime!r}")
        return translator(event)

    def _apply_guardrails(self, event: dict) -> None:
        """Apply cost and tool-call guardrails for claude_code_stream_json."""
        usage = _extract_usage(event)
        if usage:
            self._tokens_in += usage.get("input_tokens", 0)
            self._tokens_out += usage.get("output_tokens", 0)
            self._tokens_used = self._tokens_in + self._tokens_out
            try:
                from atrium.engine.pricing import estimate_cost
                self._cost_usd = float(estimate_cost(
                    self._session.model, self._tokens_in, self._tokens_out
                ))
            except Exception:
                pass
            try:
                self._guardrails.check_cost(self._cost_usd)
            except GuardrailViolation:
                asyncio.create_task(self._sandbox.kill())
                raise

        # Count tool_use blocks in claude_code_stream_json
        if event.get("type") == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "tool_use":
                    try:
                        self._guardrails.on_tool_use()
                    except GuardrailViolation:
                        asyncio.create_task(self._sandbox.kill())
                        raise

        # Echo format tool_call
        if event.get("type") == "tool_call":
            try:
                self._guardrails.on_event(event)
            except GuardrailViolation:
                asyncio.create_task(self._sandbox.kill())
                raise

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
                line_str = raw_line.decode().strip() if isinstance(raw_line, bytes) else raw_line.strip()
                event = json.loads(line_str)
            except (json.JSONDecodeError, UnicodeDecodeError):
                logger.debug("dropped non-json line", extra={"line": repr(raw_line[:200])})
                continue

            # Inject model for budget calculation if needed
            if "model" not in event and self._session.model:
                event["_model"] = self._session.model

            drafts = self._translate(event)
            for draft in drafts:
                await self._recorder.emit(
                    self._session.session_id,
                    draft.type,
                    draft.payload,
                )

            self._apply_guardrails(event)

            if event.get("type") == "result":
                result_event = event
                break

        if result_event is None:
            result_event = {"text": "", "files": [], "result": ""}

        # 3. Index artifacts produced.
        artifacts = await self._index_artifacts(result_event.get("files", []))

        return BridgeResult(
            final_message=result_event.get("text") or result_event.get("result", ""),
            artifacts=artifacts,
            tokens_used=self._tokens_used,
            cost_usd=self._cost_usd,
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
