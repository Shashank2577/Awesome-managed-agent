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

  const checkpointPath = process.env.ATRIUM_CHECKPOINT_PATH;
  let history = undefined;
  let toolCallsSoFar = 0;

  if (checkpointPath && fs.existsSync(checkpointPath)) {
    try {
      const data = fs.readFileSync(checkpointPath, 'utf8');
      const cp = JSON.parse(data);
      history = cp.history;
      toolCallsSoFar = cp.tool_calls_so_far || 0;
    } catch (err) {
      console.error("Failed to load checkpoint:", err);
    }
  }

  const agent = new Agent({
    model,
    systemPrompt,
    workspace: '/workspace',
    streamEvents: true,
    history,
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

    if (event.type === 'tool_use') {
      toolCallsSoFar++;
      if (checkpointPath && toolCallsSoFar % 5 === 0) {
        try {
          const cp = {
            history: agent.getHistory ? agent.getHistory() : [],
            tool_calls_so_far: toolCallsSoFar
          };
          const tmpPath = checkpointPath + '.tmp';
          fs.writeFileSync(tmpPath, JSON.stringify(cp));
          fs.renameSync(tmpPath, checkpointPath);
          emit({
            type: 'checkpoint',
            tokens_so_far: 0,
            tool_calls_so_far: toolCallsSoFar
          });
        } catch (err) {
          console.error("Failed to write checkpoint:", err);
        }
      }
    }

    if (event.type === 'result') break;
  }
}

main().catch((err) => {
  emit({ type: 'result', subtype: 'error', message: String(err) });
  process.exit(1);
});
