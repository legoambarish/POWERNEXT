# PowerNext Phase B v3 implementation handoff

> Historical Phase B v3 evidence (one through four modules). This report is preserved for provenance and is not the final exact-two training or release acceptance. The current scope is exactly two resistors in each front and tail branch; see [final scope](FINAL_RESISTOR_SCOPE_DECISION.md), [exact-two model report](EXACT2_MODEL_REPORT.md), and [acceptance ledger](PHASE_B_ACCEPTANCE.md).

This document describes the current Phase B implementation, the evidence that
can be relied on, the boundaries of each result, and the commands needed to
continue the work. It is written for the next engineer or reviewer working
from the current checkout.

The v3 network stack is an independent offline extension under `powernext_v3`.
The legacy physics engine, legacy application routes, accepted release and
historical artifacts remain separate. The v3 code reuses the legacy graph and
evaluator through a versioned adapter; it does not rewrite the legacy
scientific source or relabel its artifacts.

## Current state

The current source regression is green: the integrated runner completed **506
checks** across Physics, legacy ML, optimizer, application, v3, frontend,
red-team, UI-race, integration and final-release suites. The machine-readable
receipt is
[`evidence/phase_b/integrated_regression_summary.json`](../evidence/phase_b/integrated_regression_summary.json).

The corrected R2 production dataset is complete and passed the actual-loader
preflight. It contains 122,000 attempts, 99,852 eligible rows and 92,662
canonical eligible response shapes. Each of the eight routes has 10,563–14,761
eligible shapes, nonempty grouped train/validation/test partitions, all fourteen
stage counts and all sixteen front/tail module-count pairs. The primary evidence is
[`evidence/phase_b/lead_training_preflight.json`](../evidence/phase_b/lead_training_preflight.json)
and
[`evidence/phase_b/production_dataset_audit.json`](../evidence/phase_b/production_dataset_audit.json).

There are four candidate artifacts per route and eight selected route models,
so the frozen serving set is 8 of 32 candidates. Selection is recorded in
`powernext/ml/results/networks_exact2_v5/selected_models.json` and the decision is
documented by
[`evidence/phase_b/lead_validation_decision.json`](../evidence/phase_b/lead_validation_decision.json).
The decision uses the validation partition and independent request-oracle
evidence; final-test metrics were not inspected for model selection.

The selected-model application audit passed. It exercised all eight route
predictions, checked model/card identity and hashes, checked separate ML and
Physics output, attached a later scalar reference without changing the frozen
prediction, rendered the selected-model UI, and, before the active-scope change,
completed a historical four-module async search with eight ML predictions and
one bounded Physics evaluation. The
machine-readable receipt is
[`evidence/phase_b/production_application_audit.json`](../evidence/phase_b/production_application_audit.json).

The fresh oracle replay is scientifically equal: 16 requests, zero candidate
configuration mismatches, zero scientific-field mismatches and zero numeric
differences outside the stated tolerance. Equality is keyed by `catalog_index`
and covers configuration, compliance, score, verification status, gain, the
scientific front/tail timing fields and reason codes. Process scheduling and
instrumentation timing are intentionally outside this equality check. The receipt is
[`evidence/phase_b/oracle_scientific_comparison.json`](../evidence/phase_b/oracle_scientific_comparison.json).

The 17-case four-policy search benchmark is complete and documented in
[`docs/PHASE_B_SEARCH_BENCHMARK.md`](PHASE_B_SEARCH_BENCHMARK.md). It records
retention, regret, partial-coverage and no-solution bounds. ML was operationally
used, but the benchmark does not demonstrate incremental benefit over the
analytical policy; its five combined-policy alternative misses are documented.
The run used shared machine load, so its timing ratios are observations rather
than controlled speedup claims. Extracted-package acceptance remains pending;
do not use the current checkout as evidence of package-manifest or moved-folder
acceptance until the lead records those results. No claim here is a global
optimizer proof, hardware approval, laboratory calibration or IEC
measurement-software qualification.

## Current active application scope

The live application, CLI and Network optimizer UI now require exactly 2
resistor modules in both the front and tail branches. The UI has no
module-bound selector. Explicit 1-, 3-, or 4-module search requests and fixed
trees are rejected at the public boundary with `UNSUPPORTED_CURRENT_SCOPE`
before a job or prediction artifact is created. The low-level enumerator,
Physics adapter, training artifacts and historical 1-, 3-, and 4-module
evidence remain unchanged and available for archival or controlled replay;
they are outside the current live workflow.

## Architecture and ownership

| Area | Current implementation | Responsibility |
|---|---|---|
| Canonical networks | `powernext_v3/networks.py` | Validate JSON trees, canonicalize associative/commutative series and parallel nodes, calculate exact `Fraction` equivalents, retain physical recipes, stress division and BOMs. |
| Profiles | `powernext_v3/profiles.py` | Keep the CPRI 0.5 uF domain and hypothetical research 3 uF domain separate. |
| Catalog | `powernext_v3/catalog.py` | Index front/tail equivalent groups over declared uniform stages without materializing the full Cartesian product. |
| Physics adapter | `powernext_v3/physics.py` | Resolve trees to equivalent resistance, apply profile charge/energy limits, call the legacy graph/evaluator, preserve waveforms and source fingerprints. |
| Features and baseline | `powernext_v3/features.py` | Build route-specific feature matrices and the exact two-capacitor L0 baseline; expose continuous-support OOD checks through the model layer. |
| Models | `powernext_v3/models.py` | Define the four approved route candidates: `physics_guided`/`residual` × `extra_trees`/`hist_gradient_boosting`. |
| Training and selection | `powernext_v3/training.py` | Load frozen grouped data, train candidates, validate on the validation partition and write cards/selection metadata. The selected mapping is frozen separately from final-test inspection. |
| Registry | `powernext_v3/registry.py` | Strictly load trusted artifacts after card, model hash, runtime, source fingerprint and route checks. |
| Optimizer | `powernext_v3/optimizer.py` | Normalize requests, load the route model, rank a bounded candidate pool, run independent Physics verification, preserve failed alternatives and save complete results/waveforms. |
| v3 application | `powernext_v3/application.py` | Persist jobs and predictions, enforce one active search, expose fixed prediction/reference APIs, and publish an artifact only after the subprocess completes. |
| HTTP integration | `powernext_app/server.py` | Mount `/api/v3/*` lazily beside the unchanged legacy routes and enforce local-origin/security headers. |
| UI | `ui/networks.html`, `ui/networks.js`, existing `ui/app.css` | Expose domain, mode, topology, polarity, stages, the fixed two-module scope, search policy, fixed prediction and later-reference controls. |
| Acceptance harness | `tests/verify_networks_release.py` | Run isolated bundled-runtime checks against an extracted release. Pending model/manifest checks are reported as blocked, never silently downgraded to ML acceptance. |

The v3 subprocess entry point is `powernext_v3/__main__.py`. It accepts a
request JSON, a new output directory, a registry and a selection mapping. The
application uses this entry point through the existing process watchdog so a
crash or timeout cannot publish a partial recommendation.

## Network contract

The only physical resistor leaves are 30, 46, 180, 520, 3700 and 5000 ohms.
Each front or tail branch contains one through four leaves. A tree is JSON
friendly:

```json
{"op":"R","ohm":180}
```

or:

```json
{"op":"P","children":[{"op":"R","ohm":30},{"op":"R","ohm":46}]}
```

`S` and `P` nodes require at least two children. Nested nodes with the same
operation are flattened and children are sorted deterministically. Unknown
components, booleans, non-finite values, cycles, arbitrary parts and more than
four leaves are rejected. `canonicalize(tree)` returns a fresh ordinary JSON
tree. `equivalent_resistance(tree)` returns an exact `fractions.Fraction`.

The public network helpers are:

```python
from powernext_v3.networks import (
    canonicalize, equivalent_resistance, enumerate_networks,
    electrical_groups, combined_bom, stress_division,
)
```

The physical catalogue keeps every distinct tree even when two trees have the
same exact electrical equivalent. The current counts are:

| Maximum leaves | Physical recipes | Exact resistance groups |
|---:|---:|---:|
| 1 | 6 | 6 |
| 2 | 48 | 48 |
| 3 | 412 | 407 |
| 4 | 4,192 | 4,080 |

`electrical_groups()` is a grouping view, not a replacement catalogue. Each
group retains all physical alternatives and their component counts. For one
stage, the full four-module space contains 16,646,400 distinct
equivalent-response candidates and 17,572,864 physical-tree configurations.
Across all fourteen stage counts that is 233,049,600 response candidates and
246,020,096 physical-tree configurations. The catalog streams integer indices
instead of materializing the full product.

`combined_bom(front, tail, stages, inventory=None)` multiplies each physical
component count by the uniform stage count. With no inventory, availability is
`UNKNOWN` and no stock is assumed. With an explicit mapping, omitted confirmed
components are zero, a listed `None` remains unknown, and shortfalls are
reported as `INSUFFICIENT`. A BOM result does not prove pulse ratings, sockets,
thermal duty, mounting or firing legality. `stress_division()` reports the
electrical voltage/current/power at each physical resistor leaf; it is a
calculation aid, not a pulse qualification.

## Profiles, topologies and physical limits

Every request chooses one domain, one impulse mode and one declared topology.
The two topology identifiers are `GSHUNT_v0` (generator-side shunt) and
`OSHUNT_v0` (output-side shunt). They are reduced-circuit hypotheses, not
confirmed generator wiring.

| Domain | Stage capacitance | Per-stage charge limit | Per-stage energy limit | Total energy limit | Meaning |
|---|---:|---:|---:|---:|---|
| `cpri_0p5uf` | 0.5 uF | 200 kV | 10 kJ | 150 kJ | Supplied CPRI parameter profile; topology and hardware remain provisional. |
| `research_3uf` | 3 uF | 200 kV | 60 kJ | 900 kJ | Hypothetical comparison domain; not CPRI equipment. |

Both profiles use the declared 3 MV summed-charge ceiling and an explicit
480 pF basic-load coverage choice (`ADDITIONAL_DISJOINT` or
`INCLUDED_IN_OTHER_COMPONENTS`). Stage counts are 2 through 15. The Physics
adapter enforces charge, energy, positive capacitance, polarity, topology,
auxiliary-assumption and 200 ms evaluator-scope checks.

The six component values, profile limits, topology assumptions, actual pulse
ratings, available quantities, mounting positions, switching state, minimum
firing charge, thermal duty and calibrated measurement chain are separate
questions. The current source does not infer missing hardware facts. A
`PHYSICS_VERIFIED` result means that the declared synthetic waveform passed the
numeric and clean-full-impulse evaluator gates; it does not mean hardware is
eligible. Every Physics record retains explicit hardware reason codes.

The research profile is especially limited: it exists to replay or compare a
3 uF scenario and its limits are energy-derived assumptions. It must not be
described as a CPRI rating.

## Search and result semantics

The low-level `normalize_request()` accepts `adaptive` and `complete` search
modes and the `combined`, `ml`, `analytical` and `complete_physics` policies.
Its historical catalogue still supports one-through-four modules per branch.
The live application and CLI require `min_modules=2` and `max_modules=2` before
calling this low-level contract. Requests are bounded by stages 2–15, the declared six components,
finite values and explicit setup fields. `recommend()` first forms an
analytical/L0 or loaded-model candidate pool, then independently evaluates the
ordered candidates with detailed Physics.

The following counters must be read together:

- `theoretical_recipe_configurations`: physical front/tail recipes across the
  requested stages;
- `distinct_response_candidates`: exact equivalent front/tail responses;
- `considered_count`: candidates actually admitted to the bounded pool or
  evaluated directly;
- `ml_predicted_count`: candidates that received an ML prediction;
- `physics_evaluated_count`: candidates sent to detailed Physics;
- `catalog_complete`: whether all declared response candidates were covered;
- `unsupported_count`: candidates whose declared waveform could not be
  evaluated as a clean supported impulse;
- `termination_reason`: budget, candidate exhaustion, or declared completion.

ML output only orders candidates. It never permanently excludes a candidate,
declares compliance, or replaces detailed Physics. A candidate is a
recommendation only when the Physics evaluator marks it compliant. Failed rows
remain in `failed_alternatives` and are labelled **NOT RECOMMENDED**.

`VERIFIED_COMPLIANT` means a passing candidate exists. A bounded search with no
pass may return `NO_COMPLIANT_CONFIGURATION_YET`; this is a valid partial
result and not a proof of infeasibility. Only a complete declared catalog with
no pass may return `NO_COMPLIANT_CONFIGURATION_IN_DECLARED_CATALOG`. A process
crash or timeout records `FAILED` and never promotes an incomplete artifact.
The best verified candidate in a partial catalog is not a global optimum.

The four-module production audit intentionally used a bounded request with
eight ML candidates and one Physics evaluation. It completed with
`catalog_complete=false`, `ml_predicted_count=8`, `physics_evaluated_count=1`
and `NO_COMPLIANT_CONFIGURATION_YET`; that result demonstrates the partial
semantics and is not a benchmark or a global no-solution claim.

## Fixed prediction and later reference workflow

`POST /api/v3/predict` accepts `{ "request": ..., "configuration": ... }`.
The route fields explicitly supplied in the fixed configuration must agree with
the request. A mismatch in domain, mode, topology or polarity is rejected
before a prediction artifact is created.

When a selected route artifact loads, the record contains:

- the immutable normalized request and configuration;
- the model ID, route, card hash and `ML_PREDICTION` output;
- ML gain, front/tail timing and `ml_ood` support status;
- detailed Physics metrics and a saved Physics waveform;
- input, source and waveform hashes;
- hardware/provisional reason codes.

`PHYSICS_VERIFIED` is used only when numeric status is `VALID` and waveform
status is `VALID_CLEAN_FULL_IMPULSE`. Computed arrays and metrics are retained
when the waveform is unsupported, but the result is labelled
`PHYSICS_UNSUPPORTED`. If the optional leakage field
`load_resistance_ohm` is supplied, the trained L0 feature contract refuses it;
the application records an explicit `PHYSICS_FALLBACK` with source
`DETAILED_PHYSICS` and does not make an ML claim.

Reference values are attached after the prediction. Scalar values are stored
as `NUMERICAL_SCALAR_REFERENCE_ONLY`; they do not invent a waveform. Raw CSV
imports retain the original bytes, metadata and hashes, and use the existing
qualified-evaluator limitations. Neither path retrains a model or mutates the
prediction. The prediction sidecar hash is checked before comparison and the
reference is stored as a separate immutable comparison record. Measured or
reference traces do not automatically become training data or hardware
qualification.

## HTTP and command interfaces

The legacy server keeps its existing routes. The v3 surface is:

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/v3/meta` | Profiles, six components, limits, route availability and schema. |
| POST | `/api/v3/validate` | Normalize and validate a request without running a search. |
| POST | `/api/v3/runs` | Queue one bounded search; only one v3 job may be active. |
| GET | `/api/v3/runs` | List persisted job states. |
| GET | `/api/v3/runs/{id}` | Read progress, final counts, result status and artifact hash. |
| GET | `/api/v3/runs/{id}/waveform?candidate={id}` | Read a saved candidate waveform after completion. |
| POST | `/api/v3/predict` | Save one fixed configuration and forward prediction. |
| GET | `/api/v3/predictions/{id}` | Read and integrity-check the frozen prediction. |
| GET | `/api/v3/predictions/{id}/waveform` | Read the saved fixed Physics waveform. |
| POST | `/api/v3/predictions/{id}/reference-metrics` | Attach scalar reference metrics. |
| POST | `/api/v3/predictions/{id}/reference` | Attach CSV text/base64 and metadata. |

Launch the local application from the checkout with the bundled runtime:

```powershell
New-Item -ItemType Directory -Force "$env:TEMP\PowerNext-v3-demo" | Out-Null
.\runtime\python.exe -B -m powernext_app `
  --port 18767 `
  --data-dir "$env:TEMP\PowerNext-v3-demo" `
  --no-browser
```

Open `http://127.0.0.1:18767/`, select **Network optimizer**, and keep the
selected domain, impulse mode, topology, polarity and stage range visible in
the request. The current selected-model browser audit used an exact-two fixed
smoke configuration (front `S(180,30)`, tail `P(180,30)`), two active stages
and 50,000 V per stage. That setting demonstrates the route and evidence flow;
it is not a hardware recommendation.

For a direct offline optimizer subprocess, the output directory must be new:

```powershell
.\runtime\python.exe -B -m powernext_v3 optimize `
  --request .\request.json `
  --output "$env:TEMP\PowerNext-v3-result-unique" `
  --registry .\powernext\ml\registry\networks_exact2_v5 `
  --selection .\powernext\ml\results\networks_exact2_v5\selected_models.json
```

For an extracted package, run the acceptance harness from the extracted root
after the lead has finalized the package:

```powershell
runtime\python.exe -B tests\verify_networks_release.py
```

`--allow-pending` is useful for a checkout or package that intentionally lacks
the final model/manifest gate, but a blocked report is not an ML acceptance.
The harness must use the bundled runtime and must write any report outside the
immutable release root.

## Evidence map and caveats

- `evidence/phase_b/integrated_regression_summary.json` — integrated receipt: 506 checks across ten suites and commands.
- `evidence/phase_b/lead_training_preflight.json` — actual-loader R2 hash,
  split and 92,662 canonical-shape gate.
- `evidence/phase_b/production_dataset_audit.json` — per-route coverage and
  staged dataset audit.
- `evidence/phase_b/oracle_scientific_comparison.json` — fresh 16-request
  scientific equality.
- `evidence/phase_b/oracle_catalog_reconciliation.json` — catalog/index/hash
  reconciliation. Its scientific checks pass, but
  `all_checks_passed_including_git_history` is false because the historical
  oracle manifest did not record every current execution-contract hash and
  lacks a generation timestamp. Do not turn this into a claim of historical
  source-snapshot identity.
- `evidence/phase_b/lead_validation_decision.json` — validation-only frozen
  model decision for all eight routes.
- [`docs/PHASE_B_MODEL_REPORT.md`](PHASE_B_MODEL_REPORT.md) and
  [`evidence/phase_b/final_model_evaluation.json`](../evidence/phase_b/final_model_evaluation.json) —
  supplemental post-freeze final-model evaluation; it rechecked all 32
  candidate-route artifacts against the strict v2 oracle without retraining
  and reports authorized held-out metrics separately.
- [`evidence/revalidation_scripts/phase_b_final_ml_evaluation.py`](../evidence/revalidation_scripts/phase_b_final_ml_evaluation.py) —
  evaluator used to produce the supplemental receipt.
- [`powernext/ml/data/networks_v3_validation_oracles_v2/manifest.json`](../powernext/ml/data/networks_v3_validation_oracles_v2/manifest.json)
  and [`requests.json`](../powernext/ml/data/networks_v3_validation_oracles_v2/requests.json) —
  frozen strict v2 oracle archive and request list.
- `evidence/phase_b/production_application_audit.json` — fresh selected-model
  API and browser evidence, fixed-reference immutability and bounded async
  search.
- [`docs/PHASE_B_SEARCH_BENCHMARK.md`](PHASE_B_SEARCH_BENCHMARK.md) and
  [`evidence/phase_b/search_benchmark/manifest.json`](../evidence/phase_b/search_benchmark/manifest.json)
  — complete 17-case four-policy retention/regret review; the per-case report
  and [shared-load environment note](../evidence/phase_b/search_benchmark_environment.json)
  bound timing interpretation and no-solution claims.
- `training-data/PowerNext_Networks_v3_Data_Stage1_20261010.zip` and its
  adjacent manifest — preserved data-stage archive and recovery hashes.

The `boundary_errors` fields emitted by the training report have a narrow
meaning: they describe predicted distance outside a conformity band. They are
not the absolute prediction error for rows whose true value is near a boundary.
The learning-curve decision therefore uses a separate actual
prediction-minus-truth near-boundary metric and explicitly excludes the older
`boundary_errors` fields. This correction changes no fitted model or primary
selection metric.

The exact oracle comparison also has a deliberate evidence boundary: it proves
current replay equality for the compared scientific fields under the stated
numeric tolerance, not equality of process timing or an independently archived
historical working-tree snapshot. Hardware, mounting, pulse ratings, firing
limits, calibrated acquisition and licensed IEC reference-software claims
remain outside the current evidence.

## Continuation checklist

1. Keep the selected mapping, model cards, registry artifacts, R2 data and
   validation/oracle directories immutable while reviewing the pending gates.
2. Preserve and review the complete four-policy benchmark receipt and its
   shared-load limitation; do not convert its timing ratios into speedup
   claims. Continue with the lead-owned extracted-package acceptance and
   moved-folder manifest checks.
3. Build the extracted release with the lead-owned builder, verify the manifest
   and run `tests/verify_networks_release.py` from a moved extraction.
4. Preserve the existing accepted release and historical negative evidence;
   create a new evidence version if any source, model, data or evaluator hash
   changes.
5. Treat all hardware-facing conclusions as provisional until actual mounting,
   pulse-energy/rating, firing and calibrated waveform evidence are supplied.
