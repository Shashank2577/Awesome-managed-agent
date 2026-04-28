"""Thin wrapper exposing async_retry for use within the engine layer.

Graph builder imports from here so the engine doesn't depend directly on
atrium.core.retry (keeping the import tree clean: engine -> engine/retry_utils,
engine/retry_utils -> core/retry).
"""
from __future__ import annotations

from atrium.core.retry import async_retry


async def async_retry_agent(fn, *, max_attempts: int = 3):
    """Retry an agent run() call with exponential backoff."""
    return await async_retry(fn, max_attempts=max_attempts)
