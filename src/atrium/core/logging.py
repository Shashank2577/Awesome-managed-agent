"""JSON structured logging helper."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "msg": record.getMessage(),
            "module": record.name,
        }
        # Surface common context fields if attached via `extra=`
        for key in ("workspace_id", "thread_id", "session_id", "event_id"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exc_type"] = record.exc_info[0].__name__
            payload["exc_msg"] = str(record.exc_info[1])
        return json.dumps(payload, default=str)


def configure(level: str = "INFO") -> None:
    """Configure root logger to emit JSON lines to stdout. Idempotent."""
    root = logging.getLogger()
    if any(isinstance(h, logging.StreamHandler) and isinstance(h.formatter, JSONFormatter)
           for h in root.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root.handlers = [handler]
    root.setLevel(level.upper())
