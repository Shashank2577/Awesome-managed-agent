from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from uuid import UUID


class AgentStatus(str, Enum):
    CREATED = "CREATED"
    REGISTERED = "REGISTERED"
    READY = "READY"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TERMINATED = "TERMINATED"


class ThreadStatus(str, Enum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TERMINATED = "TERMINATED"


class PlanStatus(str, Enum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class NodeStatus(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    RETRYING = "RETRYING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    RETRY_WAIT = "RETRY_WAIT"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ToolInvocationStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"


@dataclass(slots=True)
class Money:
    currency: str
    amount: Decimal


@dataclass(slots=True)
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: Optional[str] = None


@dataclass(slots=True)
class ErrorInfo:
    code: str
    message: str
    retryable: bool
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Thread:
    thread_id: UUID
    org_id: UUID
    project_id: UUID
    status: ThreadStatus
    title: str
    objective: str
    budget_id: UUID
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class Plan:
    plan_id: UUID
    thread_id: UUID
    org_id: UUID
    project_id: UUID
    plan_number: int
    status: PlanStatus
    graph: dict[str, Any]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class PlanNode:
    node_id: UUID
    plan_id: UUID
    thread_id: UUID
    org_id: UUID
    node_key: str
    node_type: str
    depends_on: list[str]
    status: NodeStatus
    timeout_ms: int
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentInstance:
    instance_id: UUID
    thread_id: UUID
    plan_id: UUID
    node_id: UUID
    org_id: UUID
    agent_type: str
    status: AgentStatus
    input: dict[str, Any]
    output: Optional[dict[str, Any]] = None
    error: Optional[ErrorInfo] = None
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    cost: Money = field(default_factory=lambda: Money(currency="USD", amount=Decimal("0")))


@dataclass(slots=True)
class WorkerJob:
    job_id: UUID
    org_id: UUID
    thread_id: UUID
    instance_id: UUID
    status: JobStatus
    retry_count: int = 0


@dataclass(slots=True)
class ToolInvocation:
    invocation_id: UUID
    org_id: UUID
    thread_id: UUID
    instance_id: UUID
    tool_id: str
    status: ToolInvocationStatus
    input: dict[str, Any]
    output: Optional[dict[str, Any]] = None


