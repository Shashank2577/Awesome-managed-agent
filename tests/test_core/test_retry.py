"""Phase 0 acceptance tests — async_retry."""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from atrium.core.retry import async_retry


async def test_async_retry_returns_on_first_success():
    fn = AsyncMock(return_value=42)
    result = await async_retry(fn, max_attempts=3)
    assert result == 42
    assert fn.call_count == 1


async def test_async_retry_retries_on_failure_then_succeeds():
    call_count = 0

    async def fn():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("not yet")
        return "ok"

    result = await async_retry(fn, max_attempts=5, initial_delay=0.01)
    assert result == "ok"
    assert call_count == 3


async def test_async_retry_raises_after_max_attempts():
    fn = AsyncMock(side_effect=RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        await async_retry(fn, max_attempts=3, initial_delay=0.01)
    assert fn.call_count == 3


async def test_async_retry_respects_backoff_factor():
    delays = []
    original_sleep = asyncio.sleep

    async def mock_sleep(secs):
        delays.append(secs)

    import atrium.core.retry as retry_module
    retry_module_orig = retry_module.asyncio.sleep
    retry_module.asyncio.sleep = mock_sleep

    call_count = 0

    async def fn():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("x")
        return "done"

    try:
        await async_retry(fn, max_attempts=3, initial_delay=1.0, backoff_factor=2.0, max_delay=100.0)
    finally:
        retry_module.asyncio.sleep = retry_module_orig

    # First sleep ~1.0s (with jitter), second ~2.0s (with jitter)
    assert len(delays) == 2
    assert delays[0] < 2.5  # 1.0 * 1.25 max jitter = 1.25, well below 2.5
    assert delays[1] < 5.0  # 2.0 * 1.25 max jitter = 2.5


async def test_async_retry_non_retryable_exception_propagates_immediately():
    call_count = 0

    async def fn():
        nonlocal call_count
        call_count += 1
        raise TypeError("not retryable")

    with pytest.raises(TypeError):
        await async_retry(fn, max_attempts=5, retry_on=(ValueError,), initial_delay=0.01)
    assert call_count == 1
