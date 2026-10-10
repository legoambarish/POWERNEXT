# Phase B four-policy search benchmark

The frozen benchmark is complete. Its [manifest](../evidence/phase_b/search_benchmark/manifest.json)
contains 17 hashed case summaries: 16 held-out frozen test requests and the
separately labelled `KNOWN_RARE_LI_REGRESSION` request. The frozen requests
use the same declared catalog and a separate input seed from model selection.
All 17 case-file hashes match the manifest. The [generated report](../evidence/phase_b/search_benchmark/report.md)
contains the per-policy timings and candidate counts; the [environment note](../evidence/phase_b/search_benchmark_environment.json)
records the shared-load limitation.

The complete Physics policy is the declared-catalog reference. Adaptive
policies have the recorded candidate-pool and detailed-Physics budgets, so
their partial results are useful for retention and regret comparisons but do
not establish a global optimum.

## Retention and regret

Across the 16 frozen requests, the complete reference found 1,019 feasible
candidate configurations across 12 feasible requests. The other four requests
had no feasible candidate in the declared catalog.

| Policy | Feasible requests retained | Passing alternatives retained | Objective regret | No-feasible status |
|---|---:|---:|---:|---|
| `complete_physics` | 12/12 | 1,019/1,019 | 0 | 4 complete declared-catalog no-solution results |
| `analytical` | 12/12 | 1,019/1,019 | 0 | 4 budget-limited `NO_COMPLIANT_CONFIGURATION_YET` results |
| `ml` | 12/12 | 1,019/1,019 | 0 | 4 budget-limited `NO_COMPLIANT_CONFIGURATION_YET` results |
| `combined` | 12/12 | 1,014/1,019 | 0 | 4 budget-limited `NO_COMPLIANT_CONFIGURATION_YET` results |

The five combined-policy misses are all in
`FROZEN_test_research_3uf_SI_GSHUNT_v0_0`: 141 of 146 passing alternatives
were retained. The request remained retained, and its best objective matched
the complete reference, so the observed loss is alternative retention rather
than best-selection regret.

The separately labelled rare-LI regression contains one feasible candidate.
All four policies retained it (`1/1`) with zero regret. It is a regression
guard and is not merged into the frozen-test totals above.

The `ml` and `combined` policies operationally used the loaded models and
predicted the candidate pool before Physics verification. This benchmark does
not demonstrate incremental benefit over the analytical policy: analytical
already matched complete Physics on every feasible frozen request and every
feasible passing alternative, while combined lost five alternatives in one
case. ML OOD status remains visible in the case summaries; the frozen adaptive
runs show per-request OOD counts from 0 to 1,251.

## No-solution and coverage bounds

The four no-feasible frozen requests are the `research_3uf` OSHUNT LI/SI
`v0_0` and `v0_1` cases. `complete_physics` traversed each 6,912-candidate
declared catalog and returned
`NO_COMPLIANT_CONFIGURATION_IN_DECLARED_CATALOG` with zero passing candidates.
That conclusion is bounded to the declared catalog and evaluator support.

Analytical, ML and combined each stopped after the 256-Physics budget on those
same requests and reported `NO_COMPLIANT_CONFIGURATION_YET` with
`catalog_complete=false`. Those partial results cannot support a global
infeasibility or unrestricted no-solution claim. All passing candidates in the
benchmark were checked by the detailed simulator; no real-hardware validation
is claimed.

## Timing interpretation

The report records first-pass and total wall times after shared catalog,
feature and model warm-up. The run was conducted while other PowerNext work
was using the same machine; the [environment record](../evidence/phase_b/search_benchmark_environment.json)
classifies these as shared-load observations. Therefore the reported ratios
are descriptive for this runtime, input set and declared catalog. They are not
controlled speedup claims, isolated throughput measurements, cold-start
measurements, or evidence about four-module search.

Package extraction, moved-folder manifest checks and final offline-package
acceptance remain pending. This benchmark does not close those release gates.
