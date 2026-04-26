const state = { thread: null, events: [], selectedNode: null };

async function api(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

function renderThreads() {
  const host = document.getElementById('threadList');
  if (!state.thread) return;
  host.innerHTML = `<div class="thread"><strong>${state.thread.thread_id}</strong><br/>Status: ${state.thread.status || 'RUNNING'}<br/>Objective: ${state.thread.command}</div>`;
}

function renderBudget() {
  const el = document.getElementById('budgetPanel');
  const budget = state.thread?.budget;
  if (!budget) return;
  el.innerHTML = `<p><strong>Reserved:</strong> ${budget.currency} ${budget.reserved}</p><p><strong>Consumed:</strong> ${budget.currency} ${budget.consumed}</p>`;
}

function renderTimeline() {
  const filter = document.getElementById('eventFilter').value.trim();
  const list = document.getElementById('timeline');
  const events = state.events.filter((evt) => !filter || evt.type.includes(filter));
  list.innerHTML = events
    .map((evt) => {
      const errorClass = evt.type.includes('FAILED') || evt.type.includes('REJECTED') ? 'error' : '';
      return `<div class="event ${errorClass}"><strong>${evt.payload.sequence} · ${evt.type}</strong> — ${evt.timestamp}<br/><small>${JSON.stringify(evt.payload)}</small></div>`;
    })
    .join('');
}

function renderInspector() {
  const pre = document.getElementById('inspector');
  if (!state.selectedNode || !state.thread?.results[state.selectedNode]) {
    pre.textContent = 'Select a node to inspect.';
    return;
  }
  pre.textContent = JSON.stringify(state.thread.results[state.selectedNode], null, 2);
}

function renderGraph() {
  const svg = document.getElementById('graph');
  const nodes = Object.entries(state.thread?.results || {});
  if (!nodes.length) return;

  const positions = {
    metrics: [80, 60], traces: [80, 130], logs: [80, 200],
    alerts: [420, 130], slo: [750, 130],
  };

  const edges = [
    ['metrics', 'alerts'], ['traces', 'alerts'], ['logs', 'alerts'], ['alerts', 'slo']
  ];

  const edgeSvg = edges.map(([a,b]) => {
    const [x1,y1] = positions[a] || [0,0];
    const [x2,y2] = positions[b] || [0,0];
    return `<line x1="${x1+90}" y1="${y1+15}" x2="${x2}" y2="${y2+15}" stroke="#64748b" stroke-width="2"/>`;
  }).join('');

  const nodeSvg = nodes.map(([key, value]) => {
    const [x,y] = positions[key] || [50,50];
    const fill = value.success ? '#dcfce7' : '#fee2e2';
    return `<g class="node" data-node="${key}"><rect x="${x}" y="${y}" rx="8" ry="8" width="180" height="32" fill="${fill}" stroke="#0f172a"/><text x="${x+10}" y="${y+20}">${key} · ${value.node_type}</text></g>`;
  }).join('');

  svg.innerHTML = edgeSvg + nodeSvg;
  svg.querySelectorAll('.node').forEach((node) => {
    node.addEventListener('click', () => {
      state.selectedNode = node.dataset.node;
      renderInspector();
    });
  });
}

async function setState(statusAction) {
  if (!state.thread) return;
  await api(`/api/v1/threads/${state.thread.thread_id}/${statusAction}`, { method: 'POST' });
  state.thread.status = statusAction === 'resume' ? 'RUNNING' : statusAction.toUpperCase();
  renderThreads();
}

async function submitHumanInput(value) {
  await api(`/api/v1/threads/${state.thread.thread_id}/human_input`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ input: value }),
  });
}

async function load() {
  const threads = await api('/api/v1/threads');
  const threadId = threads.threads[0].thread_id;
  state.thread = await api(`/api/v1/threads/${threadId}`);
  state.events = state.thread.events || [];

  renderThreads();
  renderBudget();
  renderGraph();
  renderInspector();
  renderTimeline();

  document.getElementById('eventFilter').addEventListener('input', renderTimeline);
  document.getElementById('pauseBtn').addEventListener('click', () => setState('pause'));
  document.getElementById('resumeBtn').addEventListener('click', () => setState('resume'));
  document.getElementById('cancelBtn').addEventListener('click', () => setState('cancel'));
  document.getElementById('humanInputForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const value = new FormData(event.target).get('input');
    await submitHumanInput(value);
    event.target.reset();
  });
}

load().catch((err) => {
  document.getElementById('subtitle').textContent = `Failed to load: ${err.message}`;
});
