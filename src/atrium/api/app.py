"""FastAPI application factory for Atrium."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from atrium.api.middleware import setup_middleware
from atrium.api.routes import health, threads, control, registry as registry_router
from atrium.api.routes import agent_builder
from atrium.api.routes import sessions, mcp_servers, webhooks, widgets, artifacts
from atrium.core import logging as atrium_logging
from atrium.core.agent_store import AgentStore
from atrium.core.guardrails import GuardrailsConfig
from atrium.core import agent_factory
from atrium.core.registry import AgentRegistry
from atrium.core.thread_store import ThreadStore
from atrium.engine.orchestrator import ThreadOrchestrator
from atrium.streaming.events import EventRecorder
from atrium.observability import tracing
from prometheus_fastapi_instrumentator import Instrumentator

# ---------------------------------------------------------------------------
# Module-level state — set once by create_app, read by route modules
# ---------------------------------------------------------------------------

_registry: Optional[AgentRegistry] = None
_recorder: Optional[EventRecorder] = None
_orchestrator: Optional[ThreadOrchestrator] = None
_agent_store: Optional[AgentStore] = None
_thread_store: Optional[ThreadStore] = None


def get_registry() -> Optional[AgentRegistry]:
    return _registry


def get_recorder() -> Optional[EventRecorder]:
    return _recorder


def get_orchestrator() -> Optional[ThreadOrchestrator]:
    return _orchestrator


def get_agent_store() -> Optional[AgentStore]:
    return _agent_store


def get_thread_store() -> Optional[ThreadStore]:
    return _thread_store


_DEV_KEY_FILE = Path("atrium_dev_key.txt")


async def _bootstrap_dev_workspace(app_state: "AppState", logger: logging.Logger) -> Optional[str]:
    """Create a default workspace + API key if none exist. Returns plaintext key."""
    if _DEV_KEY_FILE.exists():
        return _DEV_KEY_FILE.read_text().strip()

    from atrium.core.auth import ApiKeyKind

    try:
        ws = await app_state.workspace_store.create_workspace("Development")
        _, secret = await app_state.workspace_store.issue_key(
            workspace_id=ws.workspace_id,
            kind=ApiKeyKind.WORKSPACE,
            name="dev-auto",
        )
        _DEV_KEY_FILE.write_text(secret)
        return secret
    except Exception as exc:
        logger.warning("Dev workspace bootstrap failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_app(
    registry: Optional[AgentRegistry] = None,
    llm_config: Optional[str] = None,
    guardrails: Optional[GuardrailsConfig] = None,
    db_path: str = "atrium_agents.db",
    events_db_path: str = "atrium_events.db",
    threads_db_path: str = "atrium_threads.db",
) -> FastAPI:
    """Create and configure the Atrium FastAPI application.

    Args:
        registry: Agent registry to use. Defaults to an empty ``AgentRegistry``.
        llm_config: LLM configuration string (e.g. ``"openai:gpt-4o-mini"``).
        guardrails: Guardrails configuration. Defaults to ``GuardrailsConfig()``.
        db_path: SQLite database path for persistent agent storage.
        events_db_path: SQLite database path for event records.
        threads_db_path: SQLite database path for thread records.

    Returns:
        Configured ``FastAPI`` application instance.
    """
    global _registry, _recorder, _orchestrator, _agent_store, _thread_store

    # Structured JSON logging from startup
    log_level = os.getenv("ATRIUM_LOG_LEVEL", "INFO")
    atrium_logging.configure(level=log_level)
    logger = logging.getLogger(__name__)

    from atrium.seeds import iter_seeds  # local import keeps top-level imports lean

    _registry = registry or AgentRegistry()
    _recorder = EventRecorder(db_path=events_db_path if events_db_path != ":memory:" else None)
    _agent_store = AgentStore(db_path=db_path)
    _thread_store = ThreadStore(db_path=threads_db_path)

    # Populate from the built-in seed corpus on first boot
    seeded = _agent_store.seed_if_empty(iter_seeds())
    if seeded:
        logger.info("Seeded agents from corpus", extra={"count": seeded})

    # Load previously-saved config-driven agents into the registry
    for saved_config in _agent_store.load_all():
        try:
            agent_cls = agent_factory.build_agent_class(saved_config)
            _registry.register(agent_cls)
        except Exception as exc:
            logger.warning("Failed to load saved agent config: %s", exc)

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

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Open persistent stores on startup
        await _recorder.open()
        await _thread_store.open()
        await app_state.workspace_store.open()
        await app_state.mcp_server_store.open()
        await app_state.session_store.open()

        # Dev-mode bootstrap: auto-create workspace + API key on first boot
        dev_key: Optional[str] = None
        if os.getenv("ATRIUM_DEV_MODE"):
            dev_key = await _bootstrap_dev_workspace(app_state, logger)
            if dev_key:
                logger.info(
                    "ATRIUM DEV MODE — API key: %s  (also in atrium_dev_key.txt)",
                    dev_key,
                )

        logger.info("Atrium started — stores opened")
        yield
        # Close on shutdown
        await app_state.workspace_store.close()
        await app_state.shutdown()
        logger.info("Atrium shutdown — stores closed")

    app = FastAPI(
        title="Atrium",
        description="Observable, cost-bounded, human-in-the-loop agent orchestration",
        version="0.1.0",
        lifespan=lifespan,
    )

    from atrium.api.state import AppState
    from atrium.core.config import get_config
    from atrium.core.storage.sqlite import SQLiteStorage
    from atrium.core.workspace_store import WorkspaceStore
    from atrium.core.mcp_server_store import MCPServerStore
    from atrium.harness.session import SessionStore

    app_state = AppState(
        config=get_config(),
        storage=SQLiteStorage("atrium.db"),
        workspace_store=WorkspaceStore("atrium.db"),  # accepts str path directly
        thread_store=_thread_store,
        agent_store=_agent_store,
        recorder=_recorder,
        mcp_server_store=MCPServerStore("atrium_mcp.db"),
        session_store=SessionStore("atrium_sessions.db"),
    )
    app.state.atrium = app_state
    AppState.set_instance(app_state)

    setup_middleware(app)

    # Observability
    tracing.configure("atrium-api")
    tracing.instrument_app(app)
    Instrumentator().instrument(app).expose(app)

    # Include all route groups under /api/v1
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(threads.router, prefix="/api/v1")
    app.include_router(control.router, prefix="/api/v1")
    app.include_router(registry_router.router, prefix="/api/v1")
    app.include_router(agent_builder.router, prefix="/api/v1")
    app.include_router(sessions.router)
    app.include_router(mcp_servers.router)
    app.include_router(webhooks.router)
    app.include_router(widgets.router)
    app.include_router(artifacts.router)

    # Mount dashboard static files if available
    dashboard_dir = os.path.join(os.path.dirname(__file__), "..", "dashboard", "static")
    dashboard_dir = os.path.normpath(dashboard_dir)
    if os.path.isdir(dashboard_dir):
        app.mount("/dashboard/static", StaticFiles(directory=dashboard_dir), name="dashboard-static")

        @app.get("/dashboard", include_in_schema=False)
        async def serve_dashboard():
            return FileResponse(os.path.join(dashboard_dir, "console.html"))

    @app.get("/api/v1/setup", include_in_schema=False)
    async def dev_setup():
        """Dev-mode only: return the bootstrap API key so the UI can self-configure."""
        if not os.getenv("ATRIUM_DEV_MODE"):
            raise HTTPException(404)
        if not _DEV_KEY_FILE.exists():
            raise HTTPException(503, detail="Dev setup not complete — server still starting")
        return JSONResponse({"api_key": _DEV_KEY_FILE.read_text().strip(), "dev": True})

    @app.get("/", include_in_schema=False)
    async def root_redirect():
        return RedirectResponse(url="/dashboard")

    return app
