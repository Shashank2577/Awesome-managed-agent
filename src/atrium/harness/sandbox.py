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
        mcp_socket_path: str | None = None,
        session_token: str | None = None,
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
        env_list.append("ATRIUM_WORKSPACE_DIR=/workspace")

        # Phase 4: MCP gateway wiring
        _mcp_socket = "/run/atrium/mcp.sock"
        if network_policy.allow_mcp and mcp_socket_path and session_token:
            env_list.append(f"ATRIUM_MCP_SOCKET={_mcp_socket}")
            env_list.append(f"ATRIUM_SESSION_TOKEN={session_token}")

        binds = [f"{session.workspace_path}:/workspace:rw"]
        if network_policy.allow_mcp and mcp_socket_path:
            binds.append(f"{mcp_socket_path}:{_mcp_socket}:rw")

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
                "Binds": binds,
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


# ---------------------------------------------------------------------------
# KubernetesSandboxRunner — backed by kubernetes_asyncio (Phase 6)
# ---------------------------------------------------------------------------

class KubernetesSandboxRunner(SandboxRunner):
    """Kubernetes-backed runner. Uses persistent volumes for workspaces."""

    def __init__(self, pod_name: str, namespace: str, session_id: str) -> None:
        self._pod_name = pod_name
        self._namespace = namespace
        self._session_id = session_id
        self._core_api = None

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
        mcp_socket_path: str | None = None,
        session_token: str | None = None,
    ) -> "KubernetesSandboxRunner":
        try:
            from kubernetes_asyncio import client, config, watch
        except ImportError:
            raise RuntimeError("kubernetes_asyncio is not installed")

        try:
            await config.load_incluster_config()
        except config.ConfigException:
            await config.load_kube_config()

        core_api = client.CoreV1Api()
        pod_name = f"atrium-session-{session.session_id[:8]}"
        namespace = os.getenv("ATRIUM_SANDBOX_NAMESPACE", "default")
        storage_class = os.getenv("ATRIUM_SANDBOX_STORAGE_CLASS", "standard")

        # PVC
        pvc = client.V1PersistentVolumeClaim(
            metadata=client.V1ObjectMeta(name=f"{pod_name}-workspace", namespace=namespace),
            spec=client.V1PersistentVolumeClaimSpec(
                access_modes=["ReadWriteOnce"],
                resources=client.V1VolumeResourceRequirements(
                    requests={"storage": f"{limits.disk_mb}Mi"}
                ),
                storage_class_name=storage_class,
            ),
        )
        try:
            await core_api.create_namespaced_persistent_volume_claim(namespace, pvc)
        except client.ApiException as e:
            if e.status != 409:
                raise

        env_list = [client.V1EnvVar(name=k, value=v) for k, v in env.items()]
        env_list.append(client.V1EnvVar(name="ATRIUM_WORKSPACE_DIR", value="/workspace"))

        _mcp_socket = "/run/atrium/mcp.sock"
        if network_policy.allow_mcp and mcp_socket_path and session_token:
            env_list.append(client.V1EnvVar(name="ATRIUM_MCP_SOCKET", value=_mcp_socket))
            env_list.append(client.V1EnvVar(name="ATRIUM_SESSION_TOKEN", value=session_token))

        volume_mounts = [
            client.V1VolumeMount(name="workspace", mount_path="/workspace"),
            client.V1VolumeMount(name="tmp", mount_path="/tmp"),
        ]
        volumes = [
            client.V1Volume(
                name="workspace",
                persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                    claim_name=f"{pod_name}-workspace"
                ),
            ),
            client.V1Volume(name="tmp", empty_dir=client.V1EmptyDirVolumeSource(medium="Memory")),
        ]

        if network_policy.allow_mcp and mcp_socket_path:
            volume_mounts.append(client.V1VolumeMount(name="mcp-socket", mount_path="/run/atrium"))
            volumes.append(client.V1Volume(
                name="mcp-socket",
                host_path=client.V1HostPathVolumeSource(path=mcp_socket_path)
            ))

        pod = client.V1Pod(
            metadata=client.V1ObjectMeta(
                name=pod_name,
                namespace=namespace,
                labels={
                    "app": "atrium-sandbox",
                    "session-id": session.session_id,
                    "workspace-id": session.workspace_id,
                },
            ),
            spec=client.V1PodSpec(
                restart_policy="Never",
                automount_service_account_token=False,
                security_context=client.V1PodSecurityContext(
                    run_as_user=10001, run_as_group=10001, fs_group=10001,
                ),
                containers=[
                    client.V1Container(
                        name="sandbox",
                        image=runtime.image_tag(registry),
                        command=runtime.command(model, "/workspace/.atrium/system_prompt.txt"),
                        env=env_list,
                        resources=client.V1ResourceRequirements(
                            requests={
                                "cpu": str(limits.cpus),
                                "memory": f"{limits.memory_mb}Mi",
                            },
                            limits={
                                "cpu": str(limits.cpus),
                                "memory": f"{limits.memory_mb}Mi",
                            },
                        ),
                        security_context=client.V1SecurityContext(
                            allow_privilege_escalation=False,
                            read_only_root_filesystem=True,
                            capabilities=client.V1Capabilities(drop=["ALL"]),
                        ),
                        volume_mounts=volume_mounts,
                        stdin=True, stdin_once=True, tty=False,
                    ),
                ],
                volumes=volumes,
                active_deadline_seconds=limits.wall_clock_seconds,
            ),
        )

        try:
            await core_api.create_namespaced_pod(namespace, pod)
        except client.ApiException as e:
            if e.status != 409:
                raise

        # Wait for Running
        w = watch.Watch()
        async for event in w.stream(core_api.list_namespaced_pod, namespace, field_selector=f"metadata.name={pod_name}", timeout_seconds=60):
            if event["object"].status.phase in ("Running", "Failed", "Succeeded"):
                w.stop()
                break

        runner = cls(pod_name=pod_name, namespace=namespace, session_id=session.session_id)
        runner._core_api = core_api
        return runner

    async def stream_events(self) -> AsyncIterator[bytes]:
        try:
            from kubernetes_asyncio import client
        except ImportError:
            return

        if not self._core_api:
            self._core_api = client.CoreV1Api()

        try:
            resp = await self._core_api.read_namespaced_pod_log(
                name=self._pod_name,
                namespace=self._namespace,
                follow=True,
                _preload_content=False,
            )
            async for chunk in resp.content:
                line = chunk.strip()
                if line:
                    yield line
        except client.ApiException:
            pass

    async def send_input(self, text: str) -> None:
        try:
            from kubernetes_asyncio import client
            from kubernetes_asyncio.stream import WsApiClient
        except ImportError:
            return

        if not self._core_api:
            self._core_api = client.CoreV1Api()
            
        try:
            ws_client = WsApiClient()
            resp = await ws_client.stream(
                self._core_api.connect_post_namespaced_pod_exec,
                self._pod_name,
                self._namespace,
                command=["sh", "-c", f"echo {repr(text)}"],
                stderr=True, stdin=False,
                stdout=True, tty=False,
            )
        except client.ApiException:
            pass

    async def stop(self, timeout_seconds: float = 10.0) -> None:
        try:
            from kubernetes_asyncio import client
        except ImportError:
            return

        if not self._core_api:
            self._core_api = client.CoreV1Api()
            
        try:
            await self._core_api.delete_namespaced_pod(
                name=self._pod_name,
                namespace=self._namespace,
                grace_period_seconds=int(timeout_seconds),
            )
        except client.ApiException:
            pass

    async def kill(self) -> None:
        try:
            from kubernetes_asyncio import client
        except ImportError:
            return

        if not self._core_api:
            self._core_api = client.CoreV1Api()
            
        try:
            await self._core_api.delete_namespaced_pod(
                name=self._pod_name,
                namespace=self._namespace,
                grace_period_seconds=0,
            )
        except client.ApiException:
            pass

    @property
    def container_id(self) -> str:
        return f"k8s:{self._namespace}:{self._pod_name}"
