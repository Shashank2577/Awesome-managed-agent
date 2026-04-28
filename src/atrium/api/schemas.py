"""Pydantic request/response models for the Atrium API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class CreateThreadRequest(BaseModel):
    objective: str


class ThreadResponse(BaseModel):
    thread_id: str
    title: str
    objective: str
    status: str
    created_at: datetime
    stream_url: str


class ThreadListResponse(BaseModel):
    threads: list[ThreadResponse]


class EventResponse(BaseModel):
    event_id: str
    type: str
    payload: dict[str, Any]
    sequence: int
    timestamp: datetime
    causation_id: Optional[str] = None


class AgentInfoResponse(BaseModel):
    name: str
    description: str
    capabilities: list[str]
    input_schema: Optional[dict] = None
    output_schema: Optional[dict] = None
    category: Optional[str] = None
    agent_type: str = "http"


class AgentListResponse(BaseModel):
    agents: list[AgentInfoResponse]


class HealthResponse(BaseModel):
    status: str
    version: str
    agents_registered: int


class HumanInputRequest(BaseModel):
    input: str


class ActionResponse(BaseModel):
    thread_id: str
    accepted: bool
