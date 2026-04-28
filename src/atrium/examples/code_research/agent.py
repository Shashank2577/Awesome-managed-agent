"""CodeResearchAgent — example HarnessAgent for the code_research use-case."""
from atrium.harness import HarnessAgent
from atrium.harness.runtimes.open_agent_sdk import OpenAgentSDKRuntime


class CodeResearchAgent(HarnessAgent):
    name = "code_research"
    description = "Investigates a codebase and produces a report at /workspace/report.md"
    capabilities = ["bash", "files", "search", "code"]
    runtime = OpenAgentSDKRuntime()
    model = "anthropic:claude-sonnet-4-6"
    timeout_seconds = 1800
    max_tool_calls = 150
    system_prompt = """You are a senior engineer investigating a codebase.

Use bash, file reads, and ripgrep to understand the code. When you have
enough understanding, write a structured report to /workspace/report.md
covering:

  * Architecture overview
  * Key entry points
  * Notable patterns or anti-patterns
  * Open questions

Then return briefly summarizing what you wrote.
"""
