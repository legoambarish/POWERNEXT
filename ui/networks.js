/* PowerNext v3 network workspace.  It is intentionally an independent page
 * controller: the legacy app keeps its hash based screens and /api routes. */
const main = document.getElementById('main');
const nav = document.getElementById('v3-networks-nav');
const V3_TEMPLATE = '/networks.html';
let templateText = null;
let metadata = null;
let activeJob = null;
let pollTimer = null;
let fixedPrediction = null;

const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pretty = value => JSON.stringify(value, null, 2);
const number = (id, fallback = 0) => {
  const value = Number(document.getElementById(id)?.value);
  return Number.isFinite(value) ? value : fallback;
};
const setText = (id, value) => { const node = document.getElementById(id); if (node) node.textContent = value; };

async function api(path, options = {}) {
  const response = await fetch(path, {headers: {'Content-Type': 'application/json', ...(options.headers || {})}, ...options});
  let body = null;
  try { body = await response.json(); } catch { body = null; }
  if (!response.ok) throw new Error(body?.error || body?.detail || `v3 request failed (${response.status})`);
  return body;
}

function parseStages(value) {
  const text = String(value || '').trim().replace(/[–—]/g, '-');
  if (/^\d+\s*-\s*\d+$/.test(text)) {
    const [low, high] = text.split('-').map(Number);
    if (low > high) throw new Error('Stage range must increase from low to high.');
    return Array.from({length: high - low + 1}, (_, i) => low + i);
  }
  const values = text.split(',').map(part => Number(part.trim()));
  if (!values.length || values.some(value => !Number.isInteger(value) || value < 2 || value > 15)) {
    throw new Error('Stages must be 2–15, a range such as 2-15, or comma-separated integers.');
  }
  return [...new Set(values)].sort((a, b) => a - b);
}

function buildRequest() {
  return {
    schema_version: 'network_request_v3',
    request_id: document.getElementById('v3-request-id').value.trim() || 'NETWORK_UI_REQUEST',
    domain_id: document.getElementById('v3-domain').value,
    impulse_type: document.getElementById('v3-impulse').value,
    topology_id: document.getElementById('v3-topology').value,
    target_crest_V: number('v3-target'),
    polarity: Number(document.getElementById('v3-polarity').value),
    setup: {
      setup_id: document.getElementById('v3-setup-id').value.trim() || 'V3_UI_DECLARED_SETUP',
      dut_capacitance_F: number('v3-dut-cap'),
      divider_capacitance_F: number('v3-divider-cap'),
      stray_capacitance_F: number('v3-stray-cap'),
      loop_inductance_H: number('v3-loop-inductance'),
      loop_resistance_ohm: number('v3-loop-resistance'),
      basic_coverage_assumption: document.getElementById('v3-coverage').value,
      auxiliary_assumption: document.getElementById('v3-auxiliary').value,
    },
    max_modules: Number(document.getElementById('v3-max-modules').value),
    stages: parseStages(document.getElementById('v3-stages').value),
    search_mode: document.getElementById('v3-search-mode').value,
    priority: document.getElementById('v3-priority').value,
    max_ml_candidates: Math.round(number('v3-max-ml', 4096)),
    max_physics_evaluations: Math.round(number('v3-max-physics', 128)),
    budget_seconds: number('v3-budget', 90),
    alternatives: Math.round(number('v3-alternatives', 4)),
    inventory: null,
    assumptions: [
      'Uniform ideal two-terminal resistor networks are a declared research model.',
      'Component quantities, sockets, pulse ratings, and mounting remain unknown.',
    ],
  };
}

function renderResearchBanner() {
  const domain = document.getElementById('v3-domain');
  const banner = document.getElementById('v3-research-banner');
  if (banner && domain) banner.hidden = domain.value !== 'research_3uf';
}

function renderMetadata() {
  const catalog = document.getElementById('v3-catalog-status');
  if (!catalog || !metadata) return;
  catalog.textContent = `${metadata.components_ohm.length} parts · up to ${metadata.max_modules} modules`;
  const stages = document.getElementById('v3-stages');
  if (stages && !stages.value) stages.value = metadata.default_request.stages.join(',');
}

function renderCounts(search) {
  const node = document.getElementById('v3-search-counts');
  if (!node || !search) return;
  const rows = [
    ['Theoretical recipes', search.theoretical_recipe_configurations],
    ['Distinct response candidates', search.distinct_response_candidates],
    ['Considered', search.considered_count],
    ['ML predicted', search.ml_predicted_count],
    ['Physics evaluated', search.physics_evaluated_count],
    ['Catalog complete', search.catalog_complete ? 'yes' : 'partial'],
    ['Unsupported', search.unsupported_count],
  ];
  node.innerHTML = rows.map(([key, value]) => `<div class="kv"><dt>${esc(key)}</dt><dd class="num">${esc(value)}</dd></div>`).join('');
}

function renderProgress(state) {
  const status = document.getElementById('v3-job-status');
  const progress = document.getElementById('v3-progress');
  const spinner = progress?.querySelector('.spinner');
  if (status) {
    status.textContent = state?.status || 'Idle';
    status.className = `chip ${state?.status === 'COMPLETED' ? 'pass' : state?.status === 'FAILED' ? 'fail' : state?.status ? 'info' : 'neutral'}`;
  }
  if (progress) progress.querySelector('div').textContent = state?.progress || 'Submit a request to stream catalog and Physics progress here.';
  if (spinner) spinner.hidden = !['QUEUED', 'RUNNING'].includes(state?.status);
  const events = document.getElementById('v3-progress-events');
  if (events) events.innerHTML = (state?.events || []).slice(-12).map(item => `<div><time>${esc(item.at)}</time> ${esc(item.message)}</div>`).join('');
  renderCounts(state?.search);
}

function metricValue(row, key) {
  const value = row?.physics?.metrics?.[key];
  return value === null || value === undefined ? '—' : `${Number(value).toPrecision(6)}`;
}

function rowSummary(row, label) {
  if (!row) return `<div class="note">${esc(label)} is unavailable for this result.</div>`;
  const c = row.configuration || {};
  const ml = row.ml_prediction || {};
  const network = (tree, ohm) => `<details><summary>${esc(Number(ohm || 0).toPrecision(7))} Ω equivalent</summary><pre class="v3-json">${esc(pretty(tree))}</pre></details>`;
  // The result contract keeps the immutable recipe identifier under `id`.
  // Accept the older `recipe_id` spelling too so archived result records stay
  // readable while current rows render their exact physical alternatives.
  const recipeId = recipe => recipe?.id ?? recipe?.recipe_id ?? '—';
  const bomValue = item => item?.component_ohm ?? item?.value_ohm ?? 'unknown';
  return `<article class="v3-candidate ${row.compliant ? 'is-pass' : 'is-fail'}">
    <div class="card-head"><div><span class="eyebrow">${esc(label)} · rank ${esc(row.rank ?? '—')}</span><h3>${row.compliant ? 'Physics-compliant numerical candidate' : 'Failed or unsupported alternative'}</h3></div><span class="chip ${row.compliant ? 'pass' : 'fail'}">${row.compliant ? 'PASS' : 'NOT RECOMMENDED'}</span></div>
    <div class="chips"><span class="chip neutral">${esc(c.stages)} stages</span><span class="chip neutral">${esc(c.stage_charge_V)} V/stage</span><span class="chip neutral">${esc(row.verification_status || 'not evaluated')}</span><span class="chip caution">hardware unverified</span></div>
    <div class="grid-2 inner v3-metrics"><dl class="kvs tight"><div class="kv"><dt>Front network</dt><dd>${network(c.front_network, c.front_per_stage_ohm)}</dd></div><div class="kv"><dt>Tail network</dt><dd>${network(c.tail_network, c.tail_per_stage_ohm)}</dd></div><div class="kv"><dt>Exact recipes</dt><dd><code>${esc(recipeId(row.front_recipe))} / ${esc(recipeId(row.tail_recipe))}</code></dd></div><div class="kv"><dt>Physics crest</dt><dd class="num">${metricValue(row, 'crest_magnitude_V')} V</dd></div><div class="kv"><dt>Physics front / tail</dt><dd class="num">${metricValue(row, 'T1_s') !== '—' ? metricValue(row, 'T1_s') : metricValue(row, 'Tp_s')} / ${metricValue(row, 'T2_s')} s</dd></div></dl><dl class="kvs tight"><div class="kv"><dt>ML gain / front / tail</dt><dd class="num">${ml.gain ?? '—'} / ${ml.front_us ?? '—'} / ${ml.tail_us ?? '—'}</dd></div><div class="kv"><dt>ML OOD</dt><dd>${row.ml_ood == null ? 'unavailable' : row.ml_ood ? 'yes' : 'no'}</dd></div><div class="kv"><dt>Reason codes</dt><dd>${esc((row.reason_codes || []).join(', ') || 'none')}</dd></div><div class="kv"><dt>BOM status</dt><dd>${esc((row.component_bill_of_materials || []).map(item => `${bomValue(item)}Ω × ${item.required_count ?? item.quantity ?? '—'} (${item.availability_status || 'UNKNOWN'})`).join('; ') || 'unknown')}</dd></div></dl></div>
    ${row.waveform_reference ? `<div class="actions"><button class="btn sm" data-v3-wave="${esc(row.candidate_id)}">Load saved waveform</button><span id="v3-wave-${esc(row.candidate_id)}" class="muted small"></span></div>` : ''}
  </article>`;
}

function renderResult(result) {
  const block = document.getElementById('v3-search-result');
  if (!block || !result) return;
  block.hidden = false;
  const status = document.getElementById('v3-result-status');
  if (status) { status.textContent = result.status; status.className = `chip ${result.best_configuration ? 'pass' : 'caution'}`; }
  renderCounts(result.search);
  const summary = document.getElementById('v3-result-summary');
  if (summary) summary.innerHTML = `<div class="chips"><span class="chip info">${esc(result.search?.termination_reason || 'unknown termination')}</span><span class="chip neutral">${esc(result.search?.physics_evaluated_count ?? 0)} Physics evaluations</span><span class="chip neutral">${result.search?.catalog_complete ? 'complete catalog' : 'partial catalog coverage'}</span><span class="chip caution">ML and Physics are shown separately</span></div><p class="micro">${esc((result.limitations || []).join(' '))}</p>`;
  const best = document.getElementById('v3-best-configuration');
  if (best) best.innerHTML = rowSummary(result.best_configuration, 'Best configuration');
  const alternatives = document.getElementById('v3-alternatives');
  if (alternatives) alternatives.innerHTML = `<h3>Passed alternatives</h3>${(result.ranked_alternatives || []).length ? result.ranked_alternatives.map((row, i) => rowSummary(row, `Passed alternative ${i + 1}`)).join('') : '<p class="muted">No additional Physics-passing alternative was found within the declared budget.</p>'}<h3 style="margin-top:18px">Failed alternatives · not recommended</h3>${(result.failed_alternatives || []).length ? result.failed_alternatives.map((row, i) => rowSummary(row, `Failed alternative ${i + 1}`)).join('') : '<p class="muted">No failed alternative was retained.</p>'}`;
  const json = document.getElementById('v3-result-json');
  if (json) json.textContent = pretty(result);
}

async function loadWaveform(candidate) {
  if (!activeJob) return;
  const node = document.getElementById(`v3-wave-${candidate}`);
  if (!node) return;
  node.textContent = 'Loading…';
  try {
    const wave = await api(`/api/v3/runs/${encodeURIComponent(activeJob)}/waveform?candidate=${encodeURIComponent(candidate)}`);
    node.textContent = `${wave.time_s.length} samples · ${wave.time_s[0]}–${wave.time_s[wave.time_s.length - 1]} s · sha256 ${wave.sha256.slice(0, 12)}…`;
  } catch (error) { node.textContent = error.message; }
}

async function pollJob(jobId) {
  if (activeJob !== jobId) return;
  try {
    const bundle = await api(`/api/v3/runs/${encodeURIComponent(jobId)}`);
    if (activeJob !== jobId) return;
    renderProgress(bundle.run);
    if (bundle.result) renderResult(bundle.result);
    if (['QUEUED', 'RUNNING'].includes(bundle.run.status)) {
      pollTimer = setTimeout(() => pollJob(jobId), 800);
    } else if (bundle.run.status === 'FAILED') {
      setText('v3-form-status', bundle.run.error || 'Search failed; no partial result was published.');
    }
  } catch (error) {
    if (activeJob === jobId) {
      setText('v3-form-status', error.message);
      pollTimer = setTimeout(() => pollJob(jobId), 2000);
    }
  }
}

async function validateRequest() {
  const status = document.getElementById('v3-form-status');
  if (status) status.textContent = 'Validating…';
  try {
    const response = await api('/api/v3/validate', {method: 'POST', body: JSON.stringify(buildRequest())});
    if (status) status.textContent = `Valid · ${response.catalog.distinct_response_candidates.toLocaleString()} response candidates`;
    renderCounts(response.catalog);
  } catch (error) { if (status) status.textContent = error.message; }
}

async function startSearch(event) {
  event.preventDefault();
  const run = document.getElementById('v3-run');
  const status = document.getElementById('v3-form-status');
  if (run) run.disabled = true;
  try {
    const request = buildRequest();
    const started = await api('/api/v3/runs', {method: 'POST', body: JSON.stringify({request})});
    activeJob = started.job_id;
    clearTimeout(pollTimer);
    document.getElementById('v3-search-result').hidden = true;
    renderProgress(started);
    if (status) status.textContent = `Queued ${started.job_id}`;
    pollJob(activeJob);
  } catch (error) { if (status) status.textContent = error.message; }
  finally { if (run) run.disabled = false; }
}

function currentRequest() {
  try { return buildRequest(); } catch { return metadata?.default_request || {}; }
}

async function fixedPredict(event) {
  event.preventDefault();
  const status = document.getElementById('v3-predict-status');
  if (status) status.textContent = 'Freezing input and loading route…';
  try {
    const request = currentRequest();
    const front = JSON.parse(document.getElementById('v3-front-network').value);
    const tail = JSON.parse(document.getElementById('v3-tail-network').value);
    const record = await api('/api/v3/predict', {method: 'POST', body: JSON.stringify({request, configuration: {
      impulse_type: request.impulse_type, topology_id: request.topology_id, polarity: request.polarity,
      stages: Math.round(number('v3-fixed-stages')), stage_charge_V: number('v3-stage-charge'), front_network: front, tail_network: tail,
    }})});
    fixedPrediction = record;
    const out = document.getElementById('v3-prediction-result');
    out.hidden = false;
    out.innerHTML = `<div class="note ${record.prediction.status === 'ML_PREDICTION' ? 'info' : 'caution'}"><div><b>${esc(record.prediction.status)}</b> · ${esc(record.prediction.source)}<br><span>${record.model.status === 'LOADED' ? `Model ${esc(record.model.model_id)}` : 'No versioned route model loaded; Physics L0 baseline is shown explicitly.'}</span></div></div><dl class="kvs tight"><div class="kv"><dt>Prediction id</dt><dd><code>${esc(record.prediction_id)}</code></dd></div><div class="kv"><dt>Gain / front / tail</dt><dd class="num">${record.prediction.gain} / ${record.prediction.front_us} / ${record.prediction.tail_us}</dd></div><div class="kv"><dt>Predicted crest</dt><dd class="num">${record.prediction.crest_V} V</dd></div><div class="kv"><dt>Physics status</dt><dd>${esc(record.physics?.application_status || 'unavailable')}</dd></div><div class="kv"><dt>Frozen input hash</dt><dd><code>${esc(record.input_sha256)}</code></dd></div></dl>${record.physics_waveform ? `<div class="actions"><button class="btn sm" data-v3-pred-wave="${esc(record.prediction_id)}">Load verified Physics waveform</button><span id="v3-pred-wave-${esc(record.prediction_id)}" class="muted small"></span></div>` : ''}`;
    document.getElementById('v3-reference-panel').hidden = false;
    if (status) status.textContent = 'Frozen prediction saved.';
  } catch (error) { if (status) status.textContent = error.message; }
}

function bytesToBase64(bytes) {
  let binary = '';
  for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
  return btoa(binary);
}

async function saveReference() {
  const status = document.getElementById('v3-reference-status');
  const file = document.getElementById('v3-reference-file').files[0];
  if (!fixedPrediction) { if (status) status.textContent = 'Freeze a prediction first.'; return; }
  if (!file) { if (status) status.textContent = 'Select a CSV reference export.'; return; }
  try {
    const metadataText = document.getElementById('v3-reference-metadata').value;
    const metadataValue = JSON.parse(metadataText);
    const raw = new Uint8Array(await file.arrayBuffer());
    const comparison = await api(`/api/v3/predictions/${encodeURIComponent(fixedPrediction.prediction_id)}/reference`, {method: 'POST', body: JSON.stringify({csv_base64: bytesToBase64(raw), metadata: metadataValue, metadata_text: metadataText})});
    const out = document.getElementById('v3-reference-result');
    out.hidden = false;
    out.innerHTML = `<div class="note caution"><div><b>${esc(comparison.qualification.status)}</b><br>Raw sha256 <code>${esc(comparison.raw_sha256)}</code><br>Absolute, relative, and tolerance values are saved per metric. The prediction record remains frozen.</div></div><pre class="v3-json">${esc(pretty(comparison.comparison))}</pre>`;
    if (status) status.textContent = `Saved ${comparison.comparison_id}`;
  } catch (error) { if (status) status.textContent = error.message; }
}

async function saveReferenceMetrics() {
  const status = document.getElementById('v3-reference-metrics-status');
  if (!fixedPrediction) { if (status) status.textContent = 'Freeze a prediction first.'; return; }
  try {
    const metadataText = document.getElementById('v3-reference-metadata').value;
    const metadataValue = JSON.parse(metadataText);
    const metrics = {};
    const crest = document.getElementById('v3-ref-crest').value.trim();
    const front = document.getElementById('v3-ref-front').value.trim();
    const tail = document.getElementById('v3-ref-tail').value.trim();
    if (crest) metrics.crest_magnitude_V = Number(crest);
    if (front) metrics[fixedPrediction.input.request.impulse_type === 'LI' ? 'T1_s' : 'Tp_s'] = Number(front);
    if (tail) metrics.T2_s = Number(tail);
    if (!Object.keys(metrics).length || Object.values(metrics).some(value => !Number.isFinite(value) || value <= 0)) throw new Error('Enter at least one finite positive scalar reference value.');
    const comparison = await api(`/api/v3/predictions/${encodeURIComponent(fixedPrediction.prediction_id)}/reference-metrics`, {method: 'POST', body: JSON.stringify({metrics, metadata: metadataValue, metadata_text: metadataText})});
    const out = document.getElementById('v3-reference-metrics-result');
    out.hidden = false;
    out.innerHTML = `<div class="note caution"><div><b>${esc(comparison.qualification.status)}</b><br>Scalar values are archived as a separate immutable comparison; no raw waveform was inferred.<br>Prediction record hash <code>${esc(comparison.prediction_record_sha256)}</code></div></div><pre class="v3-json">${esc(pretty(comparison.comparison))}</pre>`;
    if (status) status.textContent = `Saved ${comparison.comparison_id}`;
  } catch (error) { if (status) status.textContent = error.message; }
}

async function loadPredictionWaveform(predictionId) {
  const node = document.getElementById(`v3-pred-wave-${predictionId}`);
  if (!node) return;
  node.textContent = 'Loading…';
  try {
    const waveform = await api(`/api/v3/predictions/${encodeURIComponent(predictionId)}/waveform`);
    node.textContent = `${waveform.waveform_reference.sample_count} samples · sha256 ${waveform.waveform_reference.sha256.slice(0, 12)}…`;
  } catch (error) { node.textContent = error.message; }
}

async function showWorkspace() {
  clearTimeout(pollTimer);
  nav?.classList.add('active');
  document.querySelectorAll('.mainnav button').forEach(button => { if (button !== nav) button.classList.remove('active'); });
  if (!templateText) templateText = await fetch(V3_TEMPLATE).then(response => { if (!response.ok) throw new Error('Network workspace template unavailable'); return response.text(); });
  main.innerHTML = templateText;
  main.classList.add('enter');
  try { metadata = metadata || await api('/api/v3/meta'); } catch (error) { main.innerHTML = `<section class="card"><h1>v3 service unavailable</h1><p class="note fail">${esc(error.message)}</p></section>`; return; }
  renderMetadata();
  renderResearchBanner();
  document.getElementById('v3-domain').addEventListener('change', renderResearchBanner);
  document.getElementById('v3-validate').addEventListener('click', validateRequest);
  document.getElementById('v3-search-form').addEventListener('submit', startSearch);
  document.getElementById('v3-predict-form').addEventListener('submit', fixedPredict);
  document.getElementById('v3-reference-submit').addEventListener('click', saveReference);
  document.getElementById('v3-reference-metrics-submit').addEventListener('click', saveReferenceMetrics);
  main.addEventListener('click', event => { const button = event.target.closest('[data-v3-wave],[data-v3-pred-wave]'); if (button?.dataset.v3Wave) loadWaveform(button.dataset.v3Wave); if (button?.dataset.v3PredWave) loadPredictionWaveform(button.dataset.v3PredWave); });
  if (activeJob) pollJob(activeJob);
}

nav?.addEventListener('click', () => { showWorkspace().catch(error => { main.innerHTML = `<section class="card"><p class="note fail">${esc(error.message)}</p></section>`; }); });
document.addEventListener('click', event => {
  if (event.target.closest('[data-nav],[data-screen]') && !event.target.closest('[data-v3-nav]')) nav?.classList.remove('active');
}, true);

// Expose only pure-ish helpers for a small offline browser harness; the page
// remains usable without this object.
window.PowerNextV3 = Object.freeze({buildRequest, parseStages, showWorkspace});
