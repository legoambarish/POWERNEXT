# Four-policy search benchmark

These are measured runs over identical declared catalogs for each fixed request. Final test requests use a separate input seed from model selection. The known rare-LI regression is labeled separately.

The complete reference reuses linear waveform scaling. Adaptive policies have the recorded candidate-pool and Physics budgets; they do not establish a global optimum. All reported passing candidates were verified by the detailed simulator.

Timing protocol: Sequential policies in declared order after explicit shared catalog/feature/model warm-up; loaded-model search latency; first-route/reused-route loading separately labeled; not cold application startup; no concurrent benchmark workers.

Memory protocol: Cumulative OS process peak working set including native arrays; not per-policy incremental allocation.

| Request | Policy | First pass, s | Four passes, s | Total, s | Physics calls | ML predictions | Passes found/reference | Best J | Regret |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| FROZEN_test_seed20261202_cpri_0p5uf_LI_GSHUNT_v0_0 | complete_physics | 33.98 | 34.64 | 94.08 | 5292 | 0 | 19/19 | 0.003685 | 0 |
| FROZEN_test_seed20261202_cpri_0p5uf_LI_GSHUNT_v0_0 | analytical | 0.06891 | 0.1219 | 3.761 | 256 | 0 | 19/19 | 0.003685 | 0 |
| FROZEN_test_seed20261202_cpri_0p5uf_LI_GSHUNT_v0_0 | ml | 0.3959 | 0.4507 | 4.563 | 256 | 5292 | 19/19 | 0.003685 | 0 |
| FROZEN_test_seed20261202_cpri_0p5uf_LI_GSHUNT_v0_0 | combined | 0.3831 | 0.4455 | 3.833 | 256 | 5292 | 19/19 | 0.003685 | 0 |
| FROZEN_test_seed20261202_cpri_0p5uf_LI_GSHUNT_v0_1 | complete_physics | 4.817 | 29.31 | 80.69 | 5292 | 0 | 14/14 | 0.01463 | 0 |
| FROZEN_test_seed20261202_cpri_0p5uf_LI_GSHUNT_v0_1 | analytical | 0.09718 | 0.1852 | 3.732 | 256 | 0 | 14/14 | 0.01463 | 0 |
| FROZEN_test_seed20261202_cpri_0p5uf_LI_GSHUNT_v0_1 | ml | 0.3673 | 0.4331 | 3.72 | 256 | 5292 | 14/14 | 0.01463 | 0 |
| FROZEN_test_seed20261202_cpri_0p5uf_LI_GSHUNT_v0_1 | combined | 0.471 | 0.5225 | 4.174 | 256 | 5292 | 14/14 | 0.01463 | 0 |
| FROZEN_test_seed20261202_cpri_0p5uf_LI_OSHUNT_v0_0 | complete_physics | 3.665 | 4.232 | 81.17 | 5292 | 0 | 50/50 | 0.0515 | 0 |
| FROZEN_test_seed20261202_cpri_0p5uf_LI_OSHUNT_v0_0 | analytical | 0.1213 | 0.1944 | 4.146 | 256 | 0 | 50/50 | 0.0515 | 0 |
| FROZEN_test_seed20261202_cpri_0p5uf_LI_OSHUNT_v0_0 | ml | 0.4695 | 0.5132 | 3.825 | 256 | 5292 | 50/50 | 0.0515 | 0 |
| FROZEN_test_seed20261202_cpri_0p5uf_LI_OSHUNT_v0_0 | combined | 0.3345 | 0.3775 | 4.242 | 256 | 5292 | 50/50 | 0.0515 | 0 |
| FROZEN_test_seed20261202_cpri_0p5uf_LI_OSHUNT_v0_1 | complete_physics | 54.52 | 55.33 | 85.84 | 5292 | 0 | 15/15 | 0.1975 | 0 |
| FROZEN_test_seed20261202_cpri_0p5uf_LI_OSHUNT_v0_1 | analytical | 0.1106 | 0.1747 | 4.902 | 256 | 0 | 15/15 | 0.1975 | 0 |
| FROZEN_test_seed20261202_cpri_0p5uf_LI_OSHUNT_v0_1 | ml | 0.3763 | 0.4209 | 3.946 | 256 | 5292 | 15/15 | 0.1975 | 0 |
| FROZEN_test_seed20261202_cpri_0p5uf_LI_OSHUNT_v0_1 | combined | 0.3529 | 0.3958 | 4.462 | 256 | 5292 | 15/15 | 0.1975 | 0 |
| FROZEN_test_seed20261202_cpri_0p5uf_SI_GSHUNT_v0_0 | complete_physics | 20.95 | 21.62 | 73.81 | 5292 | 0 | 187/187 | 0.01879 | 0 |
| FROZEN_test_seed20261202_cpri_0p5uf_SI_GSHUNT_v0_0 | analytical | 0.1192 | 0.1838 | 4.226 | 256 | 0 | 187/187 | 0.01879 | 0 |
| FROZEN_test_seed20261202_cpri_0p5uf_SI_GSHUNT_v0_0 | ml | 0.7093 | 0.7514 | 4.616 | 256 | 5292 | 187/187 | 0.01879 | 0 |
| FROZEN_test_seed20261202_cpri_0p5uf_SI_GSHUNT_v0_0 | combined | 0.6549 | 0.6969 | 4.13 | 256 | 5292 | 170/187 | 0.01879 | 0 |
| FROZEN_test_seed20261202_cpri_0p5uf_SI_GSHUNT_v0_1 | complete_physics | 40.63 | 40.69 | 78.1 | 5292 | 0 | 149/149 | 0.04753 | 0 |
| FROZEN_test_seed20261202_cpri_0p5uf_SI_GSHUNT_v0_1 | analytical | 0.06835 | 0.11 | 3.681 | 256 | 0 | 149/149 | 0.04753 | 0 |
| FROZEN_test_seed20261202_cpri_0p5uf_SI_GSHUNT_v0_1 | ml | 0.6549 | 0.6974 | 4.136 | 256 | 5292 | 149/149 | 0.04753 | 0 |
| FROZEN_test_seed20261202_cpri_0p5uf_SI_GSHUNT_v0_1 | combined | 0.6565 | 0.6984 | 4.023 | 256 | 5292 | 149/149 | 0.04753 | 0 |
| FROZEN_test_seed20261202_cpri_0p5uf_SI_OSHUNT_v0_0 | complete_physics | unavailable | unavailable | 72.19 | 5292 | 0 | 0/0 | unavailable | unavailable |
| FROZEN_test_seed20261202_cpri_0p5uf_SI_OSHUNT_v0_0 | analytical | unavailable | unavailable | 4.209 | 256 | 0 | 0/0 | unavailable | unavailable |
| FROZEN_test_seed20261202_cpri_0p5uf_SI_OSHUNT_v0_0 | ml | unavailable | unavailable | 3.975 | 256 | 5292 | 0/0 | unavailable | unavailable |
| FROZEN_test_seed20261202_cpri_0p5uf_SI_OSHUNT_v0_0 | combined | unavailable | unavailable | 3.844 | 256 | 5292 | 0/0 | unavailable | unavailable |
| FROZEN_test_seed20261202_cpri_0p5uf_SI_OSHUNT_v0_1 | complete_physics | 66.48 | 67.61 | 70.24 | 5292 | 0 | 7/7 | 1.733 | 0 |
| FROZEN_test_seed20261202_cpri_0p5uf_SI_OSHUNT_v0_1 | analytical | 0.08355 | 0.1239 | 4.189 | 256 | 0 | 7/7 | 1.733 | 0 |
| FROZEN_test_seed20261202_cpri_0p5uf_SI_OSHUNT_v0_1 | ml | 0.3923 | 0.436 | 3.928 | 256 | 5292 | 7/7 | 1.733 | 0 |
| FROZEN_test_seed20261202_cpri_0p5uf_SI_OSHUNT_v0_1 | combined | 0.3631 | 0.4049 | 3.856 | 256 | 5292 | 7/7 | 1.733 | 0 |
| FROZEN_test_seed20261202_research_3uf_LI_GSHUNT_v0_0 | complete_physics | 1.359 | 2.003 | 66.77 | 5292 | 0 | 27/27 | 0.0457 | 0 |
| FROZEN_test_seed20261202_research_3uf_LI_GSHUNT_v0_0 | analytical | 0.0723 | 0.1457 | 3.698 | 256 | 0 | 27/27 | 0.0457 | 0 |
| FROZEN_test_seed20261202_research_3uf_LI_GSHUNT_v0_0 | ml | 0.3251 | 0.3675 | 3.706 | 256 | 5292 | 27/27 | 0.0457 | 0 |
| FROZEN_test_seed20261202_research_3uf_LI_GSHUNT_v0_0 | combined | 0.3436 | 0.3882 | 3.552 | 256 | 5292 | 27/27 | 0.0457 | 0 |
| FROZEN_test_seed20261202_research_3uf_LI_GSHUNT_v0_1 | complete_physics | 2.744 | 3.33 | 66.35 | 5292 | 0 | 36/36 | 0.005555 | 0 |
| FROZEN_test_seed20261202_research_3uf_LI_GSHUNT_v0_1 | analytical | 0.07367 | 0.1664 | 3.446 | 256 | 0 | 36/36 | 0.005555 | 0 |
| FROZEN_test_seed20261202_research_3uf_LI_GSHUNT_v0_1 | ml | 0.3269 | 0.3708 | 3.401 | 256 | 5292 | 36/36 | 0.005555 | 0 |
| FROZEN_test_seed20261202_research_3uf_LI_GSHUNT_v0_1 | combined | 0.3323 | 0.3766 | 3.514 | 256 | 5292 | 36/36 | 0.005555 | 0 |
| FROZEN_test_seed20261202_research_3uf_LI_OSHUNT_v0_0 | complete_physics | unavailable | unavailable | 56.91 | 5292 | 0 | 0/0 | unavailable | unavailable |
| FROZEN_test_seed20261202_research_3uf_LI_OSHUNT_v0_0 | analytical | unavailable | unavailable | 3.262 | 256 | 0 | 0/0 | unavailable | unavailable |
| FROZEN_test_seed20261202_research_3uf_LI_OSHUNT_v0_0 | ml | unavailable | unavailable | 4.162 | 256 | 5292 | 0/0 | unavailable | unavailable |
| FROZEN_test_seed20261202_research_3uf_LI_OSHUNT_v0_0 | combined | unavailable | unavailable | 3.527 | 256 | 5292 | 0/0 | unavailable | unavailable |
| FROZEN_test_seed20261202_research_3uf_LI_OSHUNT_v0_1 | complete_physics | unavailable | unavailable | 54.52 | 5292 | 0 | 0/0 | unavailable | unavailable |
| FROZEN_test_seed20261202_research_3uf_LI_OSHUNT_v0_1 | analytical | unavailable | unavailable | 3.433 | 256 | 0 | 0/0 | unavailable | unavailable |
| FROZEN_test_seed20261202_research_3uf_LI_OSHUNT_v0_1 | ml | unavailable | unavailable | 3.676 | 256 | 5292 | 0/0 | unavailable | unavailable |
| FROZEN_test_seed20261202_research_3uf_LI_OSHUNT_v0_1 | combined | unavailable | unavailable | 3.33 | 256 | 5292 | 0/0 | unavailable | unavailable |
| FROZEN_test_seed20261202_research_3uf_SI_GSHUNT_v0_0 | complete_physics | 17.02 | 18.58 | 66.8 | 5292 | 0 | 103/103 | 0.0001124 | 0 |
| FROZEN_test_seed20261202_research_3uf_SI_GSHUNT_v0_0 | analytical | 0.1263 | 0.1946 | 3.907 | 256 | 0 | 103/103 | 0.0001124 | 0 |
| FROZEN_test_seed20261202_research_3uf_SI_GSHUNT_v0_0 | ml | 0.3332 | 0.3767 | 3.745 | 256 | 5292 | 103/103 | 0.0001124 | 0 |
| FROZEN_test_seed20261202_research_3uf_SI_GSHUNT_v0_0 | combined | 0.3398 | 0.3811 | 3.342 | 256 | 5292 | 103/103 | 0.0001124 | 0 |
| FROZEN_test_seed20261202_research_3uf_SI_GSHUNT_v0_1 | complete_physics | 36.25 | 36.7 | 65.11 | 5292 | 0 | 63/63 | 0.03832 | 0 |
| FROZEN_test_seed20261202_research_3uf_SI_GSHUNT_v0_1 | analytical | 0.07613 | 0.1196 | 3.647 | 256 | 0 | 63/63 | 0.03832 | 0 |
| FROZEN_test_seed20261202_research_3uf_SI_GSHUNT_v0_1 | ml | 0.3976 | 0.4382 | 3.796 | 256 | 5292 | 63/63 | 0.03832 | 0 |
| FROZEN_test_seed20261202_research_3uf_SI_GSHUNT_v0_1 | combined | 0.3383 | 0.3807 | 3.867 | 256 | 5292 | 63/63 | 0.03832 | 0 |
| FROZEN_test_seed20261202_research_3uf_SI_OSHUNT_v0_0 | complete_physics | unavailable | unavailable | 53.92 | 5292 | 0 | 0/0 | unavailable | unavailable |
| FROZEN_test_seed20261202_research_3uf_SI_OSHUNT_v0_0 | analytical | unavailable | unavailable | 3.679 | 256 | 0 | 0/0 | unavailable | unavailable |
| FROZEN_test_seed20261202_research_3uf_SI_OSHUNT_v0_0 | ml | unavailable | unavailable | 4.008 | 256 | 5292 | 0/0 | unavailable | unavailable |
| FROZEN_test_seed20261202_research_3uf_SI_OSHUNT_v0_0 | combined | unavailable | unavailable | 3.258 | 256 | 5292 | 0/0 | unavailable | unavailable |
| FROZEN_test_seed20261202_research_3uf_SI_OSHUNT_v0_1 | complete_physics | unavailable | unavailable | 55.09 | 5292 | 0 | 0/0 | unavailable | unavailable |
| FROZEN_test_seed20261202_research_3uf_SI_OSHUNT_v0_1 | analytical | unavailable | unavailable | 3.549 | 256 | 0 | 0/0 | unavailable | unavailable |
| FROZEN_test_seed20261202_research_3uf_SI_OSHUNT_v0_1 | ml | unavailable | unavailable | 4.374 | 256 | 5292 | 0/0 | unavailable | unavailable |
| FROZEN_test_seed20261202_research_3uf_SI_OSHUNT_v0_1 | combined | unavailable | unavailable | 3.238 | 256 | 5292 | 0/0 | unavailable | unavailable |
| KNOWN_RARE_LI_SETUP_EXACT2 | complete_physics | 71.09 | 71.74 | 329.2 | 24696 | 0 | 62/62 | 0.1648 | 0 |
| KNOWN_RARE_LI_SETUP_EXACT2 | analytical | 0.4385 | 0.4834 | 3.406 | 256 | 0 | 45/62 | 0.1648 | 0 |
| KNOWN_RARE_LI_SETUP_EXACT2 | ml | 1.451 | 1.497 | 4.422 | 256 | 24696 | 62/62 | 0.1648 | 0 |
| KNOWN_RARE_LI_SETUP_EXACT2 | combined | 1.473 | 1.525 | 4.333 | 256 | 24696 | 62/62 | 0.1648 | 0 |

## Paired discovery outcomes

A missing pass time is not zero. Ratios below use only cases where both policies found a pass; missed feasible requests are listed separately to avoid hiding failures. A ratio above one means the adaptive policy reached its first pass sooner.

| Policy | Feasible test requests | Missed feasible requests | Paired first-pass timings | Median complete/adaptive time ratio |
|---|---:|---:|---:|---:|
| analytical | 11 | 0 | 11 | 175.8 |
| ml | 11 | 0 | 11 | 51.1 |
| combined | 11 | 0 | 11 | 50.1 |

Per-case JSON includes OOD and unsupported counts, complete/partial coverage, model-loading time, scoring throughput and process peak memory. These results describe this runtime, input set and declared catalog; they establish no general speedup over every electrical setup or four-module search. No real-hardware validation is claimed.
