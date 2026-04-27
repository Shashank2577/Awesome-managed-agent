"""Pathfinder — resolves ambiguous resource names."""
import json
from atrium import Agent
from atrium.examples.observe.tools import list_resources
from atrium.engine.llm import LLMClient

INSTRUCTIONS = """You are a Discovery Specialist. Resolve vague or misspelled resource names.
Compare the target against actual namespaces and pods. Find the closest match.
Return JSON: {"resolved_target": {"namespace": "string", "confidence_score": 0-1}, "rationale": "string"}"""


class PathfinderAgent(Agent):
    name = "pathfinder"
    description = "Resolves ambiguous or misspelled Kubernetes resource names by fuzzy-matching against the cluster registry"
    capabilities = ["discovery", "kubernetes", "resource_resolution"]
    input_schema = {"query": str}
    output_schema = {"resolved_target": dict, "rationale": str}

    async def run(self, input_data: dict) -> dict:
        target = input_data.get("query", input_data.get("upstream", {}).get("query", "unknown"))
        await self.say(f"Searching cluster registry for resources matching '{target}'...")

        namespaces = await list_resources("namespace")
        pods = await list_resources("pod")

        llm = LLMClient()
        prompt = (
            f"The user is asking about '{target}'.\n"
            f"Available Namespaces: {json.dumps(namespaces)}\n"
            f"Sample Pods: {json.dumps(pods[:50])}\n\n"
            "Resolve the target. If it's a typo, fix it."
        )
        res = await llm.generate_json(INSTRUCTIONS, prompt)

        resolved = res.get("resolved_target", {}).get("namespace", "unknown")
        rationale = res.get("rationale", "Exact match found.")
        await self.say(f"Resolved target to namespace: {resolved}. {rationale}")

        res["summary"] = f"Resolved '{target}' to '{resolved}'"
        return res
