"""Health check route."""
from __future__ import annotations

from fastapi import APIRouter

from atrium import __version__
from atrium.api.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Return service status, version, and agent count."""
    from atrium.api.app import get_registry

    registry = get_registry()
    agents_registered = len(registry.list_all()) if registry is not None else 0
    return HealthResponse(
        status="ok",
        version=__version__,
        agents_registered=agents_registered,
    )
