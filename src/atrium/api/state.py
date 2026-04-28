"""Per-app dependency container. Holds storage, stores, recorder, orchestrator."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from atrium.core.config import AtriumConfig
from atrium.core.storage import Storage
from atrium.core.workspace_store import WorkspaceStore
from atrium.core.thread_store import ThreadStore
from atrium.core.agent_store import AgentStore
from atrium.streaming.events import EventRecorder

if TYPE_CHECKING:
    from atrium.core.registry import AgentRegistry
    from atrium.engine.orchestrator import ThreadOrchestrator


@dataclass
class AppState:
    config: AtriumConfig
    storage: Storage
    workspace_store: WorkspaceStore
    thread_store: ThreadStore
    agent_store: AgentStore
    recorder: EventRecorder
    # per-workspace caches
    _registries: dict[str, "AgentRegistry"] = field(default_factory=dict)
    _orchestrators: dict[str, "ThreadOrchestrator"] = field(default_factory=dict)

    def get_registry(self, workspace_id: str) -> "AgentRegistry":
        """Return per-workspace agent registry, creating and seeding if needed."""
        if workspace_id not in self._registries:
            from atrium.core.registry import AgentRegistry
            from atrium.core import agent_factory
            reg = AgentRegistry()
            # Load saved configs for this workspace
            for cfg in self.agent_store.load_all_for_workspace(workspace_id):
                try:
                    cls = agent_factory.build_agent_class(cfg)
                    reg.register(cls)
                except Exception:
                    pass
            self._registries[workspace_id] = reg
        return self._registries[workspace_id]

    def get_orchestrator(self, workspace_id: str) -> "ThreadOrchestrator":
        """Return per-workspace orchestrator, creating if needed."""
        if workspace_id not in self._orchestrators:
            from atrium.core.guardrails import GuardrailsConfig
            from atrium.engine.orchestrator import ThreadOrchestrator
            self._orchestrators[workspace_id] = ThreadOrchestrator(
                registry=self.get_registry(workspace_id),
                recorder=self.recorder,
                guardrails=GuardrailsConfig(),
                llm_config=self.config.db_url,  # overridden per request if needed
            )
        return self._orchestrators[workspace_id]

    async def shutdown(self) -> None:
        """Close all open resources."""
        await self.storage.close()
        await self.recorder.close()


def get_app_state(request: Any) -> AppState:
    """FastAPI dependency that returns the AppState attached to the app."""
    return request.app.state.atrium
