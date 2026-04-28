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
- EACH AGENT CAN ONLY APPEAR ONCE in the plan. Never use the same agent name twice.
  If you need similar work done for different inputs, use ONE agent and pass all inputs together.
- depends_on must list agent names that must complete before this step runs.
- CRITICAL: If agent B needs data produced by agent A, agent B MUST list agent A in depends_on.
  For example, a summarizer that summarizes search results MUST depend on the search agent.
  Agents without depends_on run in parallel. Agents WITH depends_on wait for their dependencies.
- Pass relevant inputs from the objective (like the search query) in the inputs field.
- Do not include any text outside the JSON object.
"""

EVAL_SYSTEM_PROMPT = """\
You are synthesizing a final report from agent outputs.

OBJECTIVE: {objective}

AGENT OUTPUTS:
{outputs}

Your job is to write a clear, intelligent report that directly answers the user's objective.
Adapt the format to what makes sense for the content:
- For factual questions: a clear answer paragraph
- For research: organized sections with key points
- For analysis: structured findings with context
- For comparisons: side-by-side key facts

Return JSON:
{{
  "decision": "finalize",
  "headline": "A clear, concise title for the report",
  "summary": "A well-written 2-4 sentence answer that directly addresses the objective. This is the main content the user sees.",
  "sections": [
    {{
      "title": "Section heading",
      "content": "Paragraph of text with the key information. Write in complete sentences.",
      "key_facts": ["Key fact 1", "Key fact 2"]
    }}
  ],
  "recommendations": ["Optional next step or suggestion"],
  "rationale": "Why you chose to finalize"
}}

Rules:
- The summary should DIRECTLY answer the user's question in plain language.
- sections should organize the detailed information logically.
- key_facts within sections are short, scannable bullet points.
- Do NOT use severity ratings (high/med/low) unless the objective is about risk or incidents.
- Do NOT include meta-commentary about agents or failures — just present the findings.
- Write as if you are the expert presenting results, not a system reporting status.
"""


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
    headline: str = ""
    summary: str = ""
    rationale: str = ""
    new_steps: list[PlanStep] = field(default_factory=list)
    sections: list[dict] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    # Legacy compat
    findings: list[dict] = field(default_factory=list)


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

        try:
            raw: dict[str, Any] = await self._llm.generate_json(system_prompt, user_prompt)
        except Exception:
            # Fallback: run all agents sequentially
            return Plan(
                thread_id="",
                rationale="LLM planning failed, running all agents.",
                steps=[PlanStep(agent=e["name"], inputs={}, depends_on=[]) for e in manifest],
            )

        if not isinstance(raw, dict):
            return Plan(
                thread_id="",
                rationale="LLM returned non-dict, running all agents.",
                steps=[PlanStep(agent=e["name"], inputs={}, depends_on=[]) for e in manifest],
            )

        known_agents: set[str] = {entry["name"] for entry in manifest}

        # Validate and filter steps (no duplicate agent names)
        valid_steps: list[PlanStep] = []
        seen_agents: set[str] = set()
        for step_data in raw.get("steps", []):
            agent_name = step_data.get("agent", "")
            if agent_name not in known_agents:
                continue
            if agent_name in seen_agents:
                continue  # Skip duplicates — each agent can only appear once
            seen_agents.add(agent_name)
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
        try:
            outputs_json = json.dumps(outputs, indent=2, default=str)
        except Exception:
            outputs_json = str(outputs)[:5000]

        system_prompt = EVAL_SYSTEM_PROMPT.format(
            objective=objective,
            outputs=outputs_json,
        )
        user_prompt = f"Evaluate the outputs and decide: finalize or pivot."

        try:
            raw: dict[str, Any] = await self._llm.generate_json(system_prompt, user_prompt)
        except Exception:
            return EvalDecision(
                action="finalize",
                summary="Evaluation failed, finalizing with available results.",
                findings=[{"severity": "low", "text": "LLM evaluation call failed"}],
                recommendations=["Review raw agent outputs"],
            )

        if not isinstance(raw, dict):
            return EvalDecision(
                action="finalize",
                summary=str(raw)[:200] if raw else "Analysis complete.",
            )

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

        # Parse sections (new format)
        raw_sections = raw.get("sections", [])
        if not isinstance(raw_sections, list):
            raw_sections = []
        sections = []
        for s in raw_sections:
            if isinstance(s, dict):
                sections.append({
                    "title": str(s.get("title", "")),
                    "content": str(s.get("content", "")),
                    "key_facts": [str(f) for f in s.get("key_facts", []) if f] if isinstance(s.get("key_facts"), list) else [],
                })
            elif isinstance(s, str):
                sections.append({"title": "", "content": s, "key_facts": []})

        # Sanitize recommendations
        raw_recs = raw.get("recommendations", [])
        if not isinstance(raw_recs, list):
            raw_recs = [str(raw_recs)] if raw_recs else []
        recommendations = [str(r) for r in raw_recs]

        # Legacy findings compat (convert sections to findings for old dashboard)
        findings = []
        for s in sections:
            if s.get("content"):
                findings.append({"severity": "low", "text": s["content"][:200]})

        headline = raw.get("headline", "") or summary[:60]

        return EvalDecision(
            action=decision,
            headline=headline,
            summary=summary,
            rationale=rationale,
            new_steps=new_steps,
            sections=sections,
            recommendations=recommendations,
            findings=findings,
        )
