// Atrium Console · Multi-view Agent Platform
const $=(s,r=document)=>r.querySelector(s);const $$=(s,r=document)=>[...r.querySelectorAll(s)];
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

// ── API ──────────────────────────────────────────────────────
let _apiKey=localStorage.getItem("atrium_api_key")||null;
async function ensureApiKey(){if(_apiKey)return _apiKey;try{const r=await fetch("/api/v1/setup");if(r.ok){const d=await r.json();_apiKey=d.api_key;localStorage.setItem("atrium_api_key",_apiKey);if(d.dev){const b=$("#devBadge");if(b)b.style.display=""}}}catch(_){}return _apiKey}
async function api(path,init={}){const key=await ensureApiKey();const r=await fetch(path,{headers:{"Content-Type":"application/json",...(key?{"X-Atrium-Key":key}:{}),...(init.headers||{})},...init});if(!r.ok)throw new Error(`${r.status} ${r.statusText}`);return r.json()}

// ── Provider presets ─────────────────────────────────────────
const PRESETS={deepseek:{base_url:"https://api.deepseek.com/v1",model:"deepseek-chat"},openrouter:{base_url:"https://openrouter.ai/api/v1",model:"anthropic/claude-sonnet-4-5"},openai:{base_url:"https://api.openai.com/v1",model:"gpt-4o-mini"},gemini:{base_url:"https://generativelanguage.googleapis.com/v1beta/openai/",model:"gemini-2.5-flash"},xai:{base_url:"https://api.x.ai/v1",model:"grok-3-mini"},nvidia:{base_url:"https://integrate.api.nvidia.com/v1",model:"meta/llama-3.3-70b-instruct"},groq:{base_url:"https://api.groq.com/openai/v1",model:"llama-3.3-70b-versatile"},ollama:{base_url:"http://localhost:11434/v1",model:"llama3.2"}};
// Anthropic SDK override presets — DeepSeek natively supports Anthropic API format!
// Base URL: https://api.deepseek.com/anthropic  (no proxy needed)
const ANTHROPIC_PRESETS={deepseek:{base_url:"https://api.deepseek.com/anthropic",model:"deepseek-chat",hint:"DeepSeek native Anthropic API — use your DeepSeek API key directly"},deepseek_reasoner:{base_url:"https://api.deepseek.com/anthropic",model:"deepseek-reasoner",hint:"DeepSeek R1 reasoning model via Anthropic API"},openrouter_claude:{base_url:"https://openrouter.ai/api/v1",model:"anthropic/claude-sonnet-4-5",hint:"Claude via OpenRouter"},openrouter_gemini:{base_url:"https://openrouter.ai/api/v1",model:"google/gemini-2.5-flash",hint:"Gemini via OpenRouter"},litellm:{base_url:"http://localhost:4000/v1",model:"deepseek-chat",hint:"Local LiteLLM proxy"},custom:{base_url:"https://api.anthropic.com",model:"claude-sonnet-4-6",hint:"Default Anthropic — or enter any proxy URL"}};
const RUNTIME_MODELS={echo:"echo:test",direct_gemini:"gemini:gemini-2.5-flash",direct_anthropic:"anthropic:claude-sonnet-4-6",open_agent_sdk:"openai:gpt-4o-mini",universal:"universal:configured"};

function loadPC(){try{return JSON.parse(localStorage.getItem("atrium_provider")||"{}")}catch(_){return{}}}
function savePC(c){localStorage.setItem("atrium_provider",JSON.stringify(c))}

// ── View switching ───────────────────────────────────────────
let _currentView="home";
function switchView(view,data){
  _currentView=view;
  // Hide all pages
  $$(".page").forEach(p=>p.style.display="none");
  // Show target page
  const page=$(`#page-${view}`);if(page)page.style.display="";
  // Update sidebar
  $$(".sidebar-item").forEach(i=>i.classList.toggle("active",i.dataset.view===view));
  // Special: run detail
  if(view==="run-detail"&&data)renderRunDetail(data);
  // Composer bar only on run-detail
  $("#composerBar").style.display=view==="run-detail"?"":"none";
  if(view==="home")refreshHome();
  if(view==="runs")refreshRunsPage();
  if(view==="agents")refreshAgentsPage();
  if(view==="tools")refreshToolsPage();
}
function switchTab(tab){
  $$(".tab").forEach(t=>t.classList.toggle("active",t.dataset.tab===tab));
  $$(".tab-content").forEach(c=>c.style.display="none");
  const c=$(`#tab-${tab}`);if(c)c.style.display="";
}

// ── Home page ────────────────────────────────────────────────
async function refreshHome(){
  try{
    const sessions=await api("/api/v1/sessions");state.sessions=sessions||[];
    const total=state.sessions.length;
    const completed=state.sessions.filter(s=>s.status==="COMPLETED").length;
    const active=state.sessions.filter(s=>s.status==="RUNNING"||s.status==="PLANNING").length;
    const failed=state.sessions.filter(s=>s.status==="FAILED").length;
    const successRate=total>0?Math.round((completed/total)*100)+"%":"—";
    // Estimate cost
    let totalCost=0;state.sessions.forEach(s=>{const c=parseFloat(s.cost||0);totalCost+=c||(s.status==="COMPLETED"?0.01:0)});
    $("#metricTotal").textContent=total;
    $("#metricSuccess").textContent=successRate;
    $("#metricActive").textContent=active;
    $("#metricSpent").textContent=`$${totalCost.toFixed(2)}`;
    // Recent runs table
    const recent=state.sessions.slice(0,10);
    $("#recentRunsTable").innerHTML=recent.length?recent.map(s=>{
      const statusBadge=s.status==="COMPLETED"?"badge-success":s.status==="FAILED"?"badge-error":s.status==="RUNNING"?"badge-info":"badge";
      return`<tr style="cursor:pointer" onclick="switchView('run-detail','${s.session_id}')"><td style="max-width:280px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(s.objective||s.title||"—")}</td><td><span class="badge">${esc(s.runtime||"—")}</span></td><td><span class="badge ${statusBadge}"><span class="dot"></span>${esc(s.status||"—")}</span></td><td class="text-mono text-muted">—</td><td class="text-mono text-muted">${esc(s.created_at?.split("T")[0]||"—")}</td></tr>`;
    }).join(""):`<tr><td colspan="5" style="text-align:center;color:var(--text-muted);padding:var(--s-4)">No runs yet. <a href="#" onclick="switchView('new-run');return false">Create your first run</a>.</td></tr>`;
  }catch(_){}
}

// ── Runs page ────────────────────────────────────────────────
async function refreshRunsPage(){
  try{
    const sessions=await api("/api/v1/sessions");state.sessions=sessions||[];
    $("#runCount").textContent=state.sessions.length;
    $("#allRunsTable").innerHTML=state.sessions.length?state.sessions.map(s=>{
      const sb=s.status==="COMPLETED"?"badge-success":s.status==="FAILED"?"badge-error":s.status==="RUNNING"?"badge-info":"badge";
      return`<tr style="cursor:pointer" onclick="switchView('run-detail','${s.session_id}')"><td style="max-width:260px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(s.objective||s.title||"—")}</td><td><span class="badge">${esc(s.runtime||"—")}</span></td><td><span class="badge ${sb}"><span class="dot"></span>${esc(s.status||"—")}</span></td><td class="text-mono text-muted">—</td><td class="text-mono text-muted">$${esc(String(s.cost||"—"))}</td><td class="text-mono text-muted">${esc(s.created_at?.split("T")[0]||"—")}</td></tr>`;
    }).join(""):`<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:var(--s-4)">No runs yet.</td></tr>`;
  }catch(_){}
}

// ── Agents page ──────────────────────────────────────────────
async function refreshAgentsPage(){
  try{
    const resp=await api("/api/v1/agents").catch(()=>({agents:[]}));
    const agents=resp.agents||[];
    const mcp=await api("/api/v1/mcp-servers").catch(()=>[]);
    const all=[...agents,...(mcp||[])];
    $("#agentCount").textContent=all.length;
    if(!all.length){$("#agentsList").innerHTML=`<div class="empty"><h3>No agents configured</h3><p>Seed agents load automatically from the corpus. Create custom agents or register MCP tools to extend your agent fleet.</p><button class="btn btn-primary btn-sm" onclick="switchView('new-run')">+ New Run</button></div>`;return}
    $("#agentsList").innerHTML=`<div class="table-wrap"><table><thead><tr><th>Name</th><th>Type</th><th>Category</th><th>Description</th></tr></thead><tbody>${all.map(a=>{const n=(a.name||"").replace(/^seed\//,"");return`<tr><td style="font-weight:500">${esc(n)}</td><td><span class="badge badge-info">${esc(a.agent_type||a.transport||"—")}</span></td><td><span class="badge">${esc(a.category||"—")}</span></td><td style="max-width:300px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(a.description||a.upstream||"—")}</td></tr>`}).join("")}</tbody></table></div>`;
  }catch(_){}
}

// ── Tools page ───────────────────────────────────────────────
async function refreshToolsPage(){
  try{
    const mcp=await api("/api/v1/mcp-servers").catch(()=>[]);
    if(!mcp.length){$("#toolsList").innerHTML=`<div class="empty"><h3>No MCP servers registered</h3><p>Connect external tools — databases, APIs, GitHub — to your agents via MCP.</p><button class="btn btn-primary btn-sm" onclick="openMcpModal()">Register MCP Server</button></div>`;return}
    $("#toolsList").innerHTML=`<div class="table-wrap"><table><thead><tr><th>Name</th><th>Transport</th><th>Upstream</th><th></th></tr></thead><tbody>${mcp.map(m=>`<tr><td style="font-weight:500">${esc(m.name||"—")}</td><td><span class="badge">${esc(m.transport||"—")}</span></td><td style="font-family:var(--mono);font-size:11.5px;max-width:300px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(m.upstream||"—")}</td><td><button class="btn btn-ghost btn-xs" onclick="deleteMcp('${esc(m.name)}')">Remove</button></td></tr>`).join("")}</tbody></table></div>`;
  }catch(_){}
}
async function deleteMcp(name){try{await api(`/api/v1/mcp-servers/${name}`,{method:"DELETE"});showToast(`Removed "${name}"`);refreshToolsPage()}catch(e){showToast("Failed: "+e.message,true)}}

// ── New Run flow ─────────────────────────────────────────────
function wireNewRunForm(){
  const rt=$("#newRunRuntime"),preset=$("#newRunPreset");
  if(!rt||!preset)return;
  rt.addEventListener("change",()=>{
    const showProvider=rt.value==="universal"||rt.value==="direct_anthropic";
    $("#providerFields").style.display=showProvider?"":"none";
    $("#newRunPreset").parentElement.parentElement.style.display=showProvider?"":"none";
    $("#newRunModel").parentElement.style.display=showProvider?"":"none";
    // Show Anthropic override hint
    $("#providerHint").style.display=rt.value==="direct_anthropic"?"none":"";
    $("#anthropicOverrideHint").style.display=rt.value==="direct_anthropic"?"":"none";
    // Swap preset options based on runtime
    if(rt.value==="direct_anthropic"){
      preset.innerHTML=Object.keys(ANTHROPIC_PRESETS).map(k=>`<option value="${k}">${k.replace(/_/g," ").replace(/\b\w/g,c=>c.toUpperCase())}</option>`).join("");
      preset.value="deepseek";const p=ANTHROPIC_PRESETS["deepseek"];
      $("#newRunBaseUrl").value=p.base_url;$("#newRunModel").value=p.model;
    }else{
      preset.innerHTML='<option value="deepseek">DeepSeek</option><option value="openrouter">OpenRouter</option><option value="openai">OpenAI</option><option value="gemini">Google Gemini</option><option value="xai">xAI / Grok</option><option value="nvidia">NVIDIA NIM</option><option value="groq">Groq</option><option value="ollama">Ollama (local)</option>';
      preset.value="deepseek";const p=PRESETS["deepseek"];$("#newRunBaseUrl").value=p.base_url;$("#newRunModel").value=p.model;
    }
  });
  preset.addEventListener("change",()=>{
    const isAnthropic=rt.value==="direct_anthropic";
    const dict=isAnthropic?ANTHROPIC_PRESETS:PRESETS;
    const p=dict[preset.value];if(p){$("#newRunBaseUrl").value=p.base_url;$("#newRunModel").value=p.model}
  });
  // Init: DeepSeek preset (universal is default selected)
  preset.value="deepseek";const p=PRESETS["deepseek"];$("#newRunBaseUrl").value=p.base_url;$("#newRunModel").value=p.model;
}

async function deployRun(){
  const obj=$("#newRunObjective").value.trim();if(!obj){showToast("Enter an objective for the agent",true);return}
  const rt=$("#newRunRuntime").value||"universal",model=RUNTIME_MODELS[rt]||"universal:configured";
  const body={objective:obj,runtime:rt,model,timeout_seconds:parseInt($("#newRunTimeout").value)||1800};
  if(rt==="universal"||rt==="direct_anthropic")body.provider={base_url:$("#newRunBaseUrl").value.trim(),api_key:$("#newRunApiKey").value.trim(),model:$("#newRunModel").value.trim()};
  // Save provider config
  const pc=loadPC();pc._last={base_url:$("#newRunBaseUrl").value,api_key:$("#newRunApiKey").value,model:$("#newRunModel").value,preset:$("#newRunPreset").value};savePC(pc);

  const btn=$("#deployBtn"),hint=$("#deployHint");btn.disabled=true;btn.textContent="Deploying...";hint.textContent="";
  try{
    const d=await api("/api/v1/sessions",{method:"POST",body:JSON.stringify(body)});
    state.sessions.unshift({session_id:d.session_id,title:d.title||`Run: ${rt}`,objective:obj,status:d.status,runtime:rt});
    // Clear form
    $("#newRunObjective").value="";
    // Navigate to run detail
    switchView("run-detail",d.session_id);
  }catch(e){showToast("Failed: "+e.message,true)}
  btn.disabled=false;btn.textContent="Deploy Agent";
}

// ── Run detail (with tabs) ───────────────────────────────────
let _activeThread=null;

async function renderRunDetail(sessionId){
  if(_activeThread){_activeThread.closeStream();_activeThread=null}
  // Clear
  $("#transcript").innerHTML="";$("#eventFeed").innerHTML="";$("#eventCount").textContent="";
  $("#configGrid").innerHTML="";$("#apiSseUrl").textContent="—";
  $("#pauseBtn").disabled=true;$("#resumeBtn").disabled=true;$("#cancelBtn").disabled=true;
  switchTab("transcript");

  try{
    const s=await api(`/api/v1/sessions/${sessionId}`);
    $("#detailTitle").textContent=s.title||"Run Detail";
    $("#detailId").textContent=`ID: ${s.session_id}`;
    // Config tab
    $("#configGrid").innerHTML=`<div class="config-item"><label>Runtime</label><div class="config-val">${esc(s.runtime||"—")}</div></div><div class="config-item"><label>Model</label><div class="config-val">${esc(s.model||"—")}</div></div><div class="config-item"><label>Status</label><div class="config-val"><span class="badge ${s.status==="COMPLETED"?"badge-success":s.status==="FAILED"?"badge-error":"badge-info"}">${esc(s.status||"—")}</span></div></div><div class="config-item"><label>Objective</label><div class="config-val" style="font-family:var(--font);font-size:13px">${esc(s.objective||"—")}</div></div>`;
    // API tab
    const token=_apiKey?`?token=${encodeURIComponent(_apiKey)}`:"";$("#apiSseUrl").textContent=`GET /api/v1/sessions/${s.session_id}/stream${token}`;
    // Sidebar context
    $("#sidebarRunContext").style.display="";$("#sidebarRunTitle").textContent=s.title||"—";$("#sidebarRunId").textContent=s.session_id.slice(0,8);$("#sidebarRunStatus").innerHTML=`<span class="dot"></span>${esc((s.status||"unknown").toLowerCase())}`;

    // Always connect the SSE stream — for COMPLETED/FAILED sessions the
    // server replays stored events; for RUNNING sessions it streams live.
    const tv=new ThreadView(s.session_id,s.title,s.objective);_activeThread=tv;tv.startStream();
    if(s.status==="RUNNING"||s.status==="PLANNING"||s.status==="CREATED"){
      $("#pauseBtn").disabled=false;$("#cancelBtn").disabled=false;
    }
    // Close the stream when it receives the end sentinel
    tv.eventSource?.addEventListener("end",()=>{tv.closeStream();});
  }catch(e){showToast("Failed to load run: "+e.message,true)}
}

// ── ThreadView (streaming) ───────────────────────────────────
class ThreadView{
  constructor(sid,title,obj){this.sessionId=sid;this.title=title;this.objective=obj;this.status="CREATED";this.agents=new Map;this.eventSource=null;this.evCount=0;this.planNodes=[]}

  _el(cls,who,body){
    const d=document.createElement("div");d.className="msg";d.innerHTML=`<div class="${cls}">${who?`<div class="${cls.includes("user")?"":cls.includes("agent")?"ma-who":cls.includes("tool")?"mt-who":cls.includes("result")?"mr-who":"ma-who"}">${esc(who)}</div>`:""}${body}</div>`;
    $("#transcript").appendChild(d);this._scroll();return d;
  }
  _card(h){const d=document.createElement("div");d.className="msg";d.innerHTML=h;$("#transcript").appendChild(d);this._scroll();return d}
  _scroll(){const c=$("#transcript").parentElement;if(c)c.scrollTop=c.scrollHeight}

  _pushEvent(evt){this.evCount++;$("#eventCount").textContent=this.evCount;const kl=evt.type?.includes("FAILED")?"err":evt.type?.startsWith("PIVOT")?"warn":"";const r=document.createElement("div");r.className=`ev-item ${kl}`;r.innerHTML=`<span class="ev-seq">#${evt.sequence??"?"}</span><span class="ev-type">${esc(evt.type)}</span>`;$("#eventFeed").appendChild(r)}

  handleEvent(evt){
    this._pushEvent(evt);
    switch(evt.type){
      case "SESSION_CREATED":case "THREAD_CREATED":break;
      case "BUDGET_RESERVED":case "BUDGET_CONSUMED":this._budget(evt);break;
      case "THREAD_PLANNING":case "THREAD_PLANNING_START":this._status("PLANNING");this._el("msg-cmd","",`<span class="thinking"><span></span><span></span><span></span></span> Planning the work…`);break;
      case "THREAD_PAUSED":case "SESSION_PAUSED":this._status("PAUSED");break;
      case "COMMANDER_MESSAGE":this._el("msg-cmd","Commander",esc(evt.payload?.text||""));break;
      case "PLAN_CREATED":this._plan(evt);break;
      case "THREAD_RUNNING":case "SESSION_RUNNING":this._status("RUNNING");$("#pauseBtn").disabled=false;$("#cancelBtn").disabled=false;break;
      case "AGENT_HIRED":this._agentHired(evt);break;
      case "AGENT_RUNNING":this._agentStatus(evt,"RUNNING");break;
      case "AGENT_COMPLETED":this._agentStatus(evt,"COMPLETED");break;
      case "AGENT_FAILED":this._agentStatus(evt,"FAILED");break;
      case "AGENT_MESSAGE":this._agentMsg(evt);break;
      case "AGENT_OUTPUT":this._agentOut(evt);break;
      case "PIVOT_REQUESTED":this._card(`<div class="pivot-card"><div class="pv-label">Pivot requested</div><div class="pv-text">${esc(evt.payload?.rationale||"")}</div></div>`);break;
      case "HUMAN_APPROVAL_REQUESTED":this._card(`<div class="pivot-card"><div class="pv-label">Approval required</div><div class="pv-text">${esc(evt.payload?.message||"")}</div><div class="pv-actions"><button class="btn btn-primary btn-sm" onclick="controlAction('approve')">Approve</button><button class="btn btn-ghost btn-sm" onclick="controlAction('reject')">Reject</button></div></div>`);break;
      case "EVIDENCE_PUBLISHED":this._evidence(evt);break;
      case "HARNESS_MESSAGE":this._harnessMsg(evt);break;
      case "HARNESS_TOOL_CALLED":this._harnessTool(evt);break;
      case "HARNESS_TOOL_RESULT":this._harnessResult(evt);break;
      case "THREAD_COMPLETED":case "SESSION_COMPLETED":this._status("COMPLETED");$("#pauseBtn").disabled=true;$("#cancelBtn").disabled=true;break;
      case "THREAD_FAILED":case "SESSION_FAILED":this._status("FAILED");$("#pauseBtn").disabled=true;$("#cancelBtn").disabled=true;break;
      case "THREAD_CANCELLED":case "SESSION_CANCELLED":this._status("CANCELLED");$("#pauseBtn").disabled=true;$("#cancelBtn").disabled=true;break;
      case "end":this.closeStream();break;
    }
  }

  _status(s){
    this.status=s;const b=$("#statusBadge");
    if(s==="RUNNING"||s==="PLANNING")b.innerHTML='<span class="sdot sdot-running dot-live"></span> running',b.className="nav-badge";
    else if(s==="COMPLETED")b.innerHTML='<span class="sdot sdot-completed"></span> completed',b.className="nav-badge";
    else if(s==="FAILED")b.innerHTML='<span class="sdot sdot-failed"></span> failed',b.className="nav-badge";
    else b.innerHTML=`<span class="sdot sdot-created"></span> ${s.toLowerCase()}`,b.className="nav-badge";
    $("#sidebarRunStatus").innerHTML=`<span class="dot${s==="RUNNING"||s==="PLANNING"?" dot-live":""}"></span>${s.toLowerCase()}`;
  }
  _budget(e){/* simplified */}

  _plan(e){
    this.planNodes=(e.payload.graph?.nodes||[]).map(n=>({...n,status:"PENDING"}));
    const h=`<div class="plan-card"><div class="pc-head"><div style="display:flex;align-items:center;gap:8px"><span class="badge badge-info">Plan ${esc(e.payload.plan_number??1)}</span><span style="font-weight:600;font-size:13px">Hiring ${this.planNodes.length} specialist${this.planNodes.length!==1?"s":""}</span></div><span class="text-mono text-muted">${esc((e.payload.plan_id||"").slice(0,8))}</span></div><div class="pc-body"><p style="font-size:13.5px;color:var(--text-secondary);margin-bottom:var(--s-3)">${esc(e.payload.rationale||"")}</p><svg class="plan-graph" viewBox="0 0 600 200"></svg></div></div>`;
    const c=this._card(h);this._drawPlan(c.querySelector(".plan-graph"));
  }
  _drawPlan(svg){if(!svg)return;const W=600,H=200,ns=this.planNodes;const depthOf=(k,seen=new Set)=>{if(seen.has(k))return 0;seen.add(k);const n=ns.find(x=>x.key===k);if(!n||!n.depends_on?.length)return 0;return 1+Math.max(...n.depends_on.map(d=>depthOf(d,seen)))};const layers=new Map;ns.forEach(n=>{const d=depthOf(n.key);if(!layers.has(d))layers.set(d,[]);layers.get(d).push(n)});const dc=layers.size||1,cw=W/dc,pos=new Map;[...layers.entries()].sort((a,b)=>a[0]-b[0]).forEach(([,list],ci)=>{const rh=H/(list.length+1);list.forEach((n,i)=>pos.set(n.key,{x:ci*cw+cw/2,y:rh*(i+1)}))});const edges=ns.flatMap(n=>(n.depends_on||[]).map(dep=>{const a=pos.get(dep),b=pos.get(n.key);if(!a||!b)return"";return`<path class="edge" d="M ${a.x+60} ${a.y} C ${(a.x+b.x)/2} ${a.y}, ${(a.x+b.x)/2} ${b.y}, ${b.x-60} ${b.y}"/>`})).join("");const rects=ns.map(n=>{const p=pos.get(n.key);if(!p)return"";return`<g transform="translate(${p.x-60} ${p.y-16})" data-key="${esc(n.key)}"><rect class="node-rect ${n.status}" x="0" y="0" width="120" height="32" rx="5"/><text x="60" y="20" text-anchor="middle">${esc(n.key)}</text></g>`}).join("");svg.innerHTML=edges+rects}

  _agentHired(e){
    const ak=e.payload.agent_key;if(this.agents.has(ak))return;const role=e.payload.role||"",obj=e.payload.objective||"",mg=ak.slice(0,2).toUpperCase();
    const h=`<div class="ac-wrap" data-agent="${esc(ak)}"><div class="ac-head"><div class="ac-left"><div class="ac-avatar">${esc(mg)}</div><div><span class="ac-name">${esc(ak)}</span><span class="ac-role">${esc(role)}</span></div></div><div class="ac-status"><span class="badge" data-pill><span class="dot"></span>hired</span><span class="ac-chevron">&#8250;</span></div></div><div class="ac-body"><div class="ac-inner"><div data-thoughts></div><div class="ac-output" data-output hidden></div></div></div></div>`;
    const w=this._card(h),card=w.querySelector(".ac-wrap");card.querySelector(".ac-head").addEventListener("click",()=>card.classList.toggle("open"));if(this.agents.size<3)card.classList.add("open");
    this.agents.set(ak,{cardEl:card,pill:card.querySelector("[data-pill]"),thoughts:card.querySelector("[data-thoughts]"),output:card.querySelector("[data-output]")});
  }
  _agentStatus(e,s){const a=this.agents.get(e.payload.agent_key);if(!a)return;const bc=s==="FAILED"?"badge-error":s==="RUNNING"?"badge-info":"badge-success";a.pill.className=`badge ${bc}`;a.pill.innerHTML=`<span class="dot${s==="RUNNING"?" dot-live":""}"></span>${s.toLowerCase()}`}
  _agentMsg(e){const a=this.agents.get(e.payload.agent_key);if(!a)return;const d=document.createElement("div");d.className="ac-thought";d.textContent=e.payload.text||"";a.thoughts.appendChild(d)}
  _agentOut(e){const a=this.agents.get(e.payload.agent_key);if(!a)return;a.output.hidden=false;a.output.textContent=JSON.stringify(e.payload.output??{},null,2)}

  _evidence(e){
    const p=e.payload||{};const sh=(p.sections||[]).map(s=>`<div class="ev-section">${s.title?`<h4>${esc(s.title)}</h4>`:""}${s.content?`<p>${esc(s.content)}</p>`:""}${(s.key_facts||[]).length?`<ul class="ev-facts">${s.key_facts.map(f=>`<li>${esc(f)}</li>`).join("")}</ul>`:""}</div>`).join("");
    const rh=(p.recommendations||[]).map(r=>`<div class="rec">${esc(r)}</div>`).join("");
    let fh="";if(!p.sections?.length&&p.findings?.length)fh=`<div class="findings">${p.findings.map(f=>`<div class="finding severity-${esc(f.severity||"low")}"><span class="text-mono">${esc((f.severity||"low").toUpperCase())}</span><span>${esc(f.text||"")}</span></div>`).join("")}</div>`;
    this._card(`<div class="ev-card"><span class="badge badge-success" style="margin-bottom:8px">Report ready</span><div class="ev-headline">${esc(p.headline||"Analysis Complete")}</div><div class="ev-summary">${esc(p.summary||"")}</div>${sh?`<div class="ev-sections">${sh}</div>`:""}${fh}${rh?`<div class="recs">${rh}</div>`:""}</div>`);
  }

  _harnessMsg(e){const t=e.payload?.text||"";if(!t)return;this._el("msg-agent","Agent",`<div class="ma-text">${esc(t).replace(/\n/g,"<br>").replace(/```(\w*)\n([\s\S]*?)```/g,(_,lang,code)=>`<pre class="mt-code">${esc(code.trim())}</pre>`).replace(/\*\*(.+?)\*\*/g,"<strong>$1</strong>")}</div>`)}
  _harnessTool(e){const tool=e.payload?.tool||"tool",input=e.payload?.input||{};const istr=typeof input==="object"?JSON.stringify(input):String(input);const preview=istr.length>150?istr.slice(0,150)+"...":istr;this._el("msg-tool",tool,`<div class="mt-toggle" onclick="this.nextElementSibling.classList.toggle('open')"><span class="mt-cmd">${esc(preview)}</span></div><div class="mt-detail">${esc(istr)}</div>`)}
  _harnessResult(e){const o=String(e.payload?.output||"").trim();if(!o)return;const lines=o.split("\n");const preview=lines.slice(0,6).join("\n");const more=lines.length>6?`<div class="mr-more" onclick="this.previousElementSibling.classList.toggle('full');this.classList.toggle('on')">Show all ${lines.length} lines ▾</div>`:"";const full=lines.length>6?`<div class="mr-full">${esc(o).replace(/\n/g,"<br>")}</div>`:"";this._el("msg-result","Result",`<div class="mr-text">${esc(preview).replace(/\n/g,"<br>")}</div>${full}${more}`)}

  async startStream(){
    if(this.eventSource)this.eventSource.close();
    // Ensure we have an API key before connecting (required for auth)
    await ensureApiKey();
    const t=_apiKey?`?token=${encodeURIComponent(_apiKey)}`:"";
    const es=new EventSource(`/api/v1/sessions/${this.sessionId}/stream${t}`);
    es.onmessage=msg=>{try{this.handleEvent(JSON.parse(msg.data))}catch(e){}};
    es.onerror=()=>{};this.eventSource=es;
  }
  closeStream(){if(this.eventSource)this.eventSource.close()}
}

// ── Control ──────────────────────────────────────────────────
async function controlAction(a){if(!_activeThread)return;await api(`/api/v1/sessions/${_activeThread.sessionId}/${a}`,{method:"POST"})}
window.controlAction=controlAction;

// ── MCP ──────────────────────────────────────────────────────
function openMcpModal(){$("#mcpName").value="";$("#mcpTransport").value="stdio";$("#mcpUpstream").value="";$("#mcpModal").style.display="flex"}
function closeMcpModal(){$("#mcpModal").style.display="none"}
async function createMcpServer(){
  const n=$("#mcpName").value.trim(),t=$("#mcpTransport").value,u=$("#mcpUpstream").value.trim();if(!n||!u){showToast("Name and Upstream are required",true);return}
  try{try{await api("/api/v1/mcp-servers",{method:"POST",body:JSON.stringify({name:n,transport:t,upstream:u})})}catch(e){if(e.message.includes("409")){await api(`/api/v1/mcp-servers/${n}`,{method:"DELETE"});await api("/api/v1/mcp-servers",{method:"POST",body:JSON.stringify({name:n,transport:t,upstream:u})})}else throw e}closeMcpModal();showToast(`MCP server "${n}" registered.`);refreshToolsPage();refreshAgentsPage()}catch(e){showToast("Failed: "+e.message,true)}
}
window.openMcpModal=openMcpModal;window.closeMcpModal=closeMcpModal;window.createMcpServer=createMcpServer;
window.deployRun=deployRun;

// ── Toast ────────────────────────────────────────────────────
function showToast(msg,err){const t=document.createElement("div");t.className=`toast ${err?"toast-err":"toast-ok"}`;t.textContent=msg;document.body.appendChild(t);requestAnimationFrame(()=>t.classList.add("on"));setTimeout(()=>{t.classList.remove("on");setTimeout(()=>t.remove(),300)},3500)}

// ── State ────────────────────────────────────────────────────
const state={sessions:[]};

// ── Boot ─────────────────────────────────────────────────────
window.switchView=switchView;window.switchTab=switchTab;
(async function(){
  await ensureApiKey();wireNewRunForm();
  switchView("home");
  // Composer
  $("#composerInput")?.addEventListener("keydown",e=>{if(e.key==="Enter"){e.preventDefault();const v=$("#composerInput").value.trim();if(v){$("#composerInput").value="";/* TODO: follow-up message */}}});
  $("#closeRunBtn")?.addEventListener("click",()=>{if(_activeThread)_activeThread.closeStream();switchView("runs")});
  $("#pauseBtn")?.addEventListener("click",()=>controlAction("pause"));
  $("#resumeBtn")?.addEventListener("click",()=>controlAction("resume"));
  $("#cancelBtn")?.addEventListener("click",()=>controlAction("cancel"));
})();
