"""Echo runtime — fake adapter for testing the pipeline without LLM calls.

The echo runtime's container is a tiny Python script that:

  * Reads the objective from stdin.
  * Emits a few fake ``tool_use`` and ``tool_result`` events.
  * Writes a file to /workspace/echo.txt.
  * Emits a ``result`` event with a deterministic message.

Used in CI to prove the BridgeStream → SandboxRunner → Session pipeline
works end-to-end without spending a single token. Should be the first
runtime that's actually implemented (phase 2), even before
open_agent_sdk.

This file is a SCAFFOLD. Implementation lands in roadmap phase 2.
"""
from __future__ import annotations


class EchoRuntime:
    """Trivial runtime — no LLM. Echoes inputs, writes a file, exits."""

    name = "echo"
    event_format = "claude_code_stream_json"  # uses the same shape

    def image_tag(self) -> str:
        return "atrium-echo:0.1.0"

    def command(self, model: str, system_prompt: str | None) -> list[str]:
        return ["python", "/app/echo_runtime.py"]

    def model_endpoint(self, model: str) -> str:
        # Echo runtime needs no egress at all.
        return ""
