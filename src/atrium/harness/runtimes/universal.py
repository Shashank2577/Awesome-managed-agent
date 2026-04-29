"""Universal runtime — any OpenAI-compatible LLM provider."""
from __future__ import annotations


PROVIDER_PRESETS: dict[str, dict] = {
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "key_env": "OPENROUTER_API_KEY",
        "example_models": ["anthropic/claude-sonnet-4-5", "google/gemini-2.5-flash",
                           "openai/gpt-4o", "meta-llama/llama-3.3-70b-instruct"],
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "key_env": "OPENAI_API_KEY",
        "example_models": ["gpt-4o", "gpt-4o-mini", "o1", "o3-mini"],
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key_env": "GEMINI_API_KEY",
        "example_models": ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"],
    },
    "xai": {
        "base_url": "https://api.x.ai/v1",
        "key_env": "XAI_API_KEY",
        "example_models": ["grok-3", "grok-3-mini", "grok-2"],
    },
    "nvidia": {
        "base_url": "https://integrate.api.nvidia.com/v1",
        "key_env": "NVIDIA_API_KEY",
        "example_models": ["meta/llama-3.3-70b-instruct", "nvidia/llama-3.1-nemotron-70b-instruct"],
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        "example_models": ["llama-3.3-70b-versatile", "mixtral-8x7b-32768"],
    },
    "anthropic_compat": {
        "base_url": "https://openrouter.ai/api/v1",
        "key_env": "OPENROUTER_API_KEY",
        "example_models": ["anthropic/claude-sonnet-4-5", "anthropic/claude-haiku-3-5"],
        "note": "Access Anthropic models via OpenRouter (no direct Anthropic API compat needed)",
    },
    "ollama": {
        "base_url": "http://host.docker.internal:11434/v1",
        "key_env": "",
        "example_models": ["llama3.2", "mistral", "qwen2.5-coder"],
        "note": "Local Ollama — no API key needed",
    },
}


class UniversalRuntime:
    """Runs in a Docker sandbox. Calls any OpenAI-compatible LLM API."""

    name = "universal"
    event_format = "claude_code_stream_json"

    def image_tag(self, registry: str) -> str:
        return f"{registry}/universal:0.1.0"

    def command(self, model: str, system_prompt_path: str | None) -> list[str]:
        return ["python", "/app/universal_entrypoint.py"]

    def model_endpoint(self, model: str) -> str:
        return ""  # base_url comes from env, not from model string

    def required_env(self, model: str) -> list[str]:
        return ["LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"]
