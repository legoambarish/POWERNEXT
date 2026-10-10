# Preliminary actual ≤2 versus ≤3 waveform study

This report records the bounded five-case preliminary study requested before a full campaign. It compares actual detailed Physics waveforms from the frozen cpri requests in [`evidence/two_vs_three/preliminary_v4/study_manifest.json`](../evidence/two_vs_three/preliminary_v4/study_manifest.json). The run contains three LI cases and two SI cases, all on the `cpri_0p5uf` profile, with GSHUNT and OSHUNT topologies. Earlier drafts remain at [`preliminary`](../evidence/two_vs_three/preliminary), [`preliminary_v2`](../evidence/two_vs_three/preliminary_v2), and [`preliminary_v3`](../evidence/two_vs_three/preliminary_v3). The v4 directory is the accepted hardened-script replay; [`rerun_validation.json`](../evidence/two_vs_three/preliminary_v4/rerun_validation.json) records equality of the selected scientific metrics, configurations, and recipe trees with v3.

The five inputs were selected before any ≤3 waveform was simulated:

| request | mode | topology | requested crest |
| --- | --- | --- | ---: |
| `FROZEN_test_cpri_0p5uf_LI_GSHUNT_v0_0` | LI | GSHUNT_v0 | 1,000,000 V |
| `FROZEN_test_cpri_0p5uf_LI_GSHUNT_v0_1` | LI | GSHUNT_v0 | 750,000 V |
| `FROZEN_test_cpri_0p5uf_LI_OSHUNT_v0_0` | LI | OSHUNT_v0 | 1,550,000 V |
| `FROZEN_test_cpri_0p5uf_SI_GSHUNT_v0_0` | SI | GSHUNT_v0 | 1,300,000 V |
| `FROZEN_test_cpri_0p5uf_SI_OSHUNT_v0_0` | SI | OSHUNT_v0 | 750,000 V |

Each ≤2 baseline replays the matching completed Physics benchmark configuration, including its exact network trees, stage count, and legal stage charge. The study also evaluates a guided catalog baseline and a simple diagnostic baseline; those rows remain in each case file but are not used to claim a crossover. The ≤3 pool contains the exact ≤2 baseline plus 24 deterministic catalog samples (three seeds, stage coverage across 6/9/12, and front/tail module-pair coverage across the nine 1–3 module combinations). Two local three-module response neighbours per seed are selected around the frozen ≤2 anchor, and all selection rules are recorded before simulation.

The complete catalog sizes for the declared stages are 6,912 distinct ≤2 response candidates and 496,947 distinct ≤3 response candidates. The ≤3 catalog also has 509,232 recipe configurations before response-equivalence grouping. This preliminary run evaluates only the bounded sample; it is not an unrestricted ≤3 search or a hardware recommendation.

The main ≤3 row is the best finite row in the declared pool, ranked by the existing canonical parameter score after Physics-only legal-charge verification. The exact ≤2 row is always retained in that pool. A separate **post-selection replay** uses the selected three-module network at the exact ≤2 stage count and stage charge. The network was selected at its legal optimized charge first, then replayed at the ≤2 baseline N/q; it is therefore a network-only crossover diagnostic and is not an optimum at fixed charge. All five post-selection replay rows are finite and evaluator PASS. A PASS requires `numeric_status=VALID`, `waveform_status=VALID_CLEAN_FULL_IMPULSE`, and evaluator `compliance_status=PASS`; failed and unsupported sampled rows remain in the case JSON and the cost counts.

## Best-found timing rows

Values are from the actual output waveform metadata. `T1` is used for LI and `Tp` for SI. The result is labelled `exact ≤2 baseline` when the best row in the declared ≤3 pool is the required exact baseline replay.

| request | ≤2: N / q (V), front / tail (µs), J | ≤3 selected: N / q (V), front / tail (µs), J | interpretation |
| --- | --- | --- | --- |
| LI GSHUNT 1.0 MV | 9 / 115,232.57; 1.2117 / 48.5052; 0.023404 | 9 / 115,018.61; 1.2071 / 49.9039; 0.000478 | sampled three-module PASS |
| LI GSHUNT 0.75 MV | 6 / 131,428.01; 1.2070 / 49.8050; 0.000755 | 6 / 131,428.01; 1.2070 / 49.8050; 0.000755 | exact ≤2 baseline PASS |
| LI OSHUNT 1.55 MV | 12 / 181,984.50; 1.2484 / 46.1905; 0.163198 | 12 / 181,984.50; 1.2484 / 46.1905; 0.163198 | exact ≤2 baseline PASS |
| SI GSHUNT 1.3 MV | 12 / 126,245.84; 260.2321 / 2,232.8243; 0.073604 | 12 / 126,134.05; 257.5354 / 2,226.8556; 0.055872 | sampled three-module PASS |
| SI OSHUNT 0.75 MV | 12 / 135,708.51; 244.4612 / 2,934.2534; 0.096083 | 12 / 135,774.55; 244.3042 / 2,932.3111; 0.096040 | sampled three-module PASS |

The ≤3 rows are sampled best-found results. They do not establish a global optimum, and a matching J value for the exact baseline means the bounded sample found no accepted improvement in that case. The generated rows preserve exact `front_network` and `tail_network` trees, candidate indices, seeds, stage charge, and compact Physics metrics in each [`case.json`](../evidence/two_vs_three/preliminary_v4/cases/).

## Per-requirement values and PASS flags

The following ten rows are read from the saved case JSON. Crest deviation is absolute percentage from the requested crest; front and tail deviations are absolute differences from the nominal timing values. The three flags are scalar evaluator limits in the order crest/front/tail. They describe the selected waveform rows and do not turn the synthetic Physics result into hardware evidence.

| mode/topology | target (kV) | row | actual crest (kV) | Abs. crest deviation | Abs. front deviation (µs) | Abs. tail deviation (µs) | flags | J |
| --- | ---: | --- | ---: | ---: | ---: | ---: | --- | ---: |
| LI/GSHUNT | 1,000 | ≤2 locked complete | 1,000.000 | 0.0000% | 0.0117 | 1.4948 | PASS/PASS/PASS | 0.023404 |
| LI/GSHUNT | 1,000 | ≤3 selected | 1,000.000 | 0.0000% | 0.0071 | 0.0961 | PASS/PASS/PASS | 0.000478 |
| LI/GSHUNT | 750 | ≤2 locked complete | 750.000 | 0.0000% | 0.0070 | 0.1950 | PASS/PASS/PASS | 0.000755 |
| LI/GSHUNT | 750 | ≤3 selected | 750.000 | 0.0000% | 0.0070 | 0.1950 | PASS/PASS/PASS | 0.000755 |
| LI/OSHUNT | 1,550 | ≤2 locked complete | 1,550.000 | 0.0000% | 0.0484 | 3.8095 | PASS/PASS/PASS | 0.163198 |
| LI/OSHUNT | 1,550 | ≤3 selected | 1,550.000 | 0.0000% | 0.0484 | 3.8095 | PASS/PASS/PASS | 0.163198 |
| SI/GSHUNT | 1,300 | ≤2 locked complete | 1,300.000 | 0.0000% | 10.2321 | 267.1757 | PASS/PASS/PASS | 0.073604 |
| SI/GSHUNT | 1,300 | ≤3 selected | 1,300.000 | 0.0000% | 7.5354 | 273.1444 | PASS/PASS/PASS | 0.055872 |
| SI/OSHUNT | 750 | ≤2 locked complete | 750.000 | 0.0000% | 5.5388 | 434.2534 | PASS/PASS/PASS | 0.096083 |
| SI/OSHUNT | 750 | ≤3 selected | 750.000 | 0.0000% | 5.6958 | 432.3111 | PASS/PASS/PASS | 0.096040 |

No failed crest/front/tail scalar flag occurs in these selected rows. The sampled pools still retain failed attempts in their case JSON; this table reports only the two comparison rows per case and does not imply that every sampled candidate passed.

## Exact selected recipe trees

`R<number>` is a resistor in ohms. `P(...)` and `S(...)` are the exact parallel and series tree operators preserved in the case records. The ≤3 row is the selected legal-charge row; when it is labelled exact baseline, its recipe is intentionally the same ≤2 tree.

| case | ≤2 front | ≤2 tail | ≤3 selected front | ≤3 selected tail |
| --- | --- | --- | --- | --- |
| LI GSHUNT 1.0 MV | `P(R30,R520)` | `P(R180,R520)` | `P(R30,R520,R5000)` | `S(R46,R46,R46)` |
| LI GSHUNT 0.75 MV | `P(R46,R520)` | `P(R180,R520)` | `P(R46,R520)` | `P(R180,R520)` |
| LI OSHUNT 1.55 MV | `P(R30,R5000)` | `S(R46,R46)` | `P(R30,R5000)` | `S(R46,R46)` |
| SI GSHUNT 1.3 MV | `P(R5000,R5000)` | `S(R180,R5000)` | `P(R3700,S(R3700,R3700))` | `S(R5000,P(R180,R5000))` |
| SI OSHUNT 0.75 MV | `S(R46,R3700)` | `S(R30,R3700)` | `S(R3700,P(R46,R3700))` | `S(R3700,P(R30,R180))` |

## Post-selection replay at fixed N and fixed charge

The rows below compare the selected ≤2 waveform with a separate **post-selection replay** of the best sampled network containing three modules at the baseline stage count, using the same setup and baseline stage charge. This diagnostic network can differ from the main ≤3 winner above, especially when that winner retains the two-module baseline. The network was chosen at its legal optimized charge before this replay; the replay does not claim fixed-charge optimization. Errors are calculated on the intersection of the two simulated time domains using the common 1,600-point grid. Absolute errors are in volts; normalized errors divide by the requested crest.

| request | post-selection replay ≤3 front / tail (µs), J | L∞ (V / normalized) | RMSE (V / normalized) | absolute-error integral (V·s) |
| --- | --- | ---: | ---: | ---: |
| LI GSHUNT 1.0 MV | 1.2071 / 49.9039; 0.004323 | 11,532 / 0.011532 | 4,558 / 0.004558 | 2.2222 |
| LI GSHUNT 0.75 MV | 1.1905 / 50.3912; 0.004674 | 3,963 / 0.005284 | 1,565 / 0.002086 | 0.7500 |
| LI OSHUNT 1.55 MV | 1.2476 / 46.0422; 0.175979 | 2,843 / 0.001834 | 1,093 / 0.000705 | 0.4579 |
| SI GSHUNT 1.3 MV | 257.5354 / 2,226.8556; 0.056745 | 6,906 / 0.005312 | 525 / 0.000404 | 7.0293 |
| SI OSHUNT 0.75 MV | 244.3042 / 2,932.3111; 0.096303 | 412 / 0.000549 | 144 / 0.000192 | 3.4901 |

For the first LI controlled experiment, both circuits use N=9 and q=115,232.57 V. The actual crest changes from 1,000.000 kV to 1,001.860 kV while front/tail timing changes from 1.2117/48.5052 µs to 1.2071/49.9039 µs. Both waveforms pass; the controlled three-resistor J is 0.004323. Only the two resistor-network recipes change.

The main best-found ≤3 versus ≤2 common-grid RMSE values are 4,292 V (0.004292 normalized), 0 V (the exact-baseline row), 0 V (the exact-baseline row), 637 V (0.000490 normalized), and 78 V (0.000104 normalized), respectively. The post-selection replay row is kept separate because it answers a different question from the legal-charge best-found row.

## Reference waveform and metric definitions

The plot reference is generated by [`tools/impulse_target_reference.py`](../tools/impulse_target_reference.py). It is a non-unique double-exponential plotting reference whose nominal scalar definitions match LI `T1=1.2 µs`, `T2=50 µs` and SI `Tp=250 µs`, `T2=2,500 µs`. It starts at physical firing time `t=0`. Simulated traces are neither peak-shifted nor amplitude-renormalized. The three timing requirements do not uniquely determine a physical waveform, so this reference is a comparison aid rather than an official trace or a Physics label.

The reported `J` is the repository's canonical `parameter_score`: the sum of squared, requirement-normalized deviations for crest, front, and tail, with lower values preferred. It is the same objective used for both module bounds; the fixed-N/fixed-charge rows are post-selection replays and are not re-optimized at that charge.

For LI, the report uses the evaluator's virtual-front and virtual-origin timing. For SI, it uses the physical peak time and physical `T2`. The plots include the complete simulated duration and a separate nominal front/first-peak window; both use the same physical time origin. The case files also store target-reference time and voltage arrays, target residual L∞/RMSE values, actual 2-versus-3 L∞/MAE/RMSE, time-integral, and L2 time-norm metrics.

## Waveform artifacts

Each overlay contains the selected ≤2 trace, the main selected ≤3 trace, the post-selection replay ≤3 trace when available, and the nominal reference. The corresponding `.npz` files retain the full selected waveforms and reference arrays.

- [LI GSHUNT 1.0 MV overlay](../evidence/two_vs_three/preliminary_v4/plots/cpri_0p5uf_LI_GSHUNT_v0_FROZEN_test_cpri_0p5uf_LI_GSHUNT_v0_0__overlay.png) · [case JSON](../evidence/two_vs_three/preliminary_v4/cases/cpri_0p5uf_LI_GSHUNT_v0_FROZEN_test_cpri_0p5uf_LI_GSHUNT_v0_0/case.json)
- [LI GSHUNT 0.75 MV overlay](../evidence/two_vs_three/preliminary_v4/plots/cpri_0p5uf_LI_GSHUNT_v0_FROZEN_test_cpri_0p5uf_LI_GSHUNT_v0_1__overlay.png) · [case JSON](../evidence/two_vs_three/preliminary_v4/cases/cpri_0p5uf_LI_GSHUNT_v0_FROZEN_test_cpri_0p5uf_LI_GSHUNT_v0_1/case.json)
- [LI OSHUNT 1.55 MV overlay](../evidence/two_vs_three/preliminary_v4/plots/cpri_0p5uf_LI_OSHUNT_v0_FROZEN_test_cpri_0p5uf_LI_OSHUNT_v0_0__overlay.png) · [case JSON](../evidence/two_vs_three/preliminary_v4/cases/cpri_0p5uf_LI_OSHUNT_v0_FROZEN_test_cpri_0p5uf_LI_OSHUNT_v0_0/case.json)
- [SI GSHUNT 1.3 MV overlay](../evidence/two_vs_three/preliminary_v4/plots/cpri_0p5uf_SI_GSHUNT_v0_FROZEN_test_cpri_0p5uf_SI_GSHUNT_v0_0__overlay.png) · [case JSON](../evidence/two_vs_three/preliminary_v4/cases/cpri_0p5uf_SI_GSHUNT_v0_FROZEN_test_cpri_0p5uf_SI_GSHUNT_v0_0/case.json)
- [SI OSHUNT 0.75 MV overlay](../evidence/two_vs_three/preliminary_v4/plots/cpri_0p5uf_SI_OSHUNT_v0_FROZEN_test_cpri_0p5uf_SI_OSHUNT_v0_0__overlay.png) · [case JSON](../evidence/two_vs_three/preliminary_v4/cases/cpri_0p5uf_SI_OSHUNT_v0_FROZEN_test_cpri_0p5uf_SI_OSHUNT_v0_0/case.json)

The accepted v4 replay used bundled Python with `-B`, `n_points=1600`, seed base `20261010`, and `max_three=32` per seed before deduplication. It completed in 11.685 seconds (shared-machine wall time, not a controlled throughput claim). Its exact executed source is saved as `compare_two_three_waveforms_run.py` with SHA-256 `64af52904f3c81357db0a3f4f464767c3ec9b3da1be00a2e84b59728c0309f1b`. The v4 replay includes the benchmark identity guard and explicit post-selection naming. All selected scientific metrics and recipes match v3. No ML model was loaded and no training data was produced by this study.

All five selected two-module baselines already use exactly two resistors in both front and tail branches. They therefore remain admissible under the later exact-two production decision. The 6,912-candidate baseline coverage and 71.90× catalog ratio above describe the historical **up-to** catalogs; the new exact-two production catalog has 5,292 responses at stages 6/9/12 (24,696 over stages 2–15).
