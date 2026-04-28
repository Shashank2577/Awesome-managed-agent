# Atrium: Managed Agent Orchestrator

**Atrium** has evolved from a simple Python orchestration script running on top of LangGraph to a fully-featured, production-ready **Managed Agent Orchestration Platform**. It allows you to build, deploy, and scale complex agentic workflows in secure, multi-tenant sandboxes with full observability and external tool integrations.

## 🚀 The Evolution (From 0 to 1)

Originally, Atrium was a lightweight wrapper around LangGraph that ran agent threads in-memory within the same Python process. While this worked for simple, trusted scripts, it wasn't suitable for untrusted code execution or enterprise-scale deployment.

We have entirely overhauled the architecture across 6 implementation phases:

1. **Multi-Tenancy & Auth:** Transitioned from a single-user system to a robust API Key + Workspace model. We swapped out in-memory state for persistent SQLite/PostgreSQL storage, ensuring that API keys are hashed and stored securely, and all sessions and MCP servers are isolated per workspace.
2. **Containerized Sandboxing:** Replaced the unsafe, local `PythonREPL` with a dynamic `HarnessAgent`. Agents now execute their code in ephemeral, network-isolated sandboxes. The system dynamically scales from an in-memory test runner, to local Docker containers, all the way to Kubernetes Pods with PVC mounts.
3. **Advanced Integrations:** 
   * **Webhooks:** Added reliable asynchronous webhook delivery for system events (e.g., `session.completed`, `session.failed`) with cryptographic HMAC signing, automatic retries, and exponential backoff via a dedicated background worker.
   * **MCP (Model Context Protocol):** Built a registry and proxy routing system to connect agents directly to standard MCP servers using SSE (Server-Sent Events) or HTTP, allowing LLMs to safely use external data tools.
4. **Enhanced API Surface:** Upgraded from basic CRUD to a fully streaming-capable REST API. Clients can connect via Server-Sent Events (`/stream`) to get real-time, token-by-token LLM output and lifecycle events. We added pause, resume, checkpointing, and cancellation workflows.
5. **Production Hardening:** Wrapped the entire application in OpenTelemetry (for distributed tracing) and Prometheus (for metrics scraping). Created comprehensive Helm charts to deploy the API, PostgreSQL database, and Webhook worker into Kubernetes with Horizontal Pod Autoscaling and restricted Network Policies.

## ✨ Features

- **Multi-Tenant REST API**: Manage API keys, workspaces, and sessions via a robust FastAPI backend.
- **Secure Sandbox Execution**: LLM-generated code runs in ephemeral Docker containers or Kubernetes pods with hard resource limits and restricted file systems.
- **Real-Time Streaming**: Consume token-level outputs and execution events via Server-Sent Events (SSE).
- **Asynchronous Webhooks**: Receive cryptographically signed payload notifications when sessions pause, complete, or fail.
- **Model Context Protocol (MCP)**: Safely connect external data sources (SQL, GitHub, etc.) to your agents.
- **Built-in Observability**: Automatic Prometheus metrics exposure (`/metrics`) and OpenTelemetry traces.
- **Kubernetes Native**: Deploy seamlessly to production clusters using the included Helm chart.

## 📦 Quick Start (Local Development)

### Prerequisites
- Python 3.12+ (managed via `uv`)
- Docker (for local sandbox execution)

### 1. Install Dependencies
```bash
git clone https://github.com/Atrium/Awesome-managed-agent.git
cd Awesome-managed-agent
uv sync
```

### 2. Run the API Server
By default, the server runs with SQLite persistence and the Docker sandbox backend.
```bash
# Enable the Docker sandbox backend
export ATRIUM_SANDBOX_BACKEND="docker"
export GEMINI_API_KEY="your-google-gemini-key"

uv run uvicorn "atrium.api.app:create_app" --host 0.0.0.0 --port 8080 --factory
```

### 3. Run the Webhook Delivery Worker
In a separate terminal, start the dedicated background worker that processes webhook delivery queues:
```bash
uv run atrium worker webhook-delivery
```

### 4. Create a Session
You can now create a new workspace and run an agent session via the API:
```bash
# Create a new session (Assuming you have generated an API key)
curl -X POST http://localhost:8080/api/v1/sessions \
  -H "Authorization: Bearer <YOUR_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "objective": "Write a python script that calculates the 100th Fibonacci number and run it."
  }'
```

## 🏗 Kubernetes Production Deployment

The project is fully prepped for Kubernetes deployment using Helm.

```bash
# Deploy to your cluster
helm upgrade --install atrium ./deploy/helm/atrium \
  --namespace atrium-system \
  --create-namespace \
  --set ingress.enabled=true \
  --set ingress.hosts[0].host="atrium.yourdomain.com"
```

*For detailed production runbooks (rollbacks, stuck sessions, etc.), see the `docs/operations/runbooks/` directory.*

## 📖 Using the Platform

### The Atrium UI Dashboard
The UI Dashboard (`http://localhost:8080/dashboard`) is still the heart of the user experience. It has been updated seamlessly to consume the new `v1` REST APIs and SSE endpoints. You can monitor active sessions, watch the sandbox execution logs live, and interact with the human-in-the-loop checkpoints directly from the console.

### Model Context Protocol (MCP) Integration
You can register MCP servers to expand your agent's capabilities. For example, to give your agent access to a local SQLite database:

```bash
curl -X POST http://localhost:8080/api/v1/mcp-servers \
  -H "Authorization: Bearer <YOUR_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "sqlite-tool",
    "transport": "stdio",
    "upstream": "uvx mcp-server-sqlite --db-path /workspace/data.db"
  }'
```

The agent will automatically be granted the tools provided by the MCP server upon starting a session.
