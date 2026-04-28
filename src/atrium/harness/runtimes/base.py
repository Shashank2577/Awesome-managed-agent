"""Runtime protocol implemented by every inner-loop adapter."""
from __future__ import annotations

from typing import Protocol


class Runtime(Protocol):
    """A runtime tells the SandboxRunner WHICH image and HOW to start it."""

    name: str
    event_format: str

    def image_tag(self, registry: str) -> str:
        """Full image reference, e.g. 'atrium/echo:0.1.0'."""
        ...

    def command(self, model: str, system_prompt_path: str | None) -> list[str]:
        """argv for the container entrypoint."""
        ...

    def model_endpoint(self, model: str) -> str:
        """Egress URL to allow-list for the network policy. Empty if no egress needed."""
        ...

    def required_env(self, model: str) -> dict[str, str]:
        """Names of env vars the runtime needs. Values come from the secret store."""
        ...
