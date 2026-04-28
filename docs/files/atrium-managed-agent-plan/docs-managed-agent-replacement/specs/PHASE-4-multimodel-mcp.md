# PHASE 4 — Multi-Model and MCP Gateway

**Goal:** prove model agnosticism by running the same harness agent on Gemini,
GPT-4o, and DeepSeek (via OpenRouter) with no code change. Add the MCP gateway
so harness sessions can talk to MCP servers safely.

**Estimated effort:** 6 days (1 engineer).

**Depends on:** Phase 3.

**Unblocks:** Phase 5.

## 4.1 Files to create or modify

| Action | Path | What |
|--------|------|------|
| MODIFY | `src/atrium/harness/runtimes/openclaude.py` | Real adapter. |
| CREATE | `src/atrium/harness/dockerfiles/openclaude.Dockerfile` | Image. |
| CREATE | `src/atrium/harness/dockerfiles/openclaude_entrypoint.js` | Entrypoint. |
| MODIFY | `src/atrium/harness/runtimes/open_agent_sdk.py` | Add OpenRouter passthrough. |
| MODIFY | `src/atrium/harness/dockerfiles/oas_entrypoint.js` | Detect OPENROUTER_API_KEY. |
| MODIFY | `src/atrium/harness/mcp_gateway.py` | Real implementation. |
| CREATE | `src/atrium/core/mcp_server_store.py` | Per-workspace MCP registry. |
| CREATE | `src/atrium/api/routes/mcp_servers.py` | CRUD for workspace MCP servers. |
| MODIFY | `src/atrium/harness/sandbox.py` | Mount MCP socket; egress allow-list. |
| MODIFY | `src/atrium/harness/agent.py` | Wire `allowed_mcp_servers` into the gateway. |
| MODIFY | `src/atrium/engine/pricing.py` | Add OpenRouter, DeepSeek, more Gemini models. |
| CREATE | `migrations/versions/0003_mcp_servers.py` |  |
| CREATE | `tests/test_harness/test_mcp_gateway.py` |  |
| CREATE | `tests/integration/docker/test_multi_model.py` |  |
| CREATE | `tests/integration/docker/test_mcp_session.py` |  |

## 4.2 `OpenClaudeRuntime`

```python
# verbatim
class OpenClaudeRuntime:
    name = "openclaude"
    event_format = "claude_code_stream_json"

    def image_tag(self, registry: str) -> str:
        return f"{registry}/openclaude:0.1.0"

    def command(self, model: str, system_prompt_path: str | None) -> list[str]:
        argv = ["node", "/app/openclaude_entrypoint.js", "--stream-json"]
        if system_prompt_path:
            argv += ["--system-prompt-file", system_prompt_path]
        argv += ["--model", model]
        return argv

    def model_endpoint(self, model: str) -> str:
        # OpenClaude routes through provider-native or OpenAI-compatible endpoints.
        provider = model.split(":", 1)[0]
        return {
            "anthropic": "https://api.anthropic.com",
            "openai": "https://api.openai.com",
            "gemini": "https://generativelanguage.googleapis.com",
            "deepseek": "https://api.deepseek.com",
            "openrouter": "https://openrouter.ai",
            "ollama": "http://host.docker.internal:11434",
        }.get(provider, "https://openrouter.ai")

    def required_env(self, model: str) -> dict[str, str]:
        provider = model.split(":", 1)[0]
        return {
            "anthropic":  {"ANTHROPIC_API_KEY":  "ANTHROPIC_API_KEY"},
            "openai":     {"OPENAI_API_KEY":     "OPENAI_API_KEY"},
            "gemini":     {"GEMINI_API_KEY":     "GEMINI_API_KEY"},
            "deepseek":   {"DEEPSEEK_API_KEY":   "DEEPSEEK_API_KEY"},
            "openrouter": {"OPENROUTER_API_KEY": "OPENROUTER_API_KEY"},
            "ollama":     {},
        }.get(provider, {"OPENROUTER_API_KEY": "OPENROUTER_API_KEY"})
```

OpenClaude image pins to a tagged release. Entrypoint mirrors the OAS
entrypoint shape — same JSON-line format on stdout.

## 4.3 MCP Gateway — real implementation

The gateway is a separate asyncio task started by `AppState.__init__`.
It listens on `config.mcp_socket_path` (default `/run/atrium/mcp.sock`).
The Atrium process owns this socket; sandbox containers bind-mount it
into their own filesystem at the same path.

### Wire protocol

The MCP standard transport is JSON-RPC 2.0 over a duplex stream. The
gateway speaks JSON-RPC on the Unix socket, framed with newlines (one
JSON object per line — matches the rest of the harness).

Each connection from a sandbox starts with a "hello" frame Atrium
injects via env var:

```json
{"jsonrpc":"2.0","method":"$/atrium/hello","params":{"session_token":"..."}}
```

The `session_token` is generated when the sandbox starts and passed
into the container as `ATRIUM_SESSION_TOKEN`. The OAS / OpenClaude
entrypoint reads it and sends it as the first frame on every MCP
connection it opens.

After the hello, the gateway:

1. Looks up the session by token.
2. Resolves `session.workspace_id` and `agent.allowed_mcp_servers`.
3. Subsequent JSON-RPC frames are forwarded to the upstream MCP
   server NAMED in the frame's `params.server` field (Atrium-specific
   extension; the inner SDK is patched to send this).

If the named server is not in the allow-list, the gateway responds
with a JSON-RPC error and emits `HARNESS_MCP_REJECTED`.

### Implementation skeleton

```python
# template — src/atrium/harness/mcp_gateway.py
class MCPGateway:
    def __init__(
        self,
        socket_path: str,
        session_store: SessionStore,
        registry: AgentRegistry,
        mcp_server_store: MCPServerStore,
        recorder: EventRecorder,
    ): ...

    async def serve(self) -> None:
        server = await asyncio.start_unix_server(
            self._handle_conn, path=self._socket_path
        )
        os.chmod(self._socket_path, 0o600)
        async with server:
            await server.serve_forever()

    async def _handle_conn(self, reader, writer):
        try:
            hello_line = await reader.readline()
            session_token, session = await self._authenticate(hello_line)
            if session is None:
                await self._reject(writer, "unauthenticated"); return
            allowed = await self._resolve_allowed_servers(session)

            async for line in reader:
                frame = json.loads(line)
                server_name = frame.get("params", {}).pop("server", None)
                if server_name not in allowed:
                    await self._recorder.emit(
                        session.session_id, "HARNESS_MCP_REJECTED",
                        {"server": server_name, "method": frame.get("method")},
                        workspace_id=session.workspace_id,
                    )
                    await self._reject(writer, f"server '{server_name}' not allowed")
                    continue

                upstream = await self._open_upstream(server_name, session.workspace_id)
                response = await self._proxy(upstream, frame)
                await self._recorder.emit(
                    session.session_id, "HARNESS_MCP_CALLED",
                    {"server": server_name,
                     "method": frame.get("method"),
                     "params": _redact(frame.get("params"))},
                    workspace_id=session.workspace_id,
                )
                writer.write(json.dumps(response).encode() + b"\n")
                await writer.drain()
        finally:
            writer.close()
```

`_redact` strips obvious secrets before logging — at minimum any field
named `password`, `api_key`, `token`, `secret`. Aggressive redaction is
safe; the gateway's value is the audit trail, not the full payload.

## 4.4 `MCPServerStore` and routes

Per-workspace MCP server registry. Migration 0003 creates:

```sql
CREATE TABLE mcp_servers (
    mcp_server_id   TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    name            TEXT NOT NULL,             -- logical, e.g. "github"
    transport       TEXT NOT NULL,             -- "stdio" | "sse" | "http"
    upstream        TEXT NOT NULL,             -- command or URL
    credentials_ref TEXT NOT NULL,             -- name of secret in secret store
    created_at      TEXT NOT NULL,
    UNIQUE(workspace_id, name)
);
```

Routes:

| Method | Path | Body |
|--------|------|------|
| POST | `/api/v1/mcp-servers` | `{name, transport, upstream, credentials_ref}` |
| GET | `/api/v1/mcp-servers` | — |
| DELETE | `/api/v1/mcp-servers/{name}` | — |

All require `Depends(require_workspace)`.

## 4.5 Sandbox changes for MCP

`DockerSandboxRunner.start()` adds:

- Bind mount `config.mcp_socket_path` into the container at the same
  path. Read-write.
- `env["ATRIUM_SESSION_TOKEN"] = session_token` (generated at start).
- `env["ATRIUM_MCP_SOCKET"] = "/run/atrium/mcp.sock"`.
- The runtime's entrypoint is responsible for noticing
  `ATRIUM_MCP_SOCKET` and routing MCP traffic through it.

The egress NetworkPolicy now matters. For Phase 4, implement a
per-session Docker network with iptables egress rules:

- Allow egress to `runtime.model_endpoint(model)` (resolved DNS).
- Allow egress to `127.0.0.1` (the Unix socket via host bind, no IP
  egress actually needed).
- Drop everything else.

If full network policy is too complex for this phase, a documented
acceptable shortcut is: allow all egress, log a deviation, and rely on
the gateway-only MCP access plus the API-key-only model access for
isolation. Tighten in Phase 6.

## 4.6 Pricing table extensions

```python
# additions to src/atrium/engine/pricing.py
PRICING_PER_MILLION.update({
    "openai:gpt-4o-2024-08-06":           (Decimal("2.50"), Decimal("10")),
    "openai:o1":                          (Decimal("15"),   Decimal("60")),
    "openai:o3-mini":                     (Decimal("1.10"), Decimal("4.40")),
    "gemini:gemini-2.5-pro":              (Decimal("1.25"), Decimal("5")),
    "gemini:gemini-2.5-flash":            (Decimal("0.075"), Decimal("0.30")),
    "deepseek:deepseek-chat":             (Decimal("0.27"), Decimal("1.10")),
    "deepseek:deepseek-reasoner":         (Decimal("0.55"), Decimal("2.19")),
    # OpenRouter is markup-on-passthrough; use a conservative average.
    "openrouter:default":                 (Decimal("3"),    Decimal("15")),
})
```

A model not in the table costs $0 in our accounting; emit a WARNING
log on first use of an unknown model so we know to add pricing.

## 4.7 Acceptance tests

### `tests/test_harness/test_mcp_gateway.py`

```
test_unauthenticated_connection_rejected
test_unknown_server_emits_mcp_rejected_event
test_allowed_server_emits_mcp_called_event
test_credentials_redacted_from_event_payload
test_socket_chmod_is_0600
test_concurrent_connections_handled
```

### `tests/integration/docker/test_multi_model.py` (live API keys required)

```
test_same_agent_completes_with_anthropic
test_same_agent_completes_with_gemini
test_same_agent_completes_with_openai
test_same_agent_completes_with_deepseek_via_openrouter
test_token_cost_recorded_for_each_provider
test_swap_model_via_model_override_no_code_change
```

The "same agent" referenced is `code_research`. The agent definition
is unchanged; only `model_override` in the session POST body changes.

### `tests/integration/docker/test_mcp_session.py`

```
test_session_lists_repos_via_github_mcp
test_session_with_no_allowed_mcp_cannot_call_anything
test_attempt_to_call_disallowed_server_logged_as_rejected
```

## 4.8 Non-goals for Phase 4

- Resume / checkpoint — Phase 5.
- Webhook delivery — Phase 5.
- Embeddable widgets — Phase 5.
- Computer use tool — out of scope for v1.
- Building our own MCP servers — use existing ones (GitHub, Linear,
  filesystem, etc.).

## 4.9 Definition of done

- [ ] All files in §4.1 created or modified per spec.
- [ ] All acceptance tests in §4.7 present and passing.
- [ ] Manual smoke: same agent definition runs successfully against
      Anthropic, Gemini, OpenAI, and DeepSeek-via-OpenRouter.
- [ ] Manual smoke: agent calls a real GitHub MCP server through the
      gateway and the `HARNESS_MCP_CALLED` event appears in the SSE
      stream with redacted credentials.
- [ ] Token costs recorded in BUDGET_CONSUMED match each provider's
      invoice within 5% (broader than Phase 3's 1% because some
      providers report usage less precisely).
- [ ] No `TODO(phase-4)` markers remain.
