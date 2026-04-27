"""Mapper — maps service topology."""
import json
from atrium import Agent
from atrium.examples.observe.tools import run_promql
from atrium.engine.llm import LLMClient

INSTRUCTIONS = """You are a Topology Mapper. Build a map of service dependencies.
Provide a 'summary' field describing the service relationships in plain English.
Return JSON with summary and topology data."""


class MapperAgent(Agent):
    name = "mapper"
    description = "Maps service dependencies and topology in a Kubernetes namespace using metrics"
    capabilities = ["topology", "kubernetes", "service_map"]
    output_schema = {"summary": str}

    async def run(self, input_data: dict) -> dict:
        upstream = input_data.get("upstream", {})
        namespace = "default"
        for v in upstream.values():
            if isinstance(v, dict) and "resolved_target" in v:
                namespace = v["resolved_target"].get("namespace", "default")
                break

        await self.say(f"Mapping service dependencies in {namespace}...")

        query = f'sum(rate(http_requests_total{{namespace=~".*{namespace}.*"}}[5m])) by (source_service, destination_service)'
        topology_data = await run_promql(query)

        llm = LLMClient()
        prompt = f"Map topology for '{namespace}':\n{json.dumps(topology_data)}\n\nExplain the service connections."
        res = await llm.generate_json(INSTRUCTIONS, prompt)

        summary = res.get("summary", f"Mapped {namespace} services.")
        await self.say(f"{summary}")
        res["summary"] = summary
        return res
