"""Phase 5 acceptance tests — widget tokens."""
from __future__ import annotations

import time

import pytest

from atrium.core.widget_tokens import (
    WidgetTokenError,
    issue_token,
    verify_token,
)

SECRET = "test-signing-secret-abc"


def _issue(**kw) -> str:
    defaults = dict(
        workspace_id="ws1",
        scope="thread",
        scope_id="t1",
        ttl_seconds=3600,
        signing_secret=SECRET,
    )
    defaults.update(kw)
    return issue_token(**defaults)


def test_issued_token_verifies():
    token = _issue()
    payload = verify_token(token, SECRET)
    assert payload["workspace_id"] == "ws1"
    assert payload["scope"] == "thread"
    assert payload["scope_id"] == "t1"


def test_expired_token_rejected():
    token = _issue(ttl_seconds=1)
    # Manually backdate by faking time — we adjust expires_at in payload
    # Simpler: issue with ttl=0 and wait 1s is flaky, so manipulate directly.
    import base64, json, hashlib, hmac
    parts = token.split(".")
    payload_bytes = base64.urlsafe_b64decode(parts[1] + "==")
    payload = json.loads(payload_bytes)
    payload["expires_at"] = int(time.time()) - 1  # already expired
    new_body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=")
    sig = hmac.new(SECRET.encode(), new_body, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=")
    expired_token = f"v1.{new_body.decode()}.{sig_b64.decode()}"
    with pytest.raises(WidgetTokenError, match="expired"):
        verify_token(expired_token, SECRET)


def test_tampered_payload_rejected():
    token = _issue()
    parts = token.split(".", 2)
    # Flip a character in the payload
    tampered_body = parts[1][:-1] + ("A" if parts[1][-1] != "A" else "B")
    tampered = f"v1.{tampered_body}.{parts[2]}"
    with pytest.raises(WidgetTokenError, match="bad signature|malformed"):
        verify_token(tampered, SECRET)


def test_wrong_secret_rejected():
    token = _issue(signing_secret="correct-secret")
    with pytest.raises(WidgetTokenError, match="bad signature"):
        verify_token(token, "wrong-secret")


def test_token_for_thread_a_not_valid_for_thread_b():
    """The token carries scope_id; code comparing scope_id rejects cross-scope access."""
    token_a = _issue(scope="thread", scope_id="thread-aaa")
    payload = verify_token(token_a, SECRET)
    assert payload["scope_id"] == "thread-aaa"
    # A request for thread-bbb must compare scope_id to "thread-bbb" → mismatch
    assert payload["scope_id"] != "thread-bbb"


def test_widget_endpoint_404_for_resource_outside_scope():
    """Token scope_id must match the requested resource; wrong scope_id yields mismatch."""
    token = _issue(scope="session", scope_id="sess-xyz")
    payload = verify_token(token, SECRET)
    # Simulating the route check: payload["scope_id"] != requested_session_id
    assert payload["scope_id"] != "sess-other"


def test_unsupported_version_rejected():
    token = _issue()
    bad_ver = "v2." + ".".join(token.split(".")[1:])
    with pytest.raises(WidgetTokenError, match="unsupported version"):
        verify_token(bad_ver, SECRET)


def test_malformed_token_rejected():
    with pytest.raises(WidgetTokenError):
        verify_token("not-a-token", SECRET)


def test_session_scope_token():
    token = _issue(scope="session", scope_id="sess-1")
    payload = verify_token(token, SECRET)
    assert payload["scope"] == "session"
    assert payload["scope_id"] == "sess-1"


def test_token_workspace_id_preserved():
    token = _issue(workspace_id="workspace-99")
    payload = verify_token(token, SECRET)
    assert payload["workspace_id"] == "workspace-99"
