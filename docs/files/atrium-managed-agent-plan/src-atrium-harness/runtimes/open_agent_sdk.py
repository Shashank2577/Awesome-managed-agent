"""Open Agent SDK runtime adapter.

Wraps `@shipany/open-agent-sdk`, the in-process port of Claude Code with
multi-provider support. Runs inside a Node container; we communicate
over stdin/stdout in stream-json mode.

This file is a SCAFFOLD. Implementation lands in roadmap phase 3.
"""
from __future__ import annotations


class OpenAgentSDKRuntime:
    """Adapter for @shipany/open-agent-sdk."""

    name = "open_agent_sdk"
    event_format = "claude_code_stream_json"

    def image_tag(self) -> str:
        # Built from ../dockerfiles/open_agent_sdk.Dockerfile in CI.
        return "atrium-oas:0.1.0"

    def command(self, model: str, system_prompt: str | None) -> list[str]:
        # Phase 3: emit `node /app/run.js --model={model} --stream-json
        # --system-prompt-file=/workspace/.atrium/system_prompt.txt`
        raise NotImplementedError

    def model_endpoint(self, model: str) -> str:
        # Phase 3: parse model="provider:model_id" and return:
        #   anthropic -> https://api.anthropic.com
        #   openai    -> https://api.openai.com
        #   gemini    -> https://generativelanguage.googleapis.com
        #   anything  -> https://openrouter.ai (when ANTHROPIC_BASE_URL is set)
        raise NotImplementedError
