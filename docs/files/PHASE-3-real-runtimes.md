# PHASE 3 — Real Harness Runtimes

**Goal:** plug Open Agent SDK and the direct Anthropic Claude Agent SDK into
the bridge. After this phase, a session can run real Claude with bash/file/web
tools end-to-end. The PLC Direct code-research agent is the canonical example.

**Estimated effort:** 8 days (1 engineer).

**Depends on:** Phase 2.

**Unblocks:** Phase 4.

## 3.1 Files to create or modify

| Action | Path | What |
|--------|------|------|
| MODIFY | `src/atrium/harness/runtimes/open_agent_sdk.py` | Real adapter. |
| MODIFY | `src/atrium/harness/runtimes/direct_anthropic.py` | Real adapter. |
| CREATE | `src/atrium/harness/dockerfiles/open_agent_sdk.Dockerfile` | Image. |
| CREATE | `src/atrium/harness/dockerfiles/oas_entrypoint.js` | Container entrypoint. |
| CREATE | `src/atrium/harness/dockerfiles/anthropic.Dockerfile` | Image. |
| CREATE | `src/atrium/harness/dockerfiles/anthropic_entrypoint.py` | Container entrypoint. |
| MODIFY | `src/atrium/harness/bridge.py` | Add `claude_code_stream_json` translator. |
| MODIFY | `src/atrium/harness/agent.py` | Token-based budget enforcement; pricing lookup. |
| MODIFY | `src/atrium/api/routes/agent_builder.py` | Support `kind: "harness"`. |
| CREATE | `src/atrium/examples/code_research/__init__.py` |  |
| CREATE | `src/atrium/examples/code_research/agent.py` | The example HarnessAgent. |
| CREATE | `src/atrium/examples/code_research/app.py` | Runnable example. |
| CREATE | `tests/test_harness/test_oas_translator.py` |  |
| CREATE | `tests/integration/docker/test_oas_session.py` | Docker-only. |
| CREATE | `tests/integration/docker/test_anthropic_session.py` | Docker-only. |

## 3.2 Translation table — `claude_code_stream_json`

Both real runtimes emit the Claude Code stream-JSON format. The events
seen on stdout look like (one JSON object per line):

| Inner type | Sample payload | Atrium translation |
|------------|----------------|--------------------|
| `system` | `{"subtype":"init","model":"...","tools":[...]}` | dropped (not user-facing) |
| `assistant` with `text` content | `{"message":{"content":[{"type":"text","text":"..."}]}}` | `HARNESS_MESSAGE` `{text}` |
| `assistant` with `thinking` content | `{"message":{"content":[{"type":"thinking","thinking":"..."}]}}` | `HARNESS_THINKING` `{text}` (Phase 3+) |
| `assistant` with `tool_use` content | `{"message":{"content":[{"type":"tool_use","name":"bash","input":{"command":"ls"}}]}}` | `HARNESS_TOOL_CALLED` `{tool, input}` |
| `user` with `tool_result` content | `{"message":{"content":[{"type":"tool_result","content":"..."}]}}` | `HARNESS_TOOL_RESULT` `{tool, output}` |
| `result` | `{"subtype":"success","result":"..."}` | terminal — final message |
| `result` with `subtype:"error_max_turns"` | `{"subtype":"error_max_turns"}` | `SESSION_FAILED` with `error_code:"max_tool_calls_exceeded"` |
| usage in any message | `{"message":{"usage":{"input_tokens":N,"output_tokens":M,...}}}` | `BUDGET_CONSUMED` payload `{tokens_in:N, tokens_out:M, cost_usd}` |

`HARNESS_THINKING` is a new event type added in Phase 3. Payload:
`{text: str}`. Used so the dashboard can render an extended-thinking
panel; the dashboard is updated to render it as collapsed-by-default.

The bridge gains a translator registry indexed by `event_format`:

```python
# template — bridge.py
_TRANSLATORS: dict[str, Callable[[dict], list[AtriumEventDraft]]] = {
    "echo": translate_echo,
    "claude_code_stream_json": translate_claude_code,
}

def _translate(self, event: dict) -> list[AtriumEventDraft]:
    fmt = self._runtime.event_format
    translator = _TRANSLATORS.get(fmt)
    if translator is None:
        raise ValueError(f"no translator for event_format={fmt}")
    return translator(event)
```

`translate_claude_code` is implemented per the table above. For
`assistant` messages with multiple content blocks, the function
returns one draft per block (so a single inner event can become
multiple Atrium events, in order).

## 3.3 `OpenAgentSDKRuntime`

```python
# verbatim
class OpenAgentSDKRuntime:
    name = "open_agent_sdk"
    event_format = "claude_code_stream_json"

    def image_tag(self, registry: str) -> str:
        return f"{registry}/open-agent-sdk:0.1.0"

    def command(self, model: str, system_prompt_path: str | None) -> list[str]:
        argv = ["node", "/app/oas_entrypoint.js", "--stream-json"]
        if system_prompt_path:
            argv += ["--system-prompt-file", system_prompt_path]
        argv += ["--model", model]
        return argv

    def model_endpoint(self, model: str) -> str:
        provider = model.split(":", 1)[0]
        return {
            "anthropic": "https://api.anthropic.com",
            "openai": "https://api.openai.com",
            "gemini": "https://generativelanguage.googleapis.com",
        }.get(provider, "https://openrouter.ai")

    def required_env(self, model: str) -> dict[str, str]:
        provider = model.split(":", 1)[0]
        env_var = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "gemini": "GEMINI_API_KEY",
        }.get(provider, "OPENROUTER_API_KEY")
        return {env_var: env_var}  # name -> name; the secret store fills value
```

## 3.4 OAS Dockerfile

```dockerfile
# verbatim — src/atrium/harness/dockerfiles/open_agent_sdk.Dockerfile
FROM node:22-slim

# Standard tools the harness expects
RUN apt-get update && apt-get install -y --no-install-recommends \
      ripgrep git curl jq ca-certificates && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -u 10001 -m atrium
RUN mkdir -p /workspace /app && chown -R atrium:atrium /workspace /app

WORKDIR /app

# Pin the version. Bump intentionally via PR.
RUN npm install -g @shipany/open-agent-sdk@0.4.2

COPY --chown=atrium:atrium oas_entrypoint.js /app/oas_entrypoint.js

USER atrium
WORKDIR /workspace
ENV NODE_ENV=production

CMD ["node", "/app/oas_entrypoint.js", "--stream-json"]
```

## 3.5 OAS entrypoint

```javascript
// verbatim — src/atrium/harness/dockerfiles/oas_entrypoint.js
// Reads stdin lines (objective + follow-up messages), drives the SDK,
// writes one JSON event per line to stdout. Errors go to stderr.

const { Agent } = require('@shipany/open-agent-sdk');
const fs = require('fs');
const readline = require('readline');

function emit(event) {
  process.stdout.write(JSON.stringify(event) + '\n');
}

async function main() {
  const args = process.argv.slice(2);
  let model = 'anthropic:claude-sonnet-4-6';
  let systemPromptPath = null;
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--model') model = args[++i];
    else if (args[i] === '--system-prompt-file') systemPromptPath = args[++i];
  }

  const systemPrompt = systemPromptPath ? fs.readFileSync(systemPromptPath, 'utf8') : undefined;

  const agent = new Agent({
    model,
    systemPrompt,
    workspace: '/workspace',
    streamEvents: true,
  });

  // First stdin line is the objective.
  const rl = readline.createInterface({ input: process.stdin });
  const lines = rl[Symbol.asyncIterator]();
  const first = await lines.next();
  if (first.done) {
    emit({ type: 'result', subtype: 'error', message: 'no objective' });
    process.exit(1);
  }
  const objective = first.value.trim();

  emit({ type: 'system', subtype: 'init', model });

  for await (const event of agent.run(objective)) {
    emit(event);
    if (event.type === 'result') break;
  }
}

main().catch((err) => {
  emit({ type: 'result', subtype: 'error', message: String(err) });
  process.exit(1);
});
```

If the SDK's actual stream-event shape differs from what's coded here,
the Phase 3 implementer must reconcile: the Atrium-side translator and
the entrypoint emit format MUST agree. The Phase 3 PR includes a
fixture file at `tests/fixtures/oas_stream_sample.jsonl` that's used
to drive `test_oas_translator.py` — capture this file once from a
real OAS run, then assert the translator produces the expected Atrium
events.

## 3.6 `DirectAnthropicRuntime`

```python
# verbatim
class DirectAnthropicRuntime:
    name = "direct_anthropic"
    event_format = "claude_code_stream_json"

    def image_tag(self, registry: str) -> str:
        return f"{registry}/anthropic:0.1.0"

    def command(self, model: str, system_prompt_path: str | None) -> list[str]:
        argv = ["python", "/app/anthropic_entrypoint.py"]
        if system_prompt_path:
            argv += ["--system-prompt-file", system_prompt_path]
        argv += ["--model", model.split(":", 1)[1]]  # strip provider prefix
        return argv

    def model_endpoint(self, model: str) -> str:
        return "https://api.anthropic.com"

    def required_env(self, model: str) -> dict[str, str]:
        return {"ANTHROPIC_API_KEY": "ANTHROPIC_API_KEY"}
```

Dockerfile pins `claude-agent-sdk-python` to a specific tagged version.
Entrypoint reads stdin, drives the SDK's async iterator, prints
JSON-line events to stdout in the same shape as OAS.

## 3.7 Token-based budget in `HarnessAgent`

The bridge already accumulates tokens from `BUDGET_CONSUMED` events.
Phase 3 wires this to `engine/pricing.py:estimate_cost()` and to the
guardrail enforcer:

```python
# template — bridge.py _apply_guardrails
def _apply_guardrails(self, event: dict) -> None:
    usage = self._extract_usage(event)
    if usage:
        self._tokens_in += usage.get("input_tokens", 0)
        self._tokens_out += usage.get("output_tokens", 0)
        cost = estimate_cost(
            self._session.model, self._tokens_in, self._tokens_out,
        )
        try:
            self._guardrails.check_cost(cost)
        except GuardrailViolation:
            asyncio.create_task(self._sandbox.kill())
            raise

    if event.get("type") == "tool_use" or (
        event.get("type") == "assistant"
        and any(
            b.get("type") == "tool_use"
            for b in event.get("message", {}).get("content", [])
        )
    ):
        self._tool_calls += 1
        if self._tool_calls > self._max_tool_calls:
            asyncio.create_task(self._sandbox.kill())
            raise GuardrailViolation(
                f"max_tool_calls {self._max_tool_calls} exceeded",
                {"tool_calls": self._tool_calls},
            )
```

After every BUDGET_CONSUMED, the bridge also emits the running cost in
the payload so the dashboard's budget bar updates live.

## 3.8 Config-driven harness creation

`POST /api/v1/agents/create` already exists for HTTP agents. Extend
`agent_builder.py` to accept `kind: "harness"`:

```json
{
  "kind": "harness",
  "name": "code_research",
  "description": "Investigates a codebase",
  "capabilities": ["bash", "files", "search", "code"],
  "runtime": "open_agent_sdk",
  "model": "anthropic:claude-sonnet-4-6",
  "system_prompt": "...",
  "timeout_seconds": 1800,
  "max_tool_calls": 200
}
```

Stored as a row in `agent_configs` with `kind="harness"`. On startup or
on creation, a dynamic `HarnessAgent` subclass is built (parallel to
the existing `create_agent_class` factory) and registered.

## 3.9 Example: `code_research`

```python
# template — examples/code_research/agent.py
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
```

```python
# template — examples/code_research/app.py
from atrium import Atrium
from atrium.examples.code_research.agent import CodeResearchAgent


app = Atrium(agents=[CodeResearchAgent])

if __name__ == "__main__":
    app.serve()
```

## 3.10 Acceptance tests

### `tests/test_harness/test_oas_translator.py`

Drive the translator with `tests/fixtures/oas_stream_sample.jsonl` —
a recorded transcript from a real OAS session, captured during dev.

```
test_translator_handles_init_message
test_translator_emits_harness_thinking_for_thinking_blocks
test_translator_emits_harness_message_for_text_blocks
test_translator_emits_harness_tool_called_for_tool_use_blocks
test_translator_emits_harness_tool_result_for_tool_result_blocks
test_translator_emits_budget_consumed_with_real_token_counts
test_translator_returns_terminal_for_result_event
test_translator_drops_unknown_event_types_gracefully
test_assistant_message_with_multiple_blocks_emits_one_event_per_block_in_order
```

### `tests/integration/docker/test_oas_session.py` (gated `-m docker`, requires `ANTHROPIC_API_KEY`)

```
test_oas_session_lists_files_and_writes_report
test_oas_session_emits_at_least_one_tool_called_event
test_oas_session_artifact_count_matches_files_written
test_oas_session_token_cost_is_within_provider_invoice_1_percent
test_oas_session_killed_on_max_tool_calls_violation
test_oas_session_killed_on_max_cost_violation
```

### `tests/integration/docker/test_anthropic_session.py`

Same shape, using `DirectAnthropicRuntime`.

## 3.11 Non-goals for Phase 3

- OpenClaude (multi-provider via OpenAI-compatible APIs) — Phase 4.
- Gemini / OpenAI as the actual driving model end-to-end — Phase 4.
- MCP — Phase 4.
- Resume — Phase 5.
- Custom tool injection beyond what the inner SDK provides — out of scope.

## 3.12 Definition of done

- [ ] `pytest tests/test_harness/test_oas_translator.py` passes against
      the captured fixture.
- [ ] `pytest -m docker tests/integration/docker/` passes nightly with
      live Anthropic API.
- [ ] Manual smoke: start the `code_research` example, point it at the
      Atrium repo itself, observe a `report.md` artifact within 5
      minutes, total cost under $0.50 for a small codebase.
- [ ] Manual smoke: same agent with `model_override="anthropic:claude-opus-4-7"`
      runs end-to-end (proves model is configurable).
- [ ] Token cost reported in BUDGET_CONSUMED is within 1% of
      Anthropic's reported usage on the API key for the same window.
- [ ] No `TODO(phase-3)` markers remain.
