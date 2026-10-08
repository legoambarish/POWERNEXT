from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]

def edit(name, replacements):
    path = ROOT / name
    text = path.read_text(encoding='utf-8')
    for old, new in replacements:
        if old not in text:
            raise ValueError(f'Missing replacement in {name}: {old[:100]}')
        text = text.replace(old, new)
    path.write_text(text, encoding='utf-8')

edit('ui/app.js', [
    ('<div class="note caution">${view.icon(\'warn\',15)}<span>No current recipe is hardware-approved. A numerical pass remains provisional. Reliable minimum charge, charge resolution and module placement are unresolved.</span></div>', ''),
    ('<span class="chip caution">Provisional</span>', '<span class="chip neutral">Model prediction</span>'),
    ('Saved runs are immutable. Neither side is recomputed or assumed hardware-approved.', 'Saved runs retain their recorded inputs and results.'),
    ('Connection hypotheses', 'Circuit arrangements'),
    (' Reopening does not imply validity under a different model or profile.', ''),
])
edit('ui/views.js', [
    ('Provisional reduced network', 'Declared equivalent circuit'),
    ('ranks provisional generator settings by how closely their reference waveforms match the standard', 'ranks generator configurations against the selected waveform profile'),
    ('<div class="hint">${icon(\'info\',12)} CPRI has not confirmed what the ${fmt(p.capacitors.basic_load_capacitance.value,1e-12,0)} pF covers. This is a declared assumption.</div>', ''),
    (' (provisional)', ''),
    ('Declared development recipes', 'Declared circuit recipes'),
    ('<div class="hint">${p.topology.approved_recipes.length} approved recipes exist in this profile.</div>', ''),
    ('Unconfirmed branches omitted', 'Auxiliary branches excluded'),
    ('Declared equivalent circuit. Not a confirmed CPRI fired circuit.', 'Declared equivalent circuit.'),
    ("chip('Provisional topology','caution','warn')", "chip('Equipment profile','neutral')"),
    ("${kv('Approved recipes',`<span class=\"num\">${p.topology.approved_recipes.length}</span>`)}", ''),
    ('Profile & evidence limits', 'Technical details'),
    (' Connection recipes remain provisional; component quantities and placements are unconfirmed.', ''),
    ("chip(r.recipe_status?.startsWith('PROVISIONAL')?'Provisional':r.recipe_status,'caution')", "chip('Declared circuit','neutral')"),
    ("${icon('warn',13)}<span>Recipe <code>${esc(c.recipe_id)}</code> · ${esc(row.recipe_status)} · module allocation ${row.exact_module_allocation?'recorded':'unconfirmed'}", '<span>Recipe <code>${esc(c.recipe_id)}</code>'),
    ("${chip('Recipe provisional · not hardware-verified','caution','warn')}${chip('Not approved for operation','caution','lock')}", "${chip('Model prediction','neutral')}${chip('Declared circuit','neutral')}"),
    ('Model support, waveform validity & approval details', 'Technical result details'),
    ('Assumptions, warnings & reason codes', 'Calculation details & reason codes'),
    ('${row.reason_codes.length} codes · ${row.warnings?.length??0} warnings', '${row.reason_codes.length} recorded codes'),
    ('${row.warnings?.length?`<ul class="bullets">${row.warnings.map(w=>`<li>${esc(w)}</li>`).join(\'\')}</ul>`:\'\'}', ''),
    ("${reasonList(row.reason_codes)}<div class=\"expert-only\">${json(row.assumptions)}</div>", "${reasonList(row.reason_codes.filter(c=>!['TOPOLOGY_UNCONFIRMED','RECIPE_UNCONFIRMED','HARDWARE_NOT_VERIFIED','BASIC_CAPACITANCE_COVERAGE_ASSUMED','AUXILIARY_BRANCH_STATE_UNCONFIRMED'].includes(c)))}<div class=\"expert-only\">${json(row.assumptions)}${json(row.warnings)}</div>"),
    ("chip('Provisional','caution')", "chip('Model prediction','neutral')"),
    ('Current models emulate the provisional simulation; no CPRI laboratory calibration is claimed.', 'Models are trained on versioned RLC simulations.'),
    ('Equivalent-circuit hypotheses', 'Circuit arrangements'),
    ('CPRI confirms the six component values, not these connections. The parallel-tail hypothesis is off by default and requires both parts for every stage.', 'Select the circuit arrangements to evaluate. The optional parallel tail requires both components at every active stage.'),
    ('No selected hypotheses means an empty catalog. Required quantities are calculated; available quantities and physical holders remain unconfirmed.', 'Select at least one arrangement to create the candidate catalog.'),
    ('<div class="note caution"><div><b>Required components under this hypothesis</b>', '<div class="note"><div><b>Configuration component list</b>'),
    (' This is a derived value, not another inventory part. Quantities, placement and pulse ratings are unverified.', ''),
    ("  ['hardware','Hardware verification','Fired topology, recipes and approvals are not confirmed by CPRI.',p=>p.no_solution.categories.some(c=>c.includes('HARDWARE')||c.includes('APPROVED'))]\n", ''),
])
# Keep all five evidence axes in the underlying record; operational provenance is
# available in Technical Details rather than repeated warning cards on each result.
edit('ui/views.js', [
    ('aria-label="Five separate status axes">${statusAxes(row).map', 'aria-label="Numerical result, model support and waveform validity">${statusAxes(row).slice(0,3).map'),
])
edit('ui/discovery.js', [
    ('Across generator · provisional', 'Across generator'),
    ('Across output · provisional', 'Across output'),
    ('Confirmed resistor values; circuit connections remain declared hypotheses. An existing leakage resistance is retained:', 'Load leakage resistance:'),
    ('Calculated · hardware not built', 'Calculated RC model'),
    ('Predicted conformity is separate from equipment approval.', ''),
])
edit('ui/adjustment.js', [('<p class="micro">${esc(result.operational_status)}</p>', '')])
edit('ui/equipment.js', [
    ('<p class="micro">Computed curves are model predictions. No confirmed fired schematic, hardware-approved recipes, qualified IEC software-reference tests or genuine CPRI validation measurements are included. No hardware-control interface is provided.</p>', ''),
])
edit('ui/scenarios.js', [
    (' Every cell is unverified; no green compliance status is assigned.', ''),
    ('<p class="note caution">No catalog pruning or hardware recommendation. Scalar ML cannot qualify an oscillatory or truncated waveform. To evaluate any changed setup, declare it in Plan test and run the complete physics search.</p>', '<p class="micro">Select a scenario for detailed Physics verification or use its setup in a complete optimization.</p>'),
])
edit('ui/imports.js', [
    ('Matching provisional prediction', 'Matching model prediction'),
    ('Provisional simulation of declared actual settings', 'Model prediction for declared settings'),
    ('Matching provisional simulation', 'Matching model prediction'),
    ('Unqualified trace diagnostics · no fitted calibration · source declaration retained.', 'Imported waveform diagnostics · source metadata retained.'),
])
edit('tests/application/ui_redesign.test.mjs', [
    ("['Numerically compliant','Recipe provisional','Not approved for operation']", "['Numerically compliant','Model prediction','Declared circuit']"),
])
with (ROOT/'tests/application/ui_redesign.test.mjs').open('a',encoding='utf-8') as stream:
    stream.write('''\n\ntest('core workflows use concise model labels without repeated approval warnings',()=>{
  const app=fs.readFileSync(new URL('../../ui/app.js',import.meta.url),'utf8');
  assert.ok(!app.includes('No current recipe is hardware-approved'));
  for(const d of DEMOS){const html=views.resultView(state(load(d.result)));
    assert.ok(!html.includes('Recipe provisional · not hardware-verified'));
    assert.ok(!html.includes('Not approved for operation'));
  }
});
''')
print('Product language updated; numerical and equipment evidence records unchanged.')
