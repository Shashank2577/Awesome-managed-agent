"""HarnessAgent — base class for agents backed by a sandboxed runtime.

Subclasses declare:
    runtime: Runtime          # e.g. OpenAgentSDKRuntime()
    model: str                # e.g. "anthropic:claude-sonnet-4-6"
    timeout_seconds: int      # wall-clock limit
    max_tool_calls: int       # tool-call guardrail
    system_prompt: str        # injected into the container

Usage::

    class CodeResearchAgent(HarnessAgent):
        name = "code_research"
        runtime = OpenAgentSDKRuntime()
        model = "anthropic:claude-sonnet-4-6"
        timeout_seconds = 1800
        max_tool_calls = 150
        system_prompt = "..."
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, TYPE_CHECKING

from atrium.core.agent import Agent
from atrium.core.errors import GuardrailViolation
from atrium.harness.bridge import BridgeResult, BridgeStream, GuardrailEnforcer
from atrium.harness.sandbox import InMemorySandboxRunner, ResourceLimits, NetworkPolicy
from atrium.harness.session import Session, SessionStatus

if TYPE_CHECKING:
    from atrium.core.artifact_store import ArtifactStore
    from atrium.harness.runtimes.base import Runtime
    from atrium.harness.session import SessionStore
    from atrium.streaming.events import EventRecorder

logger = logging.getLogger(__name__)


class HarnessAgent(Agent):
    """Agent whose inner loop runs inside a sandboxed container.

    Subclasses must declare: runtime, model, timeout_seconds, max_tool_calls,
    system_prompt (optional). All other Agent lifecycle hooks work normally.
    """

    # --- Class-level configuration: override in subclasses ---
    runtime: "Runtime" = None  # type: ignore[assignment]
    model: str = ""
    timeout_seconds: int = 1800
    max_tool_calls: int = 200
    max_cost_usd: float | None = None
    system_prompt: str = ""

    # --- Injected by factory (not by subclass) ---
    _session_store: "SessionStore | None" = None
    _artifact_store: "ArtifactStore | None" = None
    _sandbox_runner_cls = InMemorySandboxRunner  # overridden to DockerSandboxRunner in prod

    async def run(self, input_data: dict) -> dict:
        """Drive one harness session end-to-end."""
        workspace_id = input_data.get("workspace_id", "default")
        objective = input_data.get("objective", "")
        model = input_data.get("model_override") or self.model

        # --- 1. Create session ---
        session = Session(
            workspace_id=workspace_id,
            title=objective[:80],
            objective=objective,
            runtime=self.runtime.name if self.runtime else "echo",
            model=model,
            parent_thread_id=input_data.get("thread_id"),
        )

        if self._session_store is not None:
            session = await self._session_store.create(session)
        else:
            # Fallback: use a temp dir for the workspace
            ws_dir = Path(tempfile.mkdtemp(prefix="atrium_session_"))
            ws_dir.chmod(0o700)
            session = session.model_copy(update={"workspace_path": str(ws_dir)})

        recorder = self._get_recorder()
        await recorder.emit(
            session.session_id,
            "SESSION_CREATED",
            {
                "session_id": session.session_id,
                "agent": self.name,
                "objective": objective,
                "runtime": session.runtime,
                "model": model,
            },
        )

        # --- 2. Write system_prompt to a temp file if present ---
        system_prompt_path: str | None = None
        if self.system_prompt:
            sp_file = session.workspace_dir / ".atrium" / "system_prompt.txt"
            sp_file.parent.mkdir(parents=True, exist_ok=True)
            sp_file.write_text(self.system_prompt)
            system_prompt_path = str(sp_file)

        # --- 3. Start sandbox ---
        runtime = self.runtime
        env: dict[str, str] = {}
        if runtime:
            for env_key in runtime.required_env(model):
                val = os.environ.get(env_key, "")
                if val:
                    env[env_key] = val

        limits = ResourceLimits(wall_clock_seconds=self.timeout_seconds)
        policy = NetworkPolicy(
            allow_egress=[runtime.model_endpoint(model)] if runtime else [],
        )

        sandbox = await self._sandbox_runner_cls.start(
            session=session,
            runtime=runtime,
            model=model,
            env=env,
            limits=limits,
            network_policy=policy,
        )

        if self._session_store is not None:
            await self._session_store.set_container_id(
                workspace_id, session.session_id, sandbox.container_id
            )
            await self._session_store.set_status(
                workspace_id, session.session_id, SessionStatus.RUNNING
            )

        await recorder.emit(
            session.session_id,
            "SESSION_RUNNING",
            {"container_id": sandbox.container_id},
        )

        # --- 4. Bridge drives the session ---
        artifact_store = self._artifact_store
        if artifact_store is None:
            from atrium.core.artifact_store import ArtifactStore
            artifact_store = ArtifactStore(":memory:")
            await artifact_store.open()

        guardrails = GuardrailEnforcer(
            max_tool_calls=self.max_tool_calls,
            max_cost_usd=self.max_cost_usd,
        )
        bridge = BridgeStream(sandbox, session, recorder, artifact_store, guardrails)

        try:
            result: BridgeResult = await asyncio.wait_for(
                bridge.run(objective, max_tool_calls=self.max_tool_calls),
                timeout=self.timeout_seconds,
            )

            if self._session_store is not None:
                await self._session_store.set_status(
                    workspace_id, session.session_id, SessionStatus.COMPLETED
                )

            await recorder.emit(
                session.session_id,
                "SESSION_COMPLETED",
                {
                    "final_message": result.final_message,
                    "artifacts": [a.artifact_id for a in result.artifacts],
                    "tokens_used": result.tokens_used,
                    "cost_usd": result.cost_usd,
                },
            )

            return {
                "result": result.final_message,
                "artifacts": [a.artifact_id for a in result.artifacts],
                "session_id": session.session_id,
                "tokens_used": result.tokens_used,
                "cost_usd": result.cost_usd,
            }

        except (GuardrailViolation, asyncio.TimeoutError) as exc:
            if self._session_store is not None:
                try:
                    await self._session_store.set_status(
                        workspace_id, session.session_id, SessionStatus.FAILED
                    )
                except Exception:
                    pass
            error_msg = str(exc)
            error_code = getattr(exc, "code", "timeout") if isinstance(exc, GuardrailViolation) else "timeout"
            await recorder.emit(
                session.session_id,
                "SESSION_FAILED",
                {"error": error_msg, "error_code": error_code},
            )
            raise

        finally:
            await sandbox.stop()

    def _get_recorder(self) -> "EventRecorder":
        """Get the EventRecorder from self._recorder (set by the orchestrator)."""
        recorder = getattr(self, "_recorder", None)
        if recorder is None:
            from atrium.streaming.events import EventRecorder
            recorder = EventRecorder()
        return recorder
