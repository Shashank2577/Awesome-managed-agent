"""Commander — LLM-powered planner that creates and evaluates execution plans."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from atrium.core.errors import ValidationError
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


def _validate_plan(steps: list[PlanStep], registry: AgentRegistry) -> None:
    """Validate a plan against the registry. Raises ValidationError on issues."""
    # 1. Every agent name exists.
    available = {cls.name for cls in registry.list_all()}
    for step in steps:
        if step.agent not in available:
            raise ValidationError(
                f"plan references unknown agent: {step.agent}",
                {"available": sorted(available)},
            )

    # 2. No duplicates.
    seen: set[str] = set()
    for step in steps:
        if step.agent in seen:
            raise ValidationError(
                f"plan uses agent '{step.agent}' more than once"
            )
        seen.add(step.agent)

    # 3. depends_on references real steps and is acyclic.
    step_names = {s.agent for s in steps}
    for step in steps:
        for dep in step.depends_on:
            if dep not in step_names:
                raise ValidationError(
                    f"step '{step.agent}' depends on missing step '{dep}'"
                )

    # Cycle detection — DFS with white/gray/black colours.
    WHITE, GRAY, BLACK = 0, 1, 2
    colour: dict[str, int] = {s.agent: WHITE for s in steps}
    deps: dict[str, list[str]] = {s.agent: list(s.depends_on) for s in steps}

    def dfs(node: str) -> None:
        colour[node] = GRAY
        for d in deps[node]:
            if colour[d] == GRAY:
                raise ValidationError(f"plan has a cycle involving '{node}' and '{d}'")
            if colour[d] == WHITE:
                dfs(d)
        colour[node] = BLACK

    for s in steps:
        if colour[s.agent] == WHITE:
            dfs(s.agent)


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
    # Token usage from the eval LLM call
    usage: dict[str, int] = field(default_factory=dict)
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

    async def plan(self, objective: str) -> tuple[Plan, dict[str, int]]:
        """Ask the LLM to create an execution plan for *objective*.

        Returns:
            (Plan, usage_dict) — usage_dict has token counts for budget accounting.

        Raises:
            ValidationError: if the plan references unknown agents, has cycles, etc.
        """
        manifest = self._registry.manifest()
        manifest_json = json.dumps(manifest, indent=2, default=_json_default)

        system_prompt = PLAN_SYSTEM_PROMPT.format(manifest=manifest_json)
        user_prompt = f"Objective: {objective}"

        try:
            raw, usage = await self._llm.generate_json(system_prompt, user_prompt)
        except Exception:
            # Fallback: only run all agents if registry is small (≤10).
            if len(manifest) > 10:
                raise RuntimeError(
                    f"Planning failed — too many agents ({len(manifest)}) to run without a plan. "
                    "Please check your LLM API key configuration "
                    "(ANTHROPIC_API_KEY, OPENAI_API_KEY, or GEMINI_API_KEY)."
                )
            steps = [PlanStep(agent=e["name"], inputs={}, depends_on=[]) for e in manifest]
            return Plan(
                thread_id="",
                rationale="LLM planning failed, running all agents.",
                steps=steps,
            ), {}

        if not isinstance(raw, dict):
            if len(manifest) > 10:
                raise RuntimeError(
                    f"Planning failed (LLM returned invalid response) — too many agents "
                    f"({len(manifest)}) to run without a plan. "
                    "Please check your LLM API key configuration "
                    "(ANTHROPIC_API_KEY, OPENAI_API_KEY, or GEMINI_API_KEY)."
                )
            steps = [PlanStep(agent=e["name"], inputs={}, depends_on=[]) for e in manifest]
            return Plan(
                thread_id="",
                rationale="LLM returned non-dict, running all agents.",
                steps=steps,
            ), {}

        known_agents: set[str] = {entry["name"] for entry in manifest}

        # Build and validate steps
        valid_steps: list[PlanStep] = []
        seen_agents: set[str] = set()
        for step_data in raw.get("steps", []):
            agent_name = step_data.get("agent", "")
            if agent_name not in known_agents:
                continue
            if agent_name in seen_agents:
                continue
            seen_agents.add(agent_name)
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

        # Strict validation — raises ValidationError on any issue
        _validate_plan(valid_steps, self._registry)

        return Plan(
            thread_id="",
            rationale=raw.get("rationale", ""),
            steps=valid_steps,
        ), usage

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    async def evaluate(self, objective: str, outputs: dict[str, Any]) -> EvalDecision:
        """Ask the LLM to evaluate *outputs* and decide to finalize or pivot.

        Returns EvalDecision with usage info for budget tracking.
        """
        try:
            outputs_json = json.dumps(outputs, indent=2, default=str)
        except Exception:
            outputs_json = str(outputs)[:5000]

        system_prompt = EVAL_SYSTEM_PROMPT.format(
            objective=objective,
            outputs=outputs_json,
        )
        user_prompt = "Evaluate the outputs and decide: finalize or pivot."

        try:
            raw, usage = await self._llm.generate_json(system_prompt, user_prompt)
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

        # Parse sections
        raw_sections = raw.get("sections", [])
        if not isinstance(raw_sections, list):
            raw_sections = []
        sections = []
        for s in raw_sections:
            if isinstance(s, dict):
                sections.append({
                    "title": str(s.get("title", "")),
                    "content": str(s.get("content", "")),
                    "key_facts": [str(f) for f in s.get("key_facts", []) if f]
                    if isinstance(s.get("key_facts"), list) else [],
                })
            elif isinstance(s, str):
                sections.append({"title": "", "content": s, "key_facts": []})

        # Sanitize recommendations
        raw_recs = raw.get("recommendations", [])
        if not isinstance(raw_recs, list):
            raw_recs = [str(raw_recs)] if raw_recs else []
        recommendations = [str(r) for r in raw_recs]

        # Legacy findings compat
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
            usage=usage,
        )
