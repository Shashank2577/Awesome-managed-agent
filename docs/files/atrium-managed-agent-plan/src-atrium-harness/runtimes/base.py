"""Runtime — the protocol every harness runtime adapter implements.

A Runtime tells the SandboxRunner which container image to use and what
command line to run. It also provides a translation hint — its
``event_format`` — so BridgeStream knows which mapping table to apply to
its event stream.

Adding a new runtime means:

  1. Subclassing this protocol.
  2. Building a Docker image with the inner-loop CLI installed (see
     ``../dockerfiles/`` for examples).
  3. Adding a translation table to ``bridge.py`` for that runtime's
     event format (or matching one of the existing formats).

This file is a SCAFFOLD. The protocol shape is the contract; concrete
runtimes implement it in roadmap phase 3.
"""
from __future__ import annotations

from typing import Protocol


class Runtime(Protocol):
    """Protocol every runtime adapter conforms to.

    Implementors (open_agent_sdk, openclaude, direct_anthropic, echo) are
    plain classes with these methods.
    """

    @property
    def name(self) -> str:
        """Human-readable identifier, e.g. 'open_agent_sdk'."""
        ...

    @property
    def event_format(self) -> str:
        """Identifier the bridge uses to pick the right translation table.

        Most runtimes will use 'claude_code_stream_json' since Open Agent
        SDK and OpenClaude both inherit Claude Code's format. New formats
        can be added by extending the bridge's translation registry.
        """
        ...

    def image_tag(self) -> str:
        """Docker image to use for this runtime, e.g. 'atrium-oas:0.1.0'."""
        ...

    def command(self, model: str, system_prompt: str | None) -> list[str]:
        """The argv passed to the container.

        The image's entrypoint is the inner-loop CLI; this returns its
        flags. Typically includes ``--output-format=stream-json`` or the
        equivalent.
        """
        ...

    def model_endpoint(self, model: str) -> str:
        """The egress endpoint to allow-list for this model.

        Used by the SandboxRunner's NetworkPolicy to permit only the
        traffic that's actually needed.
        """
        ...
