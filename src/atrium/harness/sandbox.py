"""Container lifecycle abstraction. Two implementations in v1."""
from __future__ import annotations

import abc
import asyncio
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, TYPE_CHECKING

if TYPE_CHECKING:
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
    allow_egress: list[str] = field(default_factory=list)
    allow_mcp: bool = False  # Phase 4 wires this to the gateway


class SandboxRunner(abc.ABC):
    """Abstract sandbox runner. Subclasses: Docker, Kubernetes, InMemory."""

    @classmethod
    @abc.abstractmethod
    async def start(
        cls,
        session: "Session",
        runtime: "Runtime",
        model: str,
        env: dict[str, str],
        limits: ResourceLimits,
        network_policy: NetworkPolicy,
    ) -> "SandboxRunner": ...

    @abc.abstractmethod
    async def stream_events(self) -> AsyncIterator[bytes]: ...

    @abc.abstractmethod
    async def send_input(self, text: str) -> None: ...

    @abc.abstractmethod
    async def stop(self, timeout_seconds: float = 10.0) -> None: ...

    @abc.abstractmethod
    async def kill(self) -> None: ...

    @property
    @abc.abstractmethod
    def container_id(self) -> str: ...


# ---------------------------------------------------------------------------
# InMemorySandboxRunner — runs echo_runtime.py as a subprocess on the host
# ---------------------------------------------------------------------------

class InMemorySandboxRunner(SandboxRunner):
    """In-process subprocess runner. Tests + CI only (no Docker required)."""

    def __init__(self, proc: asyncio.subprocess.Process, session_id: str) -> None:
        self._proc = proc
        self._session_id = session_id

    @classmethod
    async def start(
        cls,
        session: "Session",
        runtime: "Runtime",
        model: str,
        env: dict[str, str],
        limits: ResourceLimits,
        network_policy: NetworkPolicy,
    ) -> "InMemorySandboxRunner":
        # Find the echo_runtime.py script next to echo.py in the runtimes package
        runtimes_dir = Path(__file__).parent / "runtimes"
        script_path = runtimes_dir / "echo_runtime.py"

        merged_env = {**os.environ, **env, "ATRIUM_WORKSPACE_DIR": str(session.workspace_dir)}

        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(script_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(session.workspace_dir) if session.workspace_dir.exists() else None,
            env=merged_env,
        )
        return cls(proc, session.session_id)

    async def stream_events(self) -> AsyncIterator[bytes]:  # type: ignore[override]
        assert self._proc.stdout is not None
        async for line in self._proc.stdout:
            stripped = line.strip()
            if stripped:
                yield stripped

    async def send_input(self, text: str) -> None:
        assert self._proc.stdin is not None
        self._proc.stdin.write((text + "\n").encode())
        await self._proc.stdin.drain()

    async def stop(self, timeout_seconds: float = 10.0) -> None:
        if self._proc.returncode is None:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=timeout_seconds)
            except (asyncio.TimeoutError, ProcessLookupError):
                await self.kill()

    async def kill(self) -> None:
        if self._proc.returncode is None:
            try:
                self._proc.kill()
                await self._proc.wait()
            except ProcessLookupError:
                pass

    @property
    def container_id(self) -> str:
        return f"in-memory:{self._proc.pid}"


# ---------------------------------------------------------------------------
# DockerSandboxRunner — backed by aiodocker (Phase 3+)
# ---------------------------------------------------------------------------

class DockerSandboxRunner(SandboxRunner):
    """aiodocker-backed runner. Requires Docker daemon. Used in production."""

    def __init__(self, container, container_id: str) -> None:
        self._container = container
        self._container_id = container_id

    @classmethod
    async def start(
        cls,
        session: "Session",
        runtime: "Runtime",
        model: str,
        env: dict[str, str],
        limits: ResourceLimits,
        network_policy: NetworkPolicy,
        registry: str = "atrium",
    ) -> "DockerSandboxRunner":
        try:
            import aiodocker
        except ImportError:
            raise RuntimeError(
                "aiodocker is not installed. Install with: pip install aiodocker"
            )

        docker = aiodocker.Docker()
        image = runtime.image_tag(registry)

        env_list = [f"{k}={v}" for k, v in env.items()]
        env_list.append(f"ATRIUM_WORKSPACE_DIR=/workspace")

        config = {
            "Image": image,
            "Cmd": runtime.command(model, None),
            "Env": env_list,
            "WorkingDir": "/workspace",
            "User": "10001:10001",
            "AttachStdin": True,
            "AttachStdout": True,
            "AttachStderr": True,
            "OpenStdin": True,
            "StdinOnce": False,
            "HostConfig": {
                "Binds": [f"{session.workspace_path}:/workspace:rw"],
                "Memory": limits.memory_mb * 1024 * 1024,
                "NanoCpus": int(limits.cpus * 1_000_000_000),
                "AutoRemove": True,
                "SecurityOpt": ["no-new-privileges:true"],
                "ReadonlyRootfs": True,
                "Tmpfs": {"/tmp": "rw,size=100m"},
                "NetworkMode": "bridge",
            },
        }
        container = await docker.containers.create(config=config)
        await container.start()
        cid = container.id
        return cls(container, cid)

    async def stream_events(self) -> AsyncIterator[bytes]:  # type: ignore[override]
        logs = self._container.log(stdout=True, stderr=False, follow=True)
        async for chunk in logs:
            line = chunk.strip().encode() if isinstance(chunk, str) else chunk.strip()
            if line:
                yield line

    async def send_input(self, text: str) -> None:
        await self._container.websocket(stdin=True, stdout=True)
        # Simplified: uses exec for input
        exec_inst = await self._container.exec(
            ["sh", "-c", f"echo {repr(text)}"],
        )
        await exec_inst.start()

    async def stop(self, timeout_seconds: float = 10.0) -> None:
        try:
            await self._container.stop(t=int(timeout_seconds))
        except Exception:
            pass

    async def kill(self) -> None:
        try:
            await self._container.kill(signal="SIGKILL")
        except Exception:
            pass

    @property
    def container_id(self) -> str:
        return self._container_id
