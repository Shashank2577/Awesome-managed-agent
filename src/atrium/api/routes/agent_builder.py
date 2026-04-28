"""Agent builder routes — create and delete config-driven agents at runtime."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator, model_validator

from atrium.core.categories import VALID_CATEGORIES

router = APIRouter()


# ------------------------------------------------------------------
# Request schema
# ------------------------------------------------------------------

class CreateAgentRequest(BaseModel):
    name: str
    description: str
    capabilities: list[str] = []
    api_url: str | None = None
    method: str = "GET"
    headers: dict[str, str] = {}
    query_params: dict[str, str] = {}
    response_path: str = ""
    agent_type: Literal["http", "llm"] = "http"
    category: str | None = None
    system_prompt: str | None = None
    model: str | None = None

    @field_validator("category", mode="after")
    @classmethod
    def _validate_category(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in VALID_CATEGORIES:
            raise ValueError(
                f"Invalid category '{v}'. Must be one of: {sorted(VALID_CATEGORIES)}"
            )
        return v

    @model_validator(mode="after")
    def _validate_type_fields(self) -> "CreateAgentRequest":
        if self.agent_type == "http" and not self.api_url:
            raise ValueError(
                "api_url is required for HTTP agents"
            )
        if self.agent_type == "llm" and not self.system_prompt:
            raise ValueError(
                "system_prompt is required for LLM agents"
            )
        return self


# ------------------------------------------------------------------
# Bulk import schemas
# ------------------------------------------------------------------

class BulkCreateRequest(BaseModel):
    agents: list[dict] = []
    mode: Literal["skip", "replace"] = "skip"


class BulkItemResult(BaseModel):
    name: str
    status: Literal["created", "skipped", "error"]
    detail: str = ""


class BulkCreateResponse(BaseModel):
    results: list[BulkItemResult]


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.post("/agents/create", status_code=201)
async def create_agent(req: CreateAgentRequest) -> dict:
    """Create a new config-driven agent and register it."""
    from atrium.api.app import get_registry, get_agent_store
    from atrium.core import agent_factory

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
    try:
        agent_cls = agent_factory.build_agent_class(config)
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    registry.register(agent_cls)

    # Persist so the agent survives restarts
    store.save(config)

    return {
        "name": req.name,
        "status": "registered",
        "message": f"Agent '{req.name}' created and ready for Commander",
    }


@router.post("/agents/bulk", status_code=200)
async def bulk_create_agents(req: BulkCreateRequest) -> BulkCreateResponse:
    """Bulk-import a list of agents.

    Each item in the request is processed independently; a failure on one
    agent never aborts the rest of the batch.

    ``mode="skip"`` (default) — existing agents are left untouched and
    reported as ``"skipped"``.

    ``mode="replace"`` — existing agents are deleted from registry and store
    before re-creation (upsert semantics).
    """
    from atrium.api.app import get_registry, get_agent_store
    from atrium.core import agent_factory

    registry = get_registry()
    store = get_agent_store()

    if registry is None or store is None:
        raise HTTPException(500, "Server not fully initialized")

    from pydantic import ValidationError

    results: list[BulkItemResult] = []

    for raw_item in req.agents:
        item_name = raw_item.get("name", "unknown") if isinstance(raw_item, dict) else "unknown"

        # Validate individual item — never abort the batch for a bad item
        try:
            agent_req = CreateAgentRequest.model_validate(raw_item)
        except (ValidationError, Exception) as exc:
            results.append(BulkItemResult(name=item_name, status="error", detail=str(exc)))
            continue

        name = agent_req.name
        existing = False
        try:
            registry.get(name)
            existing = True
        except KeyError:
            pass

        if existing:
            if req.mode == "skip":
                results.append(BulkItemResult(name=name, status="skipped", detail="already exists"))
                continue
            # mode == "replace": remove first, then re-create below
            try:
                store.delete(name)
                registry.remove(name)
            except Exception as exc:  # noqa: BLE001
                results.append(BulkItemResult(name=name, status="error", detail=f"delete failed: {exc}"))
                continue

        # Create and register
        try:
            config = agent_req.model_dump()
            agent_cls = agent_factory.build_agent_class(config)
            registry.register(agent_cls)
            store.save(config)
            results.append(BulkItemResult(name=name, status="created"))
        except Exception as exc:  # noqa: BLE001
            results.append(BulkItemResult(name=name, status="error", detail=str(exc)))

    return BulkCreateResponse(results=results)


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
    """Remove a config-driven agent from registry and persistent storage."""
    from atrium.api.app import get_agent_store, get_registry

    store = get_agent_store()
    registry = get_registry()
    if store is None or registry is None:
        raise HTTPException(500, "Server not fully initialized")

    store.delete(name)
    registry.remove(name)
    return {"name": name, "status": "deleted"}
