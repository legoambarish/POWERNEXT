import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const read = name => fs.readFileSync(path.join(root, name), 'utf8');
const index = read('ui/index.html');
const html = read('ui/networks.html');
const js = read('ui/networks.js');

assert.match(index, /id="v3-networks-nav"/);
assert.match(index, /data-v3-nav="networks"/);
assert.match(index, /src="\/networks\.js"/);

for (const id of [
  'v3-network-workspace', 'v3-search-form', 'v3-domain', 'v3-impulse', 'v3-topology',
  'v3-target', 'v3-polarity', 'v3-max-modules', 'v3-search-mode', 'v3-priority',
  'v3-max-ml', 'v3-max-physics', 'v3-budget', 'v3-progress-events', 'v3-search-result',
  'v3-front-network', 'v3-tail-network', 'v3-predict-form', 'v3-reference-file',
  'v3-reference-metadata', 'v3-reference-submit', 'v3-ref-crest', 'v3-ref-front', 'v3-ref-tail', 'v3-reference-metrics-submit',
]) assert.match(html, new RegExp(`id="${id}"`), `missing ${id}`);
assert.match(html, /id="v3-stage-charge"[^>]*step="any"/, 'fixed prediction accepts fractional stage charge');

for (const phrase of ['Research comparison domain', 'Physics-compliant numerical candidate', 'Passed alternatives', 'Failed alternatives', 'not recommended', 'Raw CSV bytes', 'immutable', 'ML and Physics']) {
  assert.match(`${html}\n${js}`, new RegExp(phrase.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i'), `missing UI copy: ${phrase}`);
}

for (const route of ['/api/v3/meta', '/api/v3/validate', '/api/v3/runs', '/api/v3/predict', '/api/v3/predictions/', '/api/v3/runs/', '/reference-metrics', '/waveform']) {
  assert.match(js, new RegExp(route.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')), `missing route ${route}`);
}
for (const contract of ['failed_alternatives', 'catalog_complete', 'physics_evaluated_count', 'PHYSICS_FALLBACK', 'csv_base64', 'input_sha256', 'raw_sha256']) {
  assert.match(`${html}\n${js}`, new RegExp(contract), `missing contract field ${contract}`);
}
assert.match(js, /recipe\?\.id/, 'renders canonical recipe identifiers from result rows');
assert.match(js, /component_ohm/, 'renders component BOM values from result rows');

console.log('v3 network workspace static contract: ok');
