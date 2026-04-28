"""SandboxRunner — Docker / Kubernetes container lifecycle for a session.

Two implementations are planned:
  * ``DockerSandboxRunner`` — for local dev and single-host deploys.
  * ``KubernetesSandboxRunner`` — for production EKS deploys, one Pod per
    session, PVC for the workspace.

Both implement the same async protocol below. The choice is configured per
deployment via ``ATRIUM_SANDBOX_BACKEND``.

This file is a SCAFFOLD. Real implementation lands in roadmap phase 2.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncIterator

from atrium.harness.runtimes.base import Runtime
from atrium.harness.session import Session


@dataclass
class ResourceLimits:
    cpus: float = 2.0
    memory_mb: int = 4096
    disk_mb: int = 8192
    wall_clock_seconds: int = 3600


@dataclass
class NetworkPolicy:
    """Egress allow-list. Default is deny-all except entries below."""
    allow_egress: list[str] = field(default_factory=list)
    allow_mcp: list[str] = field(default_factory=list)


class SandboxRunner:
    """Abstract container runner. Subclasses implement the four async methods."""

    @classmethod
    async def start(
        cls,
        session: Session,
        runtime: Runtime,
        model: str,
        env: dict[str, str],
        limits: ResourceLimits,
        network_policy: NetworkPolicy,
    ) -> "SandboxRunner":
        """Boot a container for the session; return a runner handle.

        The container image is selected by ``runtime.image_tag()``. The
        session's workspace directory is mounted as ``/workspace``. Model
        API keys are passed via ``env``. The container runs the inner
        runtime with stream-json output on stdout.
        """
        raise NotImplementedError

    async def stream_events(self) -> AsyncIterator[bytes]:
        """Yield raw JSON-line bytes from the container's stdout.

        Each line is one event from the inner runtime. The bridge consumes
        this and translates into Atrium events.
        """
        raise NotImplementedError
        # ``yield b''`` is here only to satisfy mypy that this is a generator
        # in the real implementation. Remove when implementing.
        if False:
            yield b""

    async def send_input(self, text: str) -> None:
        """Send a follow-up message into the running session via stdin."""
        raise NotImplementedError

    async def stop(self) -> None:
        """Graceful shutdown — SIGTERM, wait 10s, then SIGKILL."""
        raise NotImplementedError

    async def kill(self) -> None:
        """Immediate termination — SIGKILL. Used on guardrail violations."""
        raise NotImplementedError
