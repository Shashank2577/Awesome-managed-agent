# PHASE 6 — Hardening and Operational Readiness

**Goal:** the system is deployable to production EKS without hand-holding.
Helm chart, Kubernetes sandbox runner, OpenTelemetry, Prometheus metrics,
runbooks. The system is now production for Engineering Core's purposes.

**Estimated effort:** 6 days (1–2 engineers).

**Depends on:** Phase 5.

**Unblocks:** production rollout.

## 6.1 Files to create or modify

| Action | Path | What |
|--------|------|------|
| CREATE | `deploy/helm/atrium/Chart.yaml` |  |
| CREATE | `deploy/helm/atrium/values.yaml` |  |
| CREATE | `deploy/helm/atrium/templates/api-deployment.yaml` |  |
| CREATE | `deploy/helm/atrium/templates/api-service.yaml` |  |
| CREATE | `deploy/helm/atrium/templates/api-hpa.yaml` |  |
| CREATE | `deploy/helm/atrium/templates/sandbox-rbac.yaml` |  |
| CREATE | `deploy/helm/atrium/templates/configmap.yaml` |  |
| CREATE | `deploy/helm/atrium/templates/secrets.yaml` |  |
| CREATE | `deploy/helm/atrium/templates/network-policy.yaml` |  |
| CREATE | `deploy/helm/atrium/templates/ingress.yaml` |  |
| MODIFY | `src/atrium/harness/sandbox.py` | Add `KubernetesSandboxRunner`. |
| CREATE | `src/atrium/observability/__init__.py` |  |
| CREATE | `src/atrium/observability/tracing.py` | OTEL setup. |
| CREATE | `src/atrium/observability/metrics.py` | Prometheus metrics. |
| MODIFY | `src/atrium/api/app.py` | Wire OTEL + metrics. |
| MODIFY | `src/atrium/streaming/webhooks.py` | Run as separate worker. |
| CREATE | `src/atrium/cli.py` (extend) | `atrium worker webhook-delivery` entry. |
| CREATE | `docs/operations/runbooks/deploy.md` |  |
| CREATE | `docs/operations/runbooks/rollback.md` |  |
| CREATE | `docs/operations/runbooks/stuck-session.md` |  |
| CREATE | `docs/operations/runbooks/backfill-events.md` |  |
| CREATE | `tests/load/locustfile.py` | Load test. |
| CREATE | `Dockerfile.api` | Production image. |

## 6.2 Helm chart structure

```
deploy/helm/atrium/
├── Chart.yaml
├── values.yaml
└── templates/
    ├── api-deployment.yaml         # 3 replicas of the API
    ├── api-service.yaml
    ├── api-hpa.yaml                # HPA on CPU 70%, min=2 max=10
    ├── webhook-worker-deployment.yaml  # 1 replica (idempotent retries)
    ├── sandbox-rbac.yaml           # ServiceAccount, Role, RoleBinding for spawning sandbox Pods
    ├── configmap.yaml              # ATRIUM_DB_URL, log level, etc.
    ├── secrets.yaml                # API keys hash, webhook secret, model API keys
    ├── ingress.yaml                # ALB ingress, TLS termination
    └── network-policy.yaml         # API → Postgres + Redis only; sandbox Pods get a separate policy
```

`values.yaml` exposes:
- `image.repository`, `image.tag`
- `replicas.api`, `replicas.webhookWorker`
- `database.url` (or `database.host` + `secretRef`)
- `sandbox.backend` (`kubernetes`)
- `sandbox.imageRegistry`
- `sandbox.namespace` (separate namespace for sandbox Pods)
- `ingress.host`, `ingress.tls.secretName`
- `resources.api.requests.cpu/memory`
- `resources.api.limits.cpu/memory`

## 6.3 `KubernetesSandboxRunner`

Same protocol as `DockerSandboxRunner`, different backend. Uses the
official Kubernetes Python client (`kubernetes-asyncio`).

```python
# template — KubernetesSandboxRunner.start
@classmethod
async def start(cls, session, runtime, model, env, limits, network_policy):
    pod_name = f"atrium-session-{session.session_id[:8]}"
    namespace = config.sandbox_namespace

    # Create a PVC for the workspace, sized to limits.disk_mb.
    pvc = V1PersistentVolumeClaim(
        metadata=V1ObjectMeta(name=f"{pod_name}-workspace", namespace=namespace),
        spec=V1PersistentVolumeClaimSpec(
            access_modes=["ReadWriteOnce"],
            resources=V1VolumeResourceRequirements(
                requests={"storage": f"{limits.disk_mb}Mi"}
            ),
            storage_class_name=config.sandbox_storage_class,
        ),
    )
    await pvc_api.create_namespaced_persistent_volume_claim(namespace, pvc)

    # Spec out the Pod.
    pod = V1Pod(
        metadata=V1ObjectMeta(
            name=pod_name,
            namespace=namespace,
            labels={
                "app": "atrium-sandbox",
                "session-id": session.session_id,
                "workspace-id": session.workspace_id,
            },
        ),
        spec=V1PodSpec(
            restart_policy="Never",
            automount_service_account_token=False,
            security_context=V1PodSecurityContext(
                run_as_user=10001, run_as_group=10001, fs_group=10001,
            ),
            containers=[
                V1Container(
                    name="sandbox",
                    image=runtime.image_tag(config.sandbox_image_registry),
                    command=runtime.command(model, "/workspace/.atrium/system_prompt.txt"),
                    env=[V1EnvVar(name=k, value=v) for k, v in env.items()],
                    resources=V1ResourceRequirements(
                        requests={
                            "cpu": str(limits.cpus),
                            "memory": f"{limits.memory_mb}Mi",
                        },
                        limits={
                            "cpu": str(limits.cpus),
                            "memory": f"{limits.memory_mb}Mi",
                        },
                    ),
                    security_context=V1SecurityContext(
                        allow_privilege_escalation=False,
                        read_only_root_filesystem=True,
                        capabilities=V1Capabilities(drop=["ALL"]),
                    ),
                    volume_mounts=[
                        V1VolumeMount(name="workspace", mount_path="/workspace"),
                        V1VolumeMount(name="mcp-socket", mount_path="/run/atrium"),
                        V1VolumeMount(name="tmp", mount_path="/tmp"),
                    ],
                    stdin=True, stdin_once=True, tty=False,
                ),
            ],
            volumes=[
                V1Volume(
                    name="workspace",
                    persistent_volume_claim=V1PersistentVolumeClaimVolumeSource(
                        claim_name=f"{pod_name}-workspace"
                    ),
                ),
                V1Volume(
                    name="mcp-socket",
                    host_path=V1HostPathVolumeSource(path="/run/atrium"),
                ),
                V1Volume(name="tmp", empty_dir=V1EmptyDirVolumeSource(medium="Memory")),
            ],
            active_deadline_seconds=limits.wall_clock_seconds,
        ),
    )
    await core_api.create_namespaced_pod(namespace, pod)

    # Wait for Running.
    await _wait_for_pod_running(pod_name, namespace, timeout=60)

    # Attach to stdin/stdout/stderr.
    runner = cls(pod_name=pod_name, namespace=namespace, session=session, ...)
    await runner._attach()
    return runner
```

`stop()` deletes the Pod with `grace_period_seconds=10`.
`kill()` deletes with `grace_period_seconds=0`.

The MCP socket is mounted via `hostPath` from a node-local directory.
For multi-node clusters, run an Atrium API replica per node OR have
the gateway listen on a TCP socket inside the cluster (a per-namespace
ClusterIP service). The TCP-socket variant is preferred for Phase 6
production deploys.

### `network-policy.yaml`

Three policies:

1. `api-policy` — API pods can reach Postgres and the sandbox
   namespace. Outbound to model providers (allow-list of CIDRs from
   each provider's documented IP ranges).
2. `sandbox-policy` — sandbox pods can reach ONLY:
   - The MCP gateway service (cluster-internal).
   - The model endpoint (one provider per session).
   - DNS.
3. `webhook-worker-policy` — outbound HTTPS to anywhere (webhooks
   target customer-controlled URLs); inbound from nothing.

## 6.4 OpenTelemetry tracing

```python
# verbatim — src/atrium/observability/tracing.py
"""OpenTelemetry tracing setup."""
from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def configure(service_name: str = "atrium-api") -> None:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return  # OTEL disabled

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)

    HTTPXClientInstrumentor().instrument()


def instrument_app(app) -> None:
    if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        FastAPIInstrumentor.instrument_app(app)
```

Manual spans are added at four key boundaries:
- `ThreadOrchestrator.run` (one span per thread, attribute
  `thread_id`).
- `Commander.plan` and `Commander.evaluate`.
- `HarnessAgent.run` (attribute `session_id`).
- `BridgeStream.run` (one span; child spans per inner-runtime event
  if `OTEL_TRACE_INNER_EVENTS=1`).

## 6.5 Prometheus metrics

```python
# verbatim — src/atrium/observability/metrics.py
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
```

The `/metrics` endpoint is added to the API. Standard
`prometheus-fastapi-instrumentator` provides HTTP latency / status
metrics; the above are the Atrium-specific ones.

## 6.6 Webhook worker as separate process

The webhook delivery loop currently runs in the same process as the API.
For production, it should run as its own deployment so:

- API restarts don't drop webhook retries.
- Webhook backpressure doesn't slow API responses.
- Worker can be scaled independently (probably 1 is fine forever; the
  delivery query is fast and the throughput is per-request).

`atrium worker webhook-delivery` becomes a CLI command that runs only
the delivery loop. It needs the same Storage and EventRecorder as the
API but no HTTP routes. Helm deploys it as a separate Deployment.

The delivery loop is idempotent: at most one worker can claim a
delivery via SELECT FOR UPDATE SKIP LOCKED on Postgres (or an
advisory_lock fallback for SQLite, though SQLite shouldn't run more
than one worker).

## 6.7 Production Dockerfile

```dockerfile
# verbatim — Dockerfile.api
FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && \
    uv sync --frozen --no-dev --extra all

COPY src/ ./src/
RUN uv build

FROM python:3.12-slim AS runtime

RUN useradd -u 10001 -m atrium && \
    apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

USER atrium
EXPOSE 8080
ENV PYTHONUNBUFFERED=1

# Healthcheck via the existing /api/v1/health route.
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s \
    CMD curl -fsS http://localhost:8080/api/v1/health || exit 1

CMD ["uvicorn", "atrium.api.app:create_app", "--host", "0.0.0.0", "--port", "8080", "--factory"]
```

## 6.8 Runbooks

Each runbook is a single page following the same template:
1. **Symptoms** — what the operator sees.
2. **Diagnosis** — concrete commands to run (`kubectl logs`, SQL
   queries, etc.).
3. **Resolution** — steps to fix.
4. **Prevention** — what code change or alert should prevent recurrence.

### `deploy.md`
Standard Helm deploy procedure. Includes pre-flight checks (DB
migration succeeded, image pulled, secrets present), deploy command,
post-deploy verification (health check returning 200, one synthetic
session completes).

### `rollback.md`
Procedure for rolling back a bad release. Includes how to roll the DB
forward then back if a migration was applied (Atrium uses
forward-only migrations, so rollback is via restore-from-snapshot —
this runbook documents that explicitly).

### `stuck-session.md`
Symptoms: a session in RUNNING for > 1 hour with no recent events.
Diagnosis: query `last_active_at`, kubectl describe the sandbox pod.
Resolution: `kubectl delete pod` (the orchestrator's watchdog will
mark the session FAILED on next tick), or `POST
/api/v1/sessions/{id}/cancel`.

### `backfill-events.md`
For replaying events from SQLite to Postgres during a migration, or
from a backup after a data-loss incident.

## 6.9 Load test

```python
# template — tests/load/locustfile.py
from locust import HttpUser, task, between


class AtriumUser(HttpUser):
    wait_time = between(1, 5)
    host = "http://localhost:8080"

    def on_start(self):
        # admin issues a workspace key; test holds it for the run.
        ...

    @task(3)
    def create_thread(self):
        ...

    @task(1)
    def create_session(self):
        ...

    @task(5)
    def list_threads(self):
        ...

    @task(2)
    def stream_events(self):
        # SSE for 30s
        ...
```

Target: 50 concurrent sessions on a 3-node cluster (each node 4 vCPU,
16GiB) sustained for 30 minutes with p99 API latency < 500ms and zero
data corruption.

## 6.10 Acceptance tests

### `tests/test_observability/test_metrics.py`

```
test_threads_started_increments_on_create
test_sessions_active_gauge_reflects_running_count
test_tokens_consumed_recorded_for_real_session
test_metrics_endpoint_returns_prometheus_format
```

### `tests/integration/k8s/test_kubernetes_sandbox.py` (gated `-m k8s`)

Requires a kind / minikube cluster.

```
test_session_creates_pod_in_sandbox_namespace
test_pod_workspace_pvc_persists_across_pod_restart
test_pod_active_deadline_kills_pod_after_timeout
test_network_policy_blocks_unallowed_egress
```

### `tests/load/`

Manual run, not part of CI gate. Records baseline numbers in
`docs/operations/load-test-results.md`.

## 6.11 Non-goals for Phase 6

- Multi-region / DR — separate workstream.
- gVisor / Firecracker isolation — left for a hardening pass after
  v1; current isolation (Pod + read-only rootfs + dropped caps + no
  privilege escalation + active deadline + network policy) is
  acceptable for internal Taazaa workloads. CIVI may need stronger
  isolation; address when CIVI is ready.
- A separate frontend repo / single-page app for the dashboard —
  the existing static dashboard suffices for v1.
- Full OAuth integration — admin and workspace key auth is enough
  for v1.

## 6.12 Definition of done

- [ ] Helm chart renders cleanly with `helm template`.
- [ ] `helm install` against a fresh kind cluster brings up a working
      Atrium with one synthetic workspace.
- [ ] All acceptance tests passing.
- [ ] Prometheus scrapes metrics; Grafana dashboard committed at
      `deploy/grafana/atrium.json`.
- [ ] OTEL traces visible in Jaeger when running locally with the
      compose file at `deploy/dev/docker-compose.observability.yml`.
- [ ] Load test recorded baseline numbers in
      `docs/operations/load-test-results.md`.
- [ ] All four runbooks present and reviewed by an operator.
- [ ] No `TODO(phase-6)` markers remain.
- [ ] README updated with deploy instructions.
