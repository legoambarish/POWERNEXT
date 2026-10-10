# Phase B v3 ML layer

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
P95, maximum error, tolerance-normalized errors, timing and crest boundary
errors, staged 25/50/100% learning curves, fit/predict throughput, and artifact
size.  The built-in request proxy evaluates one deterministic 1 MV target per
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

Once the generated v3 dataset is complete and its manifest hash is recorded,
run the versioned command:

```powershell
$python = ".\runtime\python.exe"
& $python -B -m powernext_v3.training train `
  --data-dir .\path\to\generated_v3_dataset `
  --output-dir .\powernext\ml\results\networks_v3_YYYYMMDDTHHMMSSZ `
  --registry-dir .\powernext\ml\registry\networks_v3 `
  --optimization-oracles .\powernext\ml\data\networks_v3_validation_oracles
```

`--optimization-oracles` is optional until the independent complete-catalog
validation oracle is ready.  When supplied, the trainer constructs the
`OracleValidation` hook and gives each fitted candidate its route-matched
oracle requests; the oracle is validation-only and is never read for the
held-out test report.

The command has intentionally not been launched by the Phase B ML worker;
dataset generation and readiness are coordinated separately.  Registry cards
bind the route, feature order, model hash, data hash, v3 source/physics
fingerprints, and runtime versions.  Model loading verifies those hashes and
rejects modified artifacts or incompatible runtime/provenance information.

`selected_models.json` is the serving handoff: each key is
`domain_id:mode:topology` and each value is the selected immutable model
folder name.  The per-route `results.json` entry also retains
`candidate_models` for all four train-only artifacts and their validation and
held-out comparison metrics.

The tests in `tests/test_v3_ml.py` use a tiny explicit fixture to verify the
API, scalar L0 agreement, candidate restrictions, OOD interpolation,
artifact-integrity checks, and validation/test ordering.  They are contract
tests only and make no training acceptance claim.
