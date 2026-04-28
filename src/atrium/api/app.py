"""FastAPI application factory for Atrium."""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from atrium.api.middleware import setup_middleware
from atrium.api.routes import health, threads, control, registry as registry_router
from atrium.api.routes import agent_builder
from atrium.core.agent_store import AgentStore
from atrium.core.guardrails import GuardrailsConfig
from atrium.core import agent_factory
from atrium.core.registry import AgentRegistry
from atrium.engine.orchestrator import ThreadOrchestrator
from atrium.streaming.events import EventRecorder

# ---------------------------------------------------------------------------
# Module-level state — set once by create_app, read by route modules
# ---------------------------------------------------------------------------

_registry: Optional[AgentRegistry] = None
_recorder: Optional[EventRecorder] = None
_orchestrator: Optional[ThreadOrchestrator] = None
_agent_store: Optional[AgentStore] = None


def get_registry() -> Optional[AgentRegistry]:
    return _registry


def get_recorder() -> Optional[EventRecorder]:
    return _recorder


def get_orchestrator() -> Optional[ThreadOrchestrator]:
    return _orchestrator


def get_agent_store() -> Optional[AgentStore]:
    return _agent_store


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_app(
    registry: Optional[AgentRegistry] = None,
    llm_config: Optional[str] = None,
    guardrails: Optional[GuardrailsConfig] = None,
    db_path: str = "atrium_agents.db",
) -> FastAPI:
    """Create and configure the Atrium FastAPI application.

    Args:
        registry: Agent registry to use. Defaults to an empty ``AgentRegistry``.
        llm_config: LLM configuration string (e.g. ``"openai:gpt-4o-mini"``).
        guardrails: Guardrails configuration. Defaults to ``GuardrailsConfig()``.
        db_path: SQLite database path for persistent agent storage.  Pass
            ``":memory:"`` in tests to ensure full isolation.

    Returns:
        Configured ``FastAPI`` application instance.
    """
    global _registry, _recorder, _orchestrator, _agent_store

    from atrium.seeds import iter_seeds  # local import keeps top-level imports lean

    _registry = registry or AgentRegistry()
    _recorder = EventRecorder(db_path="atrium_events.db")
    _agent_store = AgentStore(db_path=db_path)

    # Populate from the built-in seed corpus on first boot (no-op when the
    # store already contains agent configs, preserving user customisations).
    seeded = _agent_store.seed_if_empty(iter_seeds())
    if seeded:
        logging.info("Seeded %d agents from corpus", seeded)

    # Load previously-saved config-driven agents into the registry
    for saved_config in _agent_store.load_all():
        try:
            agent_cls = agent_factory.build_agent_class(saved_config)
            _registry.register(agent_cls)
        except Exception as exc:
            logging.warning("Failed to load saved agent config: %s", exc)
    _guardrails = guardrails or GuardrailsConfig()

    if llm_config is not None:
        _orchestrator = ThreadOrchestrator(
            registry=_registry,
            recorder=_recorder,
            guardrails=_guardrails,
            llm_config=llm_config,
        )
    else:
        _orchestrator = None

    app = FastAPI(
        title="Atrium",
        description="Observable, cost-bounded, human-in-the-loop agent orchestration",
        version="0.1.0",
    )

    setup_middleware(app)

    # Include all route groups under /api/v1
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(threads.router, prefix="/api/v1")
    app.include_router(control.router, prefix="/api/v1")
    app.include_router(registry_router.router, prefix="/api/v1")
    app.include_router(agent_builder.router, prefix="/api/v1")

    # Mount dashboard static files if available
    dashboard_dir = os.path.join(os.path.dirname(__file__), "..", "dashboard", "static")
    dashboard_dir = os.path.normpath(dashboard_dir)
    if os.path.isdir(dashboard_dir):
        app.mount("/dashboard/static", StaticFiles(directory=dashboard_dir), name="dashboard-static")

        @app.get("/dashboard", include_in_schema=False)
        async def serve_dashboard():
            return FileResponse(os.path.join(dashboard_dir, "console.html"))

    @app.get("/", include_in_schema=False)
    async def root_redirect():
        return RedirectResponse(url="/dashboard")

    return app
