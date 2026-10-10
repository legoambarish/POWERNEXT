# Phase B implementation record

## Authorization and baseline

Approved scope: uniform canonical series/parallel recipes up to FOUR modules per
front or tail branch; separate 0.5 and 3 uF domains; four specified ML candidates;
adaptive ML priority with detailed Physics verification; complete-search baseline;
datasets, Excel comparison, judging workflow and tested offline release.

- Baseline commit: `5ed4b6a31c40201959146bd677f8c181d4935712` (main).
- Implementation branch: `phase-b/networks-ml-v3`.
- Accepted release is preserved at `../release/PowerNext_Track1_Offline`.
- Accepted ZIP SHA256: `297c6b3530f7933436ce2daf4b503ea5307873d291884e5f45ae2cc1ef047f98`.
- No original workbook, source evidence, v2 dataset, model or release is overwritten.

## Architecture contract

New code resides in `powernext_v3`, reusing the legacy graph, trajectory sampler and
waveform evaluator. Legacy scientific source files remain unchanged so their
existing model compatibility hashes remain valid. New artifacts have independent
source fingerprints, domains and paths.

Domain IDs are `cpri_0p5uf` and `research_3uf`. The latter uses explicitly
hypothetical 200 kV/stage, 60 kJ/stage and 900 kJ total limits, derived from 3 uF;
these are NOT CPRI equipment ratings. Both topologies remain declared hypotheses.
Actual inventory, mounting and pulse-rating approval remain unknown.

Physics API: `powernext_v3.physics.simulate(configuration, setup, domain_id=...)`.
Configuration includes equivalent front/tail resistance and optional exact trees;
setup uses the existing SI-unit field names. Research equivalent-only simulations
do not create physical resistor parts. Optimizer recommendations require recipes.

## Work in progress

- Lead: profiles, verified Physics integration, search contracts and integration.
- Worker networks (5.6 Luna MAX): exact canonical networks and unit tests.
- Worker datasets (5.6 Luna MAX): staged grouped data and Excel comparison.
- Worker ML (5.6 Luna MAX): batch features, four-model evaluation and serving.

## Acceptance still outstanding

New scientific regression, generated dataset coverage and split integrity,
eight trained routes with selection evidence, rare-feasible retention, UI and
unseen-reference workflow, full regression, release extraction, manifests and
commit remain tracked gates. The 17-case four-policy search benchmark is now
complete and documented, but its shared-load timings are not controlled speedup
evidence and it does not demonstrate incremental ML benefit over analytical.
Nothing in this file claims package acceptance has passed.

## First verified increment

Profile-aware Physics integration: seven new tests passed (legacy single-response equivalence in both modes/topologies, two-domain energy, independent zero-L oracle, full-stage GSHUNT reduction, exact charge/polarity reuse, invalid constraints). Legacy scientific files remain unchanged.

## Network and search increment

- Exact canonical enumeration: 6 / 48 / 412 / 4192 physical recipes through
  one / two / three / four modules; 6 / 48 / 407 / 4080 exact resistance groups.
- Full four-module space: 233,049,600 electrical response configurations across
  fourteen stage counts. Integer indexing and streamed deterministic traversal
  avoid materializing this Cartesian product.
- New network + Physics unit tests: 22 passed. Optimizer tests: 10 passed.
- New complete-Physics SI replay: all 504 settings, 14 passes, 27 unsupported;
  same best N=9, Rf=3700, Rt=5000, charge=164366.2942328 V as legacy evidence.
  One development run took 6.40 seconds; this is not a controlled speedup claim.
- Rare LI test: deliberately wrong ML timing predictions still retain the sole
  passing setting via the complete small-catalog fallback.
- Search results structurally separate passing alternatives and failed
  diagnostics; partial catalog and partial Physics coverage are explicit.
- Dataset review identified sampling correlation, stage coverage, split-identity,
  and exception-handling issues before any full generation. Worker corrections
  are required before freezing the dataset design.
- Model selection must include waveform-feasibility ranking metrics; gain-order
  correlation alone is not acceptable evidence of candidate retention.

# Integration checkpoint — 10 October 2026, 12:06 UTC

The complete legacy runner passed all nine suites: 47 Physics, 30 ML,
89 optimizer, 61 application, 66 frontend, 86 red-team, one UI-race fixture,
17 integration and eight final-release checks (405 checks total).
Machine-readable timings are in `evidence/phase_b/legacy_regression_summary.json`.
This validates the current source against the legacy contracts; it is not
acceptance of the still-pending new model artifacts or packaged v3 release.

Sixteen independent validation request oracles completed, each covering 6,912
electrical candidates. Their input design is separate from the final benchmark
seed. Oracle ML-score ties are resolved by catalog index, never the stored
Physics ranking. Five new benchmark-integrity tests pass.

The production dataset sampling audit found and corrected correlated tail
resistance sampling and repeated per-request catalog sorting. The corrected
2,048-input pilot design covers every stage from 2 to 15, all sixteen front/tail
module-count pairings, broad independent log-resistance samples, and approximate
inverse-guided tolerance probes. Full production generation remains gated on
current-source pilot validation and independent eligible-shape accounting.

## Dataset integrity checkpoint — 10 October 2026, 12:24 UTC

The first production attempt, `networks_v3`, was stopped after 4,500 rows when
the actual training loader found a declared setup-family split crossing that
the generator's own audit missed. Its rows and `ABORTED_SPLIT_AUDIT.json` remain
preserved; this attempt is rejected for training. Commit `efe42f7` retains the
pre-correction source for reproducing that negative evidence.

The corrected splitter unions normalized response identity, normalized setup
identity, and declared setup-family identity before assigning a partition.
The 2,048-row `networks_v3_pilot_splitfix2` passed the actual training loader,
all three identity checks, and canonical duplicate-label consistency. It contains
1,654 independent eligible shapes, with 1,627/158/263 total rows assigned to
train/validation/test. All fourteen stages and sixteen module-count pairs occur.

Production `networks_v3_r2` freezes 30,000 inputs per route before simulation.
Its initial per-route prefixes total 122,000 attempts, targeting at least 10,000
independent eligible shapes for each of eight routes. The source is frozen
during generation. At 67,750 attempts, all four completed 0.5 uF routes exceed
10,000 independent eligible shapes. Full source/hash/split/coverage acceptance
is still pending completion; no production model has yet been trained.

The independent workbook report reproduces 7,026 cached numeric formula cells.
Twenty-four detailed 3 uF comparisons retain six unsupported SI/OSHUNT cases
explicitly. Workbook synthetic observations are not laboratory measurements.

The application/API and rendered browser audit is recorded in
`evidence/phase_b/application_audit.json`; it currently exercises Physics fallback.
Actual selected-model and packaged-offline acceptance remain required.

## Integrated acceptance checkpoint — 10 October 2026, 12:36 UTC

All ten integrated suites passed: 47 Physics, 30 legacy ML, 89 optimizer,
61 application, 100 v3, 67 frontend, 86 red-team, one UI-race fixture,
17 integration and eight final-release checks: **506 checks**.
`evidence/phase_b/integrated_regression_summary.json` retains the commands,
exit codes and elapsed times. This source-regression result still does not
substitute for the pending extracted package/selected-model acceptance.

Production R2 passed both the data worker's coverage/hash/split audit and the
lead's independent actual-loader/deduplication preflight. It contains 122,000
attempts, 99,852 eligible rows and 92,662 canonical eligible shapes. Each of
eight routes contains 10,563–14,761 eligible shapes and nonempty grouped
train/validation/test partitions. All fourteen stages and sixteen front/tail
module-count pairs occur in every route. Sixty-five representative waveform
files pass their hashes.

The complete initial data stage, rejected attempt, pilots and validation
oracles are preserved in `training-data/PowerNext_Networks_v3_Data_Stage1_20261010.zip`.
Its 372 files were individually verified after compression; the adjacent
manifest provides hashes and recovery paths. The extracted working copies
remain unchanged. Production model training is running, with final-test
performance sealed from the lead's learning-curve decision.

The complete Excel static-data verification also passed all 2,000 records:
front maximum absolute residual is 2.22e-16 us, tail 4.55e-13 us; crest,
charge and stored observation-residual identities match exactly. The original
workbook hash remains unchanged. This complements the 7,026 formula-cell
reproduction and the separately interpreted transient comparisons.

## Frozen model and oracle checkpoint — 10 October 2026

All 32 train-only candidates completed for eight routes, with matched
25/50/100% learning-curve subsets. The lead preregistered the capacity-decision
thresholds before inspecting validation performance. The initial R2 data stage
and selected models are frozen: no route triggered expansion. Curves still
improve by 22–31% from half to full training capacity; this is an accuracy-gate
acceptance, not evidence of a learning plateau. Test performance remained sealed
until the validation decision and independent oracle reconciliation completed.

The earlier oracle manifest did not bind all execution sources. A new immutable
v2 oracle set binds catalog, optimizer, features, benchmark and runtime versions.
All sixteen 6,912-candidate cases were replayed and compared by catalog index:
zero configuration or scientific mismatches, zero tolerated numeric differences,
and zero pass/unsupported-count differences. The original evidence remains
preserved with its historical provenance limitation. The new eighteen-file
oracle archive was reread and verified member by member.

The production application audit loads all eight selected routes, exercises
fixed prediction and subsequent reference import without changing its hash,
and verifies separate ML/Physics/OOD presentation in the browser. A bounded
four-module API check verifies actual ML participation and honest partial
coverage; it is not the final controlled performance benchmark.

The separate four-policy search benchmark is complete across 17 hashed case
summaries: 16 held-out frozen requests plus the labelled rare-LI regression.
Across the 12 feasible frozen requests, analytical and ML retain all 1,019
passing alternatives with zero observed regret; combined retains 1,014/1,019,
losing five alternatives in one request while retaining its best objective.
The four no-feasible requests have complete declared-catalog no-solution
results only for `complete_physics`; adaptive policies are budget-limited and
remain `NO_COMPLIANT_CONFIGURATION_YET`. ML was operationally used, but this
sample does not establish incremental benefit over analytical. See
[`docs/PHASE_B_SEARCH_BENCHMARK.md`](PHASE_B_SEARCH_BENCHMARK.md) and the
machine-readable [manifest](../evidence/phase_b/search_benchmark/manifest.json).
The run used shared machine load, so its timing ratios are observations rather
than controlled speedup claims.

## Final model evaluation checkpoint

The frozen 32 models were reloaded and independently evaluated against the
strict v2 oracle: all scientific ranking fields match and all eight selections
are unchanged. Recomputed final-candidate validation scores agree exactly with
the original training records. Wrapper annotations added by the training layer
caused an initial schema-only key-set mismatch; the raw mismatch and corrected
comparison boundary are preserved in the final report.

The held-out test metrics were unsealed only after the data/selection decision.
`docs/PHASE_B_MODEL_REPORT.md` and `evidence/phase_b/final_model_evaluation.json`
record all four candidates per route, actual errors, OOD counts, measured model
loading/inference, and limitations. LI selected-model front MAE spans
0.0145–0.0307 us and SI front MAE 0.0237–0.0837 us in this synthetic test set.
Worst cases remain visible, including a 1.174 us research-LI front error;
small average errors are not universal conformity guarantees.

The 100% learning-curve estimator and the serving estimator are separate fits
of the same train-only row set in different orders. ExtraTrees consequently
has slightly different curve and final-artifact validation metrics. The capacity
gate used the curve progression plus actual final-artifact boundary errors;
all final-artifact scores also remain below its 0.25 study threshold. No test
result changed a dataset, model, selection or search policy.
