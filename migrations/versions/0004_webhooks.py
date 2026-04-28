"""Migration 0004 — create webhooks and webhook_deliveries tables."""

UP = """
CREATE TABLE IF NOT EXISTS webhooks (
    webhook_id    TEXT PRIMARY KEY,
    workspace_id  TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    url           TEXT NOT NULL,
    events        TEXT NOT NULL,
    secret        TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    disabled_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_webhooks_workspace ON webhooks(workspace_id);

CREATE TABLE IF NOT EXISTS webhook_deliveries (
    delivery_id     TEXT PRIMARY KEY,
    webhook_id      TEXT NOT NULL REFERENCES webhooks(webhook_id) ON DELETE CASCADE,
    event_id        TEXT NOT NULL,
    attempt         INTEGER NOT NULL DEFAULT 1,
    status          TEXT NOT NULL,
    response_code   INTEGER,
    error           TEXT,
    delivered_at    TEXT,
    next_attempt_at TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_pending
    ON webhook_deliveries(next_attempt_at) WHERE status = 'pending';
"""

DOWN = """
DROP TABLE IF EXISTS webhook_deliveries;
DROP TABLE IF EXISTS webhooks;
"""
