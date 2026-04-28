// OpenClaude entrypoint — uses @anthropic-ai/sdk with extended thinking support.
// Reads first stdin line as objective, emits claude_code_stream_json events.

const Anthropic = require('@anthropic-ai/sdk');
const readline = require('readline');

function emit(event) {
  process.stdout.write(JSON.stringify(event) + '\n');
}

async function main() {
  const args = process.argv.slice(2);
  let model = process.env.OPENCLAUDE_MODEL || 'claude-sonnet-4-6';
  let systemPromptPath = null;
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--model') model = args[++i];
    else if (args[i] === '--system-prompt-file') systemPromptPath = args[++i];
  }

  if (model.includes(':')) model = model.split(':').slice(1).join(':');

  let systemPrompt = 'You are a capable AI assistant. Reason carefully and complete the objective.';
  if (systemPromptPath) {
    try { systemPrompt = require('fs').readFileSync(systemPromptPath, 'utf8'); } catch (_) {}
  }

  const rl = readline.createInterface({ input: process.stdin, terminal: false });
  const objective = await new Promise(resolve => {
    rl.once('line', line => { rl.close(); resolve(line.trim()); });
  });

  const client = new Anthropic.Anthropic();
  emit({ type: 'system', subtype: 'init', model });

  let fullText = '', thinkingText = '';
  let inputTokens = 0, outputTokens = 0;

  const stream = client.messages.stream({
    model,
    max_tokens: 16000,
    thinking: { type: 'enabled', budget_tokens: 8000 },
    system: systemPrompt,
    messages: [{ role: 'user', content: objective }],
  });

  for await (const event of stream) {
    if (event.type === 'content_block_delta') {
      if (event.delta?.type === 'thinking_delta') thinkingText += event.delta.thinking;
      else if (event.delta?.type === 'text_delta') fullText += event.delta.text;
    }
  }

  const final = await stream.finalMessage();
  inputTokens = final.usage?.input_tokens || 0;
  outputTokens = final.usage?.output_tokens || 0;

  const content = [];
  if (thinkingText) content.push({ type: 'thinking', thinking: thinkingText });
  content.push({ type: 'text', text: fullText });

  emit({
    type: 'assistant',
    message: { content, usage: { input_tokens: inputTokens, output_tokens: outputTokens } },
  });
  emit({ type: 'result', subtype: 'success', result: fullText });
}

main().catch(err => {
  process.stderr.write(String(err) + '\n');
  process.exit(1);
});
