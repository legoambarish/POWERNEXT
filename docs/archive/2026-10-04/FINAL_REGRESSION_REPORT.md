# Final regression and independent acceptance

Phase 5 gate: **PASS** for the declared provisional software. 383 checks passed across all eight suites, with no failures. This is not laboratory validation or hardware approval. The final archive is packaged after this gate; its separate manifest/ZIP receipt covers delivery bytes.

## Complete suite on the final executable source

Command: `runtime\python.exe tests\run_all.py final_cpri_v2`. All modules used the bundled isolated runtime. Logs: `evidence/test_logs/final_cpri_v2/` in the release.

| Suite | Checks | Outcome | Wall seconds |
|---|---:|---|---:|
| physics | 47 | PASS | 24.03 |
| ml | 30 | PASS | 41.05 |
| optimizer | 89 | PASS | 19.72 |
| application | 61 | PASS | 630.14 |
| frontend | 61 | PASS | 25.77 |
| redteam | 86 | PASS | 41.81 |
| ui_race | 1 | PASS | 0.12 |
| final_release | 8 | PASS | 52.38 |

Counts include parametrized tests and one separate out-of-order UI race fixture. They do not include the independent oracle and laboratory measurements. The source-level 520-rejection assertion was corrected to use unconfirmed 521 Ω; the retained red-team check still rejects arbitrary inventory values. The public request schema was updated to the six parts and explicit current recipes before the suite ran. Later packaging edits are documentation/evidence only.

## Independent scientific acceptance

Phase 3 independently checked 16 requests: catalog enumeration, legal charge, compliance and ranking. All 6,720 saved NPZ waveforms were hash-checked and replayed using the original evaluator. All 63 numerical positives were independently integrated with Radau at 7,000 output samples and agreed within 1e-6 relative in crest and applicable times. The physics/backend/profiles/forward model artifacts and optimizer sources are unchanged from those accepted results; current compatibility checks passed for all 12 app demos.

The oracle has independent enumeration/charge/rank arithmetic but shares the physics backend. Independent full-stage stamping, dimensional LSODA, matrix exponential and Radau provide numerical cross-checks, not CPRI experimental evidence. The optional historical SPICE decks were not run, are explicitly labelled, and are not counted as acceptance.

## Clean moved-folder offline acceptance

A clean candidate ZIP was CRC-checked, extracted into a different directory containing spaces, and all 52,915 extracted immutable files compared by SHA-256. No application database was present initially. The exact root README command launched the extracted bundled runtime. PATH was restricted to Windows directories; invalid external PYTHONHOME/PYTHONPATH were ignored by the isolated interpreter. All imported scientific libraries and four selected models resolved inside that extraction.

Boundary tested: outbound socket connects in application and spawned optimizer workers were denied; loopback HTTP was allowed. The operating system network adapter was not disabled. The actual presentation laptop was unavailable. No external installation or network service was used by the tested application workflow.

| Demo | Candidates | Numerical passes | Waveforms fetched/checked | Scientific replay |
|---|---:|---:|---:|---|
| si | 504 | 14 | 504 | PASS |
| li | 588 | 3 | 588 | PASS |
| li_single | 504 | 0 | 504 | PASS |
| li_disagreement | 84 | 6 | 84 | PASS |
| crest | 504 | 5 | 504 | PASS |
| load | 504 | 3 | 504 | PASS |
| ood | 504 | 0 | 504 | PASS |
| band | 504 | 2 | 504 | PASS |
| infeasible | 504 | 0 | 504 | PASS |
| approved | 0 | 0 | 0 | PASS |
| output_shunt | 504 | 7 | 504 | PASS |
| low | 504 | 19 | 504 | PASS |

Every saved demo was imported byte-for-byte, then its request was freshly optimized over the complete catalog. All scientific candidate records, ordering, result status, search counts and best IDs matched; only run-specific waveform path references were normalized. All 5,208 available fresh waveform responses matched saved metrics and included an explicitly mathematical nominal target. JSON exports were byte-exact, HTML exports rendered the current report structure, and saved/live ZIP exports passed CRC.

Two additional fresh searches checked a 14-candidate restricted inventory and an empty inventory. All 26 application records survived service restart with unchanged result hashes; both SQLite stores passed quick_check. Real HTTP ML screening returned an in-domain model estimate plus OOD abstention with zero simulations and no pruning. An explicitly synthetic QA trace was imported over HTTP, its original hash preserved, clean diagnostics/model comparison checked, and its unqualified, uncalibrated, training-ineligible status persisted after restart.

Evidence: `evidence/offline_acceptance/summary.json`, `runtime_probe.json`, `ml_screen.json`, `synthetic_import.json`, and startup logs in the moved acceptance tree; compact copies accompany the final release. Full raw run records and exports remain in that audit extraction. `evidence/phase5_offline_acceptance.log` records the workflow.

## Controlled before/after result

The old demonstration had different historical requests, so it is not used to attribute numerical changes solely to inventory. Instead, the current same-request candidate records were restricted to the former four-front/one-tail domain: 56 cases with the same equations, setup and tolerances. SI has six passes in that counterfactual and fourteen in the 504-case current catalog. LI has zero in both single-tail catalogs, and three when the separate parallel hypothesis is explicitly enabled (588 total). The main load remains 1.98 nF and L=18.5 µH. The source of each change is separated: confirmed inventory, hypothesized connectivity, numerical solver acceleration, and ML batch caching.

## Integrity, stale assets and negative evidence

All 11 phase-1 frozen files, four selected model routes and twelve current demo identities matched. Only clarification_v2 data and simulation_v2 model registry remain active. 57 copied historical items containing 6,306 files were moved with hash verification to the separate audit archive; the old SPICE README was additionally retained before clarifying its historical scope. Old profile/180-only assumptions survive only in explicitly historical reproduction code/evidence, not the current catalog, schema, request or UI. The seven primary source hashes and the original 618,260,475-byte final ZIP hash still match their receipts.

Executable source scan found no absolute user/development paths. Paths are derived from the release root or explicit data-directory option. Raw test evidence records the actual test location as provenance; those records are not runtime dependencies. A final documentary check restored the profile's source-register link using current source filenames, all seven primary hashes and newest-reply precedence; all referenced source IDs resolve and all eleven frozen physics files remain unchanged (phase5_source_register.json). The final packaging comparison must confirm that executable/model/data/demo bytes equal the tested candidate. Only documentation, the documentary source register, and evidence may differ.

Initial stopped application checks, the first ineffective uncached ML timing, the stdout-encoding wrapper issue, unsupported curves, no-solution cases, ML disagreements and incomplete external evidence remain preserved and clearly separated from passed gates. A snapshot verifier also checked for an absent data folder too late, after the concurrent acceptance had correctly generated its working history. The original failed harness was retained; recovery checked the clean original ZIP and independently streamed/compared every immutable file again. No application defect or test record was hidden or removed (phase5_snapshot_harness_recovery.json). No failed research was relabelled as success.

## Remaining conditions

Hardware/topology approval, actual resistor quantities/ratings/placements, minimum firing charge and increments, full load/auxiliary identification and genuine CPRI waveform validation are unresolved. Imported clean-trace diagnostics are not metrology qualification. The actual presentation computer still needs a dry run. These conditions affect the scope of claims, not whether the checked offline software runs.
