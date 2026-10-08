# PowerNext Track 1 — October 4 competition release

Release: **PowerNext_Track1_Competition_v2**. Start from its root with `runtime\python.exe -m powernext_app`, or double-click Launch_PowerNext.cmd. Windows x64, offline, writable extraction folder required. Default address: http://127.0.0.1:8765/. No package installation, API key or external Python is needed.

## Included changes

- Profile CPRI_IVG_OCT04_2026_v2 and physics 0.2.0: six confirmed components, explicit versioned single/parallel hypotheses, physical-part BOM and guarded numerical solver. The evaluator/tolerance treatment stays unchanged.
- Fresh synthetic dataset sim_1f2992ccb93c5d9d: 18,339 attempted cases, 18,028 eligible labels, preserved failures and grouped splits. Four selected residual Extra Trees routes in simulation_v2 replace the incompatible old simulation registry.
- Exhaustive 504-candidate default catalog, 588 when both LI/GSHUNT hypotheses are selected, charge-band handling, content-based provenance and current waveform artifacts.
- Application 0.4.0+cpri20261004 / UI 0.4.0: 12 current synthetic demos, target overlay, useful clean-trace import diagnostics, actual-configuration comparison, real trained scenario screening, explicit assumptions, recipe selection and component inventory.
- All module/frontend/red-team/portability tests, updated documentation, model cards, data, primary-source copies and compact acceptance evidence. Historical workbook reproduction is labelled and isolated. Old simulation models/data/docs/examples are outside the active runtime, preserved in the audit folder.

The ML and optimizer Python package compatibility strings remain 0.1.1+redteam; those strings alone are not a scientific identity. The new equipment/recipe IDs, dataset/model IDs, selected-model hashes, transitive serving fingerprint, optimizer source hashes and release manifest distinguish the changed implementation. No old model artifact is routed as a current model.

## Verification and integrity

All 383 full-suite checks passed, alongside the independent oracle/replay/Radau checks and clean moved offline acceptance described in FINAL_REGRESSION_REPORT.md. FINAL_FILE_MANIFEST.json records immutable release bytes. Run `runtime\python.exe tests\verify_manifest.py` to verify them. New logs, caches and application history are generated under data/ or a chosen data directory and are not immutable delivery files.

The root ZIP is the only final delivery archive. The separately labelled phase-5 candidate ZIP is an audit artifact. The final ZIP's SHA-256 sidecar and sibling FINAL_ZIP_ACCEPTANCE.json record final archive CRC, manifest verification, tested-code identity, clean extraction and launch checks. Full raw intermediate evidence and original packages remain in the parent integration workspace; compact copies accompany the release.

## Limits

READY WITH CONDITIONS for a software demonstration; no approved CPRI recipe, hardware operation, metrology certification or laboratory accuracy is claimed. The LI success is conditional on an explicit unconfirmed connection and illustrative load. Minimum reliable charge, actual quantities/ratings/placements, complete load/auxiliary states and measured calibration remain unknown. The actual presentation laptop still needs a dry run.

See FINAL_CLAIMS_AND_LIMITATIONS.md and UPDATED_JUDGE_QA.md before presenting numerical results as engineering conclusions.
