"""Migration 0003 — create mcp_servers table.

Depends on: 0001_initial (workspaces, api_keys), 0002_sessions (sessions, artifacts).
"""

UP = """
CREATE TABLE IF NOT EXISTS mcp_servers (
    mcp_server_id   TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    transport       TEXT NOT NULL CHECK (transport IN ('stdio', 'sse', 'http')),
    upstream        TEXT NOT NULL,
    credentials_ref TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    UNIQUE(workspace_id, name)
);
CREATE INDEX IF NOT EXISTS idx_mcp_servers_workspace ON mcp_servers(workspace_id);
"""

DOWN = """
DROP TABLE IF EXISTS mcp_servers;
"""
