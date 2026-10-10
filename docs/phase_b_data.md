# Phase B v3 data contract

**Final production scope:** exactly two series/parallel resistors on each front and tail branch. Active data are `powernext/ml/data/networks_exact2_v5_aug1`; selected registry/results are `networks_exact2_v5`. Both branches are varied jointly, and all eight routes remain separate. Original v3 runs and broader catalog examples below are historical implementation context. See [exact-two data](EXACT2_DATASET_REPORT.md), [models](EXACT2_MODEL_REPORT.md), and [acceptance](PHASE_B_ACCEPTANCE.md).

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

The same report independently checks every 2,000 `Synthetic Dataset` rows.
It rebuilds the 3-uF front, tail, crest, and stage-charge values and verifies
the three observed-minus-theoretical residual identities.  All checks pass
with absolute and relative tolerances of `1e-12`; the largest absolute
reconstruction errors are `2.22e-16 us` for front timing and `4.55e-13 us`
for tail timing, with zero crest, charge, or residual error.  These static
checks are formula reconstruction evidence and do not fit workbook
observations.

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

The first prototype pilot at `powernext/ml/data/networks_v3_pilot` is retained
as historical negative evidence.  Its split contract was superseded by the
declared setup-family and normalized setup-key union fix; it is not an
accepted training input.  The interrupted first production attempt at
`powernext/ml/data/networks_v3` is likewise retained.  Its
`ABORTED_SPLIT_AUDIT.json` records the explicit setup-family split violation;
it is not resumed or used for training.

The accepted corrected 256-attempt-per-route pilot is
`powernext/ml/data/networks_v3_pilot_splitfix2`.  It produced 2,048 rows,
1,684 eligible rows, and 1,654 unique eligible response shapes.  Actual
`powernext_v3.training.load_rows` plus `assign_splits` accepts every explicit
partition with zero identity collisions.  Route unique eligible counts are
`219, 206, 241, 237, 194, 198, 224, 135`; the research 3-uF SI/OSHUNT route
is intentionally sparse in the pilot and receives the larger production
prefix.  The pilot retained explicit time-scope unsupported rows and target
domain failures with null labels.  All 14 stage counts and all 16
one-through-four-module front/tail pair strata occur in each route.  Its
source contract is frozen by the pilot manifest; the similarly named
`networks_v3_pilot_v2` directory remains historical until separately audited
against the current source contract.

The accepted staged production dataset is
`powernext/ml/data/networks_v3_r2`.  The complete frozen design has 30,000
requests per route; this first learning-curve stage evaluates the configured
122,000-attempt prefix and ends at `STAGE_COMPLETE`.  It contains 122,000
rows, 99,852 eligible rows, and 92,662 canonical eligible response shapes.
Unique eligible counts by route are `10,938, 11,063, 10,572, 10,563, 11,672,
11,483, 11,610, 14,761` in the route order listed above, so every route clears
the 10,000-shape gate without an extension.  The independent acceptance
record is `evidence/phase_b/production_dataset_audit.json`: it verifies the
actual training loader/splitter, zero split identity collisions, label/null
handling, source and row/design hashes, all 14 stages, all 16 module pairs,
the 4,192-recipe network catalogue, and all 65 representative waveform hashes
under the per-route cap.  No workbook observations were used for these labels
or for request selection.
