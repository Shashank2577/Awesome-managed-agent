"""Workspace and API key models + hashing helpers."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WorkspaceQuota(BaseModel):
    max_concurrent_sessions: int = 10
    max_concurrent_threads: int = 50
    max_monthly_spend_usd: float = 1000.0
    max_agents_registered: int = 200


class Workspace(BaseModel):
    workspace_id: str = Field(default_factory=lambda: f"ws_{uuid4().hex}")
    name: str
    quota: WorkspaceQuota = Field(default_factory=WorkspaceQuota)
    created_at: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApiKeyKind(str, Enum):
    WORKSPACE = "workspace"  # full access to one workspace
    READ_ONLY = "read_only"  # read-only access to one workspace
    ADMIN = "admin"          # cross-workspace admin access


class ApiKey(BaseModel):
    api_key_id: str = Field(default_factory=lambda: f"ak_{uuid4().hex[:12]}")
    workspace_id: str | None  # None for ADMIN keys
    kind: ApiKeyKind = ApiKeyKind.WORKSPACE
    hash: str                 # sha256 hex of the secret
    name: str = ""            # human-readable label
    created_at: datetime = Field(default_factory=_utcnow)
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


def generate_secret() -> str:
    """Generate a new API key secret. 64 hex chars (256 bits)."""
    return secrets.token_hex(32)


def hash_secret(secret: str) -> str:
    """Hash a secret for storage. Constant-time-comparable via the hash itself."""
    return hashlib.sha256(secret.encode()).hexdigest()


def verify_secret(secret: str, expected_hash: str) -> bool:
    """Constant-time comparison of a secret against its stored hash."""
    return secrets.compare_digest(hash_secret(secret), expected_hash)
