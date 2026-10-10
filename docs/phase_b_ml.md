# Phase B v3 ML layer

**Final production scope:** exactly two series/parallel resistors on each front and tail branch. Active data are `powernext/ml/data/networks_exact2_v5_aug1`; selected registry/results are `networks_exact2_v5`. Both branches are varied jointly, and all eight routes remain separate. Original v3 runs and broader catalog examples below are historical implementation context. See [exact-two data](EXACT2_DATASET_REPORT.md), [models](EXACT2_MODEL_REPORT.md), and [acceptance](PHASE_B_ACCEPTANCE.md).

This package is a route-specific screening layer for the approved Phase B
simulation study.  It is separate from the historical `powernext/ml` package
and does not alter its registries, models, data, or results.

The route key is `domain_id:mode:topology`, with domains
`cpri_0p5uf` and `research_3uf`, modes `LI` and `SI`, and topologies
`GSHUNT_v0` and `OSHUNT_v0`.  A model is trained and loaded for one route only;
cross-domain or cross-topology use raises a route compatibility error.  The
research 3 µF profile remains a separate hypothetical comparison domain.

`powernext_v3.features.feature_matrix(...)` is the batch feature API.  It
accepts active stages and per-stage equivalent front and tail resistances,
plus a legacy SI-unit setup dictionary/object.  The public schema is:

```text
stages, front_per_stage_ohm, tail_per_stage_ohm,
dut_nF, divider_nF, stray_nF, basic_additional_nF,
loop_uH, loop_ohm, load_kohm,
Cg_nF, CL_nF, Rf_ohm, Rt_ohm,
CL_over_Cg, Rf_CL_us, Rt_Cg_us, LC_us, zero_L,
baseline_gain, baseline_front_us, baseline_tail_us
```

The last three values are the `BASELINE_COLUMNS` L0 oracle.  It uses the
legacy two-capacitor characteristic rates for the selected topology and
vectorized bisection for the 30%, 90%, and falling 50% crossings.  The oracle
is independent of stage charge, requested crest, polarity, and recipe
identity.  The optional legacy leakage field `load_resistance_ohm` is rejected
explicitly because it is outside this L0 oracle; callers should use the
physics route until a versioned leakage baseline exists.  `feature_rows(configurations, setup, domain_id)` returns the same
schema as JSON-friendly dictionaries.  Optional network trees are reduced to
their equivalent resistance; their identities are not features.

Each data-worker JSONL row must retain the route metadata and simulation
provenance alongside the feature dictionary and labels:

```json
{
  "domain_id": "cpri_0p5uf",
  "mode": "LI",
  "topology": "GSHUNT_v0",
  "features": {"...": "..."},
  "gain": 0.94,
  "front_us": 1.3,
  "tail_us": 50.2,
  "split": "train",
  "group_id": "setup-family-1",
  "eligible": true,
  "status": "VALID",
  "configuration": {"...": "..."},
  "setup": {"...": "..."}
}
```

The four approved candidates per route are exactly
`physics_guided`/`residual` crossed with `extra_trees`/`hist_gradient_boosting`.
The residual formulation predicts positive log ratios to the L0 baseline; the
physics-guided formulation predicts positive outputs with the baseline in its
feature context.  `NetworkModel.predict` returns an `N x 3` array ordered as
`gain`, `front_us`, and `tail_us`.  `NetworkModel.ood` uses continuous feature
ranges and nearest-neighbour distance in transformed feature space.  It does
not reject a resistor solely because that exact value was absent from the
training catalog.

Training reads a completed immutable dataset and never edits it.  The data
worker manifest must be `COMPLETE`, `STAGE_COMPLETE`, or
`FULL_DESIGN_COMPLETE`, must contain a matching `rows_sha256`, and must bind
the current v3 feature/network/profile/Physics source hashes.  `IN_PROGRESS`,
`FAILED`, missing manifests, missing hashes, and stale source contracts fail
closed.  The tiny `write_rows_jsonl(..., fixture=True)` path is reserved for
the contract tests and does not represent production data.  Selection uses
validation rows only.  All four 100% train-only candidates are persisted
as immutable cards before the held-out test is read, so an independent
request-level oracle can choose among them without retraining.  The selected
winner is then compared with the other train-only candidates on the untouched
test rows.  Reports include MAE, RMSE,
P95, maximum error, tolerance-normalized errors, staged 25/50/100% learning
curves, fit/predict throughput, and artifact size.  The legacy
`boundary_errors` fields are conformity-distance diagnostics: they measure how
far a prediction lies outside a timing band.  They are not actual prediction
error for cases near a boundary.  The corrected near-boundary metric selects
truth cases within 25% of either tolerance half-width and reports absolute
prediction-minus-truth error; see
[`production_validation_report.json`](../evidence/phase_b/production_validation_report.json)
and the final frozen evaluation in
[`PHASE_B_MODEL_REPORT.md`](PHASE_B_MODEL_REPORT.md).  The built-in request proxy evaluates one deterministic 1 MV target per
fixed-setup validation group using profile charge/energy caps and the legacy
waveform limits.  It reports feasible misses/hits at top-1/3/5, first feasible
prefix rank, true-J regret, and group coverage status.  Gain-order concordance
is retained only as a named secondary diagnostic.  The validation-only
selection key uses an independent request oracle when supplied, then missed
feasible requests at top-5, true-J regret, normalized error, throughput, and
fit time.  The `optimization_validation_metrics` hook receives
`(fitted_model, validation_rows)` when declared with those two argument names,
so the lead can supply a complete-catalog request oracle without test-row
access; the compact row/prediction hook form remains supported.  A route whose
oracle requests contain no true-feasible candidate is marked
`UNAVAILABLE_NO_TRUE_FEASIBLE_REQUESTS`; its feasible retention and regret are
undefined, and selection explicitly falls back to normalized validation
regression evidence.  Hook and frozen-oracle manifest hashes are recorded in
run and model provenance.

Before fitting, eligible rows are grouped by route and the data worker's
normalized `response_group_key` (with documented legacy aliases).  Repeated
charge/polarity variants contribute one deterministic canonical row; labels
must agree within the recorded numerical tolerances or training fails closed.
The original row hash and a per-row duplicate audit remain in the run output,
and learning-curve counts use canonical response shapes.  The staged subsets
are frozen once per route and reused by all four candidates; their row/group
hashes are recorded so learning-curve comparisons share the same samples.  A
plain `group_id`
is not used for this deduplication because distinct shapes may carry different
group identifiers.

Production training performs a preflight before fitting: all eight route keys
must be present, and every route must have nonempty train, validation, and test
partitions.  A missing or partial route fails before model artifacts are
created.  Explicit fixture runs are scoped in their result and run manifests
as `COMPLETE_FIXTURE` and do not establish production coverage.

Once the generated v3 dataset is complete and its manifest hash is recorded,
run the versioned command:

```powershell
$python = ".\runtime\python.exe"
& $python -B -m powernext_v3.training train `
  --data-dir .\powernext\ml\data\networks_v3_r2 `
  --output-dir .\powernext\ml\results\networks_v3 `
  --registry-dir .\powernext\ml\registry\networks_v3 `
  --optimization-oracles .\powernext\ml\data\networks_v3_validation_oracles_v2
```

`--optimization-oracles` is optional until the independent complete-catalog
validation oracle is ready.  When supplied, the trainer constructs the
`OracleValidation` hook and gives each fitted candidate its route-matched
oracle requests; the oracle is validation-only and is never read for the
held-out test report.

The recorded production run used the completed initial validation-oracle
directory `powernext/ml/data/networks_v3_validation_oracles`.  The strict v2
directory shown in the command was generated afterward for an
execution-contract-aware re-evaluation; exact request/candidate scientific
replay confirmed that it does not change the frozen selection.  It must not be
described as the oracle used during the original training run.  Registry cards
bind the route, feature order, model hash, data hash, v3 source/physics
fingerprints, and runtime versions.  Model loading verifies those hashes and
rejects modified artifacts or incompatible runtime/provenance information.
The [R2 manifest](../powernext/ml/data/networks_v3_r2/manifest.json),
[training results](../powernext/ml/results/networks_v3/results.json),
[selection decision](../evidence/phase_b/lead_validation_decision.json), and
[final four-candidate report](PHASE_B_MODEL_REPORT.md) are retained as the
production evidence set.

`selected_models.json` is the serving handoff: each key is
`domain_id:mode:topology` and each value is the selected immutable model
folder name.  The per-route `results.json` entry also retains
`candidate_models` for all four train-only artifacts and their validation and
held-out comparison metrics.

The tests in `tests/test_v3_ml.py` use a tiny explicit fixture to verify the
API, scalar L0 agreement, candidate restrictions, OOD interpolation,
artifact-integrity checks, and validation/test ordering.  They are contract
tests only and make no training acceptance claim.

### Supported 2/3-module held-out scope

The supplemental held-out table in [the final model report](PHASE_B_MODEL_REPORT.md) and [`evidence/phase_b/two_three_model_scope.json`](../evidence/phase_b/two_three_model_scope.json) stratifies the frozen canonical test rows by `max(front_network_module_count, tail_network_module_count) <= 2` versus exactly `== 3`, separately for all eight routes. It reuses original selected-model predictions from the production `results.json`; it does not retrain or run new inference. The trained artifacts remain mixed 1–4-module models, and rows with maximum count 4 are historical/excluded from the two active strata.

The exact count fields are `front_network_module_count` and `tail_network_module_count` in immutable `design.jsonl`; each test row is joined by `row_id` and checked against the leaf count of the equivalent-resistance trees stored in `rows.jsonl`. v3 features use equivalent resistance and physics baseline columns while excluding recipe/tree identity, so this is a scope diagnostic for the existing mixed models rather than evidence from a dedicated 2/3-only fit.
