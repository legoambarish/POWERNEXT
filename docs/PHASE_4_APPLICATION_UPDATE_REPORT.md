# Phase 4 — application gate

Completed 2026-10-04. Phase 3 was reported and passed before application changes. All changes are in the new integration folder; original packages and sources remain preserved.

## Change and reason

- The existing interface now exposes the six confirmed component values and explicit recipe selection. Uniform single-component arrangements are the development default. The LI/GSHUNT 180 || 520 hypothesis is off by default and adds 84 configurations only when explicitly selected. The review shows 504 or 588 as appropriate. Recipe, numerical, model-domain, waveform-evaluation and operational status remain separate.
- The conditional LI example displays the actual 9 × 30 Ω, 9 × 180 Ω and 9 × 520 Ω bill of materials. 133.714 Ω is labelled as a derived equivalent, never an available part. Unknown quantities, placements and ratings remain visible.
- Twelve current, labelled synthetic scenarios replace historical demonstrations. The single-resistor LI failure, conditional LI success, real ML false acceptance, low-charge SI, OOD, no-solution, load/crest changes and approved-scope empty result are retained. Switching LI/SI updates the test reference correctly.
- The waveform view and HTML report show a mathematical nominal target generated using the frozen shared waveform definitions. Target curves are not asserted to be achievable hardware outputs. Historical mismatched artifacts cannot acquire current target overlays.
- The new scenario grid calls the four trained models in batches over explicit fixed-configuration DUT/L scenarios. It performs no physics simulation, exposes abstention/OOD and presents only unverified estimates. Final recommendations still require exhaustive physics.
- Trace imports distinguish SYNTHETIC_IMPORT, BENCH_MEASURED_UNVERIFIED and CPRI_MEASURED_CLAIMED. Original bytes and metadata are archived. Clean-curve timing diagnostics and comparison against the declared actual configuration are useful for future experiments; they do not qualify measured waveforms or enable calibration/training. Source authentication, de-embedding and noisy/overshoot qualification remain unresolved. No actual CPRI trace was found or invented.
- Candidate access uses a small hash-verifying cache and returns detached rows. Every access verifies saved bytes, including same-mtime tampering; cached objects cannot alter metrics. Warm read latency fell from approximately 318 ms to 38 ms in local probes. Model, physics and optimizer decision artifacts were not changed by this presentation optimization.

## Evidence and verification

| Check | Outcome | Evidence |
|---|---|---|
| Complete application suite | **61 passed**, 644.59 s | `evidence/phase4_application_final.log` |
| Complete current frontend suite | **61 passed**, 0 failed, 21.09 s | `evidence/phase4_frontend_gate.log` |
| New application regressions | 19 included above | `tests/application/test_clarification_v2.py` in release |
| New frontend regressions | 6 included above | `tests/application/clarification.test.mjs` |
| Real browser | Conditional LI, single LI failure, 588 review, synthetic trace import, ML discrepancy, actual 289-scenario grid, no console errors | `evidence/ui/*.jpg` |
| Actual UI grid | 289 estimates, 0 abstentions, 0 physics calls; observed 858.7 ms | `evidence/ui/ml_screen.jpg` |
| Synthetic import | T1 1.2 µs / T2 50 µs versus predicted 1.29689 / 50.90867; 79.869 kV sample RMS; unqualified and training-ineligible | `evidence/ui/synthetic_import.jpg`, `evidence/ui_import_fixture/` |
| Physics/ML discrepancy | ML scalar crest passes while reference crest fails the 3% interval; physics remains authoritative | `evidence/ui/ml_false_acceptance.jpg` |
| Restart with latest service | Current LI artifact matches current stack; correct component counts/status/nominal target | `evidence/ui/li_result_viewport.jpg` |
| Cache | Current result byte checks and detached metric integrity; timing probes retained | `evidence/phase4_read_initial.json`, `evidence/phase4_read_cached.json` |

The earlier broad application attempt was intentionally stopped after identifying two stale test assertions and excessive repeated JSON parsing. Its incomplete log is retained, not counted as a pass. Assertions now recognize PROVISIONAL_HYPOTHESIS as provisional. The first frontend wrapper also hit a Windows stdout encoding error after Node had passed all tests; the UTF-8 wrapper and later successful gate log resolve that reporting issue. Negative evidence was not erased.

## Limits and next gate

Application version is 0.4.0+cpri20261004 (UI 0.4.0). No recipe is CPRI approved, no operator setting is authorized, no laboratory accuracy or physical calibration is claimed. The 1550 kV example uses the same explicitly declared illustrative load as the physics/optimizer acceptance; it is not a measured definition of the briefing's 400 kV equipment setup.

Phase 4 passes. Phase 5 must still complete the all-module suite, current-asset audit, controlled before/after comparison, and clean moved-folder offline acceptance. This report does not claim final release readiness.
