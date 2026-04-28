"""HarnessAgent — Atrium-side wrapper around a sandboxed agentic loop.

This is the piece that lets the Commander treat a long-running, tool-using
sandboxed Claude/GPT/Gemini run as just another agent in the registry. From
the orchestrator's perspective, ``HarnessAgent.run(input_data)`` looks like
any other agent invocation — it just happens to take minutes-to-hours and
emit dozens of inner events.

This file is a SCAFFOLD. Real implementation lands in roadmap phase 3.
The shape below is the contract the rest of the system will be built
against.
"""
from __future__ import annotations

from typing import Any

from atrium.core.agent import Agent
from atrium.harness.runtimes.base import Runtime
from atrium.harness.session import Session


class HarnessAgent(Agent):
    """Base class for long-running, tool-using, sandboxed agents.

    Subclasses set ``runtime``, ``model``, and optionally
    ``allowed_mcp_servers`` / ``system_prompt`` / ``timeout_seconds``.

    The agent's ``run()`` is a thin wrapper:

      * resolve or create the Session
      * boot a SandboxRunner
      * stream the inner runtime's events through BridgeStream
      * return the final result dict

    All of the actual tool dispatch (bash, file edit, web fetch, MCP) happens
    inside the sandbox. The host process does not call the model directly.
    """

    # Subclasses MUST override these
    name: str = ""
    description: str = ""
    runtime: Runtime | None = None
    model: str = ""

    # Optional overrides
    capabilities: list[str] = ["bash", "files", "web_fetch", "code"]
    system_prompt: str | None = None
    allowed_mcp_servers: list[str] = []
    timeout_seconds: int = 3600
    max_tool_calls: int = 200

    async def run(self, input_data: dict) -> dict[str, Any]:
        """Run a harness session.

        Args:
            input_data: must contain ``objective`` (str) and ``workspace_id``
                (str). May contain ``session_id`` (resume), ``thread_id``
                (parent thread), and ``model_override`` (str).

        Returns:
            ``{"result": ..., "artifacts": [...], "session_id": "...",
                "tokens_used": {...}}``.
        """
        # Phase 3 implementation. The skeleton:
        #
        #   session = await Session.create_or_resume(
        #       workspace_id=input_data["workspace_id"],
        #       session_id=input_data.get("session_id"),
        #       parent_thread_id=input_data.get("thread_id"),
        #   )
        #
        #   sandbox = await SandboxRunner.start(
        #       session=session,
        #       runtime=self.runtime,
        #       model=input_data.get("model_override") or self.model,
        #       env={"ATRIUM_SESSION_ID": session.session_id, ...},
        #       limits=ResourceLimits(
        #           cpus=2, memory_mb=4096, disk_mb=8192,
        #           wall_clock_seconds=self.timeout_seconds,
        #       ),
        #       network_policy=NetworkPolicy(
        #           allow_egress=[self.runtime.model_endpoint(input_data)],
        #           allow_mcp=self.allowed_mcp_servers,
        #       ),
        #   )
        #
        #   bridge = BridgeStream(
        #       sandbox=sandbox,
        #       session=session,
        #       recorder=self._emitter,
        #       guardrails=GuardrailEnforcer(...),
        #   )
        #
        #   try:
        #       result = await bridge.run(
        #           objective=input_data["objective"],
        #           system_prompt=self.system_prompt,
        #           max_tool_calls=self.max_tool_calls,
        #       )
        #       return result
        #   finally:
        #       await sandbox.stop()  # workspace persists for resume
        #
        raise NotImplementedError(
            "HarnessAgent.run is a scaffold; see roadmap phase 3."
        )
