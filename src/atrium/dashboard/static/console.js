// =============================================================
// Atrium · Console  (sessions-first, auth-aware)
// =============================================================

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const escape = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]),
  );

// ---------------------------------------------------------------
// API key management
// ---------------------------------------------------------------

let _apiKey = localStorage.getItem("atrium_api_key") || null;

async function ensureApiKey() {
  if (_apiKey) return _apiKey;
  try {
    const res = await fetch("/api/v1/setup");
    if (res.ok) {
      const data = await res.json();
      _apiKey = data.api_key;
      localStorage.setItem("atrium_api_key", _apiKey);
      if (data.dev) {
        const badge = $("#devModeBadge");
        if (badge) badge.style.display = "";
      }
    }
  } catch (_) { /* non-dev mode or not ready */ }
  return _apiKey;
}

async function api(path, init = {}) {
  const key = await ensureApiKey();
  const res = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(key ? { "X-Atrium-Key": key } : {}),
      ...(init.headers || {}),
    },
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

// ---------------------------------------------------------------
// Runtime selector
// ---------------------------------------------------------------

const RUNTIME_MODELS = {
  echo: "echo:test",
  direct_gemini: "gemini:gemini-2.5-flash",
  direct_anthropic: "anthropic:claude-haiku-4-5-20251001",
  open_agent_sdk: "openai:gpt-4o-mini",
  openclaude: "anthropic:claude-sonnet-4-6",
};

const RUNTIME_HINTS = {
  echo: "No API key needed — simulates a full agent run",
  direct_gemini: "Calls Gemini server-side — requires GEMINI_API_KEY in server env",
  direct_anthropic: "Requires ANTHROPIC_API_KEY in server env",
  open_agent_sdk: "Requires OPENAI_API_KEY + running sandbox",
  openclaude: "Requires ANTHROPIC_API_KEY + running sandbox",
};

function wireRuntimeSelector() {
  const sel = $("#runtimeSelect");
  const hint = $("#runtimeHint");
  if (!sel || !hint) return;
  sel.addEventListener("change", () => {
    hint.textContent = RUNTIME_HINTS[sel.value] || "";
  });
}

// ---------------------------------------------------------------
// ThreadView — per-session render state
// ---------------------------------------------------------------

class ThreadView {
  constructor(sessionId, title, objective) {
    this.sessionId = sessionId;
    this.title = title;
    this.objective = objective;
    this.status = "CREATED";

    this.planId = null;
    this.planNodes = [];
    this.planCardEl = null;

    this.agents = new Map();
    this.evidenceEl = null;
    this.eventBuffer = [];
    this.budget = { consumed: "0.00", limit: "12.00" };
    this.eventSource = null;
    this.transcript = $("#transcript");
    this.feed = $("#eventFeed");
    this.lastSequence = 0;
  }

  appendMessage({ avatarClass, avatarText, who, body, klass = "" }) {
    const wrap = document.createElement("div");
    wrap.className = "msg";
    wrap.innerHTML = `
      <div class="avatar ${avatarClass}">${escape(avatarText)}</div>
      <div class="bubble ${klass}">
        <div class="who"><strong>${escape(who)}</strong></div>
        ${body}
      </div>
    `;
    this.transcript.appendChild(wrap);
    this._scroll();
    return wrap;
  }

  appendCard(html) {
    const wrap = document.createElement("div");
    wrap.className = "msg";
    wrap.innerHTML = `<div class="avatar cmd">A</div><div class="bubble" style="padding:0;background:transparent;border:0;">${html}</div>`;
    this.transcript.appendChild(wrap);
    this._scroll();
    return wrap;
  }

  _scroll() {
    requestAnimationFrame(() => { this.transcript.scrollTop = this.transcript.scrollHeight; });
  }

  pushEventRow(evt) {
    const klass = evt.type?.includes("FAILED") || evt.type?.includes("REJECTED")
      ? "error" : evt.type?.startsWith("PIVOT") ? "pivot" : "";
    const row = document.createElement("div");
    row.className = `event-row ${klass}`;
    row.innerHTML = `<span class="seq mono">#${evt.sequence ?? "?"}</span><span class="type">${escape(evt.type)}</span>`;
    this.feed.appendChild(row);
    this.feed.scrollTop = this.feed.scrollHeight;
  }

  handleEvent(evt) {
    this.lastSequence = Math.max(this.lastSequence, evt.sequence ?? 0);
    this.pushEventRow(evt);

    switch (evt.type) {
      case "SESSION_CREATED":
      case "THREAD_CREATED":
        this._onSessionCreated(evt); break;
      case "BUDGET_RESERVED":
      case "BUDGET_CONSUMED":
        this._onBudget(evt); break;
      case "THREAD_PLANNING_STARTED":
      case "THREAD_PLANNING":
        this._setStatus("PLANNING");
        this._appendCommanderThinking("Planning the work…"); break;
      case "THREAD_PAUSED":
      case "SESSION_PAUSED":
        this._setStatus("PAUSED"); break;
      case "HUMAN_APPROVAL_REQUESTED":
        this._onApprovalRequested(evt); break;
      case "COMMANDER_MESSAGE":
        this._onCommanderMessage(evt); break;
      case "PLAN_CREATED":
        this._onPlanCreated(evt); break;
      case "PLAN_APPROVED":
      case "PLAN_EXECUTION_STARTED":
        break;
      case "THREAD_RUNNING":
      case "SESSION_RUNNING":
        this._setStatus("RUNNING"); break;
      case "AGENT_HIRED":
        this._onAgentHired(evt); break;
      case "AGENT_RUNNING":
        this._onAgentStatus(evt, "RUNNING"); break;
      case "AGENT_COMPLETED":
        this._onAgentStatus(evt, "COMPLETED"); break;
      case "AGENT_FAILED":
        this._onAgentStatus(evt, "FAILED"); break;
      case "AGENT_MESSAGE":
        this._onAgentMessage(evt); break;
      case "AGENT_OUTPUT":
        this._onAgentOutput(evt); break;
      case "PIVOT_REQUESTED":
        this._onPivot(evt); break;
      case "PIVOT_APPLIED":
        break;
      case "EVIDENCE_PUBLISHED":
        this._onEvidence(evt); break;
      case "THREAD_COMPLETED":
      case "SESSION_COMPLETED":
        this._setStatus("COMPLETED"); break;
      case "THREAD_FAILED":
      case "SESSION_FAILED":
        this._setStatus("FAILED"); break;
      case "THREAD_CANCELLED":
      case "SESSION_CANCELLED":
        this._setStatus("CANCELLED"); break;
    }
  }

  _setStatus(status) {
    this.status = status;
    const pill = $("#streamPill");
    pill.classList.toggle("live", status === "RUNNING" || status === "PLANNING");
    pill.lastChild.textContent = ` ${status.toLowerCase()}`;
    const isTerminal = ["COMPLETED", "FAILED", "CANCELLED"].includes(status);
    $("#pauseBtn").disabled = isTerminal || status !== "RUNNING";
    $("#resumeBtn").disabled = status !== "PAUSED";
    $("#cancelBtn").disabled = isTerminal;
    $("#infoStatus").textContent = status.toLowerCase();
    renderSessionList();
  }

  _onSessionCreated(evt) {
    $("#threadTitle").textContent = this.title;
    $("#threadObjective").textContent = this.objective;
    $("#infoSession").textContent = this.sessionId.slice(0, 8);
    this._setStatus("PLANNING");
  }

  _onBudget(evt) {
    const p = evt.payload || {};
    this.budget.consumed = p.consumed ?? this.budget.consumed;
    this.budget.limit = p.hard_limit ?? this.budget.limit;
    const consumed = parseFloat(this.budget.consumed);
    const limit = parseFloat(this.budget.limit);
    const pct = Math.min(100, (consumed / limit) * 100);
    $("#budgetFill").style.width = `${pct}%`;
    $("#budgetConsumed").textContent = `$${consumed.toFixed(2)} consumed`;
    $("#budgetLimit").textContent = `/ $${limit.toFixed(2)}`;
  }

  _appendCommanderThinking(text) {
    this.appendMessage({
      avatarClass: "cmd", avatarText: "C", who: "Commander", klass: "cmd",
      body: `<div class="thinking" aria-label="thinking"><span></span><span></span><span></span></div> <span class="muted">${escape(text)}</span>`,
    });
  }

  _onCommanderMessage(evt) {
    const phase = evt.payload?.phase || "planning";
    const text = evt.payload?.text || "";
    this.appendMessage({
      avatarClass: phase === "pivot" ? "pivot" : "cmd",
      avatarText: phase === "pivot" ? "P" : "C",
      who: phase === "pivot" ? "Commander · pivot" : "Commander",
      klass: phase === "pivot" ? "pivot" : "cmd",
      body: escape(text),
    });
  }

  _onPlanCreated(evt) {
    this.planId = evt.payload.plan_id;
    const nodes = evt.payload.graph?.nodes || [];
    this.planNodes = nodes.map((n) => ({ ...n, status: "PENDING" }));

    const html = `
      <article class="card plan-card">
        <header class="plan-head">
          <div class="row gap-2 center">
            <span class="pill"><span class="dot"></span> Plan ${escape(evt.payload.plan_number ?? 1)}</span>
            <h3>Hiring ${this.planNodes.length} specialist${this.planNodes.length !== 1 ? "s" : ""}</h3>
          </div>
          <span class="muted mono">${escape((evt.payload.plan_id || "").slice(0, 8))}</span>
        </header>
        <div class="plan-body">
          <p class="plan-rationale">${escape(evt.payload.rationale || "")}</p>
          <svg class="plan-graph" viewBox="0 0 600 200" preserveAspectRatio="xMidYMid meet"></svg>
        </div>
      </article>
    `;
    this.planCardEl = this.appendCard(html);
    this._renderPlanGraph();
  }

  _renderPlanGraph() {
    const svg = this.planCardEl?.querySelector(".plan-graph");
    if (!svg) return;
    const W = 600, H = 200;
    const depthOf = (key, seen = new Set()) => {
      if (seen.has(key)) return 0;
      seen.add(key);
      const node = this.planNodes.find((n) => n.key === key);
      if (!node || !node.depends_on?.length) return 0;
      return 1 + Math.max(...node.depends_on.map((d) => depthOf(d, seen)));
    };
    const layers = new Map();
    this.planNodes.forEach((n) => {
      const d = depthOf(n.key);
      if (!layers.has(d)) layers.set(d, []);
      layers.get(d).push(n);
    });
    const depthCount = layers.size || 1;
    const colW = W / depthCount;
    const positions = new Map();
    [...layers.entries()].sort((a, b) => a[0] - b[0]).forEach(([, list], colIdx) => {
      const rowH = H / (list.length + 1);
      list.forEach((n, i) => positions.set(n.key, { x: colIdx * colW + colW / 2, y: rowH * (i + 1) }));
    });
    const edges = this.planNodes.flatMap((n) =>
      (n.depends_on || []).map((dep) => {
        const a = positions.get(dep), b = positions.get(n.key);
        if (!a || !b) return "";
        const cx = (a.x + b.x) / 2;
        return `<path class="edge" d="M ${a.x + 60} ${a.y} C ${cx} ${a.y}, ${cx} ${b.y}, ${b.x - 60} ${b.y}" />`;
      })
    ).join("");
    const rects = this.planNodes.map((n) => {
      const p = positions.get(n.key);
      if (!p) return "";
      return `<g transform="translate(${p.x - 60} ${p.y - 16})" data-key="${escape(n.key)}">
        <rect class="node-rect ${n.status}" x="0" y="0" width="120" height="32" />
        <text x="60" y="20" text-anchor="middle">${escape(n.key)}</text>
      </g>`;
    }).join("");
    svg.innerHTML = `${edges}${rects}`;
  }

  _setNodeStatus(key, status) {
    const node = this.planNodes.find((n) => n.key === key);
    if (node) node.status = status;
    const rect = this.planCardEl?.querySelector(`g[data-key="${CSS.escape(key)}"] rect`);
    if (rect) { rect.classList.remove("PENDING", "RUNNING", "COMPLETED", "FAILED"); rect.classList.add(status); }
  }

  _onAgentHired(evt) {
    const ak = evt.payload.agent_key;
    if (this.agents.has(ak)) return;
    const role = evt.payload.role || "";
    const objective = evt.payload.objective || "";
    const monogram = ak.slice(0, 2).toUpperCase();
    const html = `
      <article class="card agent-card" data-agent="${escape(ak)}">
        <header class="agent-head">
          <div class="left">
            <div class="avatar" style="width:28px;height:28px;border-radius:8px;font-size:11px;">${escape(monogram)}</div>
            <div class="col" style="min-width:0;">
              <div class="agent-name">${escape(ak)} <span class="agent-role">· ${escape(role)}</span></div>
              <div class="muted" style="font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escape(objective)}</div>
            </div>
          </div>
          <div class="agent-status">
            <span class="pill" data-pill><span class="dot"></span> hired</span>
            <span class="chev">›</span>
          </div>
        </header>
        <div class="agent-body">
          <div class="inner">
            <ul class="agent-thoughts" data-thoughts></ul>
            <div class="agent-output" data-output hidden></div>
          </div>
        </div>
      </article>`;
    const cardWrap = this.appendCard(html);
    const cardEl = cardWrap.querySelector(".agent-card");
    cardEl.querySelector(".agent-head").addEventListener("click", () => cardEl.classList.toggle("open"));
    if (this.agents.size < 3) cardEl.classList.add("open");
    this.agents.set(ak, {
      role, objective, cardEl,
      statusPill: cardEl.querySelector("[data-pill]"),
      thoughtsList: cardEl.querySelector("[data-thoughts]"),
      outputEl: cardEl.querySelector("[data-output]"),
    });
    if (!this.planNodes.find((n) => n.key === ak)) {
      this.planNodes.push({ key: ak, role, objective, depends_on: evt.payload.depends_on || [], status: "PENDING" });
      this._renderPlanGraph();
    }
  }

  _onAgentStatus(evt, status) {
    const ak = evt.payload.agent_key;
    const a = this.agents.get(ak);
    this._setNodeStatus(ak, status);
    if (!a) return;
    const pillTextMap = { RUNNING: "running", COMPLETED: "done", FAILED: "failed" };
    const klass = status === "FAILED" ? "pivot" : status === "RUNNING" ? "live" : "";
    a.statusPill.className = `pill ${klass}`;
    a.statusPill.innerHTML = `<span class="dot"></span> ${pillTextMap[status] || status.toLowerCase()}`;
  }

  _onAgentMessage(evt) {
    const a = this.agents.get(evt.payload.agent_key);
    if (!a) return;
    const li = document.createElement("li");
    li.className = "agent-thought";
    li.textContent = evt.payload.text || "";
    a.thoughtsList.appendChild(li);
  }

  _onAgentOutput(evt) {
    const a = this.agents.get(evt.payload.agent_key);
    if (!a) return;
    a.outputEl.hidden = false;
    a.outputEl.textContent = JSON.stringify(evt.payload.output ?? {}, null, 2);
  }

  _onPivot(evt) {
    this.appendCard(`
      <div class="pivot-ribbon">
        <div class="avatar pivot" style="width:28px;height:28px;border-radius:8px;font-size:11px;">↻</div>
        <div>
          <div class="label">Pivot requested</div>
          <div>${escape(evt.payload.rationale || "")}</div>
          <div class="muted mono" style="font-size:11px;margin-top:6px;">trigger · ${escape(evt.payload.trigger_agent || "")}</div>
        </div>
      </div>`);
  }

  _onApprovalRequested(evt) {
    const p = evt.payload || {};
    this.appendCard(`
      <div class="pivot-ribbon">
        <div class="avatar pivot" style="width:28px;height:28px;border-radius:8px;font-size:11px;">?</div>
        <div>
          <div class="label">Approval required</div>
          <div>${escape(p.message || "Review the plan and approve or reject.")}</div>
          <div style="margin-top:8px;display:flex;gap:8px;">
            <button class="btn primary small" onclick="controlAction('approve')">Approve</button>
            <button class="btn ghost small" onclick="controlAction('reject')">Reject</button>
          </div>
        </div>
      </div>`);
  }

  _onEvidence(evt) {
    const p = evt.payload || {};
    const sectionsHtml = (p.sections || []).map((s) => {
      const factsHtml = (s.key_facts || []).map((f) => `<li>${escape(f)}</li>`).join("");
      return `<div class="evidence-section">
        ${s.title ? `<h4 class="section-title">${escape(s.title)}</h4>` : ""}
        ${s.content ? `<p class="section-content">${escape(s.content)}</p>` : ""}
        ${factsHtml ? `<ul class="key-facts">${factsHtml}</ul>` : ""}
      </div>`;
    }).join("");
    const recsHtml = (p.recommendations || []).map((r) => `<div class="rec">→ ${escape(r)}</div>`).join("");
    let findingsHtml = "";
    if (!p.sections?.length && p.findings?.length) {
      findingsHtml = `<div class="findings">${(p.findings || []).map((f) =>
        `<div class="finding severity-${escape(f.severity || "low")}"><span class="mono">${escape((f.severity || "low").toUpperCase())}</span><span>${escape(f.text || "")}</span></div>`
      ).join("")}</div>`;
    }
    const chartHtml = p.chart ? `<div class="chart-host"><div class="chart-title">${escape(p.chart.title || "")}</div>${renderChart(p.chart)}</div>` : "";
    this.evidenceEl = this.appendCard(`
      <div class="evidence">
        <span class="pill"><span class="dot"></span> Report ready</span>
        <div class="headline">${escape(p.headline || "Analysis Complete")}</div>
        <div class="summary">${escape(p.summary || "")}</div>
        ${sectionsHtml ? `<div class="evidence-sections">${sectionsHtml}</div>` : ""}
        ${chartHtml}${findingsHtml}
        ${recsHtml ? `<div class="recs">${recsHtml}</div>` : ""}
      </div>`);
  }

  // SSE wiring — uses ?token= because EventSource can't send custom headers
  startStream() {
    if (this.eventSource) this.eventSource.close();
    const token = _apiKey ? `?token=${encodeURIComponent(_apiKey)}` : "";
    const es = new EventSource(`/api/v1/sessions/${this.sessionId}/stream${token}`);
    es.onmessage = (msg) => {
      try { this.handleEvent(JSON.parse(msg.data)); } catch (err) { console.error("bad event", err); }
    };
    [
      "SESSION_CREATED","SESSION_RUNNING","SESSION_PAUSED","SESSION_COMPLETED","SESSION_FAILED","SESSION_CANCELLED","SESSION_RESUMED",
      "THREAD_CREATED","THREAD_PLANNING","THREAD_PLANNING_STARTED","THREAD_RUNNING",
      "THREAD_COMPLETED","THREAD_FAILED","THREAD_CANCELLED","THREAD_PAUSED",
      "BUDGET_RESERVED","BUDGET_CONSUMED","BUDGET_EXCEEDED",
      "PLAN_CREATED","PLAN_APPROVED","PLAN_REJECTED","PLAN_EXECUTION_STARTED","PLAN_COMPLETED",
      "AGENT_HIRED","AGENT_RUNNING","AGENT_COMPLETED","AGENT_FAILED",
      "AGENT_MESSAGE","AGENT_OUTPUT",
      "COMMANDER_MESSAGE","PIVOT_REQUESTED","PIVOT_APPLIED",
      "HUMAN_APPROVAL_REQUESTED","HUMAN_INPUT_RECEIVED",
      "EVIDENCE_PUBLISHED",
    ].forEach((t) => {
      es.addEventListener(t, (msg) => {
        try { this.handleEvent(JSON.parse(msg.data)); } catch (_) {}
      });
    });
    es.addEventListener("end", () => es.close());
    es.onerror = () => {};
    this.eventSource = es;
  }

  closeStream() {
    if (this.eventSource) this.eventSource.close();
  }
}

// ---------------------------------------------------------------
// Charts (pure SVG — unchanged)
// ---------------------------------------------------------------

function renderChart(chart) {
  if (!chart) return "";
  if (chart.type === "bar") return renderBarChart(chart);
  if (chart.type === "donut") return renderDonut(chart);
  if (chart.type === "scorecard") return renderScorecard(chart);
  return "";
}

function renderBarChart(chart) {
  const series = chart.series || [];
  const W = 540, H = 200, P = 28;
  const max = Math.max(1, ...series.map((s) => s.value));
  const colW = (W - P * 2) / series.length;
  const bars = series.map((s, i) => {
    const h = (s.value / max) * (H - P * 2);
    const x = P + i * colW + 12, y = H - P - h, w = colW - 24;
    return `<rect class="bar" x="${x}" y="${y}" width="${w}" height="${h}" rx="6" />
      <text class="bar-value" x="${x + w / 2}" y="${y - 6}" text-anchor="middle">${escape(s.value)}</text>
      <text class="bar-label" x="${x + w / 2}" y="${H - 8}" text-anchor="middle">${escape(s.label)}</text>`;
  }).join("");
  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" style="width:100%;height:200px;">
    <defs><linearGradient id="brand-grad" x1="0" x2="0" y1="0" y2="1">
      <stop offset="0" stop-color="#7c5cff"/><stop offset="1" stop-color="#29c0ff"/>
    </linearGradient></defs>${bars}</svg>`;
}

function renderDonut(chart) {
  const series = chart.series || [];
  const total = series.reduce((s, x) => s + x.value, 0) || 1;
  const cx = 110, cy = 100, r = 64, sw = 18, C = 2 * Math.PI * r;
  const palette = ["#7c5cff","#29c0ff","#5fffd0","#ffb44d"];
  let offset = 0;
  const segments = series.map((s, i) => {
    const len = (s.value / total) * C;
    const seg = `<circle class="donut-segment" cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${palette[i % palette.length]}" stroke-width="${sw}" stroke-dasharray="${len} ${C - len}" stroke-dashoffset="${-offset}" transform="rotate(-90 ${cx} ${cy})" stroke-linecap="butt" />`;
    offset += len; return seg;
  }).join("");
  const legend = series.map((s, i) =>
    `<div style="display:flex;align-items:center;gap:8px;font-size:12.5px;color:var(--text-2);">
      <span style="width:10px;height:10px;border-radius:3px;background:${palette[i % palette.length]};"></span>
      ${escape(s.label)} <span class="muted mono" style="margin-left:auto;">${escape(s.value)}%</span>
    </div>`).join("");
  return `<div style="display:grid;grid-template-columns:220px 1fr;gap:16px;align-items:center;">
    <svg viewBox="0 0 220 200" style="width:220px;height:200px;">${segments}</svg>
    <div style="display:flex;flex-direction:column;gap:6px;">${legend}</div></div>`;
}

function renderScorecard(chart) {
  const rows = (chart.series || []).map((s) =>
    `<div style="display:grid;grid-template-columns:120px 1fr 48px;gap:10px;align-items:center;font-size:13px;color:var(--text-2);">
      <div class="mono" style="color:var(--text-3);">${escape(s.label)}</div>
      <div style="height:8px;border-radius:4px;background:rgba(255,255,255,0.05);overflow:hidden;">
        <div style="height:100%;width:${Math.min(100,s.value)}%;background:var(--grad-brand);"></div>
      </div>
      <div class="mono" style="text-align:right;">${escape(s.value)}</div>
    </div>`).join("");
  return `<div style="display:flex;flex-direction:column;gap:8px;">${rows}</div>`;
}

// ---------------------------------------------------------------
// App state
// ---------------------------------------------------------------

const appState = {
  currentThread: null,
  sessions: [],
};

// ---------------------------------------------------------------
// Session list
// ---------------------------------------------------------------

function renderSessionList() {
  const host = $("#sessionList");
  if (!host) return;
  $("#sessionCount").textContent = appState.sessions.length;
  host.innerHTML = appState.sessions.map((s) => {
    const active = appState.currentThread?.sessionId === s.session_id;
    return `<div class="thread-row ${active ? "active" : ""}" data-id="${escape(s.session_id)}">
      <div class="t-title">${escape(s.title || "Untitled")}</div>
      <div class="t-sub">${escape(s.objective || "").slice(0, 80)}</div>
      <div class="t-sub mono">${escape(s.status || "CREATED")} · #${escape(s.session_id.slice(0, 6))}</div>
    </div>`;
  }).join("");
  host.querySelectorAll(".thread-row").forEach((row) => {
    row.addEventListener("click", () => switchSession(row.dataset.id));
  });
}

async function refreshSessions() {
  const data = await api("/api/v1/sessions");
  appState.sessions = data || [];
  renderSessionList();
}

// ---------------------------------------------------------------
// Agent library / category filter
// ---------------------------------------------------------------

let currentCategoryFilter = null;
let cachedCategories = null;

async function loadCategories() {
  if (cachedCategories) return cachedCategories;
  try {
    const data = await api("/api/v1/agents/categories");
    cachedCategories = data.categories || [];
  } catch (_) { cachedCategories = []; }
  return cachedCategories;
}

async function renderCategoryPills(categories) {
  const host = $("#category-filter-row");
  if (!host) return;
  host.innerHTML = "";
  const all = document.createElement("button");
  all.className = `category-pill${currentCategoryFilter === null ? " active" : ""}`;
  all.textContent = "All";
  all.addEventListener("click", () => { currentCategoryFilter = null; refreshAgents(); });
  host.appendChild(all);
  (categories || []).forEach((cat) => {
    const btn = document.createElement("button");
    btn.className = `category-pill${currentCategoryFilter === cat ? " active" : ""}`;
    btn.textContent = cat;
    btn.addEventListener("click", () => { currentCategoryFilter = cat; refreshAgents(); });
    host.appendChild(btn);
  });
}

async function refreshAgents() {
  try {
    const cats = await loadCategories();
    await renderCategoryPills(cats);

    const url = currentCategoryFilter
      ? `/api/v1/agents?category=${encodeURIComponent(currentCategoryFilter)}`
      : "/api/v1/agents";
    const data = await api(url).catch(() => api("/api/v1/mcp-servers"));
    const agents = data || [];
    const host = $("#agentList");
    $("#agentCount").textContent = agents.length;

    if (agents.length === 0) {
      host.innerHTML = `<div class="empty-state">No agents found. <strong>+ MCP Server</strong> to connect external tools.</div>`;
      return;
    }
    host.innerHTML = agents.map((a) => {
      const badge = a.category
        ? `<span class="agent-category-badge">${escape(a.category)}</span>`
        : a.transport ? `<span class="agent-category-badge">${escape(a.transport)}</span>` : "";
      const name = (a.name || "").replace(/^seed\//, "");
      return `<div class="agent-row" data-name="${escape(a.name || name)}">
        <div class="agent-row-name">${escape(name)}${badge}</div>
        <div class="agent-row-desc mono" style="font-size:11px;">${escape((a.description || a.upstream || "").slice(0, 60))}</div>
      </div>`;
    }).join("");
    host.querySelectorAll(".agent-row").forEach((row) => {
      row.addEventListener("click", () => showAgentDetail(row.dataset.name));
    });
  } catch (_) { /* ignore on first boot */ }
}

async function showAgentDetail(name) {
  try {
    const agent = await api(`/api/v1/agents/${encodeURIComponent(name)}`);
    const displayName = (agent.name || name).replace(/^seed\//, "");
    const catBadge = agent.category ? `<span class="agent-category-badge" style="margin-left:8px;">${escape(agent.category)}</span>` : "";
    const typTag = agent.agent_type ? `<span class="agent-type-tag" style="margin-left:6px;">${escape(agent.agent_type.toUpperCase())}</span>` : "";
    $("#agentDetailName").innerHTML = `${escape(displayName)}${catBadge}${typTag}`;

    let html = `
      <div class="detail-section">
        <div class="detail-label">Description</div>
        <div class="detail-value">${escape(agent.description || "—")}</div>
      </div>
      <div class="detail-section">
        <div class="detail-label">Capabilities</div>
        <div class="detail-value">${(agent.capabilities || []).map((c) => `<span class="cap-tag">${escape(c)}</span>`).join(" ") || "None"}</div>
      </div>`;

    if (agent.agent_type === "llm" && agent.system_prompt) {
      html += `<div class="detail-section">
        <div class="detail-label">System Prompt</div>
        <details class="system-prompt-details"><summary>Show</summary><pre>${escape(agent.system_prompt)}</pre></details>
      </div>`;
    }
    $("#agentDetailBody").innerHTML = html;
    $("#agentDetailModal").style.display = "flex";
  } catch (err) {
    showToast("Failed to load agent: " + err.message, true);
  }
}

function closeAgentDetail() {
  $("#agentDetailModal").style.display = "none";
}

// ---------------------------------------------------------------
// Session lifecycle
// ---------------------------------------------------------------

function clearTranscript() {
  const t = $("#transcript");
  // Keep welcome panel if it exists but hide it
  const wp = $("#welcomePanel");
  t.innerHTML = "";
  if (wp) {
    wp.style.display = "none";
    t.appendChild(wp);
  }
  $("#eventFeed").innerHTML = "";
  $("#budgetFill").style.width = "0%";
  $("#budgetConsumed").textContent = "$0.00 consumed";
  $("#budgetLimit").textContent = "/ $12.00";
  $("#infoRuntime").textContent = "—";
  $("#infoSession").textContent = "—";
  $("#infoStatus").textContent = "—";
}

async function createSession(objective) {
  if (appState.currentThread) appState.currentThread.closeStream();
  clearTranscript();

  const runtime = $("#runtimeSelect")?.value || "echo";
  const model = RUNTIME_MODELS[runtime] || "echo:test";

  const data = await api("/api/v1/sessions", {
    method: "POST",
    body: JSON.stringify({ objective, runtime, model, timeout_seconds: 1800 }),
  });

  const view = new ThreadView(data.session_id, data.title || `Session: ${runtime}`, objective);
  appState.currentThread = view;
  appState.sessions = [
    { session_id: data.session_id, title: data.title || `Session: ${runtime}`, objective, status: data.status },
    ...appState.sessions.filter((x) => x.session_id !== data.session_id),
  ];
  renderSessionList();

  // Show runtime in info panel
  $("#infoRuntime").textContent = runtime;
  $("#infoSession").textContent = data.session_id.slice(0, 8);

  // Echo user message
  view.appendMessage({ avatarClass: "user", avatarText: "U", who: "You", klass: "user", body: escape(objective) });

  view.startStream();
}

async function switchSession(sessionId) {
  if (appState.currentThread?.sessionId === sessionId) return;
  if (appState.currentThread) appState.currentThread.closeStream();
  clearTranscript();

  const s = await api(`/api/v1/sessions/${sessionId}`);
  const view = new ThreadView(s.session_id, s.title, s.objective);
  appState.currentThread = view;
  renderSessionList();

  $("#infoRuntime").textContent = s.runtime || "—";
  $("#infoSession").textContent = s.session_id.slice(0, 8);
  $("#infoStatus").textContent = s.status?.toLowerCase() || "—";

  view.startStream();
}

async function controlAction(action) {
  if (!appState.currentThread) return;
  await api(`/api/v1/sessions/${appState.currentThread.sessionId}/${action}`, { method: "POST" });
}

// ---------------------------------------------------------------
// MCP Server modal
// ---------------------------------------------------------------

function openMcpModal() {
  if ($("#mcpName")) $("#mcpName").value = "";
  if ($("#mcpTransport")) $("#mcpTransport").value = "stdio";
  if ($("#mcpUpstream")) $("#mcpUpstream").value = "";
  $("#mcpModal").style.display = "flex";
}

function closeMcpModal() {
  $("#mcpModal").style.display = "none";
}

async function createMcpServer() {
  const name = $("#mcpName").value.trim();
  const transport = $("#mcpTransport").value;
  const upstream = $("#mcpUpstream").value.trim();
  if (!name || !upstream) { showToast("Name and Upstream are required", true); return; }
  try {
    try {
      await api("/api/v1/mcp-servers", { method: "POST", body: JSON.stringify({ name, transport, upstream }) });
    } catch (err) {
      if (err.message.includes("409")) {
        await api(`/api/v1/mcp-servers/${name}`, { method: "DELETE" });
        await api("/api/v1/mcp-servers", { method: "POST", body: JSON.stringify({ name, transport, upstream }) });
      } else throw err;
    }
    closeMcpModal();
    showToast(`MCP server "${name}" registered.`);
    await refreshAgents();
  } catch (err) {
    showToast("Failed to register MCP server: " + err.message, true);
  }
}

// ---------------------------------------------------------------
// Toast
// ---------------------------------------------------------------

function showToast(message, isError = false) {
  const toast = document.createElement("div");
  toast.className = `toast ${isError ? "toast-error" : "toast-success"}`;
  toast.textContent = message;
  document.body.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add("visible"));
  setTimeout(() => { toast.classList.remove("visible"); setTimeout(() => toast.remove(), 300); }, 3500);
}

// ---------------------------------------------------------------
// Expose to inline onclick handlers (module scope)
// ---------------------------------------------------------------

window.openMcpModal = openMcpModal;
window.closeMcpModal = closeMcpModal;
window.createMcpServer = createMcpServer;
window.showAgentDetail = showAgentDetail;
window.closeAgentDetail = closeAgentDetail;
window.controlAction = controlAction;

// ---------------------------------------------------------------
// Boot
// ---------------------------------------------------------------

(async function boot() {
  // Fetch dev API key first — sets the badge and stores the key
  await ensureApiKey();

  wireRuntimeSelector();

  $("#composer").addEventListener("submit", (evt) => {
    evt.preventDefault();
    const value = $("#composerInput").value.trim();
    if (!value) return;
    $("#composerInput").value = "";
    createSession(value).catch((err) => showToast("Could not start session: " + err.message, true));
  });

  $$(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      $("#composerInput").value = chip.dataset.prompt || "";
      $("#composerInput").focus();
    });
  });

  $("#newSessionBtn").addEventListener("click", () => $("#composerInput").focus());
  $("#pauseBtn").addEventListener("click", () => controlAction("pause"));
  $("#resumeBtn").addEventListener("click", () => controlAction("resume"));
  $("#cancelBtn").addEventListener("click", () => controlAction("cancel"));

  try { await refreshSessions(); } catch (_) {}
  try { await refreshAgents(); } catch (_) {}
})();
