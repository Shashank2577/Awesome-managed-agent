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

    Returns a string of the form::

        event: <type>\\n
        data: <json>\\n
        \\n
    """
    data = json.dumps(event.model_dump(), default=_json_default)
    return f"event: {event.type}\ndata: {data}\n\n"


def format_sse_end() -> str:
    """Return the SSE end-of-stream sentinel chunk."""
    return "event: end\ndata: {}\n\n"
