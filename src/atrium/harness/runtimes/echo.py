"""Echo runtime — emits scripted events; no model call. Phase 2 uses this."""
from __future__ import annotations


class EchoRuntime:
    name = "echo"
    event_format = "echo"

    def image_tag(self, registry: str) -> str:
        return f"{registry}/echo:0.1.0"

    def command(self, model: str, system_prompt_path: str | None) -> list[str]:
        return ["python", "/app/echo_runtime.py"]

    def model_endpoint(self, model: str) -> str:
        return ""  # echo needs no egress

    def required_env(self, model: str) -> dict[str, str]:
        return {}  # no secrets needed
