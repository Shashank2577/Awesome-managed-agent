"""Commander control plane.

Implements the planning loop from EXECUTION_SEMANTICS.md:
ingest -> plan -> execute -> evaluate -> pivot? -> finalize.

The commander is intentionally deterministic and offline-friendly so it can
power the demo without any model provider. The output stream emits the full
event taxonomy required by EVENTS.md so the UI receives a faithful trace.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Awaitable, Callable, Optional
from uuid import UUID, uuid4


EmitFn = Callable[[str, dict[str, Any], Optional[UUID]], Awaitable[None]]


@dataclass(slots=True)
class AgentSpec:
    """Specification for one agent the commander wants to hire."""

    agent_key: str
    role: str
    objective: str
    inputs: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PlanSpec:
    plan_id: UUID
    plan_number: int
    rationale: str
    agents: list[AgentSpec]


# ---------------------------------------------------------------------------
# Scenario library
# ---------------------------------------------------------------------------


SCENARIO_LIBRARY: dict[str, dict[str, Any]] = {
    "incident": {
        "title": "Incident triage",
        "rationale": (
            "Customer reported elevated latency. I'll fan out three log specialists "
            "across the affected services, plus traces and a correlation pass."
        ),
        "agents": [
            ("logs_checkout", "log_pipeline", "Inspect checkout-service logs"),
            ("logs_payments", "log_pipeline", "Inspect payments-service logs"),
            ("logs_search", "log_pipeline", "Inspect search-service logs"),
            ("traces", "trace_collection", "Collect distributed traces and slow paths"),
        ],
        "joins": [
            ("correlation", "incident_correlation", "Correlate logs + traces", [
                "logs_checkout", "logs_payments", "logs_search", "traces",
            ]),
        ],
        "presenter_inputs": {"theme": "incident", "headline": "Latency root cause"},
        "pivot": {
            "trigger": "logs_payments",
            "rationale": (
                "Payments errors include 'TLS handshake failed'. Pivoting: hiring a "
                "security-telemetry agent to inspect cert rotation events."
            ),
            "added": [
                ("security_pivot", "security_telemetry", "Inspect cert/TLS telemetry", []),
            ],
            "downstream_dep": "correlation",
        },
    },
    "observability": {
        "title": "Observability readiness review",
        "rationale": (
            "Audit metrics, traces, and logs paths, then judge SLO readiness."
        ),
        "agents": [
            ("metrics", "metrics_ingestion", "Audit metrics ingestion"),
            ("traces", "trace_collection", "Audit trace collection"),
            ("logs", "log_pipeline", "Audit log pipeline"),
        ],
        "joins": [
            ("alerts", "alert_routing", "Audit alert routing", ["metrics", "traces", "logs"]),
            ("slo", "dashboard_slo", "Render SLO posture", ["alerts"]),
        ],
        "presenter_inputs": {"theme": "observability", "headline": "Readiness scorecard"},
        "pivot": None,
    },
    "cost": {
        "title": "Cost-optimization review",
        "rationale": (
            "Look at storage retention, top spend drivers, and headroom forecasting."
        ),
        "agents": [
            ("retention", "data_retention", "Audit retention windows"),
            ("forecast", "capacity_forecast", "Forecast capacity headroom"),
            ("optimizer", "cost_optimization", "Identify spend drivers"),
        ],
        "joins": [
            ("rollup", "rollup_coordinator", "Roll up findings", ["retention", "forecast", "optimizer"]),
        ],
        "presenter_inputs": {"theme": "cost", "headline": "Cost reduction levers"},
        "pivot": None,
    },
}


def classify_objective(text: str) -> str:
    """Choose a scenario template from the user's objective."""
    lowered = text.lower()
    if re.search(r"\b(incident|outage|latency|slow|error|down|p[01])\b", lowered):
        return "incident"
    if re.search(r"\b(cost|spend|bill|budget|retention|capacity)\b", lowered):
        return "cost"
    return "observability"


# ---------------------------------------------------------------------------
# Commander
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class CommanderConfig:
    plan_delay_ms: int = 600
    hire_delay_ms: int = 250
    agent_think_min_ms: int = 350
    agent_think_max_ms: int = 950
    pivot_delay_ms: int = 700
    presenter_delay_ms: int = 800


class Commander:
    """Orchestrates a thread end-to-end and emits a richly typed event stream."""

    def __init__(
        self,
        *,
        thread_id: UUID,
        org_id: UUID,
        objective: str,
        emit: EmitFn,
        config: Optional[CommanderConfig] = None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self.thread_id = thread_id
        self.org_id = org_id
        self.objective = objective
        self.emit = emit
        self.config = config or CommanderConfig()
        self._clock = clock
        self._scenario_key = classify_objective(objective)
        self._scenario = SCENARIO_LIBRARY[self._scenario_key]
        self._plan_number = 0
        self._consumed = Decimal("0")
        self._reserved = Decimal("0")
        self._currency = "USD"
        self._hard_limit = Decimal("12.00")

    # -- public API ----------------------------------------------------------

    @property
    def scenario_title(self) -> str:
        return self._scenario["title"]

    async def run(self) -> dict[str, Any]:
        await self._emit("THREAD_CREATED", {"objective": self.objective, "scenario": self._scenario_key})
        await self._emit("BUDGET_RESERVED", self._budget_payload(reserve=Decimal("8.00")))

        await self._emit("THREAD_PLANNING_STARTED", {"objective": self.objective})
        await self._emit("PLAN_GENERATION_STARTED", {"prompt": self.objective})

        commentary = self._commander_message_intro()
        await self._emit("COMMANDER_MESSAGE", {"text": commentary, "phase": "planning"})

        await asyncio.sleep(self.config.plan_delay_ms / 1000)

        plan = self._build_initial_plan()
        await self._emit_plan_created(plan)
        await self._emit("PLAN_APPROVED", {"plan_id": str(plan.plan_id)})
        await self._emit("THREAD_RUNNING", {"plan_id": str(plan.plan_id)})
        await self._emit("PLAN_EXECUTION_STARTED", {"plan_id": str(plan.plan_id)})

        agent_outputs: dict[str, dict[str, Any]] = {}

        # First wave (no dependencies)
        first_wave = [a for a in plan.agents if not a.depends_on]
        await self._hire_and_run_agents(first_wave, agent_outputs)

        # Pivot decision
        pivot_added: list[AgentSpec] = []
        pivot_meta = self._scenario.get("pivot")
        if pivot_meta and pivot_meta["trigger"] in agent_outputs:
            pivot_added = await self._apply_pivot(plan, pivot_meta, agent_outputs)

        # Second wave (joins) — wire pivot deps if needed
        join_targets = [a for a in plan.agents if a.depends_on]
        for agent in join_targets:
            if pivot_meta and agent.agent_key == pivot_meta.get("downstream_dep"):
                for added in pivot_added:
                    if added.agent_key not in agent.depends_on:
                        agent.depends_on.append(added.agent_key)
        await self._hire_and_run_agents(join_targets, agent_outputs)

        # Presenter / Reporter agent
        await asyncio.sleep(self.config.presenter_delay_ms / 1000)
        evidence = await self._run_presenter(plan, agent_outputs)

        await self._emit("PLAN_COMPLETED", {"plan_id": str(plan.plan_id)})
        await self._emit("BUDGET_CONSUMED", self._budget_payload())
        await self._emit("THREAD_COMPLETED", {
            "evidence_id": evidence["evidence_id"],
            "headline": evidence["headline"],
        })

        return {
            "thread_id": str(self.thread_id),
            "scenario": self._scenario_key,
            "plan_id": str(plan.plan_id),
            "evidence": evidence,
            "agent_outputs": agent_outputs,
        }

    # -- internal helpers ----------------------------------------------------

    async def _emit(self, event_type: str, payload: dict[str, Any], correlation: Optional[UUID] = None) -> None:
        await self.emit(event_type, payload, correlation)

    def _budget_payload(self, reserve: Decimal | None = None) -> dict[str, Any]:
        if reserve is not None:
            self._reserved = reserve
        return {
            "currency": self._currency,
            "allocated": str(self._hard_limit),
            "reserved": f"{self._reserved:.2f}",
            "consumed": f"{self._consumed:.4f}",
            "hard_limit": str(self._hard_limit),
        }

    def _commander_message_intro(self) -> str:
        templates = {
            "incident": (
                "Reading the request now. This looks like an incident — I'll start by "
                "fanning logs across the suspect services and pulling traces in parallel. "
                "I'll keep an eye on what they say and pivot if a pattern shows up."
            ),
            "observability": (
                "Reading the request now. I'll audit the three data planes — metrics, "
                "traces, and logs — in parallel, then judge alert wiring and SLO posture."
            ),
            "cost": (
                "Reading the request now. I'll line up retention, capacity forecast, and a "
                "spend optimizer in parallel, then roll up findings."
            ),
        }
        return templates.get(self._scenario_key, templates["observability"])

    def _build_initial_plan(self) -> PlanSpec:
        self._plan_number += 1
        agents: list[AgentSpec] = []
        for key, role, objective in self._scenario["agents"]:
            agents.append(
                AgentSpec(
                    agent_key=key,
                    role=role,
                    objective=objective,
                    inputs={"objective": self.objective},
                )
            )
        for join in self._scenario.get("joins", []):
            join_key, role, objective, deps = join
            agents.append(
                AgentSpec(
                    agent_key=join_key,
                    role=role,
                    objective=objective,
                    depends_on=list(deps),
                    inputs={"objective": self.objective},
                )
            )
        return PlanSpec(
            plan_id=uuid4(),
            plan_number=self._plan_number,
            rationale=self._scenario["rationale"],
            agents=agents,
        )

    async def _emit_plan_created(self, plan: PlanSpec) -> None:
        await self._emit(
            "PLAN_CREATED",
            {
                "plan_id": str(plan.plan_id),
                "plan_number": plan.plan_number,
                "rationale": plan.rationale,
                "graph": {
                    "nodes": [
                        {
                            "key": a.agent_key,
                            "role": a.role,
                            "objective": a.objective,
                            "depends_on": list(a.depends_on),
                        }
                        for a in plan.agents
                    ]
                },
            },
        )

    async def _hire_and_run_agents(
        self,
        specs: list[AgentSpec],
        outputs: dict[str, dict[str, Any]],
    ) -> None:
        if not specs:
            return

        for spec in specs:
            await self._emit(
                "AGENT_HIRED",
                {
                    "agent_key": spec.agent_key,
                    "role": spec.role,
                    "objective": spec.objective,
                    "depends_on": list(spec.depends_on),
                },
            )
            await asyncio.sleep(self.config.hire_delay_ms / 1000)

        await asyncio.gather(*(self._run_agent(spec, outputs) for spec in specs))

    async def _run_agent(self, spec: AgentSpec, outputs: dict[str, dict[str, Any]]) -> None:
        ak = spec.agent_key
        await self._emit("AGENT_REGISTERED", {"agent_key": ak})
        await self._emit("AGENT_READY", {"agent_key": ak})
        await self._emit("AGENT_QUEUED", {"agent_key": ak})
        await self._emit("AGENT_RUNNING", {"agent_key": ak})

        # Stream a few "thinking" thoughts to make the chat feel alive.
        for thought in self._agent_thoughts(spec):
            await asyncio.sleep(self._jitter())
            await self._emit("AGENT_MESSAGE", {"agent_key": ak, "text": thought})

        await asyncio.sleep(self._jitter())

        result = self._agent_result(spec, outputs)
        outputs[ak] = result

        # Cost accounting (deterministic, modest).
        self._consumed += Decimal("0.07")
        await self._emit("AGENT_OUTPUT", {"agent_key": ak, "output": result})
        await self._emit("AGENT_COMPLETED", {"agent_key": ak})
        await self._emit("BUDGET_CONSUMED", self._budget_payload())

    async def _apply_pivot(
        self,
        plan: PlanSpec,
        pivot_meta: dict[str, Any],
        outputs: dict[str, dict[str, Any]],
    ) -> list[AgentSpec]:
        await asyncio.sleep(self.config.pivot_delay_ms / 1000)
        await self._emit(
            "PIVOT_REQUESTED",
            {
                "rationale": pivot_meta["rationale"],
                "trigger_agent": pivot_meta["trigger"],
            },
        )
        await self._emit(
            "COMMANDER_MESSAGE",
            {"text": pivot_meta["rationale"], "phase": "pivot"},
        )

        added: list[AgentSpec] = []
        for key, role, objective, deps in pivot_meta["added"]:
            spec = AgentSpec(
                agent_key=key,
                role=role,
                objective=objective,
                inputs={"objective": self.objective, "trigger": pivot_meta["trigger"]},
                depends_on=list(deps),
            )
            added.append(spec)
            plan.agents.append(spec)

        await self._emit("PIVOT_APPLIED", {
            "added_agents": [a.agent_key for a in added],
            "plan_id": str(plan.plan_id),
        })
        await self._hire_and_run_agents(added, outputs)
        return added

    async def _run_presenter(
        self,
        plan: PlanSpec,
        outputs: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        ak = "presenter"
        await self._emit(
            "AGENT_HIRED",
            {
                "agent_key": ak,
                "role": "presenter",
                "objective": "Compose human-friendly evidence",
                "depends_on": list(outputs.keys()),
            },
        )
        await self._emit("AGENT_RUNNING", {"agent_key": ak})
        for line in [
            "Synthesizing findings from the team.",
            "Choosing the chart shape that best tells the story.",
            "Ranking risks and recommended next actions.",
        ]:
            await asyncio.sleep(self._jitter())
            await self._emit("AGENT_MESSAGE", {"agent_key": ak, "text": line})

        evidence = self._compose_evidence(outputs)
        self._consumed += Decimal("0.12")
        await self._emit("EVIDENCE_PUBLISHED", evidence)
        await self._emit("AGENT_COMPLETED", {"agent_key": ak})
        await self._emit("BUDGET_CONSUMED", self._budget_payload())
        return evidence

    def _compose_evidence(self, outputs: dict[str, dict[str, Any]]) -> dict[str, Any]:
        presenter_inputs = self._scenario["presenter_inputs"]
        if self._scenario_key == "incident":
            chart = {
                "type": "bar",
                "title": "Errors per service (last 15 min)",
                "series": [
                    {"label": "checkout", "value": int(outputs.get("logs_checkout", {}).get("hits", 14))},
                    {"label": "payments", "value": int(outputs.get("logs_payments", {}).get("hits", 71))},
                    {"label": "search", "value": int(outputs.get("logs_search", {}).get("hits", 9))},
                ],
            }
            findings = [
                {"severity": "high", "text": "TLS handshake failures spiking on payments-service."},
                {"severity": "med", "text": "Cert rotation 6h ago likely root cause."},
                {"severity": "low", "text": "Checkout latency is downstream symptom only."},
            ]
            recommendations = [
                "Roll back the cert chain on payments-service to the prior bundle.",
                "Add a synthetic monitor for the TLS handshake.",
                "Open a runbook compliance review for cert rotations.",
            ]
            headline = "Payments TLS rotation broke handshake — roll back the bundle"
        elif self._scenario_key == "cost":
            chart = {
                "type": "donut",
                "title": "Spend mix this month",
                "series": [
                    {"label": "log retention", "value": 41},
                    {"label": "trace storage", "value": 27},
                    {"label": "metrics", "value": 18},
                    {"label": "egress", "value": 14},
                ],
            }
            findings = [
                {"severity": "high", "text": "Log retention >30d on three services accounts for 41% of spend."},
                {"severity": "med", "text": "Forecast headroom OK for 90 days; no capacity buy needed."},
            ]
            recommendations = [
                "Cut retention to 14d on staging, 21d on prod for non-PII logs.",
                "Compress traces older than 7d to cold tier.",
            ]
            headline = "Two retention tweaks reclaim ~28% of monthly spend"
        else:
            chart = {
                "type": "scorecard",
                "title": "Observability readiness",
                "series": [
                    {"label": "metrics", "value": 92},
                    {"label": "traces", "value": 81},
                    {"label": "logs", "value": 88},
                    {"label": "alerts", "value": 76},
                    {"label": "SLO", "value": 84},
                ],
            }
            findings = [
                {"severity": "med", "text": "Alert routing has two paths missing oncall coverage."},
                {"severity": "low", "text": "Traces sampled at 5%, raise to 10% for premium tier."},
            ]
            recommendations = [
                "Wire missing alert routes to the platform-oncall rotation.",
                "Bump trace sampling to 10% for paid tier.",
            ]
            headline = "Strong baseline; two alert routes need oncall wiring"

        return {
            "evidence_id": str(uuid4()),
            "theme": presenter_inputs["theme"],
            "headline": headline,
            "summary": presenter_inputs["headline"],
            "chart": chart,
            "findings": findings,
            "recommendations": recommendations,
        }

    # -- micro helpers -------------------------------------------------------

    def _agent_thoughts(self, spec: AgentSpec) -> list[str]:
        if spec.role == "log_pipeline":
            target = spec.agent_key.split("_", 1)[-1] if "_" in spec.agent_key else "service"
            return [
                f"Pulling last 15m of error logs from {target}.",
                f"Grouping by error fingerprint on {target}.",
            ]
        if spec.role == "trace_collection":
            return [
                "Sampling traces from the past 15m.",
                "Looking for slow spans tagged downstream:db.",
            ]
        if spec.role == "incident_correlation":
            return [
                "Joining log fingerprints to trace timestamps.",
                "Looking for the earliest causal event.",
            ]
        if spec.role == "security_telemetry":
            return [
                "Reading the cert-rotation audit log.",
                "Cross-checking with TLS handshake errors timeline.",
            ]
        if spec.role == "metrics_ingestion":
            return ["Walking the metrics scrape topology."]
        if spec.role == "data_retention":
            return ["Sampling retention windows by tier."]
        if spec.role == "capacity_forecast":
            return ["Projecting 90-day capacity envelope."]
        if spec.role == "cost_optimization":
            return ["Ranking spend drivers by elasticity."]
        if spec.role == "alert_routing":
            return ["Walking alert -> route -> oncall mapping."]
        if spec.role == "dashboard_slo":
            return ["Computing SLO burn rate per surface."]
        if spec.role == "rollup_coordinator":
            return ["Folding child outputs into a posture rollup."]
        return [f"{spec.role}: starting the work."]

    def _agent_result(self, spec: AgentSpec, outputs: dict[str, dict[str, Any]]) -> dict[str, Any]:
        if spec.role == "log_pipeline":
            target = spec.agent_key.split("_", 1)[-1] if "_" in spec.agent_key else "service"
            base = {
                "service": target,
                "window_minutes": 15,
                "fingerprints": [],
            }
            if target == "payments":
                base["hits"] = 71
                base["fingerprints"] = [
                    {"signature": "TLS handshake failed: certificate chain", "count": 58},
                    {"signature": "upstream connect error", "count": 13},
                ]
            elif target == "checkout":
                base["hits"] = 14
                base["fingerprints"] = [
                    {"signature": "downstream payment timeout", "count": 14},
                ]
            else:
                base["hits"] = 9
                base["fingerprints"] = [
                    {"signature": "search query slow", "count": 9},
                ]
            return base
        if spec.role == "trace_collection":
            return {
                "samples": 412,
                "slow_spans": [
                    {"name": "POST /pay", "p95_ms": 2840},
                    {"name": "RPC payments.charge", "p95_ms": 2680},
                ],
            }
        if spec.role == "incident_correlation":
            return {
                "correlation_window": "13:42 - 13:57",
                "earliest_cause": "cert rotation completed at 13:39",
                "evidence_links": list(outputs.keys()),
            }
        if spec.role == "security_telemetry":
            return {
                "cert_rotation_at": "13:39",
                "rotation_actor": "secret-ops",
                "handshake_failures_after_rotation": 58,
            }
        if spec.role == "metrics_ingestion":
            return {"score": 92, "issues": []}
        if spec.role == "data_retention":
            return {"prod_days": 30, "staging_days": 30, "savings_pct_if_cut": 28}
        if spec.role == "capacity_forecast":
            return {"headroom_days": 142, "verdict": "ok"}
        if spec.role == "cost_optimization":
            return {
                "top_drivers": [
                    {"label": "log retention", "share": 0.41},
                    {"label": "trace storage", "share": 0.27},
                ],
            }
        if spec.role == "alert_routing":
            return {"score": 76, "missing_routes": 2}
        if spec.role == "dashboard_slo":
            return {"score": 84, "burning_objectives": []}
        if spec.role == "rollup_coordinator":
            return {"verdict": "ready_with_warnings"}
        return {"role": spec.role, "ok": True}

    def _jitter(self) -> float:
        # Deterministic for tests, but feels organic.
        lo = self.config.agent_think_min_ms / 1000
        hi = self.config.agent_think_max_ms / 1000
        return (lo + hi) / 2.0
