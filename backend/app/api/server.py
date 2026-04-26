from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from backend.app.services.observability_service import run_demo

ROOT = Path(__file__).resolve().parents[3]
FRONTEND_DIR = ROOT / "frontend"


class RuntimeStore:
    def __init__(self):
        self.thread = run_demo("bootstrap observability runtime")
        self.thread["status"] = "RUNNING"

    def reset(self) -> None:
        self.thread = run_demo("bootstrap observability runtime")
        self.thread["status"] = "RUNNING"


STORE = RuntimeStore()


class Handler(BaseHTTPRequestHandler):
    server_version = "AgentRuntimeHTTP/0.1"

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, rel: str) -> None:
        target = FRONTEND_DIR / rel
        if not target.exists() or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = "text/plain"
        if target.suffix == ".html":
            content_type = "text/html"
        elif target.suffix == ".css":
            content_type = "text/css"
        elif target.suffix == ".js":
            content_type = "application/javascript"
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self._serve_static("index.html")
            return
        if path.startswith("/frontend/"):
            self._serve_static(path.replace("/frontend/", "", 1))
            return

        if path == "/api/v1/threads":
            self._send_json(
                {
                    "threads": [
                        {
                            "thread_id": STORE.thread["thread_id"],
                            "title": "Observability Runtime Demo",
                            "status": STORE.thread.get("status", "RUNNING"),
                            "objective": STORE.thread["command"],
                        }
                    ]
                }
            )
            return

        if path == f"/api/v1/threads/{STORE.thread['thread_id']}":
            self._send_json(STORE.thread)
            return

        if path == f"/api/v1/threads/{STORE.thread['thread_id']}/events":
            query = parse_qs(parsed.query)
            after_sequence = int(query.get("after_sequence", ["0"])[0])
            events = [
                event for event in STORE.thread["events"] if int(event["payload"].get("sequence", 0)) > after_sequence
            ]
            self._send_json({"events": events})
            return

        if path == f"/api/v1/threads/{STORE.thread['thread_id']}/events/stream":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            for event in STORE.thread["events"]:
                payload = json.dumps(event)
                self.wfile.write(f"event: {event['type']}\n".encode("utf-8"))
                self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        thread_id = STORE.thread["thread_id"]

        if path == f"/api/v1/threads/{thread_id}/pause":
            STORE.thread["status"] = "PAUSED"
            self._send_json({"thread_id": thread_id, "status": "PAUSED"}, status=HTTPStatus.ACCEPTED)
            return
        if path == f"/api/v1/threads/{thread_id}/resume":
            STORE.thread["status"] = "RUNNING"
            self._send_json({"thread_id": thread_id, "status": "RUNNING"}, status=HTTPStatus.ACCEPTED)
            return
        if path == f"/api/v1/threads/{thread_id}/cancel":
            STORE.thread["status"] = "CANCELLED"
            self._send_json({"thread_id": thread_id, "status": "CANCELLED"}, status=HTTPStatus.ACCEPTED)
            return
        if path == "/api/v1/threads":
            STORE.reset()
            self._send_json({"thread_id": STORE.thread["thread_id"], "status": "CREATED"}, status=HTTPStatus.CREATED)
            return
        if path == f"/api/v1/threads/{thread_id}/human_input":
            self._send_json(
                {
                    "thread_id": thread_id,
                    "event_id": str(uuid4()),
                    "status": STORE.thread.get("status", "RUNNING"),
                    "accepted": True,
                },
                status=HTTPStatus.ACCEPTED,
            )
            return

        self.send_error(HTTPStatus.NOT_FOUND)


def run_server(host: str = "127.0.0.1", port: int = 8080) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Serving Agent Runtime UI at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
