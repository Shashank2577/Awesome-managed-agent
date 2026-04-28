"""Widget token issuance + widget HTML endpoints + token-scoped SSE.

POST /api/v1/threads/{id}/widget-token
POST /api/v1/sessions/{id}/widget-token
GET  /widgets/feed
GET  /widgets/plan
GET  /widgets/budget
GET  /widgets/report
GET  /api/v1/widgets/stream    (token-scoped SSE)
"""
from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from atrium.core.widget_tokens import WidgetTokenError, issue_token, verify_token

try:
    from atrium.api.auth import require_workspace
    from atrium.api.state import AppState
    from atrium.core.workspace_store import Workspace
except ImportError:
    require_workspace = None  # type: ignore[assignment]
    AppState = None  # type: ignore[assignment]
    Workspace = None  # type: ignore[assignment]

router = APIRouter(tags=["widgets"])

_MAX_TTL = 86400  # 24 hours


class IssueTokenRequest(BaseModel):
    ttl_seconds: int = Field(default=3600, ge=60, le=_MAX_TTL)


class IssueTokenResponse(BaseModel):
    token: str
    expires_at: int


def _signing_secret(state) -> str:
    return getattr(state.config, "webhook_signing_secret", "dev-secret")


# ---------------------------------------------------------------------------
# Token issuance
# ---------------------------------------------------------------------------

@router.post("/api/v1/threads/{thread_id}/widget-token", response_model=IssueTokenResponse)
async def issue_thread_token(
    thread_id: str,
    body: IssueTokenRequest,
    workspace: "Workspace" = Depends(require_workspace),
    state: "AppState" = Depends(lambda: AppState.instance()),
) -> IssueTokenResponse:
    expires_at = int(time.time()) + body.ttl_seconds
    token = issue_token(
        workspace_id=workspace.workspace_id,
        scope="thread",
        scope_id=thread_id,
        ttl_seconds=body.ttl_seconds,
        signing_secret=_signing_secret(state),
    )
    return IssueTokenResponse(token=token, expires_at=expires_at)


@router.post("/api/v1/sessions/{session_id}/widget-token", response_model=IssueTokenResponse)
async def issue_session_token(
    session_id: str,
    body: IssueTokenRequest,
    workspace: "Workspace" = Depends(require_workspace),
    state: "AppState" = Depends(lambda: AppState.instance()),
) -> IssueTokenResponse:
    expires_at = int(time.time()) + body.ttl_seconds
    token = issue_token(
        workspace_id=workspace.workspace_id,
        scope="session",
        scope_id=session_id,
        ttl_seconds=body.ttl_seconds,
        signing_secret=_signing_secret(state),
    )
    return IssueTokenResponse(token=token, expires_at=expires_at)


# ---------------------------------------------------------------------------
# Widget HTML pages
# ---------------------------------------------------------------------------

_WIDGET_HEADERS = {
    "X-Frame-Options": "ALLOWALL",
    "Content-Security-Policy": "default-src 'self' 'unsafe-inline';",
}


@router.get("/widgets/feed", response_class=HTMLResponse)
async def widget_feed(
    token: str = Query(...),
    theme: str = Query(default="light"),
    compact: bool = Query(default=False),
    state: "AppState" = Depends(lambda: AppState.instance()),
) -> HTMLResponse:
    try:
        verify_token(token, _signing_secret(state))
    except WidgetTokenError as e:
        return HTMLResponse(_token_error_page(str(e)), status_code=401, headers=_WIDGET_HEADERS)

    html = _read_static_widget("feed.html")
    if html is None:
        html = _feed_widget_inline(token, theme, compact)
    return HTMLResponse(html, headers=_WIDGET_HEADERS)


@router.get("/widgets/plan", response_class=HTMLResponse)
async def widget_plan(
    token: str = Query(...),
    theme: str = Query(default="light"),
    state: "AppState" = Depends(lambda: AppState.instance()),
) -> HTMLResponse:
    try:
        verify_token(token, _signing_secret(state))
    except WidgetTokenError as e:
        return HTMLResponse(_token_error_page(str(e)), status_code=401, headers=_WIDGET_HEADERS)
    html = _read_static_widget("plan.html") or _plan_widget_inline(token, theme)
    return HTMLResponse(html, headers=_WIDGET_HEADERS)


@router.get("/widgets/budget", response_class=HTMLResponse)
async def widget_budget(
    token: str = Query(...),
    theme: str = Query(default="light"),
    state: "AppState" = Depends(lambda: AppState.instance()),
) -> HTMLResponse:
    try:
        verify_token(token, _signing_secret(state))
    except WidgetTokenError as e:
        return HTMLResponse(_token_error_page(str(e)), status_code=401, headers=_WIDGET_HEADERS)
    html = _read_static_widget("budget.html") or _budget_widget_inline(token, theme)
    return HTMLResponse(html, headers=_WIDGET_HEADERS)


@router.get("/widgets/report", response_class=HTMLResponse)
async def widget_report(
    token: str = Query(...),
    theme: str = Query(default="light"),
    state: "AppState" = Depends(lambda: AppState.instance()),
) -> HTMLResponse:
    try:
        verify_token(token, _signing_secret(state))
    except WidgetTokenError as e:
        return HTMLResponse(_token_error_page(str(e)), status_code=401, headers=_WIDGET_HEADERS)
    html = _read_static_widget("report.html") or _report_widget_inline(token, theme)
    return HTMLResponse(html, headers=_WIDGET_HEADERS)


# ---------------------------------------------------------------------------
# Token-scoped SSE endpoint
# ---------------------------------------------------------------------------

def _format_sse(event) -> str:
    import json
    data = json.dumps({"type": event.type, "payload": event.payload, "sequence": event.sequence})
    return f"data: {data}\n\n"


@router.get("/api/v1/widgets/stream")
async def widget_stream(
    token: str = Query(...),
    state: "AppState" = Depends(lambda: AppState.instance()),
):
    try:
        payload = verify_token(token, _signing_secret(state))
    except WidgetTokenError as e:
        return Response(status_code=401, content=str(e))

    scope = payload["scope"]
    scope_id = payload["scope_id"]
    workspace_id = payload["workspace_id"]

    recorder = state.recorder

    async def gen():
        if scope == "thread":
            async for event in recorder.subscribe(scope_id):
                if event is None:
                    break
                yield _format_sse(event)
        else:
            async for event in recorder.subscribe(scope_id):
                if event is None:
                    break
                yield _format_sse(event)

    return StreamingResponse(gen(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Static widget helpers — read from disk, fall back to inline
# ---------------------------------------------------------------------------

def _read_static_widget(filename: str) -> str | None:
    from pathlib import Path
    p = Path(__file__).parent.parent.parent / "dashboard" / "static" / "widgets" / filename
    if p.exists():
        return p.read_text()
    return None


def _token_error_page(msg: str) -> str:
    return f"<html><body style='font-family:monospace;padding:2rem'><b>Widget auth error:</b> {msg}</body></html>"


def _feed_widget_inline(token: str, theme: str, compact: bool) -> str:
    compact_style = "font-size:0.85rem;" if compact else ""
    bg = "#1a1a2e" if theme == "dark" else "#f8f9fa"
    fg = "#e0e0e0" if theme == "dark" else "#1a1a1e"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Atrium Live Feed</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: {bg}; color: {fg}; font-family: system-ui, sans-serif; {compact_style}
         display: flex; flex-direction: column; height: 100vh; }}
  header {{ padding: 12px 16px; font-weight: 700; letter-spacing: .05em;
            border-bottom: 1px solid #ffffff22; font-size: .8rem; text-transform: uppercase; }}
  #feed {{ flex: 1; overflow-y: auto; padding: 12px 16px; display: flex; flex-direction: column; gap: 8px; }}
  .event {{ padding: 8px 12px; border-radius: 8px; background: #ffffff10;
            border-left: 3px solid #6c63ff; font-size: .85rem; }}
  .event.HARNESS_TOOL_CALLED {{ border-left-color: #f59e0b; }}
  .event.HARNESS_MESSAGE {{ border-left-color: #10b981; }}
  .event.SESSION_COMPLETED {{ border-left-color: #3b82f6; }}
  .event.SESSION_FAILED {{ border-left-color: #ef4444; }}
  .type {{ font-weight: 600; font-size: .75rem; opacity: .6; margin-bottom: 2px; }}
  .payload {{ word-break: break-word; }}
  #status {{ padding: 6px 16px; font-size: .75rem; opacity: .5; border-top: 1px solid #ffffff11; }}
</style>
</head>
<body>
<header>⚡ Atrium Live Feed</header>
<div id="feed"></div>
<div id="status">Connecting…</div>
<script>
const feed = document.getElementById('feed');
const status = document.getElementById('status');
const token = {repr(token)};
const src = new EventSource('/api/v1/widgets/stream?token=' + encodeURIComponent(token));
src.onopen = () => status.textContent = 'Connected';
src.onerror = () => status.textContent = 'Disconnected — retrying…';
src.onmessage = (e) => {{
  const ev = JSON.parse(e.data);
  const div = document.createElement('div');
  div.className = 'event ' + ev.type;
  const txt = typeof ev.payload === 'object'
    ? JSON.stringify(ev.payload, null, 2)
    : String(ev.payload);
  div.innerHTML = '<div class="type">' + ev.type + '</div>'
    + '<div class="payload"><pre>' + txt.substring(0, 400) + '</pre></div>';
  feed.appendChild(div);
  feed.scrollTop = feed.scrollHeight;
}};
</script>
</body>
</html>"""


def _plan_widget_inline(token: str, theme: str) -> str:
    bg = "#1a1a2e" if theme == "dark" else "#f8f9fa"
    fg = "#e0e0e0" if theme == "dark" else "#1a1a1e"
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Atrium Plan</title>
<style>body{{background:{bg};color:{fg};font-family:system-ui,sans-serif;padding:1rem}}
svg{{width:100%;height:auto;max-height:600px}}</style></head>
<body>
<h2 style="font-size:1rem;margin-bottom:.5rem">Plan DAG</h2>
<div id="dag"><p style="opacity:.5">Waiting for plan events…</p></div>
<script>
const token = {repr(token)};
const src = new EventSource('/api/v1/widgets/stream?token=' + encodeURIComponent(token));
src.onmessage = (e) => {{
  const ev = JSON.parse(e.data);
  if (ev.type === 'PLAN_CREATED' || ev.type === 'PLAN_UPDATED') {{
    document.getElementById('dag').innerHTML = '<pre>' + JSON.stringify(ev.payload, null, 2) + '</pre>';
  }}
}};
</script></body></html>"""


def _budget_widget_inline(token: str, theme: str) -> str:
    bg = "#1a1a2e" if theme == "dark" else "#f8f9fa"
    fg = "#e0e0e0" if theme == "dark" else "#1a1a1e"
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Atrium Budget</title>
<style>
body{{background:{bg};color:{fg};font-family:system-ui,sans-serif;padding:1rem}}
.bar-bg{{background:#ffffff20;border-radius:4px;height:12px;overflow:hidden}}
.bar-fill{{height:100%;background:#6c63ff;border-radius:4px;transition:width .4s ease}}
.label{{font-size:.8rem;opacity:.6;margin-top:.25rem}}
</style></head>
<body>
<h2 style="font-size:1rem;margin-bottom:.75rem">Budget</h2>
<div class="bar-bg"><div id="fill" class="bar-fill" style="width:0%"></div></div>
<div class="label" id="lbl">$0.0000 consumed</div>
<script>
const token = {repr(token)};
let total = 0;
const src = new EventSource('/api/v1/widgets/stream?token=' + encodeURIComponent(token));
src.onmessage = (e) => {{
  const ev = JSON.parse(e.data);
  if (ev.type === 'BUDGET_CONSUMED') {{
    total += (ev.payload.cost_usd || 0);
    document.getElementById('lbl').textContent = '$' + total.toFixed(4) + ' consumed';
    const pct = Math.min(100, total * 100);
    document.getElementById('fill').style.width = pct + '%';
  }}
}};
</script></body></html>"""


def _report_widget_inline(token: str, theme: str) -> str:
    bg = "#1a1a2e" if theme == "dark" else "#f8f9fa"
    fg = "#e0e0e0" if theme == "dark" else "#1a1a1e"
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Atrium Report</title>
<style>
body{{background:{bg};color:{fg};font-family:system-ui,sans-serif;
     padding:1.5rem;max-width:720px;margin:0 auto;line-height:1.6}}
pre{{background:#ffffff10;padding:1rem;border-radius:6px;overflow-x:auto;white-space:pre-wrap}}
</style></head>
<body>
<div id="content"><p style="opacity:.5">Loading report…</p></div>
<script>
const token = {repr(token)};
const src = new EventSource('/api/v1/widgets/stream?token=' + encodeURIComponent(token));
src.onmessage = (e) => {{
  const ev = JSON.parse(e.data);
  if (ev.type === 'SESSION_COMPLETED' || ev.type === 'EVIDENCE_PUBLISHED') {{
    const msg = ev.payload.final_message || ev.payload.result || JSON.stringify(ev.payload, null, 2);
    document.getElementById('content').innerHTML =
      '<pre>' + msg.replace(/</g, '&lt;') + '</pre>';
    src.close();
  }}
}};
</script></body></html>"""
