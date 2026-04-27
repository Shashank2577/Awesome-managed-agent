"""DeepDiver — forensic log correlation."""
import json
import time
from atrium import Agent
from atrium.examples.observe.tools import run_logql
from atrium.engine.llm import LLMClient

INSTRUCTIONS = """You are a Forensic Detective. Find the root cause in logs.
Provide a 'summary' field explaining the most critical log entry found.
Return JSON with summary and root cause analysis."""


class DeepDiverAgent(Agent):
    name = "deep_diver"
    description = "Performs forensic log and trace correlation to find the root cause of service failures"
    capabilities = ["logs", "forensics", "root_cause", "kubernetes"]
    output_schema = {"summary": str}

    async def run(self, input_data: dict) -> dict:
        upstream = input_data.get("upstream", {})
        namespace = "default"
        for v in upstream.values():
            if isinstance(v, dict) and "resolved_target" in v:
                namespace = v["resolved_target"].get("namespace", "default")
                break

        await self.say(f"Searching for exceptions in {namespace} logs...")

        now = int(time.time())
        query = f'{{namespace=~".*{namespace}.*"}} |= "error" or "Exception"'
        logs = await run_logql(query, start=now - 86400, end=now, limit=50)

        if not logs.get("streams"):
            await self.say("No errors found. Checking general service health...")
            logs = await run_logql(f'{{namespace=~".*{namespace}.*"}}', start=now - 3600, end=now, limit=10)

        llm = LLMClient()
        prompt = f"Find root cause for '{namespace}':\n{json.dumps(logs)}\n\nDescribe the results."
        res = await llm.generate_json(INSTRUCTIONS, prompt)

        summary = res.get("summary", "No exceptions found.")
        await self.say(f"Forensic Summary: {summary[:150]}")
        res["summary"] = summary
        return res
