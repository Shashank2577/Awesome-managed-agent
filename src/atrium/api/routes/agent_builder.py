"""Agent builder routes — create and delete config-driven agents at runtime."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


# ------------------------------------------------------------------
# Request schema
# ------------------------------------------------------------------

class CreateAgentRequest(BaseModel):
    name: str
    description: str
    capabilities: list[str] = []
    api_url: str
    method: str = "GET"
    headers: dict[str, str] = {}
    query_params: dict[str, str] = {}
    response_path: str = ""


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.post("/agents/create", status_code=201)
async def create_agent(req: CreateAgentRequest) -> dict:
    """Create a new config-driven HTTP agent and register it."""
    from atrium.api.app import get_registry, get_agent_store

    registry = get_registry()
    store = get_agent_store()

    if registry is None or store is None:
        raise HTTPException(500, "Server not fully initialized")

    config = req.model_dump()

    # Reject duplicates
    try:
        registry.get(req.name)
        raise HTTPException(400, f"Agent '{req.name}' already exists")
    except KeyError:
        pass

    # Create the Agent subclass and register it
    from atrium.core.http_agent import create_agent_class

    agent_cls = create_agent_class(config)
    registry.register(agent_cls)

    # Persist so the agent survives restarts
    store.save(config)

    return {
        "name": req.name,
        "status": "registered",
        "message": f"Agent '{req.name}' created and ready for Commander",
    }


@router.get("/agents/{name}/config")
async def get_agent_config(name: str) -> dict:
    """Return the full persisted config for a UI-created agent."""
    from atrium.api.app import get_agent_store

    store = get_agent_store()
    if store is None:
        raise HTTPException(500, "Server not fully initialized")

    config = store.load(name)
    if not config:
        raise HTTPException(404, f"No config found for agent '{name}'")
    return config


@router.delete("/agents/{name}")
async def delete_agent(name: str) -> dict:
    """Remove a config-driven agent from persistent storage."""
    from atrium.api.app import get_agent_store

    store = get_agent_store()
    if store is None:
        raise HTTPException(500, "Server not fully initialized")

    store.delete(name)
    return {"name": name, "status": "deleted"}
