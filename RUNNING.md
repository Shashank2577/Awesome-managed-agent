# Running Atrium — What Works, What Needs What

## Quick start (Gemini runtime — no extra keys needed)

```bash
GEMINI_API_KEY="your-key" \
DOCKER_SOCK=~/.docker/run/docker.sock \
docker compose up --build -d
```

Open `http://localhost:8080` — the dashboard shows. Create a session with runtime
`direct_gemini` and any objective. It streams real LLM events through SSE.

## Quick start (Docker harness runtimes — needs Anthropic key)

The three Docker-based runtimes (`direct_anthropic`, `open_agent_sdk`, `openclaude`)
spawn an isolated container per session. They all call the Anthropic API, so you need:

```bash
ANTHROPIC_API_KEY="sk-ant-..." \
GEMINI_API_KEY="your-key" \
DOCKER_SOCK=~/.docker/run/docker.sock \
docker compose up --build -d
```

### macOS-specific: Docker socket path

Docker Desktop on macOS uses `~/.docker/run/docker.sock`, not `/var/run/docker.sock`.

```bash
export DOCKER_SOCK=~/.docker/run/docker.sock
```

The compose file defaults to `/var/run/docker.sock` (Linux), override via `DOCKER_SOCK`.

## Build sandbox images (one-time, or after entrypoint changes)

```bash
cd src/atrium/harness/dockerfiles

docker build -f anthropic.Dockerfile    -t atrium/anthropic:0.1.0      .
docker build -f open_agent_sdk.Dockerfile -t atrium/open-agent-sdk:0.1.0 .
docker build -f openclaude.Dockerfile   -t atrium/openclaude:0.1.0     .
```

These are cached — only rebuild when you change an entrypoint or Dockerfile.

## How objective delivery works

All sandbox entrypoints read the objective from the `ATRIUM_OBJECTIVE` environment
variable (set at container start). Stdin fallback exists but is not used in practice.

The old approach (Docker exec to pipe text to stdin) was broken — `exec_inst.start()`
returns a `Stream` object, not an awaitable coroutine.

## Architecture summary

```
Browser → FastAPI (port 8080)
            └─ direct_gemini: runs in-process, calls Gemini API
            └─ direct_anthropic / open_agent_sdk / openclaude:
                  DockerSandboxRunner spawns a container
                    ↓ ATRIUM_OBJECTIVE env var
                    Container calls LLM API
                    Container emits claude_code_stream_json to stdout
                    ↓ container.log(follow=True) async generator
                  BridgeStream translates → Atrium SSE events
                  EventRecorder → SSE stream to browser
```

Docker socket is mounted into the API container so it can spawn sibling containers
(Docker-in-Docker). The socket is owned by root:root; `group_add: ["0"]` in
docker-compose.yml adds the atrium user to root group so it can access the socket.

## Known limitations / next issues

1. **Workspace bind in DinD**: `DockerSandboxRunner.start()` binds
   `session.workspace_path:/workspace:rw`. This path lives inside the API container's
   named volume (`atrium_data`). When Docker (on the host) resolves the bind, it looks
   on the HOST filesystem, not inside the API container. The workspace may be empty.
   Fix: use a shared Docker volume or pass workspace content differently.

2. **ANTHROPIC_API_KEY required**: All three Docker runtimes call `api.anthropic.com`.
   Without the key, the container exits with `result:error` → `THREAD_FAILED`.

3. **Kubernetes runner untested**: `KubernetesSandboxRunner` exists and is activated
   by `ATRIUM_SANDBOX_BACKEND=kubernetes`. Needs a cluster and image registry.

## Runtime → event format mapping

| Runtime            | Container image              | Provider           | Event format              |
|--------------------|------------------------------|--------------------|---------------------------|
| `universal`        | `atrium/universal:0.1.0`     | **any** (UI-configured) | `claude_code_stream_json` |
| `direct_anthropic` | `atrium/anthropic:0.1.0`     | Anthropic only     | `claude_code_stream_json` |
| `openclaude`       | `atrium/openclaude:0.1.0`    | Anthropic (extended thinking) | `claude_code_stream_json` |
| `direct_gemini`    | (in-process)                 | Gemini (server env) | in-process events        |
| `echo`             | (in-process subprocess)      | none               | `echo`                    |

## Universal runtime — provider presets (UI)

Select "universal" in the runtime dropdown. A provider panel appears:

| Preset      | Base URL                                                  | Notes                        |
|-------------|-----------------------------------------------------------|------------------------------|
| OpenRouter  | `https://openrouter.ai/api/v1`                            | 100+ models from all vendors |
| OpenAI      | `https://api.openai.com/v1`                               | GPT-4o, o1, o3               |
| Gemini      | `https://generativelanguage.googleapis.com/v1beta/openai/`| Gemini 2.5 Flash/Pro         |
| xAI         | `https://api.x.ai/v1`                                     | Grok-3, Grok-3-mini          |
| NVIDIA NIM  | `https://integrate.api.nvidia.com/v1`                     | Llama, Nemotron              |
| Groq        | `https://api.groq.com/openai/v1`                          | Llama, Mixtral (fast)        |
| Ollama      | `http://localhost:11434/v1`                               | Local models, no API key     |

API keys are stored in browser localStorage only — never persisted server-side.
They are sent in the session creation request body and forwarded to the sandbox
container env at runtime only.

## What was fixed to get here (session log)

| Commit | Fix |
|--------|-----|
| 98be4c6 | Phase 1+2: multi-tenancy, sandbox harness |
| 5dcd773 | Phase 3: OpenAgentSDK + DirectAnthropic runtimes |
| caa9b79 | Phase 4: multi-model + MCP gateway |
| 3708624 | Phase 5: session resume, webhook delivery |
| 9d28f71 | Phase 6: production hardening |
| (post-6) | Fixed Dockerfile.api to install wheel with `[all]` extras |
| (post-6) | Fixed Gemini timeout and deprecated generation_config |
| (post-6) | Fixed SQLite path parsing, AppState get_app_state typing |
| (post-6) | Added direct_gemini in-process runtime |
| (post-6) | Fixed container permissions for /app/data |
| (post-6) | Rebuilt entrypoints: replaced fictitious packages with real SDK |
| (post-6) | Fixed anthropic.Dockerfile pip timeout (PyPI slow) |
| 8b9c7ed | Fixed Docker socket, aiodocker dep, send_input, bridge translator |
