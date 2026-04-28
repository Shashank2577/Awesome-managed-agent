// src/atrium/harness/dockerfiles/openclaude_entrypoint.js
// Multi-model entrypoint using openclaude package.
// Same JSON-line stdout shape as oas_entrypoint.js.

const { OpenClaude } = require('openclaude');
const fs = require('fs');
const readline = require('readline');

function emit(event) {
  process.stdout.write(JSON.stringify(event) + '\n');
}

async function main() {
  const args = process.argv.slice(2);
  let model = process.env.OPENCLAUDE_MODEL || 'anthropic:claude-sonnet-4-6';
  let systemPromptPath = null;

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--model') model = args[++i];
    else if (args[i] === '--system-prompt-file') systemPromptPath = args[++i];
  }

  const systemPrompt = systemPromptPath
    ? fs.readFileSync(systemPromptPath, 'utf8')
    : undefined;

  // MCP gateway wiring — present if Atrium injected the socket path.
  const mcpSocket = process.env.ATRIUM_MCP_SOCKET;
  const sessionToken = process.env.ATRIUM_SESSION_TOKEN;

  const agentOpts = {
    model,
    systemPrompt,
    workspace: '/workspace',
    streamEvents: true,
  };

  if (mcpSocket && sessionToken) {
    agentOpts.mcpTransport = {
      type: 'unix',
      socketPath: mcpSocket,
      sessionToken,
    };
  }

  const agent = new OpenClaude(agentOpts);

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
