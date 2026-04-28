"""Direct Anthropic Claude Agent SDK runtime adapter.

Wraps `claude-agent-sdk-python`, Anthropic's official SDK. Highest
fidelity for Claude (uses the same harness Anthropic ships in Claude
Code) but governed by Anthropic's Commercial Terms of Service — see
``docs/managed-agent-replacement/07-decision-log.md`` D-011.

Use this runtime for internal Taazaa work; prefer ``open_agent_sdk``
for client-deployed agents.

This file is a SCAFFOLD. Implementation lands in roadmap phase 3.
"""
from __future__ import annotations


class DirectAnthropicRuntime:
    """Adapter for Anthropic's official claude-agent-sdk-python."""

    name = "direct_anthropic"
    event_format = "claude_code_stream_json"

    def image_tag(self) -> str:
        return "atrium-anthropic:0.1.0"

    def command(self, model: str, system_prompt: str | None) -> list[str]:
        # Phase 3
        raise NotImplementedError

    def model_endpoint(self, model: str) -> str:
        return "https://api.anthropic.com"
