const BASE_PATH = (() => {
  const p = window.location.pathname;
  if (p.startsWith('/model-verification')) return '/model-verification';
  if (p.startsWith('/monas')) return '/monas';
  return '';
})();

// Path calls are always `/api/...`. Under BASE_PATH Apache proxies
// `/model-verification/api` → API port `/api`.
const API = (() => {
  const { hostname, port } = window.location;
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return 'http://127.0.0.1:8028';
  }
  if (BASE_PATH) {
    return `${window.location.origin}${BASE_PATH}`;
  }
  return port ? `${window.location.protocol}//${hostname}:8028` : `http://${hostname}:8028`;
})();

const INIT_DASHES = [
  [],                 // terbaru: solid
  [10, 5],
  [3, 4],
  [12, 4, 2, 4],
  [2, 3],
  [14, 4, 2, 4, 2, 4],
];
const INIT_MARKERS = ['circle', 'square', 'diamond', 'triangle', 'circle', 'square'];

const MODEL_COLORS = {
  Observasi: '#ca8a04',
  InaNWP: '#ea580c',
  InaCAWO: '#16a34a',
  GFS: '#dc2626',
  IFS: '#7c3aed',
};

let rankingChart, scoreChart, stationChart, stationMap;
let paramsMeta = {};
let paramsAvailableByModel = {};
let paramsUnavailableNotes = {};
let maxLeadTime = 168;
let modelSources = { InaNWP: 'real', InaCAWO: 'dummy', GFS: 'dummy', IFS: 'dummy' };
let cartoApiKey = '';
let mapBulkCache = { key: '', data: null };
let stationDetailCache = { key: '', data: null };
let leadPlayTimer = null;
const LEAD_PLAY_MS = 800;
let currentMethod = 'harp';
let currentEngine = null; // null until user picks: harp | metplus
let currentVerifier = null; // null | gsmap | stations (METplus only)
let dashboardReady = false;
const FLOW_STORAGE_KEY = 'mv_flow_v1';

const TECHNIQUES_BY_VERIFIER = {
  gsmap: [
    { id: 'metplus', label: 'GridStat (spatial)' },
    { id: 'metplus_fss', label: 'FSS (neighborhood)' },
    { id: 'metplus_mode', label: 'MODE (object-based)' },
  ],
  stations: [
    { id: 'metplus_point', label: 'PointStat (BMKG stations)' },
  ],
};

function selectedEngine() {
  const el = document.getElementById('methodSelect');
  return currentEngine || (el && el.value) || 'harp';
}

function selectedVerifier() {
  return currentVerifier;
}

/** Internal API method id: harp | metplus | metplus_point | metplus_fss | metplus_mode */
function selectedMethod() {
  const engine = selectedEngine();
  if (engine === 'harp') return 'harp';
  const sub = document.getElementById('metplusSubmethod');
  return (sub && sub.value) || (currentVerifier === 'stations' ? 'metplus_point' : 'metplus');
}

function isMetplusMethod(m = selectedMethod()) {
  return String(m || '').startsWith('metplus');
}

function methodQ(extra = '') {
  const q = `method=${encodeURIComponent(selectedMethod())}`;
  // Hanya buang ?/& di AWAL extra · jangan hapus & di tengah (bug: models=InaNWPscore=rmse)
  const rest = String(extra || '').replace(/^[?&]+/, '');
  return rest ? `${q}&${rest}` : q;
}

function saveFlowState() {
  try {
    sessionStorage.setItem(FLOW_STORAGE_KEY, JSON.stringify({
      engine: currentEngine,
      verifier: currentVerifier,
      technique: selectedMethod(),
    }));
  } catch (_) { /* ignore */ }
}

function loadFlowState() {
  try {
    const raw = sessionStorage.getItem(FLOW_STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch (_) {
    return null;
  }
}

function clearFlowState() {
  try { sessionStorage.removeItem(FLOW_STORAGE_KEY); } catch (_) { /* ignore */ }
}

function fillTechniqueSelect(verifier, preferredId) {
  const sel = document.getElementById('metplusSubmethod');
  if (!sel) return;
  const list = TECHNIQUES_BY_VERIFIER[verifier] || [];
  sel.innerHTML = list.map(t => `<option value="${t.id}">${t.label}</option>`).join('');
  if (preferredId && list.some(t => t.id === preferredId)) {
    sel.value = preferredId;
  } else if (list[0]) {
    sel.value = list[0].id;
  }
}

function updateSessionBadge() {
  const badge = document.getElementById('sessionBadge');
  const hint = document.getElementById('methodHint');
  const sub = document.getElementById('headerSubtitle');
  if (!badge) return;
  if (currentEngine === 'harp') {
    badge.textContent = 'HARP · Soft / Sinoptik';
    if (hint) hint.textContent = 'Station-point scores against BMKG Soft or Sinoptik.';
    if (sub) sub.textContent = 'HARP (station points) · Instrument Standardization Center MKG';
  } else if (currentEngine === 'metplus' && currentVerifier === 'gsmap') {
    badge.textContent = `METplus · GSMAP · ${methodLabel(selectedMethod())}`;
    if (hint) hint.textContent = 'GSMaP verifier: GridStat, FSS, and MODE against satellite rain.';
    if (sub) sub.textContent = 'METplus · GSMaP verifier · Instrument Standardization Center MKG';
  } else if (currentEngine === 'metplus' && currentVerifier === 'stations') {
    badge.textContent = 'METplus · BMKG stations · PointStat';
    if (hint) hint.textContent = 'PointStat Soft multi-param (temp, RH, QFF, wind, rain). Same Soft obs as HARP.';
    if (sub) sub.textContent = 'METplus · BMKG station verifier · Instrument Standardization Center MKG';
  } else {
    badge.textContent = '-';
  }
}

function applyTabVisibility() {
  const engine = selectedEngine();
  const verifier = selectedVerifier();
  document.querySelectorAll('#mainTabs .tab').forEach(btn => {
    const tab = btn.dataset.tab;
    let show = true;
    if (engine === 'harp') {
      // HARP: overview, scores, map, station, method · tanpa spatial
      show = ['overview', 'scores', 'map', 'station', 'method'].includes(tab);
    } else if (engine === 'metplus' && verifier === 'gsmap') {
      // GSMAP: overview, scores, spatial, method
      show = ['overview', 'scores', 'spatial', 'method'].includes(tab);
    } else if (engine === 'metplus' && verifier === 'stations') {
      // Stasiun BMKG / PointStat: overview, scores, station detail, method
      show = ['overview', 'scores', 'station', 'method'].includes(tab);
    } else {
      show = false;
    }
    btn.hidden = !show;
  });
  const active = document.querySelector('#mainTabs .tab.active');
  if (!active || active.hidden) {
    const first = document.querySelector('#mainTabs .tab:not([hidden])');
    if (first) {
      document.querySelectorAll('#mainTabs .tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
      first.classList.add('active');
      const panel = document.getElementById(first.dataset.tab);
      if (panel) panel.classList.add('active');
    }
  }
}

function showGateOnly() {
  document.getElementById('flowGate').hidden = false;
  document.getElementById('verifierGate').hidden = true;
  document.getElementById('appLayout').hidden = true;
  const sub = document.getElementById('headerSubtitle');
  if (sub) sub.textContent = 'Choose a verification engine to begin · Instrument Standardization Center MKG';
  document.getElementById('pipelineStatus').textContent = 'Choose an engine above to begin…';
}

function showVerifierGate() {
  document.getElementById('flowGate').hidden = true;
  document.getElementById('verifierGate').hidden = false;
  document.getElementById('appLayout').hidden = true;
  const sub = document.getElementById('headerSubtitle');
  if (sub) sub.textContent = 'METplus · pick an observation source · Instrument Standardization Center MKG';
}

async function enterDashboard({ engine, verifier = null, technique = null }) {
  currentEngine = engine;
  currentVerifier = engine === 'metplus' ? verifier : null;
  const methodSel = document.getElementById('methodSelect');
  if (methodSel) methodSel.value = engine === 'metplus' ? 'metplus' : 'harp';

  const techSec = document.getElementById('techniqueSection');
  if (engine === 'metplus') {
    fillTechniqueSelect(verifier, technique);
    if (techSec) techSec.hidden = (TECHNIQUES_BY_VERIFIER[verifier] || []).length <= 1;
  } else {
    if (techSec) techSec.hidden = true;
  }

  currentMethod = selectedMethod();
  document.getElementById('flowGate').hidden = true;
  document.getElementById('verifierGate').hidden = true;
  document.getElementById('appLayout').hidden = false;

  updateSessionBadge();
  applyMethodUi();
  applyTabVisibility();
  saveFlowState();

  if (!dashboardReady) {
    await bootstrapDashboard();
    dashboardReady = true;
  } else {
    await onSessionChanged();
  }
}

async function onSessionChanged() {
  const metricEl = document.getElementById('scoreMetric');
  if (metricEl) {
    if (selectedMethod() === 'metplus_fss') metricEl.value = 'fss';
    else if (selectedMethod() === 'metplus_mode') metricEl.value = 'ets';
    else if (isMetplusMethod() && metricEl.value === 'fss') metricEl.value = 'rmse';
  }
  mapBulkCache.key = '';
  stationDetailCache.key = '';
  document.querySelectorAll('.panel .error').forEach(el => el.remove());
  try {
    await loadModelSources();
    await reloadParameters();
    await loadCycles();
    await loadPipelineStatus();
    updateSidebarForTab(document.querySelector('.tab.active')?.dataset.tab || 'overview');
    await refreshAll();
  } catch (e) {
    console.warn('session change', e);
  }
}

function syncMethodUiFromApi(methodId) {
  // Dipakai hanya jika session sudah aktif; jangan override gate
  if (!currentEngine) return;
  const m = String(methodId || 'harp').toLowerCase();
  if (m === 'harp') {
    currentEngine = 'harp';
    currentVerifier = null;
    currentMethod = 'harp';
  } else if (m.startsWith('metplus')) {
    currentEngine = 'metplus';
    currentVerifier = (m === 'metplus_point') ? 'stations' : 'gsmap';
    fillTechniqueSelect(currentVerifier, m);
    currentMethod = selectedMethod();
  }
  updateSessionBadge();
  applyMethodUi();
  applyTabVisibility();
}

function applyMethodUi() {
  const m = selectedMethod();
  currentMethod = m;
  const lt = document.getElementById('leadTime');
  const spatialHint = document.getElementById('spatialHint');
  if (spatialHint) {
    spatialHint.textContent = m === 'metplus_fss'
      ? 'FSS neighborhood scores vs GSMaP by lead. GridStat maps appear below when available.'
      : m === 'metplus_mode'
        ? 'MODE object scores vs GSMaP (interest and object counts). GridStat maps appear below when available.'
        : 'METplus grid pair maps (forecast, observation, difference) against GSMaP.';
  }
  if (isMetplusMethod(m)) {
    maxLeadTime = 72;
    if (lt) { lt.max = 72; lt.step = 3; if (+lt.value > 72) lt.value = 12; }
  } else {
    maxLeadTime = 168;
    if (lt) { lt.max = 168; lt.step = 3; }
  }
  applyLeadTime(lt ? +lt.value : 12, { refresh: false });
  updateSessionBadge();
}

async function api(path, opts = {}) {
  const res = await fetch(`${API}${path}`, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

function selectedModels() { return [...document.querySelectorAll('.model-cb:checked')].map(el => el.value); }
function modelsQuery() { return selectedModels().join(','); }
function requireModels(emptyHtmlId, emptyMsg) {
  if (selectedModels().length) return true;
  if (emptyHtmlId) {
    const el = document.getElementById(emptyHtmlId);
    if (el) el.innerHTML = emptyMsg || 'Select at least one model in the sidebar.';
  }
  return false;
}

/** Param tersedia jika ≥1 model tercentang punya field NC-nya (InaNWP asim list).
 *  Jika API belum kirim available_by_model (backend lama / belum restart), jangan kunci UI. */
function paramAvailableForSelection(param) {
  const models = selectedModels();
  if (!models.length) return true;
  const known = models.filter(m => Array.isArray(paramsAvailableByModel[m]));
  if (!known.length) return true;
  return known.some(m => paramsAvailableByModel[m].includes(param));
}

function refreshParameterOptions() {
  const sel = document.getElementById('parameter');
  if (!sel || !Object.keys(paramsMeta).length) return;
  const prev = sel.value;
  const notes = paramsUnavailableNotes.InaNWP || {};
  sel.innerHTML = Object.entries(paramsMeta).map(([k, v]) => {
    const ok = paramAvailableForSelection(k);
    const hint = !ok && notes[k] ? ` (not in NC)` : (!ok ? ' (not in model NC)' : '');
    return `<option value="${k}" ${ok ? '' : 'disabled'}>${v.label} (${v.unit})${hint}</option>`;
  }).join('');
  if (prev && [...sel.options].some(o => o.value === prev && !o.disabled)) {
    sel.value = prev;
  } else {
    const first = [...sel.options].find(o => !o.disabled);
    if (first) sel.value = first.value;
  }
}
function selectedInitTime() { return document.getElementById('initCycle').value || ''; }

function formatLeadTime(h) {
  if (h === 0) return 'D+0 (analysis)';
  if (h < 24) return `D+${(h / 24).toFixed(1)} (${h} h)`;
  return `D+${(h / 24).toFixed(1)} (${h} h)`;
}

/** UTC ISO → teks WIB (Asia/Jakarta, UTC+7). */
function formatTimeWIB(isoUtc) {
  if (!isoUtc) return '·';
  const s = String(isoUtc).endsWith('Z') ? isoUtc : `${isoUtc}Z`;
  try {
    return new Date(s).toLocaleString('id-ID', {
      timeZone: 'Asia/Jakarta',
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }) + ' WIB';
  } catch {
    return String(isoUtc).slice(0, 16);
  }
}

function formatTimeDual(isoUtc) {
  if (!isoUtc) return '·';
  const utc = String(isoUtc).replace('Z', '').slice(0, 16).replace('T', ' ');
  return `${formatTimeWIB(isoUtc)} <span class="time-utc">(${utc} UTC)</span>`;
}

function nearestLeadTime(available, target) {
  if (!available?.length) return null;
  let best = available[0];
  let bestD = Math.abs(best - target);
  for (const lt of available) {
    const d = Math.abs(lt - target);
    if (d < bestD) { best = lt; bestD = d; }
  }
  return best;
}

async function loadPublicConfig() {
  try {
    const cfg = await api('/api/config/public');
    cartoApiKey = (cfg.carto_api_key || '').trim();
    if (stationMap) stationMap.setCartoKey(cartoApiKey);
  } catch (e) {
    console.warn('public config', e);
  }
}

const SCORE_METRICS = {
  rmse: { label: 'RMSE', lowerBetter: true },
  mae: { label: 'MAE', lowerBetter: true },
  bias: { label: 'Bias', lowerBetter: true },
  stde: { label: 'stde', lowerBetter: true },
  correlation: { label: 'Correlation (r)', lowerBetter: false },
  csi: { label: 'CSI', lowerBetter: false },
  ets: { label: 'ETS', lowerBetter: false },
  fss: { label: 'FSS', lowerBetter: false },
};

function selectedScoreMetric() {
  const el = document.getElementById('scoreMetric');
  const v = el?.value || 'rmse';
  return SCORE_METRICS[v] ? v : 'rmse';
}

function initCharts() {
  rankingChart = new MonasChart('rankingChart');
  scoreChart = new MonasChart('scoreChart', {
    onClick(hit) {
      if (hit.type !== 'pt' || !hit.extra) return;
      const ex = hit.extra;
      const metric = selectedScoreMetric();
      const metricLabel = SCORE_METRICS[metric]?.label || metric;
      document.getElementById('scoreDetail').innerHTML =
        `<strong>${hit.series}</strong> · ${formatLeadTime(+hit.x)}<br>
         ${metricLabel}: <strong>${hit.y.toFixed(4)}</strong> ·
         RMSE: ${ex.rmse?.toFixed(4) ?? '·'} · Bias: ${ex.bias?.toFixed(4) ?? '·'} ·
         MAE: ${ex.mae?.toFixed(4) ?? '·'} · stde: ${ex.stde?.toFixed(4) ?? '·'} ·
         r: ${ex.correlation?.toFixed(4) ?? '·'} · N: ${ex.n_cases ?? '·'}`;
    },
  });
  stationChart = new MonasChart('stationChart', { zoomable: true });
  document.getElementById('chartZoomIn')?.addEventListener('click', () => stationChart.zoomBy(0.7));
  document.getElementById('chartZoomOut')?.addEventListener('click', () => stationChart.zoomBy(1.35));
  document.getElementById('chartZoomReset')?.addEventListener('click', () => stationChart.resetZoom());
  stationMap = new StationCanvasMap('leafletMap', {
    cartoKey: cartoApiKey,
    onStationClick(st) {
      showStationMapDetail(st);
    },
  });
}

async function bootstrapDashboard() {
  initCharts();
  if (cartoApiKey && stationMap) stationMap.setCartoKey(cartoApiKey);
  try {
    await reloadParameters();
  } catch (e) {
    document.getElementById('pipelineStatus').textContent =
      `Failed to load /api/parameters (${API}): ${e.message}`;
    console.error('parameters', e);
    return;
  }
  try {
    const stations = await api('/api/stations');
    document.getElementById('stationSelect').innerHTML = stations.map(s =>
      `<option value="${s.station_id}">${s.station_id} · ${s.name || s.station_id}</option>`).join('');
  } catch (e) {
    console.warn('stations', e);
  }
  await loadCycles();
  await loadPipelineStatus();
  await loadModelSources();
  bindEvents();
  updateSidebarForTab(document.querySelector('.tab.active')?.dataset.tab || 'overview');
  await refreshAll();
  setInterval(loadPipelineStatus, 300000);
}

async function init() {
  await loadPublicConfig();
  bindFlowEvents();

  const saved = loadFlowState();
  if (saved?.engine === 'harp') {
    await enterDashboard({ engine: 'harp' });
  } else if (saved?.engine === 'metplus' && (saved.verifier === 'gsmap' || saved.verifier === 'stations')) {
    await enterDashboard({
      engine: 'metplus',
      verifier: saved.verifier,
      technique: saved.technique,
    });
  } else {
    showGateOnly();
  }
}

function bindFlowEvents() {
  document.getElementById('pickHarp')?.addEventListener('click', () => {
    enterDashboard({ engine: 'harp' });
  });
  document.getElementById('pickMetplus')?.addEventListener('click', () => {
    currentEngine = 'metplus';
    showVerifierGate();
  });
  document.getElementById('pickGsmap')?.addEventListener('click', () => {
    enterDashboard({ engine: 'metplus', verifier: 'gsmap', technique: 'metplus' });
  });
  document.getElementById('pickStations')?.addEventListener('click', () => {
    enterDashboard({ engine: 'metplus', verifier: 'stations', technique: 'metplus_point' });
  });
  document.getElementById('backToEngine')?.addEventListener('click', () => {
    currentEngine = null;
    currentVerifier = null;
    clearFlowState();
    showGateOnly();
  });
  document.getElementById('changeMethodBtn')?.addEventListener('click', () => {
    currentEngine = null;
    currentVerifier = null;
    clearFlowState();
    showGateOnly();
  });
  document.getElementById('navMethods')?.addEventListener('click', (e) => {
    e.preventDefault();
    openMethodsPanel();
  });
  document.getElementById('openMethodsFromGate')?.addEventListener('click', (e) => {
    e.preventDefault();
    openMethodsPanel();
  });
  document.getElementById('navHome')?.addEventListener('click', (e) => {
    e.preventDefault();
    currentEngine = null;
    currentVerifier = null;
    clearFlowState();
    showGateOnly();
    document.getElementById('flowGate')?.scrollIntoView({ behavior: 'smooth' });
  });
}

async function loadModelSources() {
  try {
    const data = await api(`/api/models/sources?${methodQ()}`);
    modelSources = data.sources || modelSources;
    document.querySelectorAll('.model-cb').forEach(cb => {
      const badge = cb.parentElement.querySelector('.badge');
      if (!badge) return;
      const src = modelSources[cb.value] || 'real';
      badge.textContent = src;
      badge.className = `badge ${src}`;
      if (src === 'none') {
        cb.checked = false;
      } else if (src === 'real') {
        // Pastikan model REAL selalu tercentang (HARP & METplus) agar overview tidak kosong
        cb.checked = true;
      }
    });
    refreshParameterOptions();
  } catch (e) { console.warn('model sources', e); }
}

function modelBadge(model) {
  const src = modelSources[model] || 'real';
  return `<span class="badge ${src}">${src}</span>`;
}

async function loadMethodology() {
  const el = document.getElementById('harpMethodology');
  if (!el) return;
  const focus = selectedMethod();
  try {
    const data = await api(`/api/methodology?method=${encodeURIComponent(focus)}`);
    el.innerHTML = renderMethodologyHtml(data, focus);
  } catch (e) {
    el.innerHTML = `<em>Failed to load methods: ${e.message}</em>`;
  }
}

function renderMethodologyHtml(data, focus) {
  const harp = data.harp || {};
  const metplus = data.metplus || {};

  const harpScores = (harp.scores || []).map(s =>
    `<tr><td>${s.id}</td><td><code>${s.formula}</code></td><td>${s.note}</td></tr>`
  ).join('');
  const harpFlow = (harp.workflow || []).map(w =>
    `<li><strong>${w.name}</strong>. ${w.detail}</li>`
  ).join('');
  const harpRefs = (harp.references || []).map(r =>
    `<li><a href="${r.url}" target="_blank" rel="noopener">${r.title}</a>. ${r.description}</li>`
  ).join('');

  let techHtml = '';
  for (const t of (metplus.techniques || [])) {
    const highlight = t.id === focus ? ' method-tech-focus' : '';
    const scores = (t.scores || []).map(s =>
      `<tr><td>${s.id}</td><td><code>${s.formula}</code></td><td>${s.note}</td></tr>`
    ).join('');
    const steps = (t.workflow || []).map(s => `<li>${s}</li>`).join('');
    techHtml += `
      <section class="method-tech${highlight}" id="tech-${t.id}">
        <h3>${t.title}</h3>
        <p>${t.summary}</p>
        <h4>Workflow</h4>
        <ol>${steps}</ol>
        <h4>Scores and formulas</h4>
        <table>
          <tr><th>Score</th><th>Formula</th><th>Notes</th></tr>
          ${scores}
        </table>
      </section>`;
  }

  return `
    <h1>${data.title || 'Verification methods'}</h1>
    <p class="method-intro">${data.intro || ''}</p>
    <nav class="method-toc" aria-label="Methods sections">
      <a href="#method-harp">HARP</a>
      <a href="#method-metplus">METplus</a>
      <a href="#tech-metplus">GridStat</a>
      <a href="#tech-metplus_point">PointStat</a>
      <a href="#tech-metplus_fss">FSS</a>
      <a href="#tech-metplus_mode">MODE</a>
    </nav>
    <section class="method-engine" id="method-harp">
      <h2>${harp.title || 'HARP point verification'}</h2>
      <p>${harp.subtitle || ''}</p>
      <div class="note-box">${harp.python_equivalence || ''}</div>
      <h3>Workflow</h3>
      <ol>${harpFlow}</ol>
      <h3>Deterministic scores</h3>
      <p>Every score uses complete forecast and observation pairs only. Incomplete pairs are skipped after join and QC.</p>
      <table>
        <tr><th>Score</th><th>Formula</th><th>Notes</th></tr>
        ${harpScores}
      </table>
      <h3>Quality control</h3>
      <p>${harp.qc || ''}</p>
      <h3>References</h3>
      <ul class="refs">${harpRefs}</ul>
    </section>
    <section class="method-engine" id="method-metplus">
      <h2>${metplus.title || 'METplus verification'}</h2>
      <p>${metplus.subtitle || ''}</p>
      <div class="note-box">${metplus.compute_note || ''}</div>
      <p>${metplus.shared_precip || ''}</p>
      ${techHtml}
    </section>
  `;
}

function openMethodsPanel() {
  // From gate: enter a lightweight methods view inside dashboard without forcing an engine,
  // or scroll if already open. Prefer showing methods for current session, else open HARP docs.
  const layout = document.getElementById('appLayout');
  const go = () => {
    document.querySelectorAll('#mainTabs .tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    const tab = document.querySelector('#mainTabs .tab[data-tab="method"]');
    const panel = document.getElementById('method');
    if (tab) {
      tab.hidden = false;
      tab.classList.add('active');
    }
    if (panel) panel.classList.add('active');
    loadMethodology();
    panel?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };
  if (layout && !layout.hidden) {
    go();
    return;
  }
  // No session yet: open HARP dashboard path then Methods tab so formulas are readable.
  enterDashboard({ engine: 'harp' }).then(() => {
    go();
  });
}

async function loadCycles() {
  try {
    const cycles = await api(`/api/cycles?${methodQ()}`);
    const sel = document.getElementById('initCycle');
    const opts = cycles.map(c => {
      const label = c.model
        ? `${c.model} · ${c.init_time || ''}${c.n_points != null ? ` · ${c.n_points} lead` : ''}`
        : (c.init_time || '');
      return `<option value="${c.init_time || ''}">${label}</option>`;
    });
    sel.innerHTML = '<option value="">Latest (all cycles)</option>' + opts.join('');
  } catch (e) { console.warn('cycles', e); }
}

async function loadPipelineStatus() {
  const el = document.getElementById('pipelineStatus');
  const src = document.getElementById('dataSource');
  try {
    const [status, inventory] = await Promise.all([
      api('/api/pipeline/status'),
      api('/api/pipeline/inventory'),
    ]);
    const inanwp = inventory.InaNWP || {};
    const done = status.model_runs?.filter(r => r.status === 'done').length || 0;
    const pending = status.model_runs?.filter(r => r.status === 'pending').length || 0;
    el.textContent = `Pipeline: ${status.verification_scores_count} scores · ${done} runs done · ${pending} pending · auto-sync on`;
    src.innerHTML = `NC: <code>${inanwp.path || 'litbangweb'}</code> · ${inanwp.count || 0} file`;
  } catch (e) {
    el.textContent = 'Pipeline: ' + e.message;
  }
}

function updateSidebarForTab(tab) {
  const leadSec = document.getElementById('leadTimeSection');
  if (leadSec) leadSec.style.display = (tab === 'overview' || tab === 'map') ? '' : 'none';
  if (tab !== 'overview' && tab !== 'map') stopLeadPlayback();
}

function leadSlider() { return document.getElementById('leadTime'); }

function getLeadStep() {
  const el = leadSlider();
  const step = Number(el?.step);
  return Number.isFinite(step) && step > 0 ? step : 3;
}

function applyLeadTime(hours, { refresh = true } = {}) {
  const el = leadSlider();
  if (!el) return;
  const min = +el.min || 0;
  const max = +el.max || maxLeadTime;
  const step = getLeadStep();
  let h = Math.round(+hours / step) * step;
  h = Math.min(max, Math.max(min, h));
  el.value = String(h);
  const label = document.getElementById('leadTimeLabel');
  if (label) label.textContent = formatLeadTime(h);
  if (!refresh) return;
  const tab = document.querySelector('.tab.active')?.dataset.tab;
  if (tab === 'map') renderMapFromCache();
  else if (tab === 'overview') loadOverview();
}

function stepLeadTime(dir) {
  const el = leadSlider();
  if (!el) return false;
  const step = getLeadStep();
  const next = +el.value + dir * step;
  const min = +el.min || 0;
  const max = +el.max || maxLeadTime;
  if (next < min || next > max) return false;
  applyLeadTime(next);
  return true;
}

function isLeadPlaying() { return leadPlayTimer != null; }

function stopLeadPlayback() {
  if (leadPlayTimer != null) {
    clearInterval(leadPlayTimer);
    leadPlayTimer = null;
  }
  const btn = document.getElementById('leadPlay');
  if (btn) {
    btn.textContent = '▶';
    btn.title = 'Putar lead time';
    btn.classList.remove('playing');
    btn.setAttribute('aria-pressed', 'false');
  }
}

function startLeadPlayback() {
  stopLeadPlayback();
  const btn = document.getElementById('leadPlay');
  if (btn) {
    btn.textContent = '⏸';
    btn.title = 'Jeda';
    btn.classList.add('playing');
    btn.setAttribute('aria-pressed', 'true');
  }
  leadPlayTimer = setInterval(() => {
    const el = leadSlider();
    if (!el) { stopLeadPlayback(); return; }
    const step = getLeadStep();
    const max = +el.max || maxLeadTime;
    const min = +el.min || 0;
    let next = +el.value + step;
    if (next > max) next = min; // loop D+0 → D+7
    applyLeadTime(next);
  }, LEAD_PLAY_MS);
}

function toggleLeadPlayback() {
  if (isLeadPlaying()) stopLeadPlayback();
  else startLeadPlayback();
}

async function reloadParameters() {
  const data = await api(`/api/parameters?${methodQ()}`);
  paramsMeta = data.verify_parameters || {};
  paramsAvailableByModel = data.available_by_model || {};
  paramsUnavailableNotes = data.unavailable_notes || {};
  maxLeadTime = data.max_lead_time_hours || (isMetplusMethod() ? 72 : 168);
  const ltSlider = document.getElementById('leadTime');
  if (ltSlider) {
    ltSlider.max = maxLeadTime;
    if (+ltSlider.value > maxLeadTime) ltSlider.value = Math.min(12, maxLeadTime);
  }
  refreshParameterOptions();
  applyMethodUi();
}

let eventsBound = false;
function bindEvents() {
  if (eventsBound) return;
  eventsBound = true;
  document.querySelectorAll('.tab').forEach(btn => {
    btn.addEventListener('click', () => {
      if (btn.hidden) return;
      document.querySelectorAll('.tab, .panel').forEach(el => el.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(btn.dataset.tab).classList.add('active');
      updateSidebarForTab(btn.dataset.tab);
      refreshAll();
      requestAnimationFrame(() => {
        rankingChart?.redraw();
        scoreChart?.redraw();
        stationChart?.redraw();
        stationMap?.invalidateSize();
      });
    });
  });

  document.getElementById('metplusSubmethod')?.addEventListener('change', async () => {
    applyMethodUi();
    applyTabVisibility();
    saveFlowState();
    await onSessionChanged();
  });

  ['parameter', 'initCycle'].forEach(id => document.getElementById(id).addEventListener('change', () => {
    mapBulkCache.key = '';
    stationDetailCache.key = '';
    refreshAll();
  }));
  document.getElementById('leadTime').addEventListener('input', () => {
    stopLeadPlayback();
    applyLeadTime(+document.getElementById('leadTime').value);
  });
  document.getElementById('leadPrev')?.addEventListener('click', () => {
    stopLeadPlayback();
    stepLeadTime(-1);
  });
  document.getElementById('leadNext')?.addEventListener('click', () => {
    stopLeadPlayback();
    stepLeadTime(1);
  });
  document.getElementById('leadPlay')?.addEventListener('click', () => toggleLeadPlayback());
  document.getElementById('scoreMetric')?.addEventListener('change', () => {
    if (document.querySelector('.tab.active')?.dataset.tab === 'scores') loadScores();
  });
  document.getElementById('stationRangeMonths')?.addEventListener('change', () => {
    stationDetailCache.key = '';
    loadStationDetail();
  });
  document.querySelectorAll('.model-cb').forEach(cb => cb.addEventListener('change', () => {
    mapBulkCache.key = '';
    stationDetailCache.key = '';
    refreshParameterOptions();
    refreshAll();
  }));
  document.getElementById('stationSelect').addEventListener('change', () => {
    stationDetailCache.key = '';
    loadStationDetail();
  });
}

function scoresQuery(extra = '') {
  const init = selectedInitTime();
  let param = document.getElementById('parameter').value;
  // GridStat/FSS/MODE: hanya precip_3h. PointStat Soft: parameter HARP (jangan coerce).
  if (isMetplusMethod() && selectedMethod() !== 'metplus_point') {
    if (param && !['precip_3h', 'precip', 'rainfall_6h_rrr', 'rainfall_last_mm'].includes(param)) {
      param = 'precip_3h';
    }
  }
  const base = methodQ(`models=${modelsQuery()}&parameter=${param}${init ? `&init_time=${encodeURIComponent(init)}` : ''}`);
  return extra ? `${base}${extra.startsWith('&') ? extra : `&${extra}`}` : base;
}

async function refreshAll() {
  const tab = document.querySelector('.tab.active')?.dataset.tab;
  document.querySelectorAll('.panel .error').forEach(el => el.remove());
  try {
    if (tab === 'overview') await loadOverview();
    if (tab === 'scores') await loadScores();
    if (tab === 'map') await loadMap();
    if (tab === 'spatial') await loadSpatial();
    if (tab === 'method') await loadMethodology();
    if (tab === 'station') await loadStationDetail();
  } catch (e) {
    console.error('refreshAll', tab, e);
    const host = document.querySelector('.panel.active') || document.getElementById('overview');
    if (host) {
      const box = document.createElement('div');
      box.className = 'error';
      box.style.cssText = 'margin:1rem;padding:0.75rem;border:1px solid #fca5a5;background:#fef2f2;color:#991b1b;border-radius:8px;';
      box.textContent = `Failed to load tab ${tab || '?'}: ${e.message || e}`;
      host.prepend(box);
    }
  }
  requestAnimationFrame(() => {
    rankingChart?.redraw();
    scoreChart?.redraw();
    stationChart?.redraw();
    stationMap?.invalidateSize?.();
  });
}

async function loadOverview() {
  const cards = document.getElementById('rankingCards');
  const kpis = document.getElementById('kpiGrid');
  if (!requireModels('rankingCards', '<em>Select at least one model in the sidebar.</em>')) {
    if (kpis) kpis.innerHTML = '';
    rankingChart?.setBar({ title: 'Select a model', yLabel: 'RMSE', labels: ['-'], values: [0], colors: ['#e2e8f0'] });
    return;
  }
  const lt = document.getElementById('leadTime').value;
  const init = selectedInitTime();
  const method = selectedMethod();
  const scoreMetric = method === 'metplus_fss' ? 'fss' : (method === 'metplus_mode' ? 'ets' : 'rmse');
  const param = document.getElementById('parameter')?.value || '';
  const rankQ = methodQ(
    `models=${modelsQuery()}&score=${scoreMetric}`
    + (param ? `&parameter=${encodeURIComponent(param)}` : '')
    + (init ? `&init_time=${encodeURIComponent(init)}` : '')
  );

  let ranking = { ranking: [] };
  let scores = { scores: [] };
  try {
    ranking = await api(`/api/verification/ranking?${rankQ}`);
  } catch (e) {
    if (cards) cards.innerHTML = `<em>Ranking failed: ${e.message}</em>`;
    throw e;
  }
  try {
    scores = await api(`/api/verification/scores?${scoresQuery(`&lead_time=${lt}`)}`);
  } catch (e) {
    console.warn('scores lead', lt, e);
    try {
      scores = await api(`/api/verification/scores?${scoresQuery()}`);
    } catch (e2) {
      console.warn('scores all', e2);
    }
  }

  const rows = ranking.ranking || [];
  const metricKey = ranking.score_metric || scoreMetric;
  if (!rows.length) {
    if (cards) cards.innerHTML = '<em>No ranking yet for this method or model set.</em>';
  } else {
    cards.innerHTML = rows.map(r => {
      const mean = r.mean_score ?? r.mean_rmse;
      const meanTxt = (typeof mean === 'number' && Number.isFinite(mean)) ? mean.toFixed(3) : '·';
      const maeTxt = (typeof r.mean_mae === 'number') ? r.mean_mae.toFixed(3) : null;
      const biasTxt = (typeof r.mean_bias === 'number') ? r.mean_bias.toFixed(3) : null;
      const metricLabel = (r.metric || metricKey || 'rmse').toUpperCase();
      return `<div class="rank-card rank-${r.rank || 1}">
        <div class="rank-num">#${r.rank || 1}</div>
        <div class="model-name">${r.model} ${modelBadge(r.model)}</div>
        <div class="metric">Mean ${metricLabel}: <strong>${meanTxt}</strong>${maeTxt != null ? ` · MAE: ${maeTxt}` : ''}</div>
        <div class="metric">${biasTxt != null ? `Bias: ${biasTxt} · ` : ''}Method: ${methodLabel(method)}${r.n_leads != null ? ` · N leads: ${r.n_leads}` : ''}</div>
      </div>`;
    }).join('');
  }

  rankingChart?.setBar({
    title: `Ranking ${methodLabel(method)} · Mean ${(rows[0]?.metric || metricKey || 'rmse').toUpperCase()}`,
    yLabel: rows[0]?.metric || metricKey || 'Mean score',
    labels: rows.map(r => r.model),
    values: rows.map(r => {
      const v = r.mean_score ?? r.mean_rmse ?? 0;
      return (typeof v === 'number' && Number.isFinite(v)) ? v : 0;
    }),
    colors: ['#00529B', '#64748b', '#94a3b8', '#cbd5e1'],
  });
  rankingChart?.redraw();

  const scoreRows = scores.scores || [];
  if (kpis) {
    kpis.innerHTML = scoreRows.length
      ? scoreRows.map(s => {
          const primary = method === 'metplus_fss'
            ? `FSS ${typeof s.fss === 'number' ? s.fss.toFixed(3) : '·'}`
            : method === 'metplus_mode'
              ? `Interest ${typeof s.total_interest === 'number' ? s.total_interest.toFixed(3) : (typeof s.ets === 'number' ? s.ets.toFixed(3) : '·')}`
              : `RMSE ${typeof s.rmse === 'number' ? s.rmse.toFixed(2) : '·'}`;
          return `
        <div class="kpi">
          <div class="label">${s.model} · ${formatLeadTime(s.lead_time)}</div>
          <div class="value">${primary}</div>
          <div class="label">Bias ${typeof s.bias === 'number' ? s.bias.toFixed(2) : '·'} · MAE ${typeof s.mae === 'number' ? s.mae.toFixed(2) : '·'} · CSI ${typeof s.csi === 'number' ? s.csi.toFixed(2) : '·'} · N=${s.n_cases ?? '·'}</div>
        </div>`;
        }).join('')
      : '<em class="hint">No scores for this lead. Move the lead slider or open Scores vs lead time.</em>';
  }
}

function methodLabel(m) {
  const map = {
    harp: 'HARP',
    metplus: 'METplus GridStat',
    metplus_point: 'METplus PointStat',
    metplus_fss: 'METplus FSS',
    metplus_mode: 'METplus MODE',
  };
  return map[m] || String(m || '').toUpperCase();
}

async function renderMetplusScorePanel(method) {
  const panel = document.getElementById('metplusScorePanel');
  if (!panel) return;
  if (method !== 'metplus_fss' && method !== 'metplus_mode') {
    panel.hidden = true;
    panel.innerHTML = '';
    return;
  }
  panel.hidden = false;
  try {
    const data = await api(`/api/verification/scores?${scoresQuery()}`);
    const rows = (data.scores || []).slice().sort((a, b) => a.lead_time - b.lead_time);
    if (!rows.length) {
      panel.innerHTML = `<em>No ${methodLabel(method)} scores yet. Confirm the DPU pipeline has pushed series_fss / series_mode.</em>`;
      return;
    }
    if (method === 'metplus_fss') {
      const meanFss = rows.reduce((s, r) => s + (r.fss || 0), 0) / rows.length;
      panel.innerHTML = `
        <h3>FSS (Fractions Skill Score) · InaNWP vs GSMaP</h3>
        <div class="metplus-kpis">
          <div class="kpi-mini"><div class="v">${meanFss.toFixed(3)}</div><div class="l">Mean FSS (H+3 to H+72)</div></div>
          <div class="kpi-mini"><div class="v">${rows.length}</div><div class="l">Lead points</div></div>
          <div class="kpi-mini"><div class="v">${rows[0]?.init_time || '·'}</div><div class="l">Init cycle</div></div>
        </div>
        <table>
          <thead><tr><th>Lead</th><th>Valid</th><th>FSS</th></tr></thead>
          <tbody>
            ${rows.map(r => `<tr>
              <td>${formatLeadTime(r.lead_time)}</td>
              <td>${r.valid || '·'}</td>
              <td><strong>${typeof r.fss === 'number' ? r.fss.toFixed(4) : '·'}</strong></td>
            </tr>`).join('')}
          </tbody>
        </table>`;
    } else {
      const meanI = rows.reduce((s, r) => s + (r.total_interest ?? r.ets ?? 0), 0) / rows.length;
      const meanObj = rows.reduce((s, r) => s + (r.n_cases || 0), 0) / rows.length;
      panel.innerHTML = `
        <h3>MODE (object-based) · InaNWP vs GSMaP</h3>
        <div class="metplus-kpis">
          <div class="kpi-mini"><div class="v">${meanI.toFixed(3)}</div><div class="l">Mean total interest</div></div>
          <div class="kpi-mini"><div class="v">${meanObj.toFixed(0)}</div><div class="l">Mean matched pairs</div></div>
          <div class="kpi-mini"><div class="v">${rows[0]?.init_time || '·'}</div><div class="l">Init cycle</div></div>
        </div>
        <table>
          <thead><tr><th>Lead</th><th>Valid</th><th>Interest</th><th>Matched</th></tr></thead>
          <tbody>
            ${rows.map(r => `<tr>
              <td>${formatLeadTime(r.lead_time)}</td>
              <td>${r.valid || '·'}</td>
              <td><strong>${typeof (r.total_interest ?? r.ets) === 'number' ? (r.total_interest ?? r.ets).toFixed(4) : '·'}</strong></td>
              <td>${r.n_cases ?? '·'}</td>
            </tr>`).join('')}
          </tbody>
        </table>`;
    }
  } catch (e) {
    panel.innerHTML = `<em>Failed to load ${methodLabel(method)} scores: ${e.message}</em>`;
  }
}

async function loadSpatial() {
  const gal = document.getElementById('spatialGallery');
  if (!gal) return;
  const method = selectedMethod();
  await renderMetplusScorePanel(method);

  if (!isMetplusMethod() || method === 'metplus_point') {
    gal.innerHTML = method === 'metplus_point'
      ? '<em>PointStat uses all BMKG stations. See Overview, Scores, or Station detail.</em>'
      : '<em>Choose <strong>METplus</strong> (GridStat / FSS / MODE) to see spatial output.</em>';
    return;
  }

  // FSS/MODE: skor panel is primary; still show GridStat maps as context when available
  const model = selectedModels()[0] || 'InaNWP';
  try {
    const data = await api(`/api/metplus/spatial?model=${encodeURIComponent(model)}`);
    const maps = data.maps || [];
    if (!maps.length) {
      if (method === 'metplus') {
        gal.innerHTML = '<em>No METplus maps yet. Run the DPU pipeline and sync maps/.</em>';
      } else {
        gal.innerHTML = '<em class="hint">No companion GridStat maps. FSS or MODE scores above already come from DPU artifacts.</em>';
      }
      return;
    }
    const latest = maps.slice(-6).reverse();
    const caption = method === 'metplus'
      ? ''
      : `<p class="hint">GridStat maps for context. ${methodLabel(method)} scores are in the panel above.</p>`;
    gal.innerHTML = caption + latest.map(m => {
      const fcst = m.files['fcst.png'] ? `${API}/api/metplus/maps/${m.valid}/fcst.png` : '';
      const obs = m.files['obs.png'] ? `${API}/api/metplus/maps/${m.valid}/obs.png` : '';
      const diff = m.files['diff.png'] ? `${API}/api/metplus/maps/${m.valid}/diff.png` : '';
      return `<div class="spatial-card">
        <h4>${m.valid} · ${m.model}</h4>
        <div class="spatial-row">
          ${fcst ? `<figure><img src="${fcst}" alt="fcst"/><figcaption>FCST</figcaption></figure>` : ''}
          ${obs ? `<figure><img src="${obs}" alt="obs"/><figcaption>OBS</figcaption></figure>` : ''}
          ${diff ? `<figure><img src="${diff}" alt="diff"/><figcaption>DIFF</figcaption></figure>` : ''}
        </div>
      </div>`;
    }).join('');
  } catch (e) {
    gal.innerHTML = `<em>Failed to load spatial maps: ${e.message}</em>`;
  }
}

async function loadScores() {
  const metric = selectedScoreMetric();
  const metricLabel = SCORE_METRICS[metric]?.label || metric;
  const detail = document.getElementById('scoreDetail');
  if (!selectedModels().length) {
    scoreChart?.setLines({ title: 'Select at least one model', xLabel: 'Lead time (h)', yLabel: metricLabel, xNumeric: true, series: [] });
    return;
  }
  let data;
  try {
    data = await api(`/api/verification/scores?${scoresQuery()}`);
  } catch (e) {
    if (detail) detail.innerHTML = `<span style="color:#b91c1c">Failed to load scores: ${e.message}</span>`;
    scoreChart?.setLines({ title: 'Failed to load scores', xLabel: 'Lead time (h)', yLabel: metricLabel, xNumeric: true, series: [] });
    return;
  }
  const series = selectedModels().map(m => {
    const pts = (data.scores || []).filter(s => s.model === m).sort((a, b) => a.lead_time - b.lead_time);
    return {
      name: m,
      color: MODEL_COLORS[m] || '#00529B',
      x: pts.map(p => p.lead_time),
      y: pts.map(p => {
        const v = p[metric];
        return (typeof v === 'number' && Number.isFinite(v)) ? v : null;
      }),
      extra: pts.map(p => ({
        rmse: p.rmse, bias: p.bias, mae: p.mae, stde: p.stde,
        correlation: p.correlation, csi: p.csi, ets: p.ets, fss: p.fss, n_cases: p.n_cases,
      })),
    };
  });
  scoreChart?.setLines({
    title: `${metricLabel} vs lead time · ${methodLabel(selectedMethod())} · ${document.getElementById('parameter').selectedOptions[0]?.text || ''}`,
    xLabel: 'Lead time (h)',
    yLabel: metricLabel,
    xNumeric: true,
    series,
  });
  scoreChart?.redraw();
  if (detail) {
    const n = (data.scores || []).length;
    detail.innerHTML = n
      ? `Loaded ${n} score points (${selectedMethod().toUpperCase()}). Click a point for details.`
      : '<em>No score points. Confirm the DPU pipeline ran and artifacts are synced.</em>';
  }
}

async function ensureMapBulk() {
  const model = selectedModels()[0];
  if (!model) return null;
  const param = document.getElementById('parameter').value;
  const init = selectedInitTime();
  const key = `${model}|${param}|${init}`;
  if (mapBulkCache.key !== key) {
    mapBulkCache.data = await api(
      `/api/verification/map/bulk?model=${model}&parameter=${param}${init ? `&init_time=${encodeURIComponent(init)}` : ''}`
    );
    mapBulkCache.key = key;
  }
  return mapBulkCache.data;
}

function renderMapFromCache() {
  if (!selectedModels().length) {
    stationMap?.setStations([]);
    document.getElementById('mapDetail').textContent = 'Select at least one model in the sidebar.';
    return;
  }
  if (!mapBulkCache.data) return loadMap();
  if (stationMap) stationMap.invalidateSize();
  const lt = +document.getElementById('leadTime').value;
  const available = mapBulkCache.data.available_lead_times || [];
  const resolvedLt = available.includes(lt) ? lt : nearestLeadTime(available, lt);
  const data = resolvedLt != null
    ? (mapBulkCache.data.records || []).filter(d => d.lead_time === resolvedLt)
    : [];

  if (!data.length) {
    stationMap.setStations([]);
    const detail = document.getElementById('mapDetail');
    if (!available.length) {
      detail.textContent = 'No map data for this parameter or init cycle.';
    } else {
      const minLt = Math.min(...available);
      const maxLt = Math.max(...available);
      detail.innerHTML = `<strong>Empty</strong> for ${formatLeadTime(lt)}.<br>
        Available leads: ${formatLeadTime(minLt)} to ${formatLeadTime(maxLt)} (${minLt} to ${maxLt} h).
        ${lt > maxLt ? 'Perluas data NC/pipeline untuk lead lebih jauh.' : 'Geser slider ke rentang tersebut.'}`;
    }
    return;
  }

  const maxRmse = Math.max(...data.map(d => d.rmse || 0), 0.01);
  stationMap.setStations(data.map(d => ({
    station_id: d.station_id,
    name: d.name,
    lat: d.lat,
    lon: d.lon,
    rmse: d.rmse,
    fcst: d.fcst_mean,
    obs: d.obs_mean,
    lead_time: d.lead_time,
    color: d.rmse < maxRmse * 0.33 ? '#16a34a' : d.rmse < maxRmse * 0.66 ? '#ca8a04' : '#dc2626',
  })));
  const detail = document.getElementById('mapDetail');
  if (resolvedLt !== lt) {
    detail.textContent = `Showing nearest lead ${formatLeadTime(resolvedLt)} (slider ${formatLeadTime(lt)}). Click a station for detail.`;
  } else {
    detail.textContent = `${data.length} stations · ${formatLeadTime(lt)}. Click a station for forecast vs observation.`;
  }
}

async function loadMap() {
  try {
    if (!selectedModels().length) {
      stationMap?.setStations([]);
      document.getElementById('mapDetail').textContent = 'Select at least one model in the sidebar.';
      return;
    }
    await ensureMapBulk();
    renderMapFromCache();
  } catch (e) {
    document.getElementById('mapDetail').textContent = 'Failed to load map: ' + e.message;
  }
}

async function showStationMapDetail(st) {
  const stationId = st.station_id || st;
  const model = selectedModels()[0];
  const ltSlider = +document.getElementById('leadTime').value;
  const available = mapBulkCache.data?.available_lead_times || [];
  const resolvedLt = st.lead_time
    ?? (available.includes(ltSlider) ? ltSlider : nearestLeadTime(available, ltSlider));
  const recs = (mapBulkCache.data?.records || []).filter(
    d => String(d.station_id) === String(stationId) && (resolvedLt == null || d.lead_time === resolvedLt),
  );
  const rec = recs[0];
  const fcst = rec?.fcst_mean ?? st.fcst;
  const obs = rec?.obs_mean ?? st.obs;
  const name = rec?.name || st.name || stationId;
  const initIso = mapBulkCache.data?.init_time;

  let html = `<strong>${name}</strong> · ${formatLeadTime(resolvedLt ?? ltSlider)}`;
  if (initIso) html += `<br><span class="time-utc">Init ${formatTimeDual(initIso)}</span>`;
  html += '<table><tr><th>Model</th><th>Fcst</th><th>Obs</th><th>Err</th></tr>';
  if (model) {
    const err = fcst != null && obs != null && !Number.isNaN(fcst) && !Number.isNaN(obs)
      ? (fcst - obs).toFixed(3) : '·';
    html += `<tr><td>${model}</td><td>${Number.isFinite(fcst) ? fcst.toFixed(2) : '·'}</td>`;
    html += `<td>${Number.isFinite(obs) ? obs.toFixed(2) : '·'}</td><td>${err}</td></tr>`;
  }
  html += '</table>';
  document.getElementById('mapDetail').innerHTML = html;
}

function stationDetailQuery() {
  const months = document.getElementById('stationRangeMonths')?.value || 3;
  const init = selectedInitTime();
  let q = methodQ(`parameter=${document.getElementById('parameter').value}&models=${modelsQuery()}&series_mode=by_init&months=${months}`);
  if (init) q += `&init_time=${encodeURIComponent(init)}`;
  return q;
}

function toEpochMs(isoUtc) {
  if (!isoUtc) return null;
  const s = String(isoUtc).endsWith('Z') ? isoUtc : `${isoUtc}Z`;
  const t = Date.parse(s);
  return Number.isNaN(t) ? null : t;
}

function downsamplePoints(points, maxPoints = 400) {
  if (points.length <= maxPoints) return points;
  const step = Math.ceil(points.length / maxPoints);
  const out = points.filter((_, i) => i % step === 0);
  if (out[out.length - 1] !== points[points.length - 1]) out.push(points[points.length - 1]);
  return out;
}

function renderStationFromCache() {
  const data = stationDetailCache.data;
  if (!data) return loadStationDetail();
  const param = document.getElementById('parameter').value;
  const stationId = document.getElementById('stationSelect').value;
  const months = +document.getElementById('stationRangeMonths')?.value || 3;
  const paramLabel = paramsMeta[param]?.label || data.meta?.label || param;
  const paramUnit = paramsMeta[param]?.unit || data.meta?.unit || '';

  if (data.note && !(data.inits || []).length && !(data.obs || []).length && !(data.series || []).length) {
    stationChart.setLines({
      title: `${data.station?.name || stationId} · ${selectedMethod().toUpperCase()}`,
      xLabel: 'Waktu valid (WIB)', yLabel: '', xNumeric: true, xTime: true, series: [],
    });
    document.getElementById('stationTable').innerHTML = `<em>${data.note}</em>`;
    return;
  }

  if (data.series_mode === 'by_init' || data.inits) {
    const obsPts = downsamplePoints(data.obs || [], 900);
    const series = [{
      name: 'Observasi',
      color: MODEL_COLORS.Observasi,
      width: 2,
      dotsOnly: false,
      x: obsPts.map(p => toEpochMs(p.valid_time)),
      y: obsPts.map(p => (p.obs != null ? p.obs : null)),
    }];
    const inits = (data.inits || []).slice().sort((a, b) => String(b.init_time).localeCompare(String(a.init_time)));
    const dashIdxByModel = {};
    inits.forEach((run) => {
      const n = dashIdxByModel[run.model] || 0;
      dashIdxByModel[run.model] = n + 1;
      const pts = downsamplePoints(run.points || [], 200);
      const tip = `${run.model} · init ${formatTimeWIB(run.init_time)}`;
      series.push({
        name: tip,
        legendName: run.model,
        color: MODEL_COLORS[run.model] || '#00529B',
        dash: INIT_DASHES[n % INIT_DASHES.length],
        marker: INIT_MARKERS[n % INIT_MARKERS.length],
        alpha: Math.max(0.4, 1 - n * 0.12),
        width: n === 0 ? 2.4 : 1.6,
        markers: true,
        dotsOnly: false,
        x: pts.map(p => toEpochMs(p.valid_time)),
        y: pts.map(p => (p.fcst != null ? p.fcst : null)),
      });
    });

    stationChart.setLines({
      title: `${data.station.name || stationId} · ${paramLabel} · ${data.method === 'metplus_point' ? 'PointStat' : `${months} mo`} · per init cycle`,
      xLabel: 'Waktu valid (WIB)',
      yLabel: paramUnit,
      xNumeric: true,
      xTime: true,
      series,
    });

    const obsMap = Object.fromEntries((data.obs || []).map(o => [o.valid_time, o.obs]));
    const flat = [];
    for (const run of inits) {
      const rows = run.table || run.points || [];
      for (const p of rows) {
        const obs = p.obs != null ? p.obs : obsMap[p.valid_time];
        flat.push({
          valid_time: p.valid_time,
          init_time: run.init_time,
          model: run.model,
          lead_time: p.lead_time,
          fcst: p.fcst,
          obs,
        });
      }
    }
    flat.sort((a, b) => String(a.valid_time).localeCompare(String(b.valid_time)) || String(a.init_time).localeCompare(String(b.init_time)));

    if (!flat.length && !obsPts.length) {
      document.getElementById('stationTable').innerHTML =
        `<em>${data.note || `No data for this station or parameter in the last ${months} months.`}</em>`;
      return;
    }

    let html = data.note ? `<p class="lt-note">${data.note}</p>` : '';
    html += `<p class="lt-note">${inits.length} init cycle · ${obsPts.length}+ titik obs · ${flat.length} titik fcst</p>`;
    html += '<div class="table-scroll"><table class="station-ts-table"><thead><tr><th>Valid (WIB)</th><th>Init</th><th>Model</th><th>Lead</th><th>Fcst</th><th>Obs</th><th>Err</th></tr></thead><tbody>';
    const tableRows = flat.slice(-200);
    tableRows.forEach(r => {
      const err = r.fcst != null && r.obs != null ? (r.fcst - r.obs).toFixed(2) : '·';
      html += `<tr><td>${formatTimeDual(r.valid_time)}</td><td>${formatTimeWIB(r.init_time)}</td><td>${r.model}</td>`;
      html += `<td>${formatLeadTime(r.lead_time)}</td><td>${r.fcst?.toFixed(2) ?? '·'}</td><td>${r.obs?.toFixed(2) ?? '·'}</td><td>${err}</td></tr>`;
    });
    html += '</tbody></table></div>';
    if (flat.length > 200) html = `<p class="lt-note">200 baris terakhir dari ${flat.length} titik fcst.</p>` + html;
    document.getElementById('stationTable').innerHTML = html;
    return;
  }

  // legacy by_lead (sqlite / fallback)
  const lt = data.lead_time ?? 12;
  const rows = data.series || [];
  const models = selectedModels();
  const plotRows = rows.length > 800 ? downsamplePoints(rows, 800) : rows;
  const series = [{
    name: 'Observasi',
    color: MODEL_COLORS.Observasi,
    width: 1.5,
    dotsOnly: false,
    x: plotRows.map(s => toEpochMs(s.valid_time)),
    y: plotRows.map(s => (s.obs != null ? s.obs : null)),
  }];
  models.forEach(m => {
    series.push({
      name: m,
      color: MODEL_COLORS[m] || '#00529B',
      width: 1,
      dotsOnly: true,
      x: plotRows.map(s => toEpochMs(s.valid_time)),
      y: plotRows.map(s => (s[m] != null ? s[m] : null)),
    });
  });
  stationChart.setLines({
    title: `${data.station.name || stationId} · ${paramsMeta[param]?.label} · ${months} mo · ${formatLeadTime(lt)}`,
    xLabel: 'Waktu valid (WIB)',
    yLabel: paramsMeta[param]?.unit || '',
    xNumeric: true,
    xTime: true,
    series,
  });
  document.getElementById('stationTable').innerHTML = `<em>by_lead mode (legacy).</em>`;
}

async function loadStationDetail() {
  const stationId = document.getElementById('stationSelect').value;
  if (!stationId) return;
  if (!selectedModels().length) {
    stationChart.setLines({
      title: 'Select at least one model di sidebar',
      xLabel: 'Waktu valid (WIB)', yLabel: '', xNumeric: true, xTime: true, series: [],
    });
    document.getElementById('stationTable').innerHTML = '<em>Select at least one model in the sidebar.</em>';
    return;
  }
  const key = `${stationId}|${stationDetailQuery()}`;
  if (stationDetailCache.key !== key) {
    stationDetailCache.data = await api(`/api/station/${stationId}/detail?${stationDetailQuery()}`);
    stationDetailCache.key = key;
  }
  renderStationFromCache();
}

init().catch(console.error);
