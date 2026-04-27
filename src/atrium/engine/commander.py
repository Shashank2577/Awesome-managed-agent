"""Commander — LLM-powered planner that creates and evaluates execution plans."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from atrium.core.models import Plan, PlanStep
from atrium.core.registry import AgentRegistry
from atrium.engine.llm import LLMClient

# ---------------------------------------------------------------------------
# System prompt templates
# ---------------------------------------------------------------------------

PLAN_SYSTEM_PROMPT = """\
You are an orchestration planner. Given the following agent manifest and an objective,
produce a JSON execution plan.

Agent manifest:
{manifest}

Return ONLY valid JSON in exactly this shape:
{{
  "rationale": "<why this plan achieves the objective>",
  "steps": [
    {{
      "agent": "<agent name from the manifest>",
      "inputs": {{}},
      "depends_on": []
    }}
  ]
}}

Rules:
- Only use agent names that appear in the manifest.
- depends_on must list agent names that must complete before this step runs.
- Do not include any text outside the JSON object.
"""

EVAL_SYSTEM_PROMPT = """You are the Commander evaluating agent outputs.

OBJECTIVE: {objective}

AGENT OUTPUTS:
{outputs}

Decide:
- "finalize" if the results adequately address the objective
- "pivot" if results are insufficient and more agents should run

Return JSON:
{{
  "decision": "finalize" or "pivot",
  "summary": "2-3 sentence executive summary",
  "findings": [
    {{"severity": "high" or "med" or "low", "text": "description of finding"}}
  ],
  "recommendations": ["actionable recommendation"],
  "rationale": "Why you chose this decision",
  "new_steps": []
}}"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_default(obj: Any) -> Any:
    """JSON serializer fallback: converts Python type objects to their names."""
    if isinstance(obj, type):
        return obj.__name__
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


# ---------------------------------------------------------------------------
# EvalDecision dataclass
# ---------------------------------------------------------------------------

@dataclass
class EvalDecision:
    action: str  # "finalize" or "pivot"
    summary: str = ""
    rationale: str = ""
    new_steps: list[PlanStep] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Commander
# ---------------------------------------------------------------------------

class Commander:
    """LLM-powered planner that reads the agent registry manifest and generates
    execution plans, then evaluates results to decide whether to finalize or pivot.
    """

    def __init__(self, llm_config: str, registry: AgentRegistry) -> None:
        self._llm = LLMClient(config=llm_config)
        self._registry = registry

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    async def plan(self, objective: str) -> Plan:
        """Ask the LLM to create an execution plan for *objective*.

        Agent names in steps are validated against the registry; unknown agents
        are silently filtered out. Unknown names in depends_on are also removed.
        """
        manifest = self._registry.manifest()
        manifest_json = json.dumps(manifest, indent=2, default=_json_default)

        system_prompt = PLAN_SYSTEM_PROMPT.format(manifest=manifest_json)
        user_prompt = f"Objective: {objective}"

        raw: dict[str, Any] = await self._llm.generate_json(system_prompt, user_prompt)

        known_agents: set[str] = {entry["name"] for entry in manifest}

        # Validate and filter steps
        valid_steps: list[PlanStep] = []
        for step_data in raw.get("steps", []):
            agent_name = step_data.get("agent", "")
            if agent_name not in known_agents:
                continue
            # Filter unknown names from depends_on
            clean_depends = [
                dep for dep in step_data.get("depends_on", [])
                if dep in known_agents
            ]
            valid_steps.append(
                PlanStep(
                    agent=agent_name,
                    inputs=step_data.get("inputs", {}),
                    depends_on=clean_depends,
                )
            )

        return Plan(
            thread_id="",
            rationale=raw.get("rationale", ""),
            steps=valid_steps,
        )

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    async def evaluate(self, objective: str, outputs: dict[str, Any]) -> EvalDecision:
        """Ask the LLM to evaluate *outputs* and decide to finalize or pivot.

        For pivot decisions, new_steps agent names are validated against the
        registry.
        """
        outputs_json = json.dumps(outputs, indent=2)

        system_prompt = EVAL_SYSTEM_PROMPT.format(
            objective=objective,
            outputs=outputs_json,
        )
        user_prompt = f"Evaluate the outputs and decide: finalize or pivot."

        raw: dict[str, Any] = await self._llm.generate_json(system_prompt, user_prompt)

        decision = raw.get("decision", "finalize")
        summary = raw.get("summary", "")
        rationale = raw.get("rationale", "")

        new_steps: list[PlanStep] = []
        if decision == "pivot":
            manifest = self._registry.manifest()
            known_agents: set[str] = {entry["name"] for entry in manifest}
            for step_data in raw.get("new_steps", []):
                agent_name = step_data.get("agent", "")
                if agent_name not in known_agents:
                    continue
                clean_depends = [
                    dep for dep in step_data.get("depends_on", [])
                    if dep in known_agents
                ]
                new_steps.append(
                    PlanStep(
                        agent=agent_name,
                        inputs=step_data.get("inputs", {}),
                        depends_on=clean_depends,
                    )
                )

        return EvalDecision(
            action=decision,
            summary=summary,
            rationale=rationale,
            new_steps=new_steps,
            findings=raw.get("findings", []),
            recommendations=raw.get("recommendations", []),
        )
