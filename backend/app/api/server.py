"""Streaming HTTP API server for the Agent OS demo.

The server runs a single asyncio event loop in a background thread and accepts
HTTP requests on a thread-pool. Each thread spawns a real `Commander.run()`
coroutine that emits events into a shared `ThreadStream`. The SSE endpoint
subscribes to that stream, so clients see events appear in real time with the
same timing as the commander produces them.
"""

from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Queue
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

from backend.app.runtime.commander import Commander, classify_objective, SCENARIO_LIBRARY
from backend.app.runtime.streaming import StreamRegistry, ThreadHandle, ThreadStream

ROOT = Path(__file__).resolve().parents[3]
FRONTEND_DIR = ROOT / "frontend"

REGISTRY = StreamRegistry()


# ---------------------------------------------------------------------------
# Async event loop running in a background thread
# ---------------------------------------------------------------------------


class AsyncRuntime:
    """Runs a dedicated asyncio loop on a worker thread."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, name="agent-os-loop", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop)


RUNTIME = AsyncRuntime()


# ---------------------------------------------------------------------------
# Demo orchestration
# ---------------------------------------------------------------------------


def _scenario_title(objective: str) -> str:
    return SCENARIO_LIBRARY[classify_objective(objective)]["title"]


async def _run_thread(stream: ThreadStream) -> None:
    async def emit(event_type: str, payload: dict[str, Any], causation: Optional[UUID]) -> None:
        await stream.emit(event_type, payload, causation_id=causation)

    commander = Commander(
        thread_id=stream.thread_id,
        org_id=stream.org_id,
        objective=stream.objective,
        emit=emit,
    )
    try:
        await commander.run()
    except Exception as exc:  # noqa: BLE001 - surfaced into the stream
        await stream.emit("THREAD_FAILED", {"error": str(exc)})
    finally:
        await stream.mark_complete()


def create_thread(objective: str) -> ThreadStream:
    objective = objective.strip() or "demo: walk an observability readiness review"
    title = _scenario_title(objective)
    stream = ThreadStream(
        thread_id=uuid4(),
        org_id=uuid4(),
        objective=objective,
        title=title,
    )
    REGISTRY.add(stream)
    RUNTIME.submit(_run_thread(stream))
    return stream


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    server_version = "AgentOSHTTP/0.2"

    # -- helpers -------------------------------------------------------------

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _serve_static(self, rel: str) -> None:
        candidate = (FRONTEND_DIR / rel).resolve()
        if not candidate.is_file() or FRONTEND_DIR.resolve() not in candidate.parents and candidate != FRONTEND_DIR.resolve():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        # Final containment check (defense in depth).
        try:
            candidate.relative_to(FRONTEND_DIR.resolve())
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        suffix = candidate.suffix.lower()
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".svg": "image/svg+xml",
            ".json": "application/json",
            ".woff2": "font/woff2",
            ".png": "image/png",
        }.get(suffix, "text/plain; charset=utf-8")
        body = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    # -- routing -------------------------------------------------------------

    def log_message(self, fmt: str, *args: Any) -> None:  # quieter logs
        return

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self._serve_static("index.html")
            return
        if path == "/console" or path == "/console.html":
            self._serve_static("console.html")
            return
        if path.startswith("/static/"):
            self._serve_static(path.replace("/static/", "", 1))
            return

        if path == "/api/v1/threads":
            self._send_json({"threads": REGISTRY.list()})
            return

        if path.startswith("/api/v1/threads/"):
            tail = path[len("/api/v1/threads/"):]
            parts = tail.split("/", 2)
            thread_id = parts[0]
            stream = REGISTRY.get(thread_id)
            if stream is None:
                self.send_error(HTTPStatus.NOT_FOUND)
                return

            sub = parts[1] if len(parts) > 1 else ""
            if sub == "" or sub is None:
                snapshot = stream.snapshot()
                snapshot["events"] = stream.events_after(0)
                self._send_json(snapshot)
                return
            if sub == "events":
                query = parse_qs(parsed.query)
                after = int(query.get("after_sequence", ["0"])[0])
                self._send_json({"events": stream.events_after(after)})
                return
            if sub == "events" and len(parts) > 2 and parts[2] == "stream":
                self._stream_events(stream, parsed.query)
                return
            if sub == "stream":
                self._stream_events(stream, parsed.query)
                return

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/v1/threads":
            body = self._read_json_body()
            objective = str(body.get("objective", "")).strip()
            stream = create_thread(objective)
            self._send_json(
                {
                    "thread": asdict(ThreadHandle.from_stream(stream)),
                    "stream_url": f"/api/v1/threads/{stream.thread_id}/stream",
                },
                status=HTTPStatus.CREATED,
            )
            return

        if path.startswith("/api/v1/threads/"):
            tail = path[len("/api/v1/threads/"):]
            parts = tail.split("/", 1)
            thread_id = parts[0]
            stream = REGISTRY.get(thread_id)
            if stream is None:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            action = parts[1] if len(parts) > 1 else ""
            if action == "human_input":
                body = self._read_json_body()
                value = str(body.get("input", "")).strip()
                fut = RUNTIME.submit(stream.emit("HUMAN_INPUT_RECEIVED", {"input": value}))
                fut.result(timeout=2)
                self._send_json(
                    {"thread_id": thread_id, "accepted": True}, status=HTTPStatus.ACCEPTED
                )
                return
            if action in {"pause", "resume", "cancel"}:
                event_type = {
                    "pause": "THREAD_PAUSED",
                    "resume": "THREAD_RUNNING",
                    "cancel": "THREAD_CANCELLED",
                }[action]
                fut = RUNTIME.submit(stream.emit(event_type, {"by": "operator"}))
                fut.result(timeout=2)
                self._send_json(
                    {"thread_id": thread_id, "status": stream.status},
                    status=HTTPStatus.ACCEPTED,
                )
                return

        self.send_error(HTTPStatus.NOT_FOUND)

    # -- SSE ----------------------------------------------------------------

    def _stream_events(self, stream: ThreadStream, query: str) -> None:
        params = parse_qs(query)
        since = int(params.get("since_sequence", ["0"])[0])

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        bridge: Queue = Queue()
        DONE = object()

        async def pump() -> None:
            try:
                async for event in stream.subscribe(since_sequence=since):
                    bridge.put(event.to_dict())
            finally:
                bridge.put(DONE)

        future = RUNTIME.submit(pump())

        try:
            while True:
                item = bridge.get()
                if item is DONE:
                    break
                payload = json.dumps(item)
                chunk = f"event: {item['type']}\ndata: {payload}\n\n".encode("utf-8")
                try:
                    self.wfile.write(chunk)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    future.cancel()
                    break
        finally:
            try:
                self.wfile.write(b"event: end\ndata: {}\n\n")
                self.wfile.flush()
            except Exception:
                pass


def run_server(host: str = "127.0.0.1", port: int = 8080) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Agent OS demo serving at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
