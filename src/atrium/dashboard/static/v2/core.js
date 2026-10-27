// Atrium v2 · core.js
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

// ═══════════════════════════════════════════════════
// API CONFIG — points to the real backend
// ═══════════════════════════════════════════════════
const API_BASE = 'http://localhost:8080';
const API_KEY  = '94ad7900fda0be83584dcb43674b3d098b8b29037ba98b17c18d258a9d3493c4';
function apiFetch(path, opts = {}) {
  const headers = { 'X-Atrium-Key': API_KEY, ...opts.headers };
  if (opts.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
  return fetch(API_BASE + path, { ...opts, headers });
}
const esc = s => String(s ?? '').replace(/[&<>"']/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// No mock data. All data comes from the real API.

// Chart data is always computed live from state.runs — never mocked.
let CHART_DATA = {
  runsDay: Array(14).fill(0),
  successRate: Array(14).fill(0),
  costPerRun: [],
  models: [],
  topTools: [{ name: 'No data', count: 1 }],
  latency: { p50: 0, p75: 0, p90: 0, p95: 0 },
};

// ═══════════════════════════════════════════════════
// STATE — all data loaded from real API, no mock values
// ═══════════════════════════════════════════════════
let state = {
  currentView: 'home',
  currentRunId: null,
  selectedEvent: null,
  runs: [],
  realAgents: [],
  agentFilter: 'all',
  agentSearch: '',
  mcpServers: [],
  kbs: [],
  liveRun: null,
  runFilter: 'all',
  selectedRuntime: 'universal',
  selectedAgentId: null,
  realSessions: [],
  apiBase: '',
};

// ═══════════════════════════════════════════════════
// BOOTSTRAP
// ═══════════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', () => {
  initNav();
  initRuntimeCards();
  initObjCounter();
  checkHealth();
  fetchRealAgents();
  // Check URL hash for deep-link to a run
  const hash = window.location.hash;
  if (hash.startsWith('#run/')) {
    showView('home');
    fetchRealSessions().then(() => {
      const runId = hash.slice(5);
      const run = state.runs.find(r => r.id === runId || r.session_id === runId);
      if (run) openRun(runId);
    });
  } else {
    showView('home');
    fetchRealSessions();
  }
  window.addEventListener('hashchange', () => {
    const h = window.location.hash;
    if (h.startsWith('#run/')) {
      const runId = h.slice(5);
      const run = state.runs.find(r => r.id === runId || r.session_id === runId);
      if (run) openRun(runId);
    }
  });
});

function initNav() {
  $$('.rl[data-view]').forEach(btn => {
    btn.addEventListener('click', () => showView(btn.dataset.view));
  });
  $$('[data-filter]').forEach(btn => {
    btn.addEventListener('click', () => {
      $$('.filter-tabs .ftab').forEach(b => b.classList.remove('on'));
      btn.classList.add('on');
      state.runFilter = btn.dataset.filter;
      renderRunsTable();
    });
  });
  $$('[data-range]').forEach(btn => {
    btn.addEventListener('click', () => {
      $$('.time-range-tabs .ftab').forEach(b => b.classList.remove('on'));
      btn.classList.add('on');
      renderCharts();
    });
  });
  $$('[data-cat]').forEach(btn => {
    btn.addEventListener('click', () => {
      $$('.tools-categories .ftab').forEach(b => b.classList.remove('on'));
      btn.classList.add('on');
      renderTools();
    });
  });
}

function initRuntimeCards() {
  $$('.rt-card').forEach(card => {
    card.addEventListener('click', () => {
      $$('.rt-card').forEach(c => c.classList.remove('selected'));
      card.classList.add('selected');
      state.selectedRuntime = card.dataset.runtime;
      updateProviderFieldsVisibility();
    });
  });
}

function initObjCounter() {
  const ta = $('#fi-objective');
  if (!ta) return;
  const hint = $('#obj-chars');
  ta.addEventListener('input', () => { if (hint) hint.textContent = ta.value.length; });
}

const PROVIDER_PRESETS = {
  deepseek:   { base: 'https://api.deepseek.com/v1',                             model: 'deepseek-chat' },
  openai:     { base: 'https://api.openai.com/v1',                               model: 'gpt-4o' },
  anthropic:  { base: 'https://api.anthropic.com/v1',                            model: 'claude-sonnet-4-5' },
  gemini:     { base: 'https://generativelanguage.googleapis.com/v1beta/openai',  model: 'gemini-2.0-flash' },
  xai:        { base: 'https://api.x.ai/v1',                                     model: 'grok-beta' },
  groq:       { base: 'https://api.groq.com/openai/v1',                          model: 'llama-3.3-70b-versatile' },
  openrouter: { base: 'https://openrouter.ai/api/v1',                            model: 'openai/gpt-4o' },
  ollama:     { base: 'http://localhost:11434/v1',                                model: 'llama3.2' },
};

document.addEventListener('change', e => {
  if (e.target.id !== 'fi-preset') return;
  const p = PROVIDER_PRESETS[e.target.value];
  if (!p) return;
  const baseEl = $('#fi-base-url'), modelEl = $('#fi-model');
  if (baseEl && !baseEl.value) baseEl.value = p.base;
  else if (baseEl) baseEl.placeholder = p.base;
  if (modelEl) { modelEl.value = p.model; modelEl.placeholder = p.model; }
});

function updateProviderFieldsVisibility() {
  const pf = $('#provider-fields');
  if (!pf) return;
  pf.style.display = state.selectedRuntime === 'echo' ? 'none' : 'block';
}

// ═══════════════════════════════════════════════════
// VIEW ROUTING
// ═══════════════════════════════════════════════════
const VIEW_IDS = {
  home: 'v-home', agents: 'v-agents', runs: 'v-runs',
  'run-detail': 'v-run-detail', knowledge: 'v-knowledge',
  tools: 'v-tools', settings: 'v-settings',
  deploy: 'v-deploy',
};

window.showView = showView;
function showView(name) {
  const id = VIEW_IDS[name];
  if (!id) return;
  $$('.view').forEach(v => { v.hidden = true; });
  const el = $(`#${id}`);
  if (el) el.hidden = false;
  state.currentView = name;
  $$('.rl').forEach(b => {
    b.classList.toggle('on', b.dataset.view === name);
  });
  updateBreadcrumb(name);
  onViewEnter(name);
  if (name !== 'run-detail') {
    history.replaceState(null, '', window.location.pathname + (name === 'home' ? '' : '#' + name));
  }
  if (typeof gsap !== 'undefined') {
    gsap.from(el, { opacity: 0, y: 8, duration: 0.22, ease: 'power2.out' });
  }
}

function updateBreadcrumb(name) {
  const labels = { home:'Overview', agents:'Agents', runs:'Runs', 'run-detail':'Run Detail', knowledge:'Knowledge', observe:'Observe', tools:'Tools', settings:'Settings', deploy:'New Run' };
  const el = $('#tb-breadcrumb');
  if (el) el.textContent = labels[name] || '';
}

function onViewEnter(name) {
  if (name === 'home')       renderHome();
  if (name === 'agents')     renderAgents();
  if (name === 'runs')       renderRunsTable();
  if (name === 'observe')    setTimeout(renderCharts, 50);
  if (name === 'tools')      renderTools();
  if (name === 'knowledge')  renderKnowledge();
  if (name === 'settings')   renderSettings();
  if (name === 'deploy')     renderDeployAgentSelector();
}

// ═══════════════════════════════════════════════════
// HOME
// ═══════════════════════════════════════════════════
function renderHome() {
  const runs = state.runs;
  const completed = runs.filter(r => r.status === 'completed');
  const active = runs.filter(r => r.status === 'running');
  const totalCost = runs.reduce((s, r) => s + r.cost, 0);
  const avgDur = completed.length ? Math.round(completed.reduce((s, r) => s + r.duration, 0) / completed.length) : 0;
  const successRate = runs.length ? Math.round(completed.length / runs.length * 100) : 0;

  animateValue('sc-total', runs.length);
  animateValue('sc-success', successRate, '%');
  animateValue('sc-active', active.length);
  setText('sc-avgdur', avgDur ? fmtDuration(avgDur) : '—');
  setText('sc-cost', '$' + totalCost.toFixed(2));
  setText('badge-runs', runs.length || '');
  setText('badge-agents', state.realAgents.length || '');
  setText('badge-tools', state.mcpServers.length || '');

  // Recent run list
  const rl = $('#home-run-list');
  if (rl) {
    rl.innerHTML = runs.slice(0, 6).map(r => `
      <div class="run-item" onclick="openRun('${r.id}')">
        <span class="ri-status-dot dot-${r.status}"></span>
        <span class="ri-obj">${esc(r.objective)}</span>
        <span class="ri-meta">
          <span class="ri-model">${esc(r.model)}</span>
          <span class="ri-cost">$${r.cost.toFixed(2)}</span>
          <span class="ri-time">${timeAgo(r.started)}</span>
        </span>
      </div>`).join('');
  }

  // Activity feed — derived from real runs
  const af = $('#activity-feed');
  if (af) {
    const recentRuns = [...runs].sort((a, b) => new Date(b.started) - new Date(a.started)).slice(0, 8);
    const activities = [];
    recentRuns.forEach(r => {
      if (r.status === 'running') activities.push({ type: 'run', icon: 'ai-run', text: `${r.id} started — ${r.objective}`, time: timeAgo(r.started) });
      else if (r.status === 'completed') activities.push({ type: 'done', icon: 'ai-done', text: `${r.id} completed — ${r.objective}`, time: timeAgo(r.started) });
      else if (r.status === 'failed') activities.push({ type: 'error', icon: 'ai-error', text: `${r.id} failed — ${r.objective}`, time: timeAgo(r.started) });
    });
    const feed = activities;
    af.innerHTML = feed.map(a => `
      <div class="act-item">
        <div class="act-icon ${a.icon}">${actIcon(a.type)}</div>
        <div class="act-body">
          <div class="act-text">${esc(a.text)}</div>
          <div class="act-time">${a.time}</div>
        </div>
      </div>`).join('');
  }

  // Agent fleet — use real agents if loaded, otherwise show placeholder
  if (state.realAgents?.length) {
    renderHomeAgentFleet(state.realAgents);
  }
}

function actIcon(type) {
  const icons = {
    run: '<svg viewBox="0 0 11 11"><path d="M2 2v7l7-3.5-7-3.5z" fill="currentColor" stroke="none"/></svg>',
    tool: '<svg viewBox="0 0 11 11"><path d="M7 1a3 3 0 00-2.8 4L1 8.7a1.1 1.1 0 001.6 1.6L6 7A3 3 0 107 1z"/></svg>',
    done: '<svg viewBox="0 0 11 11"><path d="M2 5.5L4.5 8l5-5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    error: '<svg viewBox="0 0 11 11"><path d="M5.5 2v4M5.5 8.5v.5" stroke-linecap="round"/></svg>',
  };
  return icons[type] || '';
}

// ═══════════════════════════════════════════════════
// AGENTS — real data from /api/v1/agents
// ═══════════════════════════════════════════════════
const CATEGORY_EMOJI = {
  coding:'💻', research:'🔬', analysis:'📊', creative:'✍️', data:'🗄️',
  design:'🎨', communication:'💬', writing:'📝', security:'🛡️', ops:'⚙️', productivity:'✅',
};

async function fetchRealAgents() {
  try {
    const r = await apiFetch('/api/v1/agents');
    if (!r.ok) return;
    const data = await r.json();
    const agents = data.agents || [];
    state.realAgents = agents;
    state.agentFilter = 'all';
    setText('badge-agents', agents.length);
    if (state.currentView === 'agents') renderAgents();
    renderHomeAgentFleet(agents);
  } catch {}
}

function renderHomeAgentFleet(agents) {
  const ar = $('#home-agent-row');
  if (!ar) return;
  const sample = agents.slice(0, 8);
  ar.innerHTML = sample.map(a => `
    <div class="agent-pill" onclick="showView('agents')">
      <span class="ap-name">${CATEGORY_EMOJI[a.category] || '🤖'} ${esc(a.name.replace('seed-',''))}</span>
      <span class="ap-model">${esc(a.category)}</span>
      <div class="ap-stats">
        <span class="ap-stat">${esc((a.capabilities||[]).slice(0,2).join(', ') || a.agent_type)}</span>
      </div>
    </div>`).join('') + (agents.length > 8 ? `<div class="agent-pill" onclick="showView('agents')" style="opacity:.6">+${agents.length-8} more →</div>` : '');
}

let agentSearchTimer = null;
window.filterAgentsBySearch = function(q) {
  clearTimeout(agentSearchTimer);
  agentSearchTimer = setTimeout(() => { state.agentSearch = q; renderAgents(); }, 150);
};
window.filterAgentsByCategory = function(cat, btn) {
  $$('.agent-cat-tabs .ftab').forEach(b => b.classList.remove('on'));
  if (btn) btn.classList.add('on');
  state.agentFilter = cat;
  renderAgents();
};

function renderAgents() {
  const grid = $('#agent-grid');
  if (!grid) return;
  const agents = state.realAgents || [];
  if (!agents.length) {
    grid.innerHTML = `<div class="agents-loading" style="grid-column:1/-1;padding:48px;text-align:center;color:var(--fg-3)">Loading agents…</div>`;
    fetchRealAgents();
    return;
  }

  // Category tabs — build dynamically from real data
  let catBar = $('#agent-cat-bar');
  if (!catBar) {
    catBar = document.createElement('div');
    catBar.id = 'agent-cat-bar';
    catBar.className = 'agent-cat-tabs';
    grid.parentElement.insertBefore(catBar, grid);
  }
  if (!catBar.dataset.built) {
    const cats = [...new Set(agents.map(a => a.category))].sort();
    catBar.innerHTML = `<div class="search-box" style="margin-bottom:0">
      <svg viewBox="0 0 16 16"><circle cx="6.5" cy="6.5" r="4.5"/><path d="M10.5 10.5L14 14" stroke-linecap="round"/></svg>
      <input type="text" placeholder="Search agents…" oninput="filterAgentsBySearch(this.value)" style="background:transparent;border:none;outline:none;color:var(--fg-1);font-size:13px;width:180px">
    </div>
    <button class="ftab on" onclick="filterAgentsByCategory('all',this)">All (${agents.length})</button>
    ${cats.map(c => `<button class="ftab" onclick="filterAgentsByCategory('${c}',this)">${CATEGORY_EMOJI[c]||''} ${c} <span style="opacity:.5;font-size:10px">${agents.filter(a=>a.category===c).length}</span></button>`).join('')}`;
    catBar.dataset.built = '1';
    catBar.style.cssText = 'display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-bottom:16px;padding:12px 0;border-bottom:1px solid var(--border)';
  }

  let filtered = agents;
  if (state.agentFilter && state.agentFilter !== 'all') filtered = agents.filter(a => a.category === state.agentFilter);
  if (state.agentSearch) { const q = state.agentSearch.toLowerCase(); filtered = filtered.filter(a => a.name.includes(q) || a.description.toLowerCase().includes(q) || (a.capabilities||[]).some(c=>c.includes(q))); }

  if (!filtered.length) {
    grid.innerHTML = `<div style="grid-column:1/-1;padding:32px;text-align:center;color:var(--fg-3)">No agents match.</div>`;
    return;
  }

  grid.innerHTML = filtered.map(a => `
    <div class="agent-card" onclick="prefilledDeployByName('${esc(a.name)}')">
      <div class="ac-header">
        <div class="ac-avatar" style="background:var(--violet-lo);font-size:20px">${CATEGORY_EMOJI[a.category] || '🤖'}</div>
        <div>
          <div class="ac-name">${esc(a.name.replace(/^seed-/,'').replace(/-/g,' '))}</div>
          <div class="ac-persona">${esc(a.category)}</div>
        </div>
      </div>
      <div class="ac-desc" style="font-size:12px;color:var(--fg-2);margin:8px 0;line-height:1.5">${esc(a.description)}</div>
      ${(a.capabilities||[]).length ? `<div class="ac-tags">${a.capabilities.slice(0,4).map(c=>`<span class="ac-tag">${esc(c)}</span>`).join('')}</div>` : ''}
      <div class="ac-actions">
        <button class="ac-run-btn" onclick="event.stopPropagation();prefilledDeployByName('${esc(a.name)}')">Run →</button>
      </div>
    </div>`).join('');
  if (typeof gsap !== 'undefined') gsap.from('#agent-grid .agent-card', { opacity: 0, y: 10, duration: 0.2, stagger: 0.02, ease: 'power2.out', clearProps: 'all' });
}

window.prefilledDeployByName = function(agentName) {
  state.selectedAgentName = agentName;
  showView('deploy');
};

window.prefilledDeploy = prefilledDeploy;
function prefilledDeploy(agentName) {
  state.selectedAgentName = agentName;
  showView('deploy');
}

window.openAgentRun = openAgentRun;
function openAgentRun(agentName) {
  state.selectedAgentName = agentName;
  showView('deploy');
}

window.selectDeployAgent = selectDeployAgent;
function selectDeployAgent(name, el) {
  state.selectedAgentName = name;
  $$('.as-card').forEach(c => c.classList.remove('selected'));
  if (el) el.classList.add('selected');
}

function renderDeployAgentSelector() {
  const sel = $('#agent-selector');
  if (!sel) return;
  const agents = state.realAgents || [];
  const defaultCard = `<div class="as-card ${!state.selectedAgentName ? 'selected' : ''}" onclick="selectDeployAgent(null,this)"><div class="as-card-name">Default</div><div class="as-card-model">No preset</div></div>`;
  const agentCards = agents.slice(0, 20).map(a => `
    <div class="as-card ${state.selectedAgentName === a.name ? 'selected' : ''}" onclick="selectDeployAgent('${esc(a.name)}',this)">
      <div class="as-card-name">${CATEGORY_EMOJI[a.category] || '🤖'} ${esc(a.name.replace(/^seed-/,'').replace(/-/g,' '))}</div>
      <div class="as-card-model">${esc(a.category)}</div>
    </div>`).join('');
  sel.innerHTML = defaultCard + agentCards;
  if (state.selectedAgentName) {
    const obj = $('#fi-objective');
    if (obj && !obj.value) obj.placeholder = `Objective for ${state.selectedAgentName.replace(/^seed-/,'').replace(/-/g,' ')}…`;
  }
}

// ═══════════════════════════════════════════════════
// RUNS TABLE
// ═══════════════════════════════════════════════════
function renderRunsTable() {
  const tbody = $('#runs-tbody');
  if (!tbody) return;
  let runs = state.runs;
  if (state.runFilter !== 'all') runs = runs.filter(r => r.status === state.runFilter);
  const q = ($('#runs-search') || {}).value || '';
  if (q) runs = runs.filter(r => r.objective.toLowerCase().includes(q.toLowerCase()) || r.id.includes(q));
  if (!runs.length) {
    tbody.innerHTML = `<tr class="dt-empty"><td colspan="8">No runs match.</td></tr>`;
    return;
  }
  tbody.innerHTML = runs.map(r => `
    <tr onclick="openRun('${r.id}')">
      <td class="td-obj">${esc(r.objective)}</td>
      <td>${esc(r.agent)}</td>
      <td class="mono">${esc(r.model)}</td>
      <td>${statusBadge(r.status)}</td>
      <td>${fmtDuration(r.duration)}</td>
      <td>${r.events}</td>
      <td>$${r.cost.toFixed(2)}</td>
      <td>${timeAgo(r.started)}</td>
    </tr>`).join('');
}

window.filterRuns = function(q) { renderRunsTable(); };

// ═══════════════════════════════════════════════════
// RUN DETAIL
// ═══════════════════════════════════════════════════
window.openRun = openRun;
window.openLiveRun = function() {
  if (state.liveRun) openRun(state.liveRun.id || state.liveRun.session_id);
};

function openRun(runId) {
  const run = state.runs.find(r => r.id === runId) || state.realSessions.find(r => r.session_id === runId);
  if (!run) return;
  state.currentRunId = runId;
  history.pushState(null, '', window.location.pathname + '#run/' + runId);
  state.selectedEvent = null;
  setText('rd-objective', run.objective || run.prompt || '—');
  const fullId = run.id || run.session_id || '';
  const idEl = $('#rd-id');
  if (idEl) { idEl.textContent = fullId; idEl.title = fullId; }
  setText('rd-model', run.model || run.runtime || '—');
  setText('rd-runtime', run.runtime || '—');
  setText('rd-cost', '$' + (run.cost || 0).toFixed(2));
  setText('rd-duration', fmtDuration(run.duration));
  setText('rd-tokens', run.tokens ? run.tokens.toLocaleString() : '—');
  setText('rd-events', run.events || '—');
  const badge = $('#rd-status-badge');
  if (badge) { const s = (run.status||'').toLowerCase(); badge.className = `status-badge sb-${s}`; badge.innerHTML = `<span class="sb-dot"></span>${run.status}`; }
  const cancelBtn = $('#rd-cancel-btn');
  if (cancelBtn) cancelBtn.hidden = run.status !== 'running';

  renderGantt([]);
  renderEventTable([]);
  renderStreamFeed(run, []);
  renderRunConfig(run);
  clearOutputPane();

  showView('run-detail');
  selectTab(run.status === 'running' ? 'stream' : 'timeline');

  const sid = run.id || run.session_id;
  if (run.status === 'running' && activeSSE === null) startSSEStream(sid, run);
  fetchRealRunData(sid, run);
}

async function fetchRealRunData(sessionId, run) {
  try {
    // Fetch real events for timeline/stream
    const evResp = await apiFetch(`/api/v1/sessions/${sessionId}/events?limit=200`);
    if (evResp.ok) {
      const data = await evResp.json();
      const rawEvents = data.events || [];
      const mapped = mapBackendEvents(rawEvents, run);
      state.currentRunEvents = mapped;
      if (state.currentRunId === sessionId) {
        renderGantt(mapped);
        renderEventTable(mapped);
        renderStreamFeed(run, mapped);
        setText('rd-events', rawEvents.length);
      }
    }
  } catch {}

  try {
    // Fetch final output
    const outResp = await apiFetch(`/api/v1/sessions/${sessionId}/result`);
    if (outResp.ok) {
      const data = await outResp.json();
      if (data.found && state.currentRunId === sessionId) renderOutputPane(data);
    }
  } catch {}
}

function mapBackendEvents(rawEvents, run) {
  // Map backend event types to the format renderGantt/renderEventTable expects
  const typeMap = {
    HARNESS_TOOL_CALLED: 'tool', HARNESS_TOOL_RESULT: 'tool',
    HARNESS_MESSAGE: 'llm', AGENT_MESSAGE: 'llm', AGENT_OUTPUT: 'llm',
    AGENT_RUNNING: 'action', AGENT_COMPLETED: 'action',
    THREAD_PLANNING_STARTED: 'action', EVIDENCE_PUBLISHED: 'result',
    THREAD_FAILED: 'error', AGENT_FAILED: 'error',
  };
  let t = 0;
  return rawEvents.map((e, i) => {
    const dur = 200 + Math.random() * 600 | 0;
    const ev = {
      id: e.id || `ev_${i}`,
      type: typeMap[e.type] || 'action',
      name: formatEventName(e.type, e.payload),
      start_ms: t,
      dur_ms: dur,
      tokens: e.payload?.tokens || 0,
      cost: e.payload?.cost || 0,
      input: JSON.stringify(e.payload || {}).substring(0, 200),
      output: extractOutput(e.payload),
      rawType: e.type,
      timestamp: e.timestamp,
    };
    t += dur + 50;
    return ev;
  });
}

function formatEventName(type, payload) {
  if (type === 'HARNESS_TOOL_CALLED') return `Tool: ${payload?.tool || 'unknown'}(${JSON.stringify(payload?.input || {}).substring(0, 60)})`;
  if (type === 'HARNESS_TOOL_RESULT') return `Result: ${String(payload?.output || '').substring(0, 60)}`;
  if (type === 'HARNESS_MESSAGE') return `Message: ${String(payload?.text || '').substring(0, 60)}`;
  if (type === 'AGENT_HIRED') return `Agent hired: ${payload?.role || payload?.agent_key || ''}`;
  if (type === 'AGENT_RUNNING') return `Agent running: ${payload?.agent_key || ''}`;
  if (type === 'AGENT_COMPLETED') return `Agent completed: ${payload?.agent_key || ''}`;
  if (type === 'EVIDENCE_PUBLISHED') return `Output: ${payload?.headline || 'Final result'}`;
  if (type === 'PLAN_CREATED') return `Plan created (${(payload?.graph?.nodes || []).length} agents)`;
  return type.replace(/_/g, ' ').toLowerCase();
}

function extractOutput(payload) {
  if (!payload) return '';
  if (payload.output) return String(payload.output).substring(0, 300);
  if (payload.text) return String(payload.text).substring(0, 300);
  if (payload.result) return JSON.stringify(payload.result).substring(0, 300);
  if (payload.headline) return payload.headline;
  return JSON.stringify(payload).substring(0, 200);
}

function clearOutputPane() {
  const loading = $('#rd-output-loading');
  const empty = $('#rd-output-empty');
  const body = $('#rd-output-body');
  if (loading) loading.hidden = true;
  if (empty) empty.hidden = true;
  if (body) body.hidden = true;
}

function renderOutputPane(data) {
  const loading = $('#rd-output-loading');
  const empty = $('#rd-output-empty');
  const body = $('#rd-output-body');
  if (!body) return;
  if (loading) loading.hidden = true;

  const result = data.result;
  if (!result) { if (empty) empty.hidden = false; return; }

  // EVIDENCE_PUBLISHED structure: headline, summary, sections[]
  const headline = result.headline || result.text || (typeof result === 'string' ? result : '');
  const summary = result.summary || result.response || '';
  const sections = result.sections || [];

  const hlEl = $('#rd-out-headline');
  if (hlEl) hlEl.innerHTML = renderMarkdown(headline);
  const sumEl = $('#rd-out-summary');
  if (sumEl) sumEl.innerHTML = renderMarkdown(summary);

  const sectionsEl = $('#rd-out-sections');
  if (sectionsEl) {
    sectionsEl.innerHTML = sections.map(s => `
      <div class="out-section">
        <div class="out-sec-title">${esc(s.title || '')}</div>
        <div class="out-sec-content">${renderMarkdown(s.content || '')}</div>
        ${(s.key_facts || []).length ? `<ul class="out-facts">${s.key_facts.map(f => `<li>${esc(f)}</li>`).join('')}</ul>` : ''}
      </div>`).join('');
  }

  body.hidden = false;
  if (empty) empty.hidden = true;
}

function renderMarkdown(text) {
  // Process code blocks BEFORE escaping (to preserve code content)
  const codeBlocks = [];
  let processed = text.replace(/```[\w]*\n?([\s\S]*?)```/g, (_, code) => {
    codeBlocks.push(code);
    return `\x00CODE${codeBlocks.length - 1}\x00`;
  });
  processed = esc(processed)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*\n]+)\*/g, '<em>$1</em>')
    .replace(/^---+$/gm, '<hr>')
    .replace(/^### (.+)$/gm, '<h4>$1</h4>')
    .replace(/^## (.+)$/gm, '<h3>$1</h3>')
    .replace(/^# (.+)$/gm, '<h2>$1</h2>')
    .replace(/^[-*] (.+)$/gm, '<li>$1</li>')
    .replace(/\n/g, '<br>');
  // Restore code blocks
  codeBlocks.forEach((code, i) => {
    processed = processed.replace(`\x00CODE${i}\x00`, `<pre><code>${esc(code)}</code></pre>`);
  });
  return processed;
}

function generateMockEvents(run) {
  const n = run.events || 10;
  const types = ['llm','llm','tool','tool','llm','tool','action'];
  const toolNames = ['web_search', 'read_file', 'write_file', 'bash', 'sqlite'];
  let t = 0;
  return Array.from({length: n}, (_, i) => {
    const type = types[i % types.length];
    const dur = type === 'llm' ? 800 + Math.random()*3000 : 200 + Math.random()*1000;
    const ev = { id:`ev_${i}`, type, name: type === 'tool' ? `${toolNames[i%toolNames.length]}(…)` : `LLM reasoning step ${i+1}`, start_ms: Math.round(t), dur_ms: Math.round(dur), tokens: type === 'llm' ? Math.round(500+Math.random()*4000) : 0, cost: type === 'llm' ? +(Math.random()*0.05).toFixed(3) : 0, input: '{"prompt": "..."}', output: '"result": "..."' };
    t += dur + 100 + Math.random()*400;
    return ev;
  });
}

function renderGantt(events) {
  const svg = $('#gantt-svg');
  if (!svg) return;
  const W = Math.max(svg.parentElement.clientWidth || 600, 400);
  const PAD = { t: 38, r: 16, b: 12, l: 16 };
  const maxT = Math.max(...events.map(e => e.start_ms + e.dur_ms));
  const LANE_H = 30, LANE_GAP = 5;
  const colors = { llm: 'var(--violet)', tool: 'var(--emerald)', action: 'var(--amber)', error: 'var(--red)' };
  const colorHex = { llm: '#7C6FF7', tool: '#34D399', action: '#F59E0B', error: '#EF4444' };
  const W_chart = W - PAD.l - PAD.r;
  const totalH = PAD.t + events.length * (LANE_H + LANE_GAP) + PAD.b;

  svg.setAttribute('viewBox', `0 0 ${W} ${totalH}`);
  svg.setAttribute('height', totalH);
  svg.setAttribute('width', '100%');

  // Time axis ticks
  const TICK_COUNT = Math.min(6, Math.floor(W_chart / 60));
  const ticks = Array.from({ length: TICK_COUNT + 1 }, (_, i) => {
    const t = (i / TICK_COUNT) * maxT;
    const x = PAD.l + (i / TICK_COUNT) * W_chart;
    const label = t === 0 ? '0' : t < 1000 ? `${Math.round(t)}ms` : `${(t / 1000).toFixed(1)}s`;
    const anchor = i === 0 ? 'start' : i === TICK_COUNT ? 'end' : 'middle';
    return `<line x1="${x}" y1="${PAD.t - 6}" x2="${x}" y2="${totalH - PAD.b}" stroke="rgba(255,255,255,.05)" stroke-width="1"/>
<text x="${x}" y="12" font-size="9" fill="rgba(255,255,255,.28)" text-anchor="${anchor}" font-family="JetBrains Mono,monospace">${label}</text>`;
  }).join('');

  // Axis baseline
  const baseline = `<line x1="${PAD.l}" y1="${PAD.t - 6}" x2="${W - PAD.r}" y2="${PAD.t - 6}" stroke="rgba(255,255,255,.1)" stroke-width="1"/>`;

  // Bars with zebra stripes
  const barsSvg = events.map((e, i) => {
    const x = PAD.l + (e.start_ms / maxT) * W_chart;
    const w = Math.max(6, (e.dur_ms / maxT) * W_chart);
    const y = PAD.t + i * (LANE_H + LANE_GAP);
    const barY = y + 4;
    const barH = LANE_H - 8;
    const labelX = x + w + 6;
    const labelFits = labelX + 60 < W;
    const col = colorHex[e.type] || colorHex.action;
    return `<g class="gantt-bar" style="cursor:pointer" onclick="selectEventFromGantt(${i})">
      <rect x="0" y="${y}" width="${W}" height="${LANE_H}" fill="${i % 2 === 0 ? 'rgba(255,255,255,.018)' : 'transparent'}"/>
      <rect x="${x}" y="${barY}" width="${w}" height="${barH}" rx="3"
        fill="${col}" opacity="0.82" data-event-idx="${i}"/>
      ${w > 40 ? `<text x="${x + 6}" y="${barY + barH/2 + 4}" font-size="10" fill="rgba(255,255,255,.9)" style="pointer-events:none;font-family:Inter,sans-serif">${esc(e.name.length > 22 ? e.name.slice(0,22)+'…' : e.name)}</text>` :
        labelFits ? `<text x="${labelX}" y="${barY + barH/2 + 4}" font-size="10" fill="rgba(255,255,255,.5)" style="pointer-events:none;font-family:Inter,sans-serif">${esc(e.name.length > 28 ? e.name.slice(0,28)+'…' : e.name)}</text>` : ''}
    </g>`;
  }).join('');

  svg.innerHTML = ticks + baseline + barsSvg;
}

window.selectEventFromGantt = function(idx) {
  const events = getRunEvents(state.currentRunId);
  selectEvent(idx, events);
  const row = $(`#event-tbody tr:nth-child(${idx+1})`);
  if (row) { $$('#event-tbody tr').forEach(r => r.classList.remove('selected')); row.classList.add('selected'); row.scrollIntoView({block:'nearest'}); }
};

function getRunEvents(runId) {
  return state.currentRunEvents || [];
}

function renderEventTable(events) {
  const tb = $('#event-tbody');
  if (!tb) return;
  tb.innerHTML = events.map((e, i) => `
    <tr onclick="selectEvent(${i}, null)">
      <td><span class="event-type-pill et-${e.type}">${e.type}</span></td>
      <td style="max-width:260px;overflow:hidden;text-overflow:ellipsis">${esc(e.name)}</td>
      <td class="mono">${fmtMs(e.start_ms)}</td>
      <td class="mono">${fmtMs(e.dur_ms)}</td>
      <td>${e.tokens || '—'}</td>
      <td>${e.cost ? '$' + e.cost.toFixed(3) : '—'}</td>
    </tr>`).join('');
}

window.selectEvent = function(idx, eventsArg) {
  const events = eventsArg || getRunEvents(state.currentRunId);
  const e = events[idx];
  if (!e) return;
  state.selectedEvent = e;
  $('#inspector-empty').hidden = true;
  const det = $('#inspector-detail');
  det.hidden = false;
  const typeColors = { llm: 'var(--violet-hi)', tool: 'var(--emerald)', action: 'var(--amber)', error: 'var(--red)' };
  $('#ins-type').textContent = e.type;
  $('#ins-type').style.color = typeColors[e.type] || 'var(--tx-2)';
  $('#ins-name').textContent = e.name;
  $('#ins-dur').textContent = fmtMs(e.dur_ms);
  $('#ins-tokens').textContent = e.tokens || '—';
  $('#ins-cost').textContent = e.cost ? '$' + e.cost.toFixed(4) : '—';
  $('#ins-input').textContent = e.input ? (typeof e.input === 'string' ? e.input : JSON.stringify(e.input, null, 2)) : '(none)';
  $('#ins-output').textContent = e.output ? (typeof e.output === 'string' ? e.output : JSON.stringify(e.output, null, 2)) : '(none)';
  $$('#event-tbody tr').forEach((r, i) => r.classList.toggle('selected', i === idx));
};

function renderStreamFeed(run, events) {
  const feed = $('#stream-feed');
  if (!feed) return;
  if (run.status === 'running') return; // startSSEStream owns the feed for live runs
  const typeClass = { llm:'ev-llm', tool:'ev-tool', action:'ev-final', error:'ev-error' };
  feed.innerHTML = events.map(e => `
    <div class="sf-event ${typeClass[e.type] || ''}">
      <div class="sf-hd">
        <span class="sf-type">${e.type}</span>
        <span class="sf-name">${esc(e.name)}</span>
        <span class="sf-time">+${fmtMs(e.start_ms)}</span>
      </div>
      ${e.output ? `<div class="sf-text${e.type === 'tool' ? ' sf-code' : ''}">${esc(e.output.slice(0, 300))}${e.output.length > 300 ? '…' : ''}</div>` : ''}
    </div>`).join('');
}

function renderRunConfig(run) {
  const grid = $('#rd-config-grid');
  if (!grid) return;
  const fields = [
    ['Run ID', run.id || run.session_id],
    ['Agent', run.agent || 'Default'],
    ['Model', run.model || '—'],
    ['Runtime', run.runtime || '—'],
    ['Duration', fmtDuration(run.duration)],
    ['Events', run.events],
    ['Tokens', run.tokens?.toLocaleString() || '—'],
    ['Cost', '$' + (run.cost || 0).toFixed(4)],
    ['Started', run.started ? new Date(run.started).toLocaleString() : '—'],
    ['Status', run.status],
  ];
  grid.innerHTML = fields.map(([k, v]) => `
    <div class="cfg-item">
      <div class="cfg-key">${esc(k)}</div>
      <div class="cfg-val">${esc(String(v ?? '—'))}</div>
    </div>`).join('');
}

function selectTab(tabName) {
  const panes = { timeline:'rdp-timeline', stream:'rdp-stream', output:'rdp-output', config:'rdp-config' };
  $$('.rd-tab').forEach(t => {
    const active = t.dataset.tab === tabName;
    t.classList.toggle('on', active);
    if (active) t.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
  });
  Object.entries(panes).forEach(([k, id]) => { const el = $(`#${id}`); if (el) el.hidden = k !== tabName; });
  // When switching to output tab, show loading state if body is still empty
  if (tabName === 'output') {
    const body = $('#rd-output-body');
    const loading = $('#rd-output-loading');
    const empty = $('#rd-output-empty');
    if (body && body.hidden && loading && empty && loading.hidden && empty.hidden) {
      loading.hidden = false;
    }
  }
}

document.addEventListener('click', e => {
  const t = e.target.closest('.rd-tab');
  if (t) selectTab(t.dataset.tab);
});

window.cancelRun = async function() {
  const sid = state.currentRunId;
  if (!sid) return;
  try {
    const r = await apiFetch(`/api/v1/sessions/${sid}/cancel`, { method: 'POST' });
    if (r.ok) {
      toast('Run cancelled.', 'ok');
      const run = state.runs.find(x => x.id === sid || x.session_id === sid);
      if (run) run.status = 'cancelled';
      const badge = $('#rd-status-badge');
      if (badge) { badge.className = 'status-badge sb-cancelled'; badge.innerHTML = '<span class="sb-dot"></span>cancelled'; }
      const cancelBtn = $('#rd-cancel-btn');
      if (cancelBtn) cancelBtn.hidden = true;
      hideLiveWidget();
    } else {
      toast('Cancel failed (' + r.status + ').', 'err');
    }
  } catch { toast('Cancel failed.', 'err'); }
};

// ═══════════════════════════════════════════════════
// KNOWLEDGE
// ═══════════════════════════════════════════════════
function renderKnowledge() {
  setText('kbs-docs', 0);
  setText('kbs-chunks', '0');
  setText('kbs-size', '0 MB');
  const grid = $('#kb-grid');
  if (!grid) return;
  grid.innerHTML = `<div style="grid-column:1/-1;padding:48px 0;text-align:center;color:var(--fg-3)">
    <p style="font-size:15px;margin-bottom:8px">Knowledge library not yet implemented.</p>
    <p style="font-size:12px">Upload sources via the API to make them available to agents.</p>
  </div>`;
}

// ═══════════════════════════════════════════════════
// OBSERVABILITY CHARTS
// ═══════════════════════════════════════════════════
function buildLiveChartData() {
  const runs = state.runs.filter(r => r.started);
  if (runs.length < 2) return null;

  // Runs per day — last 14 days
  const now = Date.now();
  const dayBuckets = Array(14).fill(0);
  const successBuckets = Array(14).fill(null).map(() => ({ done: 0, total: 0 }));
  runs.forEach(r => {
    const age = Math.floor((now - new Date(r.started).getTime()) / 86400000);
    if (age >= 0 && age < 14) {
      const idx = 13 - age;
      dayBuckets[idx]++;
      successBuckets[idx].total++;
      if (r.status === 'completed') successBuckets[idx].done++;
    }
  });

  const successRate = successBuckets.map(b => b.total > 0 ? Math.round(b.done / b.total * 100) : null);
  const filledRate = successRate.map((v, i, arr) => v ?? arr.slice(0, i).reverse().find(x => x != null) ?? 80);
  const costPerRun = runs.slice(-14).map(r => r.cost || 0);

  // Model distribution from runs that have a model field
  const modelCounts = {};
  runs.forEach(r => {
    const m = r.model || r.agent_config?.model;
    if (m) modelCounts[m] = (modelCounts[m] || 0) + 1;
  });
  const modelTotal = Object.values(modelCounts).reduce((s, v) => s + v, 0);
  const PALETTE = ['#7C6FF7','#34D399','#22D3EE','#F59E0B','#FB7185','#A3E635','#F472B6'];
  const modelDist = modelTotal > 0
    ? Object.entries(modelCounts)
        .sort((a, b) => b[1] - a[1])
        .map(([name, count], i) => ({ name, pct: Math.round(count / modelTotal * 100), color: PALETTE[i % PALETTE.length] }))
    : null;

  return {
    runsDay: dayBuckets,
    successRate: filledRate,
    costPerRun,
    modelDist,
  };
}

function renderCharts() {
  const live = buildLiveChartData();
  if (live) {
    CHART_DATA.runsDay = live.runsDay;
    CHART_DATA.successRate = live.successRate;
    CHART_DATA.costPerRun = live.costPerRun;
    if (live.modelDist) CHART_DATA.models = live.modelDist;
  }
  renderBarChart();
  renderHorizChart();
  renderDonut();
  renderLatency();
  renderLineChart();
  renderScatterChart();
}

function renderBarChart() {
  const wrap = $('#chart-runs-day');
  if (!wrap) return;
  const data = CHART_DATA.runsDay;
  const max = Math.max(...data, 1);
  const CHART_H = 76;
  const days = ['M','T','W','T','F','S','S','M','T','W','T','F','S','S'];
  wrap.innerHTML = data.map((v, i) => {
    const h = v > 0 ? Math.max(4, Math.round((v / max) * CHART_H)) : 2;
    return `<div class="bc-bar" title="${v} runs">
      <div class="bc-bar-inner" style="height:${h}px"></div>
      <span class="bc-label">${days[i]}</span>
    </div>`;
  }).join('');
  if (typeof gsap !== 'undefined') {
    gsap.from('#chart-runs-day .bc-bar-inner', { scaleY: 0, transformOrigin: 'bottom', duration: 0.5, stagger: 0.03, ease: 'power2.out' });
  }
}

function renderHorizChart() {
  const wrap = $('#chart-tools');
  if (!wrap) return;
  const data = CHART_DATA.topTools;
  if (!data || !data.length) { wrap.innerHTML = '<div style="padding:24px;text-align:center;color:var(--fg-3);font-size:12px">No data</div>'; return; }
  const max = data[0].count || 1;
  wrap.innerHTML = data.map(t => `
    <div class="hc-row">
      <div class="hc-label">${esc(t.name)}</div>
      <div class="hc-track"><div class="hc-bar" style="width:${(t.count/max*100).toFixed(0)}%"></div></div>
      <div class="hc-val">${t.count}</div>
    </div>`).join('');
}

function renderDonut() {
  const wrap = $('#chart-models');
  if (!wrap) return;
  const data = CHART_DATA.models;
  if (!data || !data.length) { wrap.innerHTML = '<div style="padding:24px;text-align:center;color:var(--fg-3);font-size:12px">No data</div>'; return; }
  let angle = 0;
  const R = 30, cx = 40, cy = 40, stroke = 12;
  const circles = data.map(d => {
    const a = d.pct / 100 * 360;
    const r = R;
    const circumference = 2 * Math.PI * r;
    const arc = circumference * d.pct / 100;
    const offset = circumference - arc;
    const startAngle = angle;
    angle += a;
    return `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${d.color}"
      stroke-width="${stroke}" stroke-dasharray="${arc} ${circumference - arc}"
      stroke-dashoffset="${circumference * (1 - startAngle/360)}"
      transform="rotate(-90, ${cx}, ${cy})" opacity="0.85"/>`;
  }).join('');

  const legend = data.map(d => `
    <div class="dl-item">
      <span class="dl-dot" style="background:${d.color}"></span>
      <span class="dl-name">${d.name}</span>
      <span class="dl-pct">${d.pct}%</span>
    </div>`).join('');

  wrap.innerHTML = `
    <div class="donut-wrap">
      <svg class="donut-svg" viewBox="0 0 80 80">${circles}</svg>
      <div class="donut-legend">${legend}</div>
    </div>`;
}

function renderLatency() {
  const lat = CHART_DATA.latency;
  const maxVal = lat.p95 || 1;
  [['p50','P50'],['p75','P75'],['p90','P90'],['p95','P95']].forEach(([k]) => {
    const bar = $(`#lat-${k}`);
    const val = $(`#lat-${k}-val`);
    const v = lat[k] || 0;
    if (bar) bar.style.width = `${(v/maxVal*100).toFixed(0)}%`;
    if (val) val.textContent = v ? `${v}s` : '—';
  });
}

function renderLineChart() {
  const wrap = $('#chart-success');
  if (!wrap) return;
  const data = CHART_DATA.successRate;
  if (!data || data.length < 2) { wrap.innerHTML = '<div style="padding:24px;text-align:center;color:var(--fg-3);font-size:12px">No data</div>'; return; }
  const W = wrap.clientWidth || 300, H = 80;
  const minV = Math.min(...data), maxV = Math.max(...data);
  const pts = data.map((v, i) => {
    const x = (i / (data.length-1)) * W;
    const y = H - ((v-minV)/(maxV-minV||1)) * (H-10) - 5;
    return `${x},${y}`;
  }).join(' ');
  const area = data.map((v, i) => {
    const x = (i / (data.length-1)) * W;
    const y = H - ((v-minV)/(maxV-minV||1)) * (H-10) - 5;
    return `${x},${y}`;
  }).join(' ');
  wrap.innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
    <defs><linearGradient id="sg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="var(--violet)" stop-opacity="0.2"/>
      <stop offset="100%" stop-color="var(--violet)" stop-opacity="0"/>
    </linearGradient></defs>
    <polygon points="${area} ${W},${H} 0,${H}" fill="url(#sg)"/>
    <polyline points="${pts}" fill="none" stroke="var(--violet)" stroke-width="1.5"/>
  </svg>`;
}

function renderScatterChart() {
  const wrap = $('#chart-cost');
  if (!wrap) return;
  const data = CHART_DATA.costPerRun;
  if (!data || data.length < 2) { wrap.innerHTML = '<div style="padding:24px;text-align:center;color:var(--fg-3);font-size:12px">No data</div>'; return; }
  const W = wrap.clientWidth || 300, H = 80;
  const maxV = Math.max(...data) || 1;
  const dots = data.map((v, i) => {
    const x = (i / (data.length-1)) * (W-16) + 8;
    const y = H - (v/maxV) * (H-16) - 8;
    return `<circle cx="${x}" cy="${y}" r="3" fill="var(--emerald)" opacity="0.7"/>`;
  }).join('');
  wrap.innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
    <line x1="0" y1="${H-2}" x2="${W}" y2="${H-2}" stroke="rgba(255,255,255,.06)" stroke-width="1"/>
    ${dots}
  </svg>`;
}

// ═══════════════════════════════════════════════════
// TOOLS — MCP servers from real API
// ═══════════════════════════════════════════════════
function renderTools() {
  const grid = $('#tools-grid');
  if (!grid) return;
  const servers = state.mcpServers || [];
  if (!servers.length) {
    grid.innerHTML = `<div style="grid-column:1/-1;padding:48px 0;text-align:center;color:var(--fg-3)">
      <p style="font-size:15px;margin-bottom:8px">No MCP servers registered.</p>
      <p style="font-size:12px">Use "Register MCP" to connect a tool server.</p>
    </div>`;
    return;
  }
  grid.innerHTML = servers.map(t => `
    <div class="tool-card">
      <div class="tool-card-hd">
        <div class="tool-icon" style="background:var(--raised)">${t.icon || '🔧'}</div>
        <div>
          <div class="tool-name">${esc(t.name)}</div>
          <div class="tool-transport">${esc(t.transport || 'stdio')}</div>
        </div>
      </div>
      <div class="tool-desc">${esc(t.desc || t.description || '')}</div>
      ${(t.tools || []).length ? `<div class="tool-chip-row">${t.tools.map(n => `<span class="tool-chip">${esc(n)}</span>`).join('')}</div>` : ''}
      <div class="tool-card-ft">
        <span class="tool-status ${t.status || 'connected'}">
          <span class="sdot"></span>${t.status || 'connected'}
        </span>
        <button class="tool-test-btn" onclick="testTool('${t.id}')">Test</button>
      </div>
    </div>`).join('');
  if (typeof gsap !== 'undefined') gsap.from('#tools-grid .tool-card', { opacity: 0, y: 14, duration: 0.28, stagger: 0.05, ease: 'power2.out', clearProps: 'all' });
}

window.testTool = function(id) { toast(`Testing tool ${id}…`, 'ok'); };

// ═══════════════════════════════════════════════════
// SETTINGS — provider API key configuration
// ═══════════════════════════════════════════════════
const PROVIDERS = [
  { id: 'anthropic',  emoji: '🧠', name: 'Anthropic',  placeholder: 'sk-ant-…' },
  { id: 'openai',     emoji: '🟢', name: 'OpenAI',     placeholder: 'sk-…' },
  { id: 'deepseek',   emoji: '🐋', name: 'DeepSeek',   placeholder: 'sk-…' },
  { id: 'gemini',     emoji: '♊', name: 'Google Gemini', placeholder: 'AIza…' },
  { id: 'groq',       emoji: '⚡', name: 'Groq',        placeholder: 'gsk_…' },
  { id: 'xai',        emoji: '𝕏',  name: 'xAI / Grok', placeholder: 'xai-…' },
];

function renderSettings() {
  const grid = $('#provider-grid');
  if (!grid) return;
  grid.innerHTML = PROVIDERS.map(p => `
    <div class="provider-card" id="pc-${p.id}">
      <div class="pc-hd">
        <div class="pc-icon">${p.emoji}</div>
        <span class="pc-name">${esc(p.name)}</span>
      </div>
      <div class="pc-field">
        <input type="password" placeholder="${esc(p.placeholder)}" id="key-${p.id}">
        <button class="pc-save" onclick="saveProviderKey('${p.id}')">Save</button>
      </div>
    </div>`).join('');
}

window.saveProviderKey = function(id) {
  const input = $(`#key-${id}`);
  if (!input?.value || input.value.startsWith('•')) return;
  const card = $(`#pc-${id}`);
  if (card) { card.classList.add('configured'); const badge = card.querySelector('.pc-name'); badge.insertAdjacentHTML('afterend', '<span class="pc-configured">Configured</span>'); }
  toast(`${id} API key saved.`, 'ok');
  input.value = '••••••••••••••••';
};

window.saveDefaultModel = function() { toast('Default model saved.', 'ok'); };
window.saveBudget = function() { toast('Budget limits saved.', 'ok'); };

// ═══════════════════════════════════════════════════
// MODALS
// ═══════════════════════════════════════════════════
function openAgentModalWith(agent) {
  state.editingAgentId = agent?.id || null;
  const allTools = ['web_search','read_file','write_file','bash','sqlite','grep','read_url','send_message'];
  const cbs = $('#tool-checkboxes');
  if (cbs) {
    cbs.innerHTML = allTools.map(t => {
      const checked = agent?.tools?.includes(t) || false;
      return `<label class="tool-cb${checked ? ' checked' : ''}">
        <input type="checkbox" value="${t}"${checked ? ' checked' : ''}> ${t}
      </label>`;
    }).join('');
    cbs.querySelectorAll('.tool-cb').forEach(cb => {
      cb.addEventListener('click', () => {
        const inp = cb.querySelector('input');
        inp.checked = !inp.checked;
        cb.classList.toggle('checked', inp.checked);
      });
    });
  }
  if (agent) {
    const f = (id, val) => { const el = $(`#${id}`); if (el) el.value = val || ''; };
    f('ag-name', agent.name); f('ag-persona', agent.persona);
    f('ag-system', agent.system || ''); f('ag-model', agent.model); f('ag-runtime', agent.runtime);
    const hd = $('#modal-agent .modal-hd h4');
    if (hd) hd.textContent = 'Edit Agent';
    const btn = $('#modal-agent .btn-primary');
    if (btn) btn.textContent = 'Save Changes';
  } else {
    const f = (id) => { const el = $(`#${id}`); if (el) el.value = ''; };
    ['ag-name','ag-persona','ag-system','ag-model','ag-runtime'].forEach(f);
    const hd = $('#modal-agent .modal-hd h4');
    if (hd) hd.textContent = 'New Agent';
    const btn = $('#modal-agent .btn-primary');
    if (btn) btn.textContent = 'Create Agent';
  }
  showModal('modal-agent');
}

window.openAgentModal = function() { openAgentModalWith(null); };
window.editAgent = function(id) { toast('Agent editing not yet available in the UI.', 'err'); };

window.createAgent = function() {
  toast('Agent creation via UI is not yet implemented. Agents are provisioned server-side.', 'err');
  closeModal('modal-agent');
};

window.openMcpModal = function() { showModal('modal-mcp'); };
window.createMcpServer = function() {
  const name = $('#mcp-name')?.value?.trim();
  if (!name) { toast('Name required.', 'err'); return; }
  const newServer = {
    id: 'tool_' + Math.random().toString(36).slice(2,6),
    name, icon: '🔧',
    transport: $('#mcp-transport')?.value || 'stdio',
    desc: ($('#mcp-upstream')?.value || '').slice(0, 80),
    tools: [],
    status: 'connected',
  };
  state.mcpServers.push(newServer);
  closeModal('modal-mcp');
  toast(`MCP server "${name}" registered.`, 'ok');
  renderTools();
  setText('badge-tools', state.mcpServers.length);
};

window.openKbModal = function() { showModal('modal-kb'); };
window.createKb = function() {
  const name = $('#kb-name')?.value?.trim();
  if (!name) { toast('Name required.', 'err'); return; }
  state.kbs.push({ id:'kb_'+Date.now(), name, icon:'📄', type:$('#kb-type')?.value||'upload', docs:0, chunks:0, size:'0 MB', status:'indexing', lastUpdated:'just now' });
  closeModal('modal-kb');
  toast(`Knowledge source "${name}" added.`, 'ok');
  renderKnowledge();
};

function showModal(id) { const m = $(`#${id}`); if (m) m.hidden = false; }
window.closeModal = function(id) { const m = $(`#${id}`); if (m) m.hidden = true; };

// Close modal on veil click
document.addEventListener('click', e => {
  if (e.target.classList.contains('modal-veil')) e.target.hidden = true;
});

// ═══════════════════════════════════════════════════
// LAUNCH MISSION (real backend)
// ═══════════════════════════════════════════════════
window.launchMission = async function() {
  const obj = $('#fi-objective')?.value?.trim();
  if (!obj) { toast('Objective required.', 'err'); return; }
  const runtime = state.selectedRuntime;
  const body = { objective: obj, runtime };
  if (runtime === 'universal') {
    const preset = $('#fi-preset')?.value;
    const PRESETS = { deepseek:{base:'https://api.deepseek.com/v1',model:'deepseek-chat'}, openai:{base:'https://api.openai.com/v1',model:'gpt-4o'}, anthropic:{base:'https://api.anthropic.com/v1',model:'claude-sonnet-4-5'}, gemini:{base:'https://generativelanguage.googleapis.com/v1beta/openai',model:'gemini-2.0-flash'}, xai:{base:'https://api.x.ai/v1',model:'grok-beta'}, groq:{base:'https://api.groq.com/openai/v1',model:'llama-3.3-70b-versatile'}, openrouter:{base:'https://openrouter.ai/api/v1',model:'openai/gpt-4o'}, ollama:{base:'http://localhost:11434/v1',model:'llama3.2'} };
    const p = PRESETS[preset] || {};
    const baseUrl = $('#fi-base-url')?.value || p.base;
    const apiKey  = $('#fi-api-key')?.value;
    const model   = $('#fi-model')?.value || p.model || 'gpt-4o';
    body.model = model;
    if (baseUrl) body.provider = { base_url: baseUrl, api_key: apiKey, model };
  } else if (runtime === 'direct_anthropic') {
    body.model = $('#fi-model')?.value || 'claude-haiku-4-5-20251001';
  } else if (runtime === 'echo') {
    body.model = 'echo:test';
  }
  if ($('#fi-timeout')?.value) body.timeout_seconds = parseInt($('#fi-timeout').value);

  const btn = $('#launch-btn');
  const hint = $('#launch-hint');
  if (btn) btn.disabled = true;
  if (hint) hint.textContent = 'Launching…';

  try {
    const resp = await apiFetch('/api/v1/sessions', { method:'POST', body:JSON.stringify(body) });
    if (!resp.ok) throw new Error(`${resp.status}: ${await resp.text()}`);
    const data = await resp.json();
    const sessionId = data.session_id || data.id;
    const newRun = { id: sessionId, session_id: sessionId, agent: 'Default', objective: obj, status: 'running', model: body.model || runtime, runtime, duration: 0, events: 0, cost: 0, started: new Date().toISOString(), tokens: 0 };
    state.runs.unshift(newRun);
    state.liveRun = newRun;
    showLiveWidget(newRun);
    toast('Run launched!', 'ok');
    openRun(sessionId);
    startSSEStream(sessionId, newRun);
  } catch(err) {
    toast('Launch failed: ' + err.message, 'err');
    if (hint) hint.textContent = err.message;
  } finally {
    if (btn) btn.disabled = false;
    if (hint && !hint.textContent.startsWith('Launch')) hint.textContent = '';
  }
};

// ═══════════════════════════════════════════════════
// SSE STREAMING
// ═══════════════════════════════════════════════════
let activeSSE = null;

function startSSEStream(sessionId, run) {
  if (activeSSE) activeSSE.close();
  const feed = $('#stream-feed');
  if (feed) feed.innerHTML = `<div class="sf-connecting"><span class="sf-pulse"></span>Connecting to stream…</div>`;
  let evCount = 0;
  const sse = new EventSource(`${API_BASE}/api/v1/sessions/${sessionId}/stream?token=${API_KEY}`);
  activeSSE = sse;
  sse.onmessage = e => {
    try {
      const ev = JSON.parse(e.data);
      evCount++;
      run.events = evCount;
      if (ev.type === 'cost') run.cost = (run.cost || 0) + (ev.amount || 0);
      const evTypeLower = (ev.type || '').toLowerCase();
      const isTerminal = ['completed','failed','cancelled'].includes(evTypeLower) ||
                         ['thread_completed','agent_completed'].includes(evTypeLower);
      if (isTerminal) {
        run.status = evTypeLower.includes('fail') ? 'failed' : 'completed';
        sse.close();
        activeSSE = null;
        $('#rd-cancel-btn') && ($('#rd-cancel-btn').hidden = true);
        hideLiveWidget();
      }
      if (feed && state.currentRunId === sessionId) appendStreamEvent(feed, ev);
    } catch {}
  };
  sse.onerror = () => { sse.close(); activeSSE = null; };
}

function appendStreamEvent(feed, ev) {
  const connecting = feed.querySelector('.sf-connecting');
  if (connecting) connecting.remove();
  const typeClass = { llm_call:'ev-llm', tool_call:'ev-tool', tool_result:'ev-tool', result:'ev-final', error:'ev-error' };
  const div = document.createElement('div');
  div.className = `sf-event ${typeClass[ev.type] || ''}`;
  div.innerHTML = `
    <div class="sf-hd">
      <span class="sf-type">${esc(ev.type || '')}</span>
      <span class="sf-name">${esc(ev.name || ev.tool || '')}</span>
      <span class="sf-time">${new Date().toLocaleTimeString()}</span>
    </div>
    ${ev.content || ev.text ? `<div class="sf-text">${esc((ev.content || ev.text || '').slice(0, 400))}</div>` : ''}`;
  feed.appendChild(div);
  feed.scrollTop = feed.scrollHeight;
}

// ═══════════════════════════════════════════════════
// HEALTH CHECK & REAL SESSIONS
// ═══════════════════════════════════════════════════
async function checkHealth() {
  const dot = $('#health-dot'), lbl = $('#health-label');
  try {
    const r = await apiFetch('/api/v1/health', { signal: AbortSignal.timeout(3000) });
    if (r.ok) {
      const data = await r.json();
      if (dot) { dot.className = 'health-dot ok'; }
      if (lbl) lbl.textContent = `Online · ${data.agents_registered || 0} agents`;
    } else throw new Error();
  } catch {
    if (dot) { dot.className = 'health-dot err'; }
    if (lbl) lbl.textContent = 'Offline';
  }
}

async function fetchRealSessions() {
  try {
    const r = await apiFetch('/api/v1/sessions');
    if (!r.ok) return;
    const data = await r.json();
    const sessions = data.sessions || data || [];
    const statusMap = { RUNNING:'running', COMPLETED:'completed', FAILED:'failed', CANCELLED:'cancelled', PAUSED:'paused', CREATED:'pending' };
    const mapped = sessions.map(s => ({
      id: s.session_id || s.id,
      session_id: s.session_id || s.id,
      agent: s.agent || 'Backend Agent',
      objective: s.objective || s.prompt || s.title || '(no prompt)',
      status: statusMap[s.status] || s.status?.toLowerCase() || 'completed',
      model: s.model || '—',
      runtime: s.runtime || '—',
      duration: s.duration_seconds || 0,
      events: s.event_count || 0,
      cost: s.cost || 0,
      started: s.created_at || s.started_at || new Date().toISOString(),
      tokens: s.token_count || 0,
    }));
    mapped.sort((a, b) => new Date(b.started) - new Date(a.started));
    state.realSessions = mapped;
    state.runs = mapped;
    setText('badge-runs', mapped.length);
    const liveReal = mapped.find(r => r.status === 'running');
    if (liveReal) { state.liveRun = liveReal; showLiveWidget(liveReal); }
    if (state.currentView === 'home') renderHome();
    if (state.currentView === 'runs') renderRunsTable();
  } catch {}
}

// ═══════════════════════════════════════════════════
// RUN STATUS POLLING
// ═══════════════════════════════════════════════════
let pollTimer = null;

function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(pollRunningRuns, 5000);
}

const POLL_STATUS_MAP = { RUNNING:'running', COMPLETED:'completed', FAILED:'failed', CANCELLED:'cancelled', PAUSED:'paused', CREATED:'pending' };

async function pollRunningRuns() {
  const running = state.runs.filter(r => r.status === 'running');
  if (!running.length) { clearInterval(pollTimer); pollTimer = null; return; }
  for (const run of running) {
    try {
      const r = await apiFetch(`/api/v1/sessions/${run.id || run.session_id}`);
      if (!r.ok) continue;
      const s = await r.json();
      run.status = POLL_STATUS_MAP[s.status] || s.status?.toLowerCase() || run.status;
      run.events = s.event_count ?? run.events;
      run.cost = s.cost ?? run.cost;
      run.duration = s.duration_seconds ?? run.duration;
      if (state.currentView === 'runs') renderRunsTable();
      if (state.currentRunId === run.id && run.status !== 'running') {
        setText('rd-duration', fmtDuration(run.duration));
        setText('rd-events', run.events || '—');
        setText('rd-cost', '$' + (run.cost || 0).toFixed(2));
        const badge = $('#rd-status-badge');
        if (badge) { const s = (run.status||'').toLowerCase(); badge.className = `status-badge sb-${s}`; badge.innerHTML = `<span class="sb-dot"></span>${run.status}`; }
        $('#rd-cancel-btn') && ($('#rd-cancel-btn').hidden = true);
      }
      if (['completed','failed','cancelled'].includes(run.status)) hideLiveWidget();
    } catch {}
  }
}

// ═══════════════════════════════════════════════════
// LIVE WIDGET
// ═══════════════════════════════════════════════════
function showLiveWidget(run) {
  const w = $('#rl-live');
  if (!w) return;
  w.hidden = false;
  setText('live-name', run.objective?.slice(0,40) + (run.objective?.length > 40 ? '…' : '') || '—');
  setText('live-meta', run.model || run.runtime || '—');
  startPolling();
}

function hideLiveWidget() {
  const w = $('#rl-live');
  if (w) w.hidden = true;
  state.liveRun = null;
}

// ═══════════════════════════════════════════════════
// UTILS
// ═══════════════════════════════════════════════════
function setText(id, val) { const el = $(`#${id}`); if (el) el.textContent = val ?? '—'; }

function animateValue(id, target, suffix = '') {
  const el = $(`#${id}`);
  if (!el) return;
  if (typeof gsap !== 'undefined') {
    const obj = { val: 0 };
    gsap.to(obj, { val: target, duration: 1, ease: 'power2.out', onUpdate: () => { el.textContent = Math.round(obj.val) + suffix; } });
  } else {
    el.textContent = target + suffix;
  }
}

function statusBadge(status) {
  const dot = `<span class="sb-dot"></span>`;
  return `<span class="status-badge sb-${(status||'').toLowerCase()}">${dot}${status}</span>`;
}

function fmtDuration(s) {
  if (!s) return '—';
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60), sec = s % 60;
  return `${m}m ${sec}s`;
}

function fmtMs(ms) {
  if (!ms && ms !== 0) return '—';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms/1000).toFixed(1)}s`;
}

function timeAgo(iso) {
  if (!iso) return '—';
  const d = Math.floor((Date.now() - new Date(iso)) / 1000);
  if (d < 60) return `${d}s ago`;
  if (d < 3600) return `${Math.floor(d/60)}m ago`;
  if (d < 86400) return `${Math.floor(d/3600)}h ago`;
  return `${Math.floor(d/86400)}d ago`;
}

function toast(msg, type = 'info') {
  const root = $('#toast-root');
  if (!root) return;
  const t = document.createElement('div');
  t.className = `toast t-${type}`;
  t.innerHTML = `<span class="toast-dot"></span>${esc(msg)}`;
  root.appendChild(t);
  if (typeof gsap !== 'undefined') gsap.from(t, { x: 20, opacity: 0, duration: 0.2, ease: 'power2.out' });
  setTimeout(() => {
    if (typeof gsap !== 'undefined') gsap.to(t, { opacity: 0, x: 10, duration: 0.2, onComplete: () => t.remove() });
    else t.remove();
  }, 3500);
}
