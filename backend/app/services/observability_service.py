from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from backend.app.agents.observability.registry import AGENT_REGISTRY, build_agent
from backend.app.models.domain import NodeStatus, PlanNode
from backend.app.runtime.executor import ParallelExecutor
from backend.app.runtime.guardrails import GuardrailEnforcer, GuardrailsConfig


def _node(key: str, node_type: str, deps: list[str]) -> PlanNode:
    return PlanNode(
        node_id=uuid4(),
        plan_id=uuid4(),
        thread_id=uuid4(),
        org_id=uuid4(),
        node_key=key,
        node_type=node_type,
        depends_on=deps,
        status=NodeStatus.PENDING,
        timeout_ms=2000,
    )


def build_demo_topology() -> list[PlanNode]:
    # five-agent test scenario from the full 15-agent registry
    return [
        _node("metrics", "metrics_ingestion", []),
        _node("traces", "trace_collection", []),
        _node("logs", "log_pipeline", []),
        _node("alerts", "alert_routing", ["metrics", "traces", "logs"]),
        _node("slo", "dashboard_slo", ["alerts"]),
    ]


async def run_observability_command(command: str) -> dict:
    guardrails = GuardrailEnforcer(
        GuardrailsConfig(max_agents=20, max_parallel=3, max_time_seconds=60)
    )
    executor = ParallelExecutor(guardrails=guardrails)
    nodes = build_demo_topology()

    node_inputs = {
        node.node_key: {"command": command}
        for node in nodes
    }

    results = await executor.execute(
        nodes=nodes,
        agent_factory=build_agent,
        node_inputs=node_inputs,
    )

    ordered_results = {
        node.node_key: {
            "node_type": node.node_type,
            "success": results[node.node_key].success,
            "error": results[node.node_key].error,
            "output": results[node.node_key].output,
        }
        for node in nodes
        if node.node_key in results
    }

    return {
        "registry_count": len(AGENT_REGISTRY),
        "scenario_agent_count": len(nodes),
        "command": command,
        "results": ordered_results,
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
    }
    path.write_text(json.dumps(ui_model, indent=2), encoding="utf-8")


def run_demo(command: str = "run observability readiness validation") -> dict:
    report = asyncio.run(run_observability_command(command))
    render_ui_snapshot(report, "artifacts/observability_ui_snapshot.json")
    return report
