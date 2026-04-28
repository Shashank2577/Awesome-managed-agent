"""Async retry helper with exponential backoff and jitter."""
from __future__ import annotations

import asyncio
import random
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


async def async_retry(
    fn: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    initial_delay: float = 0.5,
    max_delay: float = 8.0,
    backoff_factor: float = 2.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    """Retry an async callable with exponential backoff + jitter.

    Args:
        fn: zero-arg async function to call.
        max_attempts: total attempts including the first.
        initial_delay: seconds before the second attempt.
        max_delay: cap on per-attempt delay.
        backoff_factor: multiplier per attempt.
        retry_on: exception types that trigger a retry. Other exceptions
            propagate immediately.

    Raises:
        The last exception if all attempts fail.
    """
    delay = initial_delay
    last_exc: BaseException | None = None
    for attempt in range(max_attempts):
        try:
            return await fn()
        except retry_on as exc:
            last_exc = exc
            if attempt == max_attempts - 1:
                raise
            jitter = random.uniform(0, delay * 0.25)
            await asyncio.sleep(min(delay + jitter, max_delay))
            delay *= backoff_factor
    assert last_exc is not None
    raise last_exc
