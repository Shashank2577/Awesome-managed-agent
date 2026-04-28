"""OpenClaude multi-model runtime adapter.

Routes any provider:model string through the openclaude container.
Supports: anthropic, openai, gemini, deepseek, openrouter, ollama.
"""
from __future__ import annotations


class OpenClaudeRuntime:
    name = "openclaude"
    event_format = "claude_code_stream_json"

    def image_tag(self, registry: str) -> str:
        return f"{registry}/openclaude:0.1.0"

    def command(self, model: str, system_prompt_path: str | None) -> list[str]:
        argv = ["node", "/app/openclaude_entrypoint.js", "--stream-json"]
        if system_prompt_path:
            argv += ["--system-prompt-file", system_prompt_path]
        argv += ["--model", model]
        return argv

    def model_endpoint(self, model: str) -> str:
        provider = model.split(":", 1)[0]
        return {
            "anthropic":  "https://api.anthropic.com",
            "openai":     "https://api.openai.com",
            "gemini":     "https://generativelanguage.googleapis.com",
            "deepseek":   "https://api.deepseek.com",
            "openrouter": "https://openrouter.ai",
            "ollama":     "http://host.docker.internal:11434",
        }.get(provider, "https://openrouter.ai")

    def required_env(self, model: str) -> dict[str, str]:
        provider = model.split(":", 1)[0]
        return {
            "anthropic":  {"ANTHROPIC_API_KEY":  "ANTHROPIC_API_KEY"},
            "openai":     {"OPENAI_API_KEY":     "OPENAI_API_KEY"},
            "gemini":     {"GEMINI_API_KEY":     "GEMINI_API_KEY"},
            "deepseek":   {"DEEPSEEK_API_KEY":   "DEEPSEEK_API_KEY"},
            "openrouter": {"OPENROUTER_API_KEY": "OPENROUTER_API_KEY"},
            "ollama":     {},
        }.get(provider, {"OPENROUTER_API_KEY": "OPENROUTER_API_KEY"})
