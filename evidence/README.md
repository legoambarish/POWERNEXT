# Evidence domains and paths

Current phase/final reports are in ../docs. The full suite is in test_logs/final_cpri_v2; phase3_acceptance and phase3_supplemental record the independent oracle. verified_offline_acceptance contains compact actual moved-run evidence. The offline_acceptance output name is reserved for a new user-run acceptance on a fresh extraction. ui contains real browser screenshots. sources contains byte-preserved primary inputs with hashes in primary_sources.json.

Older failed/incomplete phase attempts and the initial ineffective ML acceleration are preserved beside successful gate logs. Their names and phase reports identify superseded attempts; they are not counted as passes. The legacy workbook evidence under powernext/ml is historical synthetic reproduction only.

Raw logs and the runtime probe retain acquisition paths from the tested machine as provenance. No executable path depends on those locations. The code uses paths relative to the release root; moved-folder acceptance exercised that property. The full raw optimizer caches, rerun exports, all historical packages and intermediate candidate ZIP remain in the separate integration audit folder, not the application runtime.
