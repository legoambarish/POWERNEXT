# Phase B v3 data contract

Phase B uses the standalone `powernext_v3.dataset` pipeline.  It is separate
from the legacy `powernext/ml` generator and leaves the original workbook and
legacy artifacts unchanged.

The eight routes are the Cartesian product of:

| evidence domain | mode | topology |
| --- | --- | --- |
| `cpri_0p5uf` | `LI`, `SI` | `GSHUNT_v0`, `OSHUNT_v0` |
| `research_3uf` | `LI`, `SI` | `GSHUNT_v0`, `OSHUNT_v0` |

The initial design target is 10,000 regression eligible independent response
shapes per route.  Each route has a deterministic extension capacity of
30,000 rows for the staged learning curve.  The complete 30,000-row-per-route
design and its input-only groups/splits are frozen up front, while generation
defaults to an initial 12,000-attempt prefix (target plus 20 percent).  Use
`--stage-per-route` to resume the same design at a larger 20,000 or 30,000
prefix after route coverage is inspected.  Repeatable
`--route-stage-limit domain::mode::topology=N` arguments extend only selected
routes; unspecified routes retain their current prefix.  A run reports `STAGE_COMPLETE` for
a completed prefix and `FULL_DESIGN_COMPLETE` only after the full design is
simulated; the eligible gate remains false with a route shortfall.  The design
contains bounded
series/parallel resistor recipes with one through four modules, numeric
equivalent controls, front and tail boundary probes, rare-feasible
neighborhood probes, and random requests attached to fixed setup families.
The design is created from inputs alone; no physics label, workbook output, or
test replay is used to select a request.

Network recipes come only from the public
`powernext_v3.networks.enumerate_networks(max_modules=4)` API.  If that API is
missing, empty, malformed, or lacks a one-through-four-module stratum,
generation fails before writing design rows; the dataset never substitutes a
single-resistor fallback.  The manifest records the API source, recipe count,
module-count coverage, and source hashes.

For example, the sparse research 3-uF SI/OSHUNT route can be extended inside
the frozen 30,000-row design without re-simulating other routes:

```text
python -m powernext_v3.dataset generate --output powernext/ml/data/networks_v3 \
  --route-stage-limit research_3uf::SI::OSHUNT_v0=30000
```

Each row is JSONL with these fields:

* `domain_id`, `mode`, `topology`/`topology_id`, `configuration`, and `setup`;
* `features` from the public `feature_rows` API;
* `gain`, `front_us`, and `tail_us`, which remain `null` until a valid physics
  simulation supplies complete metrics;
* `split`, `group_id`, `response_group_id`, normalized response/setup keys,
  `setup_family_id`, and the frozen `split_frozen` marker;
* `regression_eligible`, `status`, compact `metrics`, input hash, and compact
  simulation provenance.

Amplitude, polarity, and equivalent terminal-capacitance partitions share a
response identity.  A connected group also includes the normalized fixed
setup identity, so aliases with different setup IDs cannot cross a split.  The
response key, setup key, group ID, split, and `split_audit` record are
persisted before feature or label enrichment.  Consequently, rows in one group
cannot cross train/validation/test, and setup families remain atomic.
Unsupported or invalid physics cases stay in `rows.jsonl` with null labels and
an error code.  Route eligibility gates count unique normalized response keys;
the manifest separately records the raw eligible row count, so repeated
equivalent responses cannot satisfy the independent-shape target.

`generate` is append-only and resumable.  It writes `design.jsonl`,
`rows.jsonl`, `manifest.json`, and a small `progress.json` heartbeat.  A
matching in-progress manifest can resume; a different seed, plan, or design
hash is rejected.  Completed rows are never recomputed or overwritten.
Waveforms are omitted by default in model data; `representative` stores at
most the configured bounded number per route with early coverage across case
strata, `failure` stores failure artifacts when a simulator returns one, and
`all` is available only for a deliberately small diagnostic run.  Use
`python -m powernext_v3.dataset status` to inspect
the API before starting a run, then invoke `design` or `generate` explicitly.

The Excel comparison is a separate read-only command:

```text
python -m excel_comparison --output phase_b_excel_report.json --sample-per-stratum 2
```

The preserved source is
`evidence/sources/Hybrid_Physics_ML_Impulse_Generator_Optimiser.xlsx` with
SHA-256
`e855eadbe4d6da2579316e89e025e6990f9ba3c522a5af96d1dd2a5522d77480`.
`excel_comparison.py` independently reproduces all 7,026 cached numeric
formula cells in the source workbook: the calculator's 1.67 front heuristic,
0.693 tail heuristic, efficiency input, kNN helper distances/ranks/weights,
and weighted corrections.  The XML reader provides the same check when
`openpyxl` is unavailable.

The stratified RLC report samples original synthetic inputs by impulse type,
workbook split, and stage band.  It maps those inputs into the 3-uF research
profile and runs both graph assumptions.  Workbook physics values are stored
under `workbook_theoretical`; any workbook observed columns are stored
separately under `workbook_observed`; detailed RLC output is a separate
`detailed_rlc` model result.  The original workbook's observations are never
used to train or enrich generated dataset rows.  A comparison is therefore a
model-to-model diagnostic, not laboratory validation or a hardware approval.
The final sample report is written to
`evidence/phase_b/excel_comparison.json`, with an explanatory summary in
`evidence/phase_b/excel_comparison.md`.

The corrected 256-attempt-per-route pilot is retained at
`powernext/ml/data/networks_v3_pilot_v2`.  It produced 2,048 rows, 1,684
eligible rows, and 1,654 unique eligible response shapes.  Route unique
eligible counts are `219, 206, 241, 237, 194, 198, 224, 135`; the research
3-uF SI/OSHUNT route is intentionally a sparse pilot and is the first route
for a capacity extension.  The pilot retained 156 explicit time-scope
unsupported rows and 64 explicit 5-MV target-domain failures.  All 14 stage
counts and all 16 one-through-four-module front/tail pair strata occur in each
route; 220 distinct requested front/tail pairs occur per route.  The pilot
saved 8 representative waveforms per route under the configured bound and
completed in about 18 seconds on the bounded two-worker run.  The manifest's
unique response-key counts, raw eligible-row count, split audits, source
hashes, and network catalogue provenance are the gate evidence.
