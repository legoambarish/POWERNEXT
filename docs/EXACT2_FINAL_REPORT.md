# Exact-two final results

The final Network optimizer uses exactly two series/parallel resistors in each front and tail branch. Both branches are optimized jointly across 1,764 pairs per stage and 24,696 configurations over stages 2–15. There is one production resistor-count scope.

The frozen dataset contains 78,244 attempted records, 66,682 valid regression records and 66,244 distinct canonical responses. Training/validation/test totals are 39,311 / 13,179 / 13,754. Records within a setup family are correlated; [the model report](EXACT2_MODEL_REPORT.md) also lists independent split-family counts and separates fresh supplemental tests from previously viewed historical parent tests.

All 32 final candidates were compared using the four agreed approaches. Selection used validation accuracy and independent Physics request oracles before final test evaluation. The selected models are six residual ExtraTrees and two residual HistGradientBoosting models.

| Domain / mode / topology | Train / validation / test | Selected residual model | Gain MAE / RMSE | T1 or Tp MAE / RMSE, µs | T2 MAE / RMSE, µs |
|---|---:|---|---:|---:|---:|
| 0.5 µF / LI / GSHUNT | 5275 / 1778 / 1860 | ExtraTrees | 0.00177034 / 0.00677445 | 0.0540363 / 0.102615 | 0.832307 / 3.4383 |
| 0.5 µF / LI / OSHUNT | 5373 / 1805 / 1865 | ExtraTrees | 0.00112357 / 0.0032997 | 0.0550589 / 0.121198 | 1.3712 / 5.87547 |
| 0.5 µF / SI / GSHUNT | 5221 / 1793 / 1884 | HistGradientBoosting | 0.00288265 / 0.0138785 | 0.153778 / 0.376513 | 0.613844 / 2.48059 |
| 0.5 µF / SI / OSHUNT | 5359 / 1795 / 1878 | ExtraTrees | 0.0015498 / 0.00637032 | 0.180359 / 0.47786 | 0.756888 / 3.31961 |
| 3 µF / LI / GSHUNT | 4923 / 1612 / 1690 | ExtraTrees | 0.0011218 / 0.00341126 | 0.0523001 / 0.0941747 | 3.22599 / 15.9653 |
| 3 µF / LI / OSHUNT | 4055 / 1388 / 1434 | ExtraTrees | 0.000737343 / 0.00295123 | 0.0573211 / 0.112353 | 1.48193 / 6.88912 |
| 3 µF / SI / GSHUNT | 4911 / 1607 / 1674 | ExtraTrees | 0.00101241 / 0.00538002 | 0.136147 / 0.385939 | 1.31436 / 6.26274 |
| 3 µF / SI / OSHUNT | 4194 / 1401 / 1469 | HistGradientBoosting | 0.000561628 / 0.00213684 | 0.229011 / 0.429712 | 1.68937 / 11.6402 |

The two capacitance domains share a tagged storage container but never share a fitted estimator. Original CPRI Excel records were used only for independent comparison, never as training labels. Older mixed-count models and datasets remain historical; the active eight-model set is `networks_exact2_v5`. No Physics equations were changed.

## Post-selection optimizer checks

The 16 fresh requests use seed 20261202, fixed before training, with identical conditions across complete Physics, analytical, ML and combined ranking policies. Each declares stages 6/9/12 (5,292 joint candidates). Eleven requests have verified compliant references; five have none within the supported declared search.

| Policy | Feasible requests retained | Passing alternatives / reference | Maximum observed best-score regret | Median search time, s |
|---|---:|---:|---:|---:|
| complete_physics | 11 / 11 | 670 / 670 | 0 | 68.520 |
| analytical | 11 / 11 | 670 / 670 | 0 | 3.715 |
| ml | 11 / 11 | 670 / 670 | 0 | 3.937 |
| combined | 11 / 11 | 653 / 670 | 0 | 3.839 |

The separately labelled known regression covers all 24,696 candidates over stages 2–15. ML and combined ranking found all 62 compliant alternatives; analytical ranking found 45. All retained the same best verified score. Across all 17 cases, complete Physics performed 109,368 candidate checks; each bounded policy performed 4,352.

These timings came from a shared machine and do not establish a controlled general speedup. The fresh test set shows no incremental best-waveform-quality advantage from ML over analytical ranking. The known regression demonstrates additional alternative retention, not a better best waveform. Complete enumeration still has numerical support limits; unknown/unsupported traces do not prove unrestricted infeasibility.

An additional serving check loaded each actual selected model and scored all 24,696 joint candidates per route, then verified 256 per route with detailed Physics. All eight routes passed integration checks; six requests yielded compliant results and two research OSHUNT requests remained explicitly partial with no compliant result yet. No final-test outcome caused model reselection, dataset enrichment or retraining.

## Verification and delivery

- Source regression: 523 counted tests plus the UI race check across ten suites; 29 focused ML tests pass after the digest-contract correction.
- Actual eight-model application prediction, full-catalog serving and browser scope/model checks pass.
- The original accepted release ZIP is preserved and its SHA256 was rechecked unchanged.
- The exact-two archive uses the selected eight models and bundled runtime. ZIP hash and extracted-runtime acceptance are recorded in a companion receipt after extraction; this avoids a self-referential archive hash.

## Independent two-versus-three study

The preserved five-case [actual-waveform study](TWO_VS_THREE_PRELIMINARY.md) contains three LI and two SI cases, overlays, exact recipes, crest/timing compliance, full-trace errors and fixed-stage/fixed-charge diagnostics. All two-resistor baselines already use exactly two parts on both branches. Three parts materially improve one LI tail result, modestly improve one SI score, produce negligible change in another SI case, and retain the two-part baseline in two cases. No failed baseline becomes passing. The three-part search is sampled best-found and does not prove global optimality or rule out benefits in other setups. It remains separate from the exact-two production scope.

## Evidence and remaining limits

See [data](EXACT2_DATASET_REPORT.md), [all model comparisons](EXACT2_MODEL_REPORT.md), [benchmark details](../evidence/exact2_v5/search_benchmark/report.md), [actual model integration](../evidence/exact2_v5/actual_model_integration.json), and [acceptance](PHASE_B_ACCEPTANCE.md).

The pair grid is complete in five supplemental setup contexts, with stages distributed over 2–15; it is not every pair at every stage and every possible continuous DUT/parasitic condition. Research 3 µF OSHUNT selection uses regression fallback because its validation requests had no feasible oracle result. ML has prediction outliers, so detailed Physics verification remains mandatory. Hardware inventory, mounting, pulse ratings, calibration and laboratory availability are unverified; 3 µF is a research profile.

## Completed offline delivery

The new `PowerNext_Track1_Exact2.zip` is 526,806,027 bytes and passed all eight extracted bundled-runtime acceptance gates with no pending reasons. All 16,737 packaged immutable files matched their manifest before and after execution. SHA256: `b79580fd774560ac1125712d0a6127fde862dcf24089fd0b1e15287b5eafacb2`. The [companion receipt](../evidence/exact2_v5/offline_release_acceptance.json) contains the full checks and confirms preservation of the original release. This post-packaging receipt and delivery paragraph live outside the immutable archive. Launch the new package and choose **Network optimizer**; the existing legacy landing workspace is preserved.
