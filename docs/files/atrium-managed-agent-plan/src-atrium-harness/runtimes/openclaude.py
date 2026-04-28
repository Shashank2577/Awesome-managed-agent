"""OpenClaude runtime adapter.

Wraps OpenClaude, a Claude Code fork that natively supports OpenAI,
Gemini, DeepSeek, GitHub Models, Ollama, and other OpenAI-compatible
providers. Has a built-in gRPC headless mode we can leverage.

This file is a SCAFFOLD. Implementation lands in roadmap phase 4.
"""
from __future__ import annotations


class OpenClaudeRuntime:
    """Adapter for OpenClaude (multi-provider Claude Code fork)."""

    name = "openclaude"
    event_format = "claude_code_stream_json"

    def image_tag(self) -> str:
        return "atrium-openclaude:0.1.0"

    def command(self, model: str, system_prompt: str | None) -> list[str]:
        # Phase 4
        raise NotImplementedError

    def model_endpoint(self, model: str) -> str:
        # Phase 4
        raise NotImplementedError
