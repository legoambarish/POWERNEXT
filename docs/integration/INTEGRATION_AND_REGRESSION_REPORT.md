# Integration and release-quality verification — 8 October 2026

Current application: `1.0.0+integration20261008`; UI `1.0.0`; retained actual equipment profile `CPRI_IVG_OCT04_2026_v2`.

## Established software gates

The original four-page PS, all supplied CPRI clarification texts, 20-row IVG sheet, all six workbook sheets, briefing and code were reviewed. The independent 70-page October 7 architecture audit was found locally and preserved. The requested implementation architecture took precedence over its different future calibration roadmap. See `source_review_receipt.json`, `IEC_AND_PS_COMPLIANCE_VERIFICATION.md` and `IVG_PARAMETER_COVERAGE.md` for source-level traceability and remaining external dependencies.

| Suite | Result |
|---|---:|
| Physics | 47 passed |
| ML | 30 passed |
| Optimizer | 89 passed |
| Application | 61 passed |
| Frontend | 66 passed |
| Red-team | 86 passed |
| Deterministic asynchronous UI race fixture | Passed |
| New independent integration | 17 passed |
| Release/runtime checks | 8 passed |
| **Total** | **405 checks passed** |

Full source-run logs: `evidence/test_logs/integration_release_20261008/` (400 original checks). All nine suites also passed from the moved portable folder; their retained logs are in `evidence/integration/portable_tests/`. The final presentation-only changes were followed by all 66 frontend checks, including the new warning-removal regression, in `frontend_release_verified.log`. Physics, ML and backend files were byte-compared between that portable suite and the final package. This runner includes network-blocked application/worker execution and the bundled-runtime isolation checks. Failed intermediate development checks and the deliberately interrupted early smoke run were retained; they are not counted as passing acceptance. The raw-vs-normalized request check initially prevented reopening valid evidence; it was corrected and the round-trip tests rerun successfully. No physics acceptance threshold was weakened.

The independent tests cover analytic LI virtual-origin construction, physical SI peak/half-value time, both polarities, time-origin and baseline shifts, nominal target reconstruction, exact inclusive tolerance boundaries plus adjacent outside values, and two independently stamped capacitor-network matrix exponentials. Existing finite-L, energy, charging, shape rejection, catalog, OOD, manifest, stale-result and runtime tests also passed. This is internal verification of the declared competition profile, not IEC 61083 reference qualification.

## Integration invariants

- All confirmed resistor values, including 520 Ω, are available to the declared catalog. The single-component catalog is exhaustive over its stated N=2..15 and selected component/topology scope. Optional parallel LI recipes remain explicit hypotheses. No undisclosed hardware connectivity or resistor rating was invented.
- Stage/total charge and stored energy limits remain enforced. Desired crest is an output requirement. User electrical setup inputs are fixed during optimization. Correct no-solution behavior is retained.
- Current Physics/profile/specification bytes, model binaries and model cards are unchanged against the archived October 4 portable application: 19 artifacts checked. No retraining was needed because equations, features and labels did not change.
- Whole-catalog ranking snapshots are exactly equal before/after the serving performance changes. All refreshed examples retain numerical results and rankings under a new accurate serving fingerprint.
- ML discovery runs zero detailed Physics simulations during broad screening. Every scenario remains visible, including abstentions. Selected/boundary Physics checks preserve the declared stage count, component recipe and charge. Scenario band counts are not probabilities of real success.
- Measurement raw bytes and exact metadata text survive complete ZIP export/reopen with diagnostic records and normalized arrays. Imported data remains unqualified and ineligible for automatic regression training. HTML reports include acquired evidence; JSON-only result exports do not claim to be full archives.
- UI scenario handoffs explicitly create separate drafts. Existing out-of-order selection/poll tests pass; measurement and discovery views have generation guards. Users can review historical stack differences rather than silently relabelling old results.

## Portable acceptance

Portable packaging and moved-folder acceptance are performed separately from unit tests. The final acceptance receipts record launcher startup from a foreign working directory, models and local assets, full SI/LI/no-solution searches, ML batch/OOD and boundary verification, legal adjustment, measured evidence round-trip, isolated bench comparison, technical reports, complete stop/restart, saved history and immutable manifest verification. These application gates passed and are recorded in `evidence/integration/RELEASE_ACCEPTANCE.json`, with exact browser and raw-byte receipts beside it. Fresh extraction of the distribution ZIP, its SHA-256 and final default-path launch are recorded in the **adjacent `release/RELEASE_ACCEPTANCE.json`**. That distribution receipt is external to the ZIP so it can identify the archive without a circular self-hash.

## External qualification items

Unavailable items are stated rather than fabricated: fired-state auxiliary circuit nodes/switch states; 480 pF inclusion boundary; confirmed resistor placement/quantities/pulse-energy ratings; sphere gap spacing/trigger and environmental values; reliable minimum charge/resolution; actual duty/thermal behavior; calibrated divider/digitizer uncertainty; qualified real CPRI waveforms; competition confirmation of the standard edition and numerical crest/SI tolerance interpretation; full licensed normative IEC text and official software-reference evaluation tests.

The release implements the declared CPRI competition waveform profile under its stated assumptions. No setting is labelled laboratory-certified or physically approved. F4 real-machine calibration and F10 measured-data residual learning remain deliberately inactive. The low-voltage circuit is calculated software support, not assembled or experimentally validated hardware.

## Preservation

Original supplied root files were moved and verified byte-for-byte against the preservation manifest. The current Git checkout stays in place. Old releases, LFS-backed artifacts, model mirror, reports and independent audit remain recoverable in clearly dated archives. No Git history rewrite, push, remote modification, original-source overwrite or file deletion was performed. The root and source READMEs identify one current offline release and its tested commands.

## Browser acceptance corrections

Real browser acceptance found and corrected two issues beyond unit tests: late import/scenario/run responses could replace a newer navigation choice, and textarea line-ending normalization could change an untouched metadata file. Navigation-generation regressions now exercise these paths. Original uploaded metadata text is retained until explicitly edited; the repeated browser download/reopen verified exact CSV and metadata bytes, including CRLF. Reopened records now have the correct source label. The final UI suite has 66 checks; the combined suite coverage is 405.
