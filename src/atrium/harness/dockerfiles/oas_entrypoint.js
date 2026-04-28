// Open Agent SDK entrypoint — uses @anthropic-ai/sdk to drive Claude.
// Reads first stdin line as objective, streams response, emits claude_code_stream_json events.

const Anthropic = require('@anthropic-ai/sdk');
const readline = require('readline');

function emit(event) {
  process.stdout.write(JSON.stringify(event) + '\n');
}

async function main() {
  const args = process.argv.slice(2);
  let model = 'claude-sonnet-4-6';
  let systemPromptPath = null;
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--model') model = args[++i];
    else if (args[i] === '--system-prompt-file') systemPromptPath = args[++i];
  }

  // Strip provider prefix (e.g. "anthropic:claude-sonnet-4-6" → "claude-sonnet-4-6")
  if (model.includes(':')) model = model.split(':').slice(1).join(':');

  let systemPrompt = 'You are a capable AI assistant. Complete the user objective thoroughly.';
  if (systemPromptPath) {
    try { systemPrompt = require('fs').readFileSync(systemPromptPath, 'utf8'); } catch (_) {}
  }

  const rl = readline.createInterface({ input: process.stdin, terminal: false });
  const objective = await new Promise(resolve => {
    rl.once('line', line => { rl.close(); resolve(line.trim()); });
  });

  const client = new Anthropic.Anthropic();
  emit({ type: 'system', subtype: 'init', model });

  let fullText = '';
  let inputTokens = 0, outputTokens = 0;

  const stream = client.messages.stream({
    model,
    max_tokens: 8192,
    system: systemPrompt,
    messages: [{ role: 'user', content: objective }],
  });

  for await (const event of stream) {
    if (event.type === 'content_block_delta' && event.delta?.type === 'text_delta') {
      fullText += event.delta.text;
    }
  }

  const final = await stream.finalMessage();
  inputTokens = final.usage?.input_tokens || 0;
  outputTokens = final.usage?.output_tokens || 0;

  emit({
    type: 'assistant',
    message: {
      content: [{ type: 'text', text: fullText }],
      usage: { input_tokens: inputTokens, output_tokens: outputTokens },
    },
  });
  emit({ type: 'result', subtype: 'success', result: fullText });
}

main().catch(err => {
  process.stderr.write(String(err) + '\n');
  process.exit(1);
});
