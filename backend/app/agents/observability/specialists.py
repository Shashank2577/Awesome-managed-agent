from __future__ import annotations

from typing import Any

from backend.app.agents.dummy import LifecycleAgent
from backend.app.models.domain import AgentStatus


class ObservabilitySpecialistAgent(LifecycleAgent):
    """Reusable specialist agent for observability stack simulations."""

    focus_area: str = "general"

    def __init__(self, agent_type: str):
        super().__init__(agent_type=agent_type)

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        self.transition(AgentStatus.REGISTERED)
        self.transition(AgentStatus.READY)
        self.transition(AgentStatus.QUEUED)
        self.transition(AgentStatus.RUNNING)

        command = str(input_data.get("command", ""))
        upstream = input_data.get("upstream", {})
        observations = self._analyze(command=command, upstream=upstream)

        self.transition(AgentStatus.COMPLETED)
        return {
            "agent": self.agent_type,
            "focus_area": self.focus_area,
            "command": command,
            "upstream_count": len(upstream),
            "observations": observations,
            "status": self.get_status(),
        }

    def _analyze(self, command: str, upstream: dict[str, Any]) -> list[str]:
        if not command:
            return [f"{self.focus_area}: no command provided"]
        return [
            f"{self.focus_area}: evaluated command '{command}'",
            f"{self.focus_area}: merged {len(upstream)} upstream result blocks",
        ]


class MetricsIngestionAgent(ObservabilitySpecialistAgent):
    focus_area = "metrics_ingestion"

    def __init__(self):
        super().__init__("metrics_ingestion")


class TraceCollectionAgent(ObservabilitySpecialistAgent):
    focus_area = "trace_collection"

    def __init__(self):
        super().__init__("trace_collection")


class LogPipelineAgent(ObservabilitySpecialistAgent):
    focus_area = "log_pipeline"

    def __init__(self):
        super().__init__("log_pipeline")


class AlertRoutingAgent(ObservabilitySpecialistAgent):
    focus_area = "alert_routing"

    def __init__(self):
        super().__init__("alert_routing")


class DashboardSLOAgent(ObservabilitySpecialistAgent):
    focus_area = "dashboard_slo"

    def __init__(self):
        super().__init__("dashboard_slo")


class IncidentCorrelationAgent(ObservabilitySpecialistAgent):
    focus_area = "incident_correlation"

    def __init__(self):
        super().__init__("incident_correlation")


class SyntheticMonitoringAgent(ObservabilitySpecialistAgent):
    focus_area = "synthetic_monitoring"

    def __init__(self):
        super().__init__("synthetic_monitoring")


class CapacityForecastAgent(ObservabilitySpecialistAgent):
    focus_area = "capacity_forecast"

    def __init__(self):
        super().__init__("capacity_forecast")


class OnCallReadinessAgent(ObservabilitySpecialistAgent):
    focus_area = "oncall_readiness"

    def __init__(self):
        super().__init__("oncall_readiness")


class SecurityTelemetryAgent(ObservabilitySpecialistAgent):
    focus_area = "security_telemetry"

    def __init__(self):
        super().__init__("security_telemetry")


class DataRetentionAgent(ObservabilitySpecialistAgent):
    focus_area = "data_retention"

    def __init__(self):
        super().__init__("data_retention")


class CostOptimizationAgent(ObservabilitySpecialistAgent):
    focus_area = "cost_optimization"

    def __init__(self):
        super().__init__("cost_optimization")


class ServiceMapAgent(ObservabilitySpecialistAgent):
    focus_area = "service_map"

    def __init__(self):
        super().__init__("service_map")


class RunbookComplianceAgent(ObservabilitySpecialistAgent):
    focus_area = "runbook_compliance"

    def __init__(self):
        super().__init__("runbook_compliance")


class RollupCoordinatorAgent(ObservabilitySpecialistAgent):
    focus_area = "rollup_coordinator"

    def __init__(self):
        super().__init__("rollup_coordinator")
