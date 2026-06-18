/* =====================================================
   NextGen Refactor — app.js  v2
   Layout: sidebar input + pipeline | output panel
   Chat: floating popup (Ask Expert button)
   Gates: non-blocking — pipeline continues automatically
   ===================================================== */

const API = '';
let jobId   = null;
let polling = false;

const $ = id => document.getElementById(id);

/* DOM refs */
const statusBadge    = $('status-badge');
const statusLabel    = $('status-label');
const pasteArea      = $('paste-area');
const charCount      = $('char-count');
const btnConvert     = $('btn-convert');
const btnClear       = $('btn-clear');
const dropZone       = $('drop-zone');
const fileInput      = $('file-input');
const fileList       = $('file-list');
const chatOutput     = $('chat-output');
const chatMsgs       = $('chat-msgs');          /* inline chat output (pipeline messages) */
const chatPopupMsgs  = $('chat-popup-msgs');    /* popup chat messages */
const chatInputEl    = $('chat-input');
const btnChatSend    = $('btn-chat-send');
const btnChatClear   = $('btn-chat-clear-history');
const analysisEl     = $('analysis-metrics');
const chatPopup      = $('chat-popup');
const btnChatToggle  = $('btn-chat-toggle');
const btnChatClose   = $('btn-chat-close');

let activeTab     = 'paste';
let uploadedFile  = null;
let chatBusy      = false;
let chatSessionId = null;
let _chatSeq      = 0;

const STEP_FOR_STATE = {
  ingesting:               'pl-ingest',
  phase1_running:          'pl-phase1',
  awaiting_plan_approval:  'pl-gateA',
  phase2_running:          'pl-phase2',
  phase3_running:          'pl-phase3',
  phase4_running:          'pl-phase4',
  awaiting_final_approval: 'pl-gateB',
  integrating:             'pl-integrate',
};
const STEP_ORDER = [
  'pl-ingest','pl-phase1','pl-gateA',
  'pl-phase2','pl-phase3','pl-phase4','pl-gateB','pl-integrate',
];

/* ───────── status bar ───────── */
function setStatus(state, text) {
  statusBadge.className = 'dhl-badge dhl-badge--' + state;
  statusLabel.textContent = text;
}

async function initSession() {
  setStatus('loading', 'Connecting…');
  try {
    const r = await fetch(`${API}/api/health`);
    if (!r.ok) throw new Error(await r.text());
    setStatus('online', 'Ready');
    updateUI();
  } catch (e) {
    setStatus('error', 'Server offline');
    console.error(e);
  }

  chatSessionId = loadSessionId();
  if (!chatSessionId) {
    try {
      const s = await postJSON(`${API}/api/session`, {});
      chatSessionId = s.session_id;
    } catch {
      chatSessionId = Math.random().toString(36).slice(2, 12);
    }
    saveSessionId(chatSessionId);
  }
  loadChatHistory();
}

/* ───────── tabs ───────── */
document.querySelectorAll('.dhl-tab').forEach(btn => {
  btn.addEventListener('click', () => {
    activeTab = btn.dataset.tab;
    document.querySelectorAll('.dhl-tab').forEach(b => b.classList.remove('dhl-tab--active'));
    document.querySelectorAll('.dhl-tab-panel').forEach(c => c.classList.remove('dhl-tab-panel--active'));
    btn.classList.add('dhl-tab--active');
    $('tab-' + activeTab).classList.add('dhl-tab-panel--active');
    updateUI();
  });
});

/* ───────── inputs ───────── */
pasteArea.addEventListener('input', () => {
  charCount.textContent = pasteArea.value.length.toLocaleString() + ' chars';
  updateUI();
});

dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dhl-drop-zone--dragover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dhl-drop-zone--dragover'));
dropZone.addEventListener('drop', e => {
  e.preventDefault(); dropZone.classList.remove('dhl-drop-zone--dragover');
  handleFiles([...e.dataTransfer.files]);
});
fileInput.addEventListener('change', () => handleFiles([...fileInput.files]));

function handleFiles(files) {
  const zip = files.find(f => f.name.toLowerCase().endsWith('.zip'));
  if (!zip) { showError('Please select a .zip archive.'); return; }
  uploadedFile = zip; renderFileList(); updateUI();
}
function renderFileList() {
  if (!uploadedFile) { fileList.innerHTML = ''; return; }
  fileList.innerHTML = `<div class="dhl-chip">&#128230; ${escHtml(uploadedFile.name)}
    <span style="color:var(--color-text-disabled);margin-left:4px">(${fmtSize(uploadedFile.size)})</span>
    <span class="dhl-chip__remove" title="Remove">&#10005;</span></div>`;
  fileList.querySelector('.dhl-chip__remove').addEventListener('click', () => {
    uploadedFile = null; fileInput.value = ''; renderFileList(); updateUI();
  });
}
function fmtSize(b) {
  if (b < 1024) return b + ' B';
  if (b < 1048576) return (b / 1024).toFixed(1) + ' KB';
  return (b / 1048576).toFixed(2) + ' MB';
}

['github-url', 'raw-url'].forEach(id => $(id).addEventListener('input', updateUI));

btnClear.addEventListener('click', () => {
  pasteArea.value = ''; charCount.textContent = '0 chars';
  uploadedFile = null; fileInput.value = ''; renderFileList();
  $('github-url').value = ''; $('raw-url').value = ''; $('pat-token').value = '';
  resetUI(); updateUI();
});

/* ───────── UI state ───────── */
function hasCode() {
  if (activeTab === 'paste')     return pasteArea.value.trim().length > 0;
  if (activeTab === 'upload')    return !!uploadedFile;
  if (activeTab === 'integrate') return !!$('github-url').value.trim();
  return false;
}

function updateUI() {
  btnConvert.disabled = !hasCode() || polling;
  btnChatToggle.disabled = !hasCode();
  btnChatSend.disabled = chatBusy || !chatInputEl.value.trim();
}

/* ───────── chat popup ───────── */
function openChatPopup()  { chatPopup.classList.add('dhl-chat-popup--open'); }
function closeChatPopup() { chatPopup.classList.remove('dhl-chat-popup--open'); }

btnChatToggle.addEventListener('click', openChatPopup);
btnChatClose.addEventListener('click',  closeChatPopup);

/* ───────── start migration ───────── */
btnConvert.addEventListener('click', async () => {
  resetUI();
  setStatus('loading', 'Creating job…');
  btnConvert.disabled = true;
  $('output-empty').style.display = 'none';

  try {
    const source = await buildSource();
    const d = await postJSON(`${API}/api/jobs`, { source, options: { target: 'zip' } });
    jobId = d.job_id;
    if (d.state === 'failed') throw new Error('Job failed during ingestion (input may not be Angular).');
    startPolling();
  } catch (e) {
    showError(e.message); setStatus('error', 'Error'); updateUI();
  }
});

async function buildSource() {
  if (activeTab === 'paste')  return { type: 'paste', content: pasteArea.value.trim() };
  if (activeTab === 'upload') return { type: 'zip', zip_b64: await fileToB64(uploadedFile) };
  return {
    type: 'git', repo_url: $('github-url').value.trim(),
    branch: $('raw-url').value.trim() || null,
    token: $('pat-token').value.trim() || null,
  };
}
function fileToB64(file) {
  return new Promise((res, rej) => {
    const r = new FileReader();
    r.onload  = () => res(r.result.split(',')[1]);
    r.onerror = rej;
    r.readAsDataURL(file);
  });
}

/* ───────── poll loop ───────── */
function startPolling() {
  polling = true;
  updateUI();
  poll();
}

async function poll() {
  if (!polling) return;
  let s;
  try {
    s = await getJSON(`${API}/api/jobs/${jobId}`);
  } catch (e) { showError(e.message); polling = false; updateUI(); return; }

  const jsEl = $('job-state'); if (jsEl) jsEl.textContent = prettyState(s.state);

  /* Don't clear the pipeline visual on terminal error states — leave the last
     active step visible so the user can see where the job stopped. */
  if (!['failed', 'rejected', 'cancelled'].includes(s.state)) {
    paintPipeline(s.state);
  }

  /* ── auto-hide gate panel when state advances past it ── */
  const gp = $('gate-panel');
  if (gp && gp.classList.contains('dhl-gate--show') &&
      !['awaiting_plan_approval', 'awaiting_final_approval'].includes(s.state)) {
    gp.classList.remove('dhl-gate--show');
  }

  /* ── Gate A — non-blocking: show review card, keep polling ── */
  if (s.state === 'awaiting_plan_approval') {
    await showAnalysisMetrics(jobId);
    await showGate('plan', 'phase1_report', 'Gate A — Plan Review');
    setStatus('loading', 'Plan ready — pipeline continues automatically…');
    setTimeout(poll, 2500);   /* keep polling — auto-gates resolve server-side */
    return;
  }

  /* ── Gate B — non-blocking ── */
  if (s.state === 'awaiting_final_approval') {
    await showGate('final', 'phase4_report', 'Gate B — Final Review');
    setStatus('loading', 'Final review — pipeline continues automatically…');
    setTimeout(poll, 2500);
    return;
  }

  if (s.state === 'completed') { polling = false; await showDone(); return; }

  if (['failed', 'rejected', 'cancelled'].includes(s.state)) {
    polling = false;
    showError(`Job ${s.state}` + (s.error_text ? `: ${s.error_text}` : ''));
    setStatus('error', prettyState(s.state));
    updateUI();
    return;
  }

  setStatus('loading', prettyState(s.state));
  setTimeout(poll, 1500);
}

function paintPipeline(state) {
  const activeId  = STEP_FOR_STATE[state];
  const activeIdx = STEP_ORDER.indexOf(activeId);
  STEP_ORDER.forEach((id, i) => {
    const el = $(id);
    if (!el) return;
    el.classList.remove('dhl-step--active', 'dhl-step--done');
    if (state === 'completed') { el.classList.add('dhl-step--done'); return; }
    if (activeIdx === -1) return;
    if (i < activeIdx)        el.classList.add('dhl-step--done');
    else if (i === activeIdx) el.classList.add('dhl-step--active');
  });
}

/* ───────── gate panel (non-blocking review card) ───────── */
async function showGate(gate, reportKey, title) {
  setStatus('online', 'Awaiting your review');
  let reportText = '(report not yet available)';
  try {
    const a = await getJSON(`${API}/api/jobs/${jobId}/artifacts/${reportKey}`);
    reportText = a.content.summary_md || JSON.stringify(a.content, null, 2);
  } catch { /* keep default */ }

  const gt = $('gate-title');    if (gt) gt.textContent = title;
  const gr = $('gate-report');   if (gr) gr.textContent = reportText;
  const gc = $('gate-comments'); if (gc) gc.value = '';
  const gpEl = $('gate-panel');  if (gpEl) gpEl.classList.add('dhl-gate--show');

  const btnApprove = $('btn-approve');
  const btnRevise  = $('btn-revise');
  const btnReject  = $('btn-reject');
  if (btnApprove) btnApprove.onclick = () => decide(gate, 'approve');
  if (btnRevise)  btnRevise.onclick  = () => {
    const gcEl = $('gate-comments');
    const c = gcEl ? gcEl.value.trim() : '';
    if (!c) { if (gcEl) gcEl.focus(); showError('Requesting changes requires a comment.'); return; }
    decide(gate, 'revise', c);
  };
  if (btnReject)  btnReject.onclick  = () => {
    const gcEl = $('gate-comments');
    decide(gate, 'reject', gcEl ? gcEl.value.trim() : '');
  };
}

async function decide(gate, decision, comments = '') {
  const gp = $('gate-panel'); if (gp) gp.classList.remove('dhl-gate--show');
  const eb = $('error-box');  if (eb) eb.classList.remove('dhl-error-box--show');
  setStatus('loading', 'Submitting decision…');
  try {
    await postJSON(`${API}/api/jobs/${jobId}/approvals/${gate}`, { decision, comments, actor: 'web' });
    if (!polling) startPolling();   /* only restart if background polling stopped */
  } catch (e) {
    /* 409 = gate already resolved server-side (auto-approved or already decided).
       Not an error — just resume polling so the UI catches up to the real state. */
    if (e.message && (e.message.includes('409') || e.message.includes('not awaiting'))) {
      if (!polling) startPolling();
      return;
    }
    showError(e.message);
    await showGate(gate,
      gate === 'plan' ? 'phase1_report' : 'phase4_report',
      gate === 'plan' ? 'Gate A — Plan Review' : 'Gate B — Final Review');
  }
}

/* ───────── completion ───────── */
async function showDone() {
  setStatus('online', 'Completed');
  paintPipeline('completed');
  const bd = $('btn-deliverable'); if (bd) bd.href = `${API}/api/jobs/${jobId}/deliverable`;

  let files = [];
  try { files = (await getJSON(`${API}/api/jobs/${jobId}/files`)).files || []; } catch {}

  let reportText = '';
  try {
    const r = await getJSON(`${API}/api/jobs/${jobId}/artifacts/report`);
    const c = r.content;
    if (typeof c === 'object') {
      const metrics = c.metrics || {};
      const qualityScore = c.quality_score;
      const validPassed  = c.validation_passed !== false;
      const qualityNote  = qualityScore !== undefined
        ? ` (quality score: ${qualityScore}/100${!validPassed ? ' — review recommendations' : ''})`
        : '';
      const statusLabel  = `SUCCESS${qualityNote}`;
      reportText = `# Migration Report\n\n`
        + `**Status:** ${statusLabel}\n\n`
        + `**Summary:** ${c.executive_summary || c.summary || ''}\n\n`
        + `## Metrics\n`
        + Object.entries(metrics).map(([k, v]) => `- ${k}: ${v}`).join('\n')
        + `\n\n## Recommendations\n`
        + (c.recommendations || c.next_steps || []).map((s, i) => `${i + 1}. ${s}`).join('\n')
        + (c.warnings?.length ? `\n\n## Warnings\n` + c.warnings.map(w => `- ${w}`).join('\n') : '');
    } else {
      reportText = String(c);
    }
  } catch {}

  const code  = files.filter(f => !f.is_test);
  const tests = files.filter(f => f.is_test);

  renderTree('files-code',  code,  'No React files generated.');
  renderTree('files-tests', tests, 'No test files generated.');
  $('files-docs').innerHTML = '';
  addTreeItem('files-docs', '&#128203; migration-report.md', reportText || 'Migration complete.', 'migration-report.md');

  const first = code[0] || tests[0];
  if (first) showFile(first.path, first.content);
  else if (reportText) showFile('migration-report.md', reportText);

  const dp = $('done-panel'); if (dp) dp.classList.add('dhl-done--show');
  updateUI();
}

function renderTree(containerId, files, emptyMsg) {
  const el = $(containerId);
  el.innerHTML = '';
  if (!files.length) { el.innerHTML = `<div class="dhl-meta">${emptyMsg}</div>`; return; }
  files.forEach(f => addTreeItem(containerId, '&#128196; ' + f.path + ` (${f.lines}L)`, f.content, f.path));
}
function addTreeItem(containerId, label, content, name) {
  const item = document.createElement('div');
  item.className = 'dhl-file-item';
  item.innerHTML = label;
  item.addEventListener('click', () => {
    document.querySelectorAll('.dhl-file-item').forEach(x => x.classList.remove('dhl-file-item--active'));
    item.classList.add('dhl-file-item--active');
    showFile(name, content);
  });
  $(containerId).appendChild(item);
}
function showFile(name, content) {
  $('viewer-name').textContent = name;
  $('viewer-body').textContent = content;
}

/* ───────── http helpers ───────── */
async function postJSON(url, body) {
  const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  return parse(r);
}
async function getJSON(url) { return parse(await fetch(url)); }
async function parse(r) {
  let d; try { d = await r.json(); } catch { d = {}; }
  if (!r.ok) throw new Error(d.detail || `HTTP ${r.status} ${r.statusText}`);
  return d;
}

/* ───────── ui state helpers ───────── */
function resetUI() {
  const gp = $('gate-panel');   if (gp) gp.classList.remove('dhl-gate--show');
  const dp = $('done-panel');   if (dp) dp.classList.remove('dhl-done--show');
  const eb = $('error-box');    if (eb) eb.classList.remove('dhl-error-box--show');
  if (analysisEl) analysisEl.classList.remove('dhl-analysis-metrics--show');
  if (chatOutput) chatOutput.classList.remove('dhl-chat-output--show');
  const oe = $('output-empty'); if (oe) oe.style.display = '';
  const js = $('job-state');    if (js) js.textContent = '';
  STEP_ORDER.forEach(id => { const el = $(id); if (el) el.classList.remove('dhl-step--active', 'dhl-step--done'); });
}
function showError(msg) {
  const em = $('error-msg'); if (em) em.textContent = msg;
  const eb = $('error-box'); if (eb) eb.classList.add('dhl-error-box--show');
}
function prettyState(s) {
  return ({
    ingesting: 'Ingesting…',
    phase1_running: 'Phase 1 — analyzing…',
    awaiting_plan_approval: 'Gate A — plan ready for review',
    phase2_running: 'Phase 2 — transforming…',
    phase3_running: 'Phase 3 — generating tests…',
    phase4_running: 'Phase 4 — validating…',
    awaiting_final_approval: 'Gate B — final review ready',
    integrating: 'Assembling deliverable…',
    completed: 'Completed',
    failed: 'Failed',
    rejected: 'Rejected',
    cancelled: 'Cancelled',
  })[s] || s;
}
function escHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/* ═══════════════════════════════════════════════════════════
   CHAT PERSISTENCE
   ═══════════════════════════════════════════════════════════ */
const CHAT_STORAGE_KEY   = 'ngreact_chat_history';
const SESSION_STORAGE_KEY = 'ngreact_session_id';

function saveChatMessage(role, text) {
  try {
    const history = JSON.parse(localStorage.getItem(CHAT_STORAGE_KEY) || '[]');
    history.push({ role, text, timestamp: Date.now() });
    localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(history));
  } catch { /* storage not available */ }
}
function loadChatHistory() {
  try {
    const history = JSON.parse(localStorage.getItem(CHAT_STORAGE_KEY) || '[]');
    if (!history.length) return;
    const welcome = chatPopupMsgs.querySelector('.dhl-chat-welcome');
    if (welcome) welcome.remove();
    history.forEach(msg => _appendMsg(msg.role, msg.text, false));
  } catch { /* ignore */ }
}
function clearChatHistory() {
  try {
    localStorage.removeItem(CHAT_STORAGE_KEY);
    localStorage.removeItem(SESSION_STORAGE_KEY);
  } catch { /* ignore */ }
}
function saveSessionId(id) {
  try { localStorage.setItem(SESSION_STORAGE_KEY, id); } catch { /* ignore */ }
}
function loadSessionId() {
  try { return localStorage.getItem(SESSION_STORAGE_KEY); } catch { return null; }
}

/* ═══════════════════════════════════════════════════════════
   CHAT — migration-scoped popup
   ═══════════════════════════════════════════════════════════ */

function buildChatMessage(query) {
  if (activeTab === 'paste' && pasteArea.value.trim()) {
    return `[Angular source code provided by the user]\n\n${pasteArea.value.trim()}\n\n---\n\n${query}`;
  }
  if (activeTab === 'upload' && uploadedFile) {
    return `[User has uploaded Angular project zip: ${uploadedFile.name} (${fmtSize(uploadedFile.size)})]\n\n---\n\n${query}`;
  }
  if (activeTab === 'integrate' && $('github-url').value.trim()) {
    const repo   = $('github-url').value.trim();
    const branch = $('raw-url').value.trim();
    return `[Angular project from git: ${repo}${branch ? ' branch: ' + branch : ''}]\n\n---\n\n${query}`;
  }
  return query;
}

/* Suggestion chips */
document.querySelectorAll('.dhl-suggestion').forEach(btn => {
  btn.addEventListener('click', () => {
    chatInputEl.value = btn.dataset.query || '';
    chatInputEl.focus();
    updateUI();
  });
});

chatInputEl.addEventListener('input', updateUI);
chatInputEl.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); doSendChat(); }
});
btnChatSend.addEventListener('click', doSendChat);

btnChatClear.addEventListener('click', () => {
  clearChatHistory();
  chatPopupMsgs.innerHTML = `
    <div class="dhl-chat-welcome">
      <div class="dhl-chat-welcome__icon">&#128172;</div>
      <p>Ask about migration analysis, transformation decisions, risks, or recommendations.</p>
    </div>`;
});

async function doSendChat() {
  const query = chatInputEl.value.trim();
  if (!query || chatBusy) return;

  chatBusy = true;
  btnChatSend.disabled = true;
  chatInputEl.value = '';

  _appendMsg('user', query);
  saveChatMessage('user', query);
  const thinkId = _appendMsg('agent', 'Thinking… (may take 5-10 seconds)', true);

  const fullMessage = buildChatMessage(query);

  try {
    const controller = new AbortController();
    const tid = setTimeout(() => controller.abort(), 120000);
    const r = await fetch(`${API}/api/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: fullMessage, session_id: chatSessionId, job_id: jobId || '' }),
      signal: controller.signal,
    });
    clearTimeout(tid);

    if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`);
    const res = await r.json();
    _removeMsg(thinkId);
    const response = res.response || '(no response)';
    _appendMsg('agent', response);
    saveChatMessage('agent', response);
    if (res.session_id) { chatSessionId = res.session_id; saveSessionId(chatSessionId); }
  } catch (e) {
    _removeMsg(thinkId);
    const msg = e.name === 'AbortError' ? 'Request timed out (120s)' : e.message;
    _appendMsg('agent', msg);
    saveChatMessage('agent', msg);
  } finally {
    chatBusy = false;
    updateUI();
  }
}

function _appendMsg(role, text, thinking = false) {
  const welcome = chatPopupMsgs.querySelector('.dhl-chat-welcome');
  if (welcome) welcome.remove();

  const id  = 'cmsg-' + (++_chatSeq);
  const div = document.createElement('div');
  div.id        = id;
  div.className = `dhl-chat-msg dhl-chat-msg--${role}${thinking ? ' dhl-chat-msg--thinking' : ''}`;
  div.innerHTML = `
    <div class="dhl-chat-msg__label">${role === 'user' ? 'You' : 'Migration Expert'}</div>
    <div class="dhl-chat-msg__bubble">${escHtml(text)}</div>`;
  chatPopupMsgs.appendChild(div);
  chatPopupMsgs.scrollTop = chatPopupMsgs.scrollHeight;
  return id;
}
function _removeMsg(id) { const el = $(id); if (el) el.remove(); }

/* ═══════════════════════════════════════════════════════════
   ANALYSIS METRICS — Phase 1 results
   ═══════════════════════════════════════════════════════════ */
async function showAnalysisMetrics(jId) {
  try {
    const a = await getJSON(`${API}/api/jobs/${jId}/artifacts/phase1_report`);
    if (!a || !a.content) return;
    renderMetrics(a.content);
    if (analysisEl) analysisEl.classList.add('dhl-analysis-metrics--show');
  } catch { /* artifact not ready */ }
}

function renderMetrics(report) {
  const body     = $('metrics-body');
  body.innerHTML = '';

  const analysis = report.analysis_report || report.stages?.[0]?.output || report;
  const risk     = report.risk_report     || report.stages?.[1]?.output || {};
  const plan     = report.migration_plan  || report.stages?.[2]?.output || {};
  const state    = report.state_plan      || report.stages?.[3]?.output || {};

  const counters = [
    { label: 'Components',  value: _pick(analysis, ['component_count', 'components']) },
    { label: 'Services',    value: _pick(analysis, ['service_count', 'services']) },
    { label: 'Routes',      value: _pick(analysis, ['route_count', 'routes']) },
    { label: 'Modules',     value: _pick(analysis, ['module_count', 'modules']) },
    { label: 'Directives',  value: _pick(analysis, ['directive_count', 'directives']) },
    { label: 'Pipes',       value: _pick(analysis, ['pipe_count', 'pipes']) },
    { label: 'Guards',      value: _pick(analysis, ['guard_count', 'guards']) },
    { label: 'Files',       value: _pick(analysis, ['total_files', 'file_count']) },
    { label: 'Lines',       value: _fmtNum(_pick(analysis, ['total_lines', 'lines_count'])) },
    { label: 'Chunks',      value: _pick(plan, ['chunk_count', 'chunks']) },
  ];

  const riskScore = risk.overall_score ?? risk.risk_score ?? risk.score;
  if (riskScore !== undefined) {
    const cls = riskScore >= 7 ? 'dhl-metric-card--red' : riskScore >= 4 ? 'dhl-metric-card--amber' : 'dhl-metric-card--green';
    counters.push({ label: 'Risk score', value: riskScore, cls });
  }
  const effort = plan.estimated_days ?? plan.effort_days ?? plan.duration_days;
  if (effort !== undefined) counters.push({ label: 'Est. days', value: effort });
  const ngVersion = analysis.angular_version ?? analysis.ng_version;
  if (ngVersion) counters.push({ label: 'Angular', value: ngVersion });
  const stateApproach = state.approach ?? state.strategy ?? state.state_strategy;
  if (stateApproach) counters.push({ label: 'State', value: stateApproach });

  body.innerHTML = counters.map(m =>
    `<div class="dhl-metric-card${m.cls ? ' ' + m.cls : ''}">
       <div class="dhl-metric-card__value">${m.value ?? '—'}</div>
       <div class="dhl-metric-card__label">${m.label}</div>
     </div>`
  ).join('');

  const stages = report.stages || [];
  if (stages.length) {
    const rows = stages.map(st => {
      const ok    = ['completed', 'success', 'done'].includes((st.status || '').toLowerCase());
      const agent = st.agent || st.stage || '—';
      const toks  = st.tokens_in != null ? `${_fmtNum(st.tokens_in)} / ${_fmtNum(st.tokens_out)}` : '';
      const dur   = st.duration_s != null ? `${(+st.duration_s).toFixed(1)}s` : '';
      return `<div class="dhl-stage-row dhl-stage-row--${ok ? 'ok' : 'fail'}">
        <span class="dhl-stage-row__agent">${escHtml(agent)}</span>
        <span class="dhl-stage-row__status">${ok ? 'done' : st.status || 'failed'}</span>
        ${toks ? `<span class="dhl-stage-row__tokens">${toks}</span>` : ''}
        ${dur  ? `<span class="dhl-stage-row__tokens">${dur}</span>` : ''}
      </div>`;
    }).join('');
    body.insertAdjacentHTML('beforeend', `
      <div class="dhl-metrics-stages" style="grid-column:1/-1">
        <div class="dhl-metrics-stages__title">Agents invoked</div>${rows}
      </div>`);
  }

  const risks = risk.risks || risk.identified_risks || [];
  if (risks.length) {
    const items = risks.slice(0, 4).map(r => {
      const sev = (r.severity || '').toLowerCase();
      const cls = sev === 'high' || sev === 'critical' ? 'dhl-risk-item--high' : sev === 'low' ? 'dhl-risk-item--low' : '';
      const desc = typeof r === 'string' ? r : (r.description || r.message || JSON.stringify(r));
      return `<div class="dhl-risk-item ${cls}">${escHtml(desc)}</div>`;
    }).join('');
    body.insertAdjacentHTML('beforeend', `
      <div class="dhl-metrics-risks" style="grid-column:1/-1">
        <div class="dhl-metrics-risks__title">Top risks</div>${items}
      </div>`);
  }
}

function _pick(obj, keys) {
  if (!obj || typeof obj !== 'object') return undefined;
  for (const k of keys) {
    const v = obj[k];
    if (v === null || v === undefined) continue;
    if (Array.isArray(v)) return v.length;
    return v;
  }
  return undefined;
}
function _fmtNum(n) {
  if (n === undefined || n === null) return undefined;
  return Number(n).toLocaleString();
}

$('btn-metrics-toggle').addEventListener('click', () => {
  const body = $('metrics-body');
  const btn  = $('btn-metrics-toggle');
  if (body.style.display === 'none') { body.style.display = ''; btn.textContent = '▲ Collapse'; }
  else { body.style.display = 'none'; btn.textContent = '▼ Expand'; }
});

/* ═══════════════════════════════════════════════════════════
   TEST REPORT DOWNLOAD
   ═══════════════════════════════════════════════════════════ */
$('btn-test-report').addEventListener('click', async () => {
  const btn = $('btn-test-report');
  const orig = btn.textContent;
  btn.textContent = 'Fetching…';
  btn.disabled = true;

  try {
    /* Use job-specific report when a migration is active; otherwise the static pytest report */
    const reportUrl  = jobId ? `${API}/api/jobs/${jobId}/test-report` : `${API}/api/test-report/xlsx`;
    const reportName = jobId ? `${jobId}_test_report.xlsx` : 'ngreact_test_report.xlsx';

    const r = await fetch(reportUrl);
    if (r.status === 404) {
      showError(jobId
        ? 'Test report not ready — wait for Phase 3 (test generation) to complete.'
        : 'Test report not found. Run:  pytest tests/  to generate it.');
      return;
    }
    if (!r.ok) {
      const bd = await r.json().catch(() => ({}));
      throw new Error(bd.detail || `HTTP ${r.status}`);
    }
    const blob = await r.blob();
    const blobUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = blobUrl; a.download = reportName;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(blobUrl);
    btn.textContent = 'Downloaded';
    setTimeout(() => { btn.textContent = orig; }, 2500);
  } catch (e) {
    showError('Test report download failed: ' + e.message);
  } finally {
    btn.disabled = false;
    if (btn.textContent === 'Fetching…') btn.textContent = orig;
  }
});

/* ───────── boot ───────── */
initSession();
