# PowerNext — offline impulse engineering workbench

Current integration: **1.0.0+integration20261008**. The application combines exhaustive Physics-authoritative recommendations with trained ML prediction, rapid scenario discovery and complete waveform evidence review. LI uses virtual T1 1.2/50 µs; SI uses the CPRI-requested physical time-to-peak 250/2500 µs profile.

Double-click **Launch_PowerNext.cmd**, then use **http://127.0.0.1:8765/**. All required runtimes, models and dependencies are local. Stop with **Stop_PowerNext.cmd** or Ctrl+C in the launcher console.

```powershell
.\Launch_PowerNext.cmd
.\runtime\python.exe tests\verify_manifest.py
.\runtime\python.exe tests\run_all.py
.\Stop_PowerNext.cmd
```

See [complete run and presentation instructions](docs/integration/RUN_INSTRUCTIONS.md), [project structure](docs/integration/PROJECT_STRUCTURE.md), [PS and IEC verification](docs/integration/IEC_AND_PS_COMPLIANCE_VERIFICATION.md), [IVG parameter coverage](docs/integration/IVG_PARAMETER_COVERAGE.md), [changes](docs/integration/CHANGELOG.md), [performance](docs/integration/PERFORMANCE_REPORT.md), and [integration/acceptance evidence](docs/integration/INTEGRATION_AND_REGRESSION_REPORT.md).

## Engineering workflows

- **Configuration & Recommendations:** fixed engineer-entered setup, real confirmed resistor values, exhaustive declared catalog, charge/energy constraints, waveform comparison, per-parameter conformity, BOM, alternatives and Next Legal Adjustment.
- **ML Prediction & Discovery:** actual single-configuration predictions alongside detailed Physics; explicit batches and fixed-charge sensitivity grids; support/abstention; selected/boundary Physics checks; saved explorations; explicit handoff to a new optimization draft.
- **Waveform Review & Evidence:** raw trace and actual configuration/metadata, quality diagnostics, prediction comparison, history, complete ZIP export and verified reopen. Uploads do not train models or change ranking authority.

The equipment profile is `powernext/physics/CPRI_EQUIPMENT_PROFILE.json`. The four selected ExtraTrees models are in `powernext/ml/registry/simulation_v2/`; their cards and validation evidence are retained. Physics equations, waveform definitions, training labels and model binaries were preserved. ML never prunes the final catalog.

## Evidence and limits

Numerical conformity is a model result under a declared circuit recipe. No recipe is labelled approved CPRI hardware. Auxiliary resistor connectivity, the 480 pF inclusion boundary, resistor quantities/pulse ratings and reliable charge adjustment limits remain external confirmation items. The supplied 2 pulses/minute is a planning reference, not a timing controller or thermal qualification. Full licensed IEC normative text and reference evaluation tests were unavailable; formal IEC measurement/software certification is not claimed.

All historical sources and releases were preserved. In the development workspace, the single current release is `../release/PowerNext_Track1_Offline/`, original root sources are `../sources/original/`, and prior packages are `../archive/`. This Git checkout also retains historical reports/assets under `docs/archive/` and `archive/`; no remote or Git history changes were made. Complete training waveform archives remain in `training-data/` and the previous full release, while the portable application includes the operational dataset records and all inference/test dependencies.

`data/` contains writable local evidence. Move the whole folder after stopping the server to retain it. Never overwrite primary sources, original result identities, or historical manifests. Current run ZIPs preserve raw measurement bytes and configuration provenance.

