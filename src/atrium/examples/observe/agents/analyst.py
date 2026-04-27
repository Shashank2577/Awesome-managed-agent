"""Analyst — analyzes time-series metrics."""
import json
import time
from atrium import Agent
from atrium.examples.observe.tools import run_promql
from atrium.engine.llm import LLMClient

INSTRUCTIONS = """You are a Time-Series Analyst. Analyze metrics to identify failure patterns.
Provide a 'summary' field with a human-readable explanation.
Return JSON with summary and analysis."""


class AnalystAgent(Agent):
    name = "analyst"
    description = "Analyzes memory and CPU metrics for Kubernetes pods to identify resource exhaustion patterns like sawtooth leaks or sudden spikes"
    capabilities = ["metrics", "analysis", "kubernetes", "time_series"]
    output_schema = {"summary": str}

    async def run(self, input_data: dict) -> dict:
        upstream = input_data.get("upstream", {})
        namespace = "default"
        for v in upstream.values():
            if isinstance(v, dict) and "resolved_target" in v:
                namespace = v["resolved_target"].get("namespace", "default")
                break

        await self.say(f"Analyzing memory consumption for pods in {namespace}...")

        query = f'sum(container_memory_working_set_bytes{{namespace=~".*{namespace}.*"}}) by (pod)'
        metrics = await run_promql(query, start=int(time.time()) - 3600)

        llm = LLMClient()
        prompt = f"Analyze metrics for namespace '{namespace}':\n{json.dumps(metrics)}\n\nProvide a human-readable summary."
        res = await llm.generate_json(INSTRUCTIONS, prompt)

        summary = res.get("summary", "Metrics appear stable.")
        await self.say(f"Analysis: {summary}")
        res["summary"] = summary
        return res
