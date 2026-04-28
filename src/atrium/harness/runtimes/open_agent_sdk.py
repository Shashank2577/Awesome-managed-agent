"""Open Agent SDK runtime adapter."""
from __future__ import annotations


class OpenAgentSDKRuntime:
    name = "open_agent_sdk"
    event_format = "claude_code_stream_json"

    def image_tag(self, registry: str) -> str:
        return f"{registry}/open-agent-sdk:0.1.0"

    def command(self, model: str, system_prompt_path: str | None) -> list[str]:
        argv = ["node", "/app/oas_entrypoint.js", "--stream-json"]
        if system_prompt_path:
            argv += ["--system-prompt-file", system_prompt_path]
        argv += ["--model", model]
        return argv

    def model_endpoint(self, model: str) -> str:
        provider = model.split(":", 1)[0]
        return {
            "anthropic": "https://api.anthropic.com",
            "openai": "https://api.openai.com",
            "gemini": "https://generativelanguage.googleapis.com",
        }.get(provider, "https://openrouter.ai")

    def required_env(self, model: str) -> dict[str, str]:
        provider = model.split(":", 1)[0]
        env_var = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "gemini": "GEMINI_API_KEY",
        }.get(provider, "OPENROUTER_API_KEY")
        return {env_var: env_var}  # name → name; the secret store fills value
