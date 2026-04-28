"""Runtime adapters for the harness layer.

Each runtime adapts an open-source agentic loop so the SandboxRunner
can boot it and the BridgeStream can consume its events.

  * ``open_agent_sdk`` — @shipany/open-agent-sdk (TypeScript, in-process).
    Best general-purpose adapter; supports any OpenAI-compatible model
    via ANTHROPIC_BASE_URL override (works with OpenRouter).

  * ``openclaude`` — OpenClaude. Forked from Claude Code, native
    support for OpenAI/Gemini/DeepSeek/Ollama via OpenAI-compatible
    APIs. Has a gRPC headless mode that the sandbox can use.

  * ``direct_anthropic`` — claude-agent-sdk-python. Native Anthropic
    SDK. Highest fidelity for Claude. Use for internal Taazaa work
    where licensing isn't an issue.

  * ``echo`` — fake runtime. Doesn't call any model. Used in tests and
    for verifying the pipeline plumbing without burning tokens.
"""
