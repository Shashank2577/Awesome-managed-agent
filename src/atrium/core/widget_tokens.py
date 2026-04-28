"""Short-lived signed tokens for embeddable widgets.

Token format: "v1.{base64(payload)}.{base64(hmac)}"
Payload JSON: {workspace_id, scope, scope_id, expires_at}
scope: "thread" | "session"
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Literal


class WidgetTokenError(Exception):
    pass


def issue_token(
    *,
    workspace_id: str,
    scope: Literal["thread", "session"],
    scope_id: str,
    ttl_seconds: int,
    signing_secret: str,
) -> str:
    payload = {
        "workspace_id": workspace_id,
        "scope": scope,
        "scope_id": scope_id,
        "expires_at": int(time.time()) + ttl_seconds,
    }
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=")
    sig = hmac.new(signing_secret.encode(), body, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=")
    return f"v1.{body.decode()}.{sig_b64.decode()}"


def verify_token(token: str, signing_secret: str) -> dict:
    try:
        version, body, sig_b64 = token.split(".", 2)
        if version != "v1":
            raise WidgetTokenError("unsupported version")
        body_bytes = base64.urlsafe_b64decode(body + "==")
        expected = hmac.new(signing_secret.encode(), body.encode(), hashlib.sha256).digest()
        actual = base64.urlsafe_b64decode(sig_b64 + "==")
        if not hmac.compare_digest(expected, actual):
            raise WidgetTokenError("bad signature")
        payload = json.loads(body_bytes)
        if payload["expires_at"] < int(time.time()):
            raise WidgetTokenError("expired")
        return payload
    except (ValueError, KeyError) as exc:
        raise WidgetTokenError(f"malformed: {exc}") from exc
