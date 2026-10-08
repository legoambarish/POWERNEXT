# Run PowerNext offline

## Windows launch

Extract **the complete folder** to a writable Windows x64 location. Double-click `Launch_PowerNext.cmd`. The launcher changes to its own directory, starts the bundled isolated Python runtime and opens the default browser.

From PowerShell, for the delivered folder:

```powershell
& "C:\Users\User\Downloads\Powernext\release\PowerNext_Track1_Offline\Launch_PowerNext.cmd"
```

Browser: **http://127.0.0.1:8765/**. Keep the launcher console open while using the application. Only loopback is exposed. No Python/Node installation, account, API key, package download or internet connection is required. A current local browser and writable folder are required.

Optional console-only launch from inside the extracted folder:

```powershell
.\Launch_PowerNext.cmd --no-browser
```

An occupied port or second instance produces an error instead of silently serving a stale application. Use `--port 8766` if another service legitimately owns 8765; then use the corresponding browser URL. Do not start two instances against the same `data` folder.

## Stop and restart

Double-click `Stop_PowerNext.cmd`, or run it from the release folder:

```powershell
.\Stop_PowerNext.cmd
```

This requests shutdown of the instance recorded in this folder. An active optimization is allowed to finish before the data lock is released. It never terminates unrelated Python processes. Restart with the same launcher; saved history and discoveries remain in `data/`.

## Verify and test

From the release folder:

```powershell
.\runtime\python.exe tests\verify_manifest.py
.\runtime\python.exe tests\run_all.py
```

The manifest verifies immutable application/runtime/model/source bytes. `data/` and newly produced `evidence/test_logs/` are writable and excluded. The suite prints timestamped progress and writes individual logs plus `summary.json` under `evidence/test_logs/<timestamp>/`. It uses the bundled runtimes and blocks non-loopback outbound socket connections in the Python application/workers during acceptance tests. Tests do not modify your normal history.

For only the new integration checks:

```powershell
.\runtime\python.exe -m pytest tests\integration -q -p no:cacheprovider
```

## Fresh extraction and folder moves

Close the application first. Move the **whole** folder, including `runtime`, `powernext`, `ui`, models and `data`; then double-click the launcher in its new location. Paths are resolved relative to that location. Run the manifest verifier after extraction or moving. A fresh ZIP extraction starts with an empty personal history; existing history can be moved with `data/` or reopened from complete run ZIP exports. Do not copy only a SQLite file, JSON result or launcher and expect waveform assets to follow.

The delivered working folder includes the two preserved earlier local history records, labelled historical because their serving fingerprint differs. The distribution ZIP starts clean. The archived October 4 release retains the untouched original history copy.

## Evidence workflow

Use Waveform Review to import a CSV together with its actual units, configuration, polarity, origin and measurement metadata. Synthetic examples remain explicitly labelled. Complete evidence export (ZIP) includes all candidate curves, raw imported data, metadata and analysis. In History, choose **Reopen evidence ZIP** to restore that record. JSON-only result exports do not claim to include raw measurement files. Imported traces do not train models or approve hardware recipes.

Discovery has its own saved exploration history and JSON export, including every explicit scenario, ML support result and selected Physics verification. Fixed-setting sensitivity holds stage count, resistors and charge constant. To investigate a point, verify it in Physics or copy its setup into a separate optimization draft; neither action silently changes an already saved test.

## Presentation order

1. Configuration: enter an SI request, review fixed inputs and inventory, run the complete catalog. Explain requested **output crest**, stage charge, BOM and each individual conformity result.
2. Recommendations: show why the best result ranks first, alternatives, and Next Legal Adjustment from a lower-charge current setting.
3. Show the LI single-component no-solution case; then the explicitly selected 180 || 520 Ω circuit hypothesis and its provisional physical status.
4. ML Prediction: enter one fixed configuration, inspect ML versus Physics, support and simulation validation evidence.
5. Rapid Discovery: enter explicit DUT/inductance ranges, screen a grid, inspect a point, and verify boundary scenarios without retuning charge.
6. Waveform Review: import a correctly labelled trace and metadata, inspect quality/mismatch diagnostics, export complete evidence, and reopen it in History.
7. Equipment & technical details: show the 20-parameter IVG audit, 520 Ω clarification and PS/IEC traceability. Low-voltage bench is optional and is identified as a calculated circuit, not built hardware.

Numerical conformity refers to the declared competition profile and equivalent circuit. Hardware connectivity and pulse ratings remain external confirmation items; IEC measuring-system/software qualification is not claimed.
