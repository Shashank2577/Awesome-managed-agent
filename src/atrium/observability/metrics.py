"""Prometheus metrics. Exposed at /metrics on the API."""
from prometheus_client import Counter, Gauge, Histogram


threads_started = Counter(
    "atrium_threads_started_total",
    "Threads created.",
    ["workspace_id"],
)
threads_completed = Counter(
    "atrium_threads_completed_total",
    "Threads reaching a terminal state.",
    ["workspace_id", "status"],
)
sessions_active = Gauge(
    "atrium_sessions_active",
    "Sessions currently RUNNING.",
    ["workspace_id"],
)
session_duration = Histogram(
    "atrium_session_duration_seconds",
    "Wall-clock duration of completed sessions.",
    ["workspace_id", "runtime", "status"],
    buckets=(1, 5, 30, 60, 300, 1800, 3600, 7200, 14400),
)
tokens_consumed = Counter(
    "atrium_tokens_consumed_total",
    "Token usage by direction and provider.",
    ["workspace_id", "model", "direction"],
)
tool_calls = Counter(
    "atrium_tool_calls_total",
    "Tool calls inside sandboxes.",
    ["workspace_id", "tool"],
)
mcp_calls = Counter(
    "atrium_mcp_calls_total",
    "MCP calls.",
    ["workspace_id", "server", "result"],  # result: "allowed" | "rejected"
)
webhook_deliveries = Counter(
    "atrium_webhook_deliveries_total",
    "Webhook delivery outcomes.",
    ["workspace_id", "status"],  # "delivered" | "failed" | "pending"
)
sandbox_starts_failed = Counter(
    "atrium_sandbox_starts_failed_total",
    "Sandbox container creation failures.",
    ["reason"],
)
http_requests_in_flight = Gauge(
    "atrium_http_requests_in_flight",
    "Currently-being-processed HTTP requests.",
)
