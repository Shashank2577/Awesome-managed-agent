"""Agent registry routes — list and detail."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException

from atrium.api.schemas import AgentInfoResponse, AgentListResponse
from atrium.core.categories import CATEGORIES

router = APIRouter()


def _serialize_schema(schema: dict | None) -> dict | None:
    """Convert Python type objects in schemas to string names for JSON."""
    if schema is None:
        return None
    result = {}
    for key, val in schema.items():
        if isinstance(val, type):
            result[key] = val.__name__
        elif hasattr(val, "__origin__"):  # e.g. list[str]
            result[key] = str(val)
        else:
            result[key] = str(val)
    return result


def _agent_info(cls) -> AgentInfoResponse:
    return AgentInfoResponse(
        name=cls.name,
        description=cls.description,
        capabilities=list(cls.capabilities),
        input_schema=_serialize_schema(cls.input_schema),
        output_schema=_serialize_schema(cls.output_schema),
        category=getattr(cls, "category", None),
        agent_type=getattr(cls, "agent_type", "http"),
    )


@router.get("/agents/categories")
async def list_categories() -> dict:
    """Return all valid agent category values."""
    return {"categories": list(CATEGORIES)}


@router.get("/agents", response_model=AgentListResponse)
async def list_agents(category: Optional[str] = None) -> AgentListResponse:
    """Return all registered agents with their capabilities.

    Optional ``?category=<cat>`` query param filters results server-side.
    """
    from atrium.api.app import get_registry

    registry = get_registry()
    if registry is None:
        return AgentListResponse(agents=[])

    agents = [_agent_info(cls) for cls in registry.list_all()]

    if category is not None:
        agents = [a for a in agents if a.category == category]

    return AgentListResponse(agents=agents)


@router.get("/agents/{name}", response_model=AgentInfoResponse)
async def get_agent(name: str) -> AgentInfoResponse:
    """Return detail for a specific agent by name."""
    from atrium.api.app import get_registry

    registry = get_registry()
    if registry is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        cls = registry.get(name)
    except KeyError:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _agent_info(cls)
