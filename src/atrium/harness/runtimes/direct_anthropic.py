"""Direct Anthropic Claude Agent SDK runtime adapter."""
from __future__ import annotations

import os


class DirectAnthropicRuntime:
    name = "direct_anthropic"
    event_format = "claude_code_stream_json"

    def image_tag(self, registry: str) -> str:
        return f"{registry}/anthropic:0.1.0"

    def command(self, model: str, system_prompt_path: str | None) -> list[str]:
        argv = ["python", "/app/anthropic_entrypoint.py"]
        if system_prompt_path:
            argv += ["--system-prompt-file", system_prompt_path]
        # Strip provider prefix — "anthropic:claude-sonnet-4-6" → "claude-sonnet-4-6"
        model_id = model.split(":", 1)[1] if ":" in model else model
        argv += ["--model", model_id]
        return argv

    def model_endpoint(self, model: str) -> str:
        # Allow override via env var (for proxies like OpenRouter, LiteLLM)
        return os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")

    def required_env(self, model: str) -> dict[str, str]:
        return {
            "ANTHROPIC_API_KEY": "ANTHROPIC_API_KEY",
            "ANTHROPIC_BASE_URL": "ANTHROPIC_BASE_URL",  # optional: override for proxies
        }
