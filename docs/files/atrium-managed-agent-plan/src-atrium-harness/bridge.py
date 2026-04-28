"""BridgeStream — translate inner-runtime events into Atrium events.

This is the most important new file in the harness layer. It is the only
place in Atrium that knows about the JSON event format of the inner
runtimes (Open Agent SDK, OpenClaude). Every other layer talks Atrium
events.

Responsibilities:

1. **Translate.** Each line from the sandbox stdout is a JSON object.
   Map each one to a typed Atrium event with a stable schema:

      tool_use     → HARNESS_TOOL_CALLED
      tool_result  → HARNESS_TOOL_RESULT
      text         → HARNESS_MESSAGE
      usage        → BUDGET_CONSUMED
      compaction   → HARNESS_COMPACTION
      checkpoint   → HARNESS_CHECKPOINT
      file_event   → ARTIFACT_CREATED / ARTIFACT_UPDATED

2. **Enforce guardrails.** Every ``usage`` event accumulates into running
   token cost. If the running cost crosses ``max_cost_usd``, kill the
   sandbox and raise ``GuardrailViolation``. Same for max_tool_calls and
   wall-clock time.

3. **Index artifacts.** When the inner runtime writes files to /workspace,
   index them in the artifacts table.

This file is a SCAFFOLD. Real implementation lands in roadmap phase 2-3.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Awaitable, Callable

from atrium.core.guardrails import GuardrailEnforcer
from atrium.harness.sandbox import SandboxRunner
from atrium.harness.session import Session


# Type alias for the recorder emitter, matching ``Agent.set_emitter``.
EmitFn = Callable[..., Awaitable[None]]


@dataclass
class BridgeResult:
    final_message: str
    artifacts: list[str]
    tokens_used: dict[str, int]


class BridgeStream:
    """Read JSON-line events from a sandbox, emit Atrium events, enforce limits."""

    def __init__(
        self,
        sandbox: SandboxRunner,
        session: Session,
        emit: EmitFn,
        guardrails: GuardrailEnforcer,
    ) -> None:
        self._sandbox = sandbox
        self._session = session
        self._emit = emit
        self._guardrails = guardrails
        self._tokens_in = 0
        self._tokens_out = 0
        self._cost_usd = Decimal("0.0")
        self._tool_calls = 0

    async def run(
        self,
        objective: str,
        system_prompt: str | None,
        max_tool_calls: int,
    ) -> BridgeResult:
        """Drive the sandbox to completion, streaming events as they arrive.

        Sends the initial message, then iterates ``sandbox.stream_events()``,
        translates each, applies guardrails, and returns a BridgeResult on
        the inner runtime's terminal event.
        """
        # Phase 2-3:
        #
        #   await self._sandbox.send_input(_build_initial_input(objective, system_prompt))
        #
        #   async for raw_line in self._sandbox.stream_events():
        #       try:
        #           event = json.loads(raw_line)
        #       except json.JSONDecodeError:
        #           # log and continue; some runtimes emit non-JSON debug output
        #           continue
        #
        #       atrium_event = self._translate(event)
        #       if atrium_event is None:
        #           continue
        #
        #       await self._emit(atrium_event.type, atrium_event.payload)
        #
        #       self._apply_guardrails(event)
        #
        #       if event.get("type") == "result":
        #           return BridgeResult(
        #               final_message=event.get("text", ""),
        #               artifacts=await self._index_artifacts(),
        #               tokens_used={"input": self._tokens_in, "output": self._tokens_out},
        #           )
        #
        #   raise RuntimeError("sandbox stream ended without a terminal event")
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Translation table — to be filled in per-runtime
    # ------------------------------------------------------------------

    def _translate(self, inner: dict[str, Any]) -> "AtriumEventDraft | None":
        """Map an inner-runtime event to an Atrium event payload.

        Returns None for events we deliberately drop (heartbeats, debug).
        """
        raise NotImplementedError

    def _apply_guardrails(self, inner: dict[str, Any]) -> None:
        """Update accumulators and raise GuardrailViolation if exceeded."""
        raise NotImplementedError

    async def _index_artifacts(self) -> list[str]:
        """Walk the session workspace, index new files in the artifacts table."""
        raise NotImplementedError


@dataclass
class AtriumEventDraft:
    """Minimal type for an event before it's recorded — just (type, payload)."""
    type: str
    payload: dict[str, Any]
