"""FastAPI application factory for Atrium."""
from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from atrium.api.middleware import setup_middleware
from atrium.api.routes import health, threads, control, registry as registry_router
from atrium.core.guardrails import GuardrailsConfig
from atrium.core.registry import AgentRegistry
from atrium.engine.orchestrator import ThreadOrchestrator
from atrium.streaming.events import EventRecorder

# ---------------------------------------------------------------------------
# Module-level state — set once by create_app, read by route modules
# ---------------------------------------------------------------------------

_registry: Optional[AgentRegistry] = None
_recorder: Optional[EventRecorder] = None
_orchestrator: Optional[ThreadOrchestrator] = None


def get_registry() -> Optional[AgentRegistry]:
    return _registry


def get_recorder() -> Optional[EventRecorder]:
    return _recorder


def get_orchestrator() -> Optional[ThreadOrchestrator]:
    return _orchestrator


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_app(
    registry: Optional[AgentRegistry] = None,
    llm_config: Optional[str] = None,
    guardrails: Optional[GuardrailsConfig] = None,
) -> FastAPI:
    """Create and configure the Atrium FastAPI application.

    Args:
        registry: Agent registry to use. Defaults to an empty ``AgentRegistry``.
        llm_config: LLM configuration string (e.g. ``"openai:gpt-4o-mini"``).
        guardrails: Guardrails configuration. Defaults to ``GuardrailsConfig()``.

    Returns:
        Configured ``FastAPI`` application instance.
    """
    global _registry, _recorder, _orchestrator

    _registry = registry or AgentRegistry()
    _recorder = EventRecorder()
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
