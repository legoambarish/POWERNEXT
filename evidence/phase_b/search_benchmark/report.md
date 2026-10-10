# Four-policy search benchmark

These are measured runs over identical declared catalogs for each fixed request. Final test requests use a separate input seed from model selection. The known rare-LI regression is labeled separately.

The complete reference reuses linear waveform scaling. Adaptive policies have the recorded candidate-pool and Physics budgets; they do not establish a global optimum. All reported passing candidates were verified by the detailed simulator.

Timing protocol: Sequential policies in declared order after explicit shared catalog/feature/model warm-up; loaded-model search latency; first-route/reused-route loading separately labeled; not cold application startup; no concurrent benchmark workers. This run was collected under shared machine load; see `../search_benchmark_environment.json`. Its wall times and ratios are run observations, not controlled speedup measurements or isolated throughput results.

Memory protocol: Cumulative OS process peak working set including native arrays; not per-policy incremental allocation.

| Request | Policy | First pass, s | Four passes, s | Total, s | Physics calls | ML predictions | Passes found/reference | Best J | Regret |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| FROZEN_test_cpri_0p5uf_LI_GSHUNT_v0_0 | complete_physics | 3.89 | 4.523 | 108 | 6912 | 0 | 22/22 | 0.0234 | 0 |
| FROZEN_test_cpri_0p5uf_LI_GSHUNT_v0_0 | analytical | 0.2169 | 0.3004 | 3.939 | 256 | 0 | 22/22 | 0.0234 | 0 |
| FROZEN_test_cpri_0p5uf_LI_GSHUNT_v0_0 | ml | 0.4776 | 0.5241 | 4.604 | 256 | 6912 | 22/22 | 0.0234 | 0 |
| FROZEN_test_cpri_0p5uf_LI_GSHUNT_v0_0 | combined | 0.6221 | 0.682 | 2.681 | 256 | 6912 | 22/22 | 0.0234 | 0 |
| FROZEN_test_cpri_0p5uf_LI_GSHUNT_v0_1 | complete_physics | 1.092 | 1.115 | 97.1 | 6912 | 0 | 33/33 | 0.0007547 | 0 |
| FROZEN_test_cpri_0p5uf_LI_GSHUNT_v0_1 | analytical | 0.04675 | 0.07231 | 1.943 | 256 | 0 | 33/33 | 0.0007547 | 0 |
| FROZEN_test_cpri_0p5uf_LI_GSHUNT_v0_1 | ml | 0.2791 | 0.3054 | 2.227 | 256 | 6912 | 33/33 | 0.0007547 | 0 |
| FROZEN_test_cpri_0p5uf_LI_GSHUNT_v0_1 | combined | 0.2732 | 0.2997 | 2.166 | 256 | 6912 | 33/33 | 0.0007547 | 0 |
| FROZEN_test_cpri_0p5uf_LI_OSHUNT_v0_0 | complete_physics | 41.18 | 41.53 | 62.58 | 6912 | 0 | 20/20 | 0.1632 | 0 |
| FROZEN_test_cpri_0p5uf_LI_OSHUNT_v0_0 | analytical | 0.04529 | 0.06984 | 3.246 | 256 | 0 | 20/20 | 0.1632 | 0 |
| FROZEN_test_cpri_0p5uf_LI_OSHUNT_v0_0 | ml | 0.4587 | 0.5034 | 3.981 | 256 | 6912 | 20/20 | 0.1632 | 0 |
| FROZEN_test_cpri_0p5uf_LI_OSHUNT_v0_0 | combined | 0.4738 | 0.5153 | 4.061 | 256 | 6912 | 20/20 | 0.1632 | 0 |
| FROZEN_test_cpri_0p5uf_LI_OSHUNT_v0_1 | complete_physics | 2.668 | 3.856 | 93.42 | 6912 | 0 | 66/66 | 0.09299 | 0 |
| FROZEN_test_cpri_0p5uf_LI_OSHUNT_v0_1 | analytical | 0.1044 | 0.1671 | 4.869 | 256 | 0 | 66/66 | 0.09299 | 0 |
| FROZEN_test_cpri_0p5uf_LI_OSHUNT_v0_1 | ml | 0.6906 | 0.7558 | 4.434 | 256 | 6912 | 66/66 | 0.09299 | 0 |
| FROZEN_test_cpri_0p5uf_LI_OSHUNT_v0_1 | combined | 0.5453 | 0.6127 | 4.929 | 256 | 6912 | 66/66 | 0.09299 | 0 |
| FROZEN_test_cpri_0p5uf_SI_GSHUNT_v0_0 | complete_physics | 59.57 | 60.28 | 107.6 | 6912 | 0 | 130/130 | 0.0736 | 0 |
| FROZEN_test_cpri_0p5uf_SI_GSHUNT_v0_0 | analytical | 0.08612 | 0.1278 | 4.477 | 256 | 0 | 130/130 | 0.0736 | 0 |
| FROZEN_test_cpri_0p5uf_SI_GSHUNT_v0_0 | ml | 1.074 | 1.145 | 5.904 | 256 | 6912 | 130/130 | 0.0736 | 0 |
| FROZEN_test_cpri_0p5uf_SI_GSHUNT_v0_0 | combined | 1.139 | 1.2 | 5.758 | 256 | 6912 | 130/130 | 0.0736 | 0 |
| FROZEN_test_cpri_0p5uf_SI_GSHUNT_v0_1 | complete_physics | 59.14 | 59.93 | 115.7 | 6912 | 0 | 129/129 | 0.0906 | 0 |
| FROZEN_test_cpri_0p5uf_SI_GSHUNT_v0_1 | analytical | 0.1523 | 0.2231 | 5.745 | 256 | 0 | 129/129 | 0.0906 | 0 |
| FROZEN_test_cpri_0p5uf_SI_GSHUNT_v0_1 | ml | 1.159 | 1.226 | 6.156 | 256 | 6912 | 129/129 | 0.0906 | 0 |
| FROZEN_test_cpri_0p5uf_SI_GSHUNT_v0_1 | combined | 1.206 | 1.27 | 6.703 | 256 | 6912 | 129/129 | 0.0906 | 0 |
| FROZEN_test_cpri_0p5uf_SI_OSHUNT_v0_0 | complete_physics | 75.67 | 76.59 | 130.4 | 6912 | 0 | 146/146 | 0.09608 | 0 |
| FROZEN_test_cpri_0p5uf_SI_OSHUNT_v0_0 | analytical | 0.08146 | 0.1453 | 2.909 | 256 | 0 | 146/146 | 0.09608 | 0 |
| FROZEN_test_cpri_0p5uf_SI_OSHUNT_v0_0 | ml | 0.4889 | 0.5113 | 2.379 | 256 | 6912 | 146/146 | 0.09608 | 0 |
| FROZEN_test_cpri_0p5uf_SI_OSHUNT_v0_0 | combined | 0.489 | 0.511 | 2.457 | 256 | 6912 | 146/146 | 0.09608 | 0 |
| FROZEN_test_cpri_0p5uf_SI_OSHUNT_v0_1 | complete_physics | 42.06 | 42.12 | 97.53 | 6912 | 0 | 140/140 | 0.1566 | 0 |
| FROZEN_test_cpri_0p5uf_SI_OSHUNT_v0_1 | analytical | 0.1364 | 0.2026 | 5.068 | 256 | 0 | 140/140 | 0.1566 | 0 |
| FROZEN_test_cpri_0p5uf_SI_OSHUNT_v0_1 | ml | 1.19 | 1.25 | 6.149 | 256 | 6912 | 140/140 | 0.1566 | 0 |
| FROZEN_test_cpri_0p5uf_SI_OSHUNT_v0_1 | combined | 1.086 | 1.155 | 5.893 | 256 | 6912 | 140/140 | 0.1566 | 0 |
| FROZEN_test_research_3uf_LI_GSHUNT_v0_0 | complete_physics | 2.577 | 4.217 | 71.02 | 6912 | 0 | 44/44 | 0.03412 | 0 |
| FROZEN_test_research_3uf_LI_GSHUNT_v0_0 | analytical | 0.2967 | 0.3219 | 2.003 | 256 | 0 | 44/44 | 0.03412 | 0 |
| FROZEN_test_research_3uf_LI_GSHUNT_v0_0 | ml | 0.2724 | 0.2958 | 2.034 | 256 | 6912 | 44/44 | 0.03412 | 0 |
| FROZEN_test_research_3uf_LI_GSHUNT_v0_0 | combined | 0.2829 | 0.3119 | 1.857 | 256 | 6912 | 44/44 | 0.03412 | 0 |
| FROZEN_test_research_3uf_LI_GSHUNT_v0_1 | complete_physics | 16.59 | 16.91 | 63.03 | 6912 | 0 | 35/35 | 0.02552 | 0 |
| FROZEN_test_research_3uf_LI_GSHUNT_v0_1 | analytical | 0.09132 | 0.1494 | 5.088 | 256 | 0 | 35/35 | 0.02552 | 0 |
| FROZEN_test_research_3uf_LI_GSHUNT_v0_1 | ml | 0.2718 | 0.3099 | 4.522 | 256 | 6912 | 35/35 | 0.02552 | 0 |
| FROZEN_test_research_3uf_LI_GSHUNT_v0_1 | combined | 0.6279 | 0.692 | 4.416 | 256 | 6912 | 35/35 | 0.02552 | 0 |
| FROZEN_test_research_3uf_LI_OSHUNT_v0_0 | complete_physics | unavailable | unavailable | 63.15 | 6912 | 0 | 0/0 | unavailable | unavailable |
| FROZEN_test_research_3uf_LI_OSHUNT_v0_0 | analytical | unavailable | unavailable | 1.854 | 256 | 0 | 0/0 | unavailable | unavailable |
| FROZEN_test_research_3uf_LI_OSHUNT_v0_0 | ml | unavailable | unavailable | 2.103 | 256 | 6912 | 0/0 | unavailable | unavailable |
| FROZEN_test_research_3uf_LI_OSHUNT_v0_0 | combined | unavailable | unavailable | 1.87 | 256 | 6912 | 0/0 | unavailable | unavailable |
| FROZEN_test_research_3uf_LI_OSHUNT_v0_1 | complete_physics | unavailable | unavailable | 39.21 | 6912 | 0 | 0/0 | unavailable | unavailable |
| FROZEN_test_research_3uf_LI_OSHUNT_v0_1 | analytical | unavailable | unavailable | 1.961 | 256 | 0 | 0/0 | unavailable | unavailable |
| FROZEN_test_research_3uf_LI_OSHUNT_v0_1 | ml | unavailable | unavailable | 2.157 | 256 | 6912 | 0/0 | unavailable | unavailable |
| FROZEN_test_research_3uf_LI_OSHUNT_v0_1 | combined | unavailable | unavailable | 1.927 | 256 | 6912 | 0/0 | unavailable | unavailable |
| FROZEN_test_research_3uf_SI_GSHUNT_v0_0 | complete_physics | 12.7 | 13.67 | 48.85 | 6912 | 0 | 146/146 | 0.02092 | 0 |
| FROZEN_test_research_3uf_SI_GSHUNT_v0_0 | analytical | 0.04859 | 0.07152 | 2.005 | 256 | 0 | 146/146 | 0.02092 | 0 |
| FROZEN_test_research_3uf_SI_GSHUNT_v0_0 | ml | 0.2856 | 0.312 | 2.316 | 256 | 6912 | 146/146 | 0.02092 | 0 |
| FROZEN_test_research_3uf_SI_GSHUNT_v0_0 | combined | 0.2793 | 0.3021 | 2.03 | 256 | 6912 | 141/146 | 0.02092 | 0 |
| FROZEN_test_research_3uf_SI_GSHUNT_v0_1 | complete_physics | 27.25 | 27.7 | 47.76 | 6912 | 0 | 108/108 | 0.001006 | 0 |
| FROZEN_test_research_3uf_SI_GSHUNT_v0_1 | analytical | 0.04697 | 0.07033 | 1.991 | 256 | 0 | 108/108 | 0.001006 | 0 |
| FROZEN_test_research_3uf_SI_GSHUNT_v0_1 | ml | 0.2858 | 0.3118 | 2.229 | 256 | 6912 | 108/108 | 0.001006 | 0 |
| FROZEN_test_research_3uf_SI_GSHUNT_v0_1 | combined | 0.2743 | 0.2972 | 2.055 | 256 | 6912 | 108/108 | 0.001006 | 0 |
| FROZEN_test_research_3uf_SI_OSHUNT_v0_0 | complete_physics | unavailable | unavailable | 39.24 | 6912 | 0 | 0/0 | unavailable | unavailable |
| FROZEN_test_research_3uf_SI_OSHUNT_v0_0 | analytical | unavailable | unavailable | 1.977 | 256 | 0 | 0/0 | unavailable | unavailable |
| FROZEN_test_research_3uf_SI_OSHUNT_v0_0 | ml | unavailable | unavailable | 2.382 | 256 | 6912 | 0/0 | unavailable | unavailable |
| FROZEN_test_research_3uf_SI_OSHUNT_v0_0 | combined | unavailable | unavailable | 2.137 | 256 | 6912 | 0/0 | unavailable | unavailable |
| FROZEN_test_research_3uf_SI_OSHUNT_v0_1 | complete_physics | unavailable | unavailable | 39.63 | 6912 | 0 | 0/0 | unavailable | unavailable |
| FROZEN_test_research_3uf_SI_OSHUNT_v0_1 | analytical | unavailable | unavailable | 2.165 | 256 | 0 | 0/0 | unavailable | unavailable |
| FROZEN_test_research_3uf_SI_OSHUNT_v0_1 | ml | unavailable | unavailable | 2.314 | 256 | 6912 | 0/0 | unavailable | unavailable |
| FROZEN_test_research_3uf_SI_OSHUNT_v0_1 | combined | unavailable | unavailable | 2.084 | 256 | 6912 | 0/0 | unavailable | unavailable |
| KNOWN_RARE_LI_REGRESSION | complete_physics | 1.166 | unavailable | 3.45 | 504 | 0 | 1/1 | 0.7832 | 0 |
| KNOWN_RARE_LI_REGRESSION | analytical | 0.01832 | unavailable | 3.549 | 504 | 0 | 1/1 | 0.7832 | 0 |
| KNOWN_RARE_LI_REGRESSION | ml | 0.04663 | unavailable | 3.738 | 504 | 504 | 1/1 | 0.7832 | 0 |
| KNOWN_RARE_LI_REGRESSION | combined | 0.04737 | unavailable | 5.258 | 504 | 504 | 1/1 | 0.7832 | 0 |

## Paired discovery outcomes

A missing pass time is not zero. Ratios below use only cases where both policies found a pass; missed feasible requests are listed separately to avoid hiding failures. A ratio above one means the adaptive policy reached its first pass sooner.

| Policy | Feasible test requests | Missed feasible requests | Paired first-pass timings | Median complete/adaptive time ratio |
|---|---:|---:|---:|---:|
| analytical | 12 | 0 | 12 | 284.9 |
| ml | 12 | 0 | 12 | 47.74 |
| combined | 12 | 0 | 12 | 42.09 |

Per-case JSON includes OOD and unsupported counts, complete/partial coverage, model-loading time, scoring throughput and process peak memory. These results describe this runtime, input set and declared catalog; they establish no general speedup over every electrical setup or four-module search. No real-hardware validation is claimed.

The `ml` and `combined` rows exercised the loaded ML path and predicted the
declared candidate pool before detailed Physics verification. That operational
use does not demonstrate an incremental retention or regret benefit over the
analytical policy in this sample: analytical matched the complete reference on
all feasible frozen requests, while combined missed five passing alternatives
in one request (with zero best-objective regret).
