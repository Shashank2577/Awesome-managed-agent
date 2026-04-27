"""Agent registry routes — list and detail."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from atrium.api.schemas import AgentInfoResponse, AgentListResponse

router = APIRouter()


def _agent_info(cls) -> AgentInfoResponse:
    return AgentInfoResponse(
        name=cls.name,
        description=cls.description,
        capabilities=list(cls.capabilities),
        input_schema=cls.input_schema,
        output_schema=cls.output_schema,
    )


@router.get("/agents", response_model=AgentListResponse)
async def list_agents() -> AgentListResponse:
    """Return all registered agents with their capabilities."""
    from atrium.api.app import get_registry

    registry = get_registry()
    if registry is None:
        return AgentListResponse(agents=[])
    return AgentListResponse(agents=[_agent_info(cls) for cls in registry.list_all()])


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
