"""Domain models for Atrium — Thread, Plan, Event, Budget."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ThreadStatus(str, Enum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Thread(BaseModel):
    thread_id: str = Field(default_factory=lambda: str(uuid4()))
    objective: str
    title: str = ""
    status: ThreadStatus = ThreadStatus.CREATED
    created_at: datetime = Field(default_factory=_utcnow)


class PlanStep(BaseModel):
    agent: str
    inputs: dict = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    status: str = "pending"


class Plan(BaseModel):
    plan_id: str = Field(default_factory=lambda: str(uuid4()))
    thread_id: str
    plan_number: int = 1
    rationale: str = ""
    steps: list[PlanStep] = Field(default_factory=list)


class AtriumEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    thread_id: str
    type: str
    payload: dict = Field(default_factory=dict)
    sequence: int
    timestamp: datetime = Field(default_factory=_utcnow)
    causation_id: Optional[str] = None


class BudgetSnapshot(BaseModel):
    consumed: str
    limit: str
    currency: str = "USD"
