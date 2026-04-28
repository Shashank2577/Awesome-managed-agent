"""Atrium runtime configuration. Read from environment, cached on first access."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal


@dataclass(frozen=True)
class AtriumConfig:
    db_url: str
    sandbox_backend: Literal["docker", "kubernetes", "in_memory"]
    sandbox_image_registry: str
    sessions_root: str
    artifact_root: str
    mcp_socket_path: str
    max_concurrent_sessions: int
    log_level: str
    admin_api_key_hash: str
    webhook_signing_secret: str
    cors_allowed_origins: tuple[str, ...]


@lru_cache(maxsize=1)
def get_config() -> AtriumConfig:
    return AtriumConfig(
        db_url=os.getenv("ATRIUM_DB_URL", "sqlite:///atrium.sqlite"),
        sandbox_backend=os.getenv("ATRIUM_SANDBOX_BACKEND", "in_memory"),  # type: ignore[arg-type]
        sandbox_image_registry=os.getenv("ATRIUM_SANDBOX_REGISTRY", "atrium"),
        sessions_root=os.getenv("ATRIUM_SESSIONS_ROOT", "/var/atrium/sessions"),
        artifact_root=os.getenv("ATRIUM_ARTIFACT_ROOT", "/var/atrium/artifacts"),
        mcp_socket_path=os.getenv("ATRIUM_MCP_SOCKET", "/run/atrium/mcp.sock"),
        max_concurrent_sessions=int(os.getenv("ATRIUM_MAX_CONCURRENT_SESSIONS", "20")),
        log_level=os.getenv("ATRIUM_LOG_LEVEL", "INFO"),
        admin_api_key_hash=os.getenv("ATRIUM_ADMIN_KEY_HASH", ""),
        webhook_signing_secret=os.getenv("ATRIUM_WEBHOOK_SECRET", ""),
        cors_allowed_origins=tuple(
            o.strip() for o in os.getenv("ATRIUM_CORS_ORIGINS", "*").split(",") if o.strip()
        ),
    )
