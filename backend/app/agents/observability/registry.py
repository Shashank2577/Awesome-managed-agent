from __future__ import annotations

from collections.abc import Callable

from backend.app.agents.base import BaseAgent
from backend.app.agents.observability.specialists import (
    AlertRoutingAgent,
    CapacityForecastAgent,
    CostOptimizationAgent,
    DashboardSLOAgent,
    DataRetentionAgent,
    IncidentCorrelationAgent,
    LogPipelineAgent,
    MetricsIngestionAgent,
    OnCallReadinessAgent,
    RollupCoordinatorAgent,
    RunbookComplianceAgent,
    SecurityTelemetryAgent,
    ServiceMapAgent,
    SyntheticMonitoringAgent,
    TraceCollectionAgent,
)

AGENT_REGISTRY: dict[str, Callable[[], BaseAgent]] = {
    "metrics_ingestion": MetricsIngestionAgent,
    "trace_collection": TraceCollectionAgent,
    "log_pipeline": LogPipelineAgent,
    "alert_routing": AlertRoutingAgent,
    "dashboard_slo": DashboardSLOAgent,
    "incident_correlation": IncidentCorrelationAgent,
    "synthetic_monitoring": SyntheticMonitoringAgent,
    "capacity_forecast": CapacityForecastAgent,
    "oncall_readiness": OnCallReadinessAgent,
    "security_telemetry": SecurityTelemetryAgent,
    "data_retention": DataRetentionAgent,
    "cost_optimization": CostOptimizationAgent,
    "service_map": ServiceMapAgent,
    "runbook_compliance": RunbookComplianceAgent,
    "rollup_coordinator": RollupCoordinatorAgent,
}


def build_agent(agent_type: str) -> BaseAgent:
    if agent_type not in AGENT_REGISTRY:
        raise KeyError(f"Unknown observability agent type: {agent_type}")
    return AGENT_REGISTRY[agent_type]()
