from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import UUID, uuid4

from backend.app.agents.observability.registry import AGENT_REGISTRY
from backend.app.models.domain import NodeStatus, PlanNode
from backend.app.runtime.events import InMemoryEventBus
from backend.app.runtime.executor import ParallelExecutor
from backend.app.runtime.guardrails import GuardrailEnforcer, GuardrailsConfig
from backend.app.runtime.registry import AgentRegistry


def _node(key: str, node_type: str, deps: list[str], *, thread_id: UUID, org_id: UUID) -> PlanNode:
    return PlanNode(
        node_id=uuid4(),
        plan_id=uuid4(),
        thread_id=thread_id,
        org_id=org_id,
        node_key=key,
        node_type=node_type,
        depends_on=deps,
        status=NodeStatus.PENDING,
        timeout_ms=2000,
    )


def build_demo_topology(*, thread_id: UUID, org_id: UUID) -> list[PlanNode]:
    return [
        _node("metrics", "metrics_ingestion", [], thread_id=thread_id, org_id=org_id),
        _node("traces", "trace_collection", [], thread_id=thread_id, org_id=org_id),
        _node("logs", "log_pipeline", [], thread_id=thread_id, org_id=org_id),
        _node("alerts", "alert_routing", ["metrics", "traces", "logs"], thread_id=thread_id, org_id=org_id),
        _node("slo", "dashboard_slo", ["alerts"], thread_id=thread_id, org_id=org_id),
    ]


async def run_observability_command(command: str, *, thread_id: UUID | None = None) -> dict:
    thread_id = thread_id or uuid4()
    org_id = uuid4()
    guardrails = GuardrailEnforcer(
        GuardrailsConfig(max_agents=20, max_parallel=3, max_time_seconds=60)
    )
    event_bus = InMemoryEventBus()
    executor = ParallelExecutor(guardrails=guardrails, event_bus=event_bus)
    nodes = build_demo_topology(thread_id=thread_id, org_id=org_id)

    node_inputs = {
        node.node_key: {"command": command}
        for node in nodes
    }

    registry = AgentRegistry()
    for agent_type, factory in AGENT_REGISTRY.items():
        registry.register(agent_type, factory)

    results = await executor.execute(
        nodes=nodes,
        registry=registry,
        node_inputs=node_inputs,
    )

    ordered_results = {
        node.node_key: {
            "node_type": node.node_type,
            "success": results[node.node_key].success,
            "error": results[node.node_key].error,
            "output": results[node.node_key].output,
            "depends_on": node.depends_on,
        }
        for node in nodes
        if node.node_key in results
    }

    events = [
        {
            "event_id": str(event.event_id),
            "type": event.type,
            "timestamp": event.timestamp.isoformat(),
            "payload": event.payload,
        }
        for event in event_bus.list_events(thread_id)
    ]

    return {
        "org_id": str(org_id),
        "thread_id": str(thread_id),
        "registry_count": len(AGENT_REGISTRY),
        "scenario_agent_count": len(nodes),
        "command": command,
        "results": ordered_results,
        "events": events,
        "budget": {
            "currency": "USD",
            "reserved": "5.00",
            "consumed": f"{0.001 * len([r for r in results.values() if r.success]):.3f}",
        },
    }


def render_ui_snapshot(report: dict, output_path: str) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ui_model = {
        "header": {
            "title": "Observability Stack Simulation",
            "registry_agents": report["registry_count"],
            "active_agents": report["scenario_agent_count"],
            "command": report["command"],
        },
        "states": [
            {
                "agent_node": key,
                "agent_type": value["node_type"],
                "status": "COMPLETED" if value["success"] else "FAILED",
                "handoff_count": value["output"].get("upstream_count", 0) if value["output"] else 0,
            }
            for key, value in report["results"].items()
        ],
        "timeline": report.get("events", []),
    }
    path.write_text(json.dumps(ui_model, indent=2), encoding="utf-8")


def run_demo(command: str = "run observability readiness validation") -> dict:
    report = asyncio.run(run_observability_command(command))
    render_ui_snapshot(report, "artifacts/observability_ui_snapshot.json")
    return report
