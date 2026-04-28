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
