"""SSE formatting utilities for Atrium event streaming."""
from __future__ import annotations

import json
from datetime import datetime

from atrium.core.models import AtriumEvent


def _json_default(obj: object) -> str:
    """Fallback serializer for types not handled by json.dumps natively."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def format_sse(event: AtriumEvent) -> str:
    """Format an AtriumEvent as an SSE chunk.

    Uses unnamed SSE messages so the browser's ``EventSource.onmessage``
    handler catches every event regardless of race conditions with named
    listener registration.  The event type lives in the JSON payload.
    """
    data = json.dumps(event.model_dump(), default=_json_default)
    return f"data: {data}\n\n"


def format_sse_end() -> str:
    """Return the SSE end-of-stream sentinel chunk."""
    return 'data: {"type":"end"}\n\n'
