# Training data

`clarification_v2_training_data.zip` is the complete generated dataset used for the current model-training campaign. It contains:

- `clarification_v2/design.json`
- `clarification_v2/rows.jsonl`
- `clarification_v2/manifest.json`
- 36,664 files under `clarification_v2/waveforms/`

Archive details:

| Item | Value |
| --- | --- |
| Size | 1,335,555,581 bytes |
| Entries | 36,669 |
| SHA-256 | `8e2b622c28d423545ccfc7ee0e5da7ec69a6fe4d221076fb17ec9d6034483ef6` |

The unarchived design, rows and manifest are also under `powernext/ml/data/clarification_v2/` for inspection. Train/test grouping is recorded in `powernext/ml/results/simulation_v2/split_assignments.csv`.

The data are simulated under provisional circuit topologies. They are not measured CPRI waveforms. Invalid and unsupported simulation outcomes were retained rather than silently discarded; only eligible labels entered model fitting.

Verify after cloning with Git LFS:

```powershell
Get-FileHash .\training-data\clarification_v2_training_data.zip -Algorithm SHA256
Get-Content .\training-data\clarification_v2_training_data.zip.sha256
```


## Network v3 initial-stage data — 10 October 2026

`PowerNext_Networks_v3_Data_Stage1_20261010.zip` is an immutable Git LFS
archive of 372 files (230,728,065 compressed bytes). SHA-256:
`a7700247013cec245ccee4d8f02cfd7b813e99b82934f5bb4394c993c46bb817`.
The adjacent `.manifest.json` lists every relative path, size and file hash.
All archived files were reread and verified against the source bytes.

After `git lfs pull`, extract into a separate checkout root to recover the
original `powernext/ml/data/...` paths. Do not overwrite existing evidence.
The current workspace retains the original extracted copies unchanged; Git
ignores those copies because the ZIP is the versioned artifact.

- Accepted production data: `networks_v3_r2`, 122,000 attempts, 92,662 canonical
  eligible shapes across eight separate routes. Full source/hash/split/coverage
  acceptance is recorded in `evidence/phase_b/production_dataset_audit.json`
  and `lead_training_preflight.json`.
- Validation-only complete-catalog oracles: `networks_v3_validation_oracles`.
- Accepted corrected pilot: `networks_v3_pilot_splitfix2`.
- `networks_v3` is an aborted split-audit rejection, preserved as negative
  evidence. Other pilot folders are development diagnostics. Do not train a
  production model from these rejected/prototype artifacts.

Each production route has a frozen 30,000-input capacity. The accepted archive
contains the initial prefixes, not labels for the unexecuted remainder. Any
later validation-driven extension requires another immutable archive identity.
The original workbook and all historical training archives remain unchanged.

## Network v3 validation-oracle archive — 10 October 2026

`PowerNext_Networks_v3_ValidationOracles_20261010.zip` is an immutable
oracle-only archive containing the completed v2 validation-oracle directory:
16 complete Physics cases plus `requests.json` and `manifest.json` (18 files,
22,115,615 compressed bytes). SHA-256:
`3f073dc61ba63aaffb0f3ce66bde4949496c85cac1556c3630f1c68967d4b4c2`.
The adjacent `.manifest.json` records every member's size and SHA-256, and
the `.zip.sha256` sidecar records the archive hash. Every member was reread
from the ZIP and matched both the manifest and its retained extracted source.

This archive is marked `training_role: NOT_TRAINING_DATA` and
`validation_role: INDEPENDENT_MODEL_SELECTION_ORACLES_ONLY`. It contains
complete Physics labels used for model-selection validation; it is not a
training dataset and is not final test evidence. The retained extracted copy
is `powernext/ml/data/networks_v3_validation_oracles_v2/`, and the original
oracle folders and accepted production archive remain unchanged.

After `git lfs pull`, verify and recover the oracle files into a separate
checkout root without overwriting existing evidence:

```powershell
Get-FileHash .\training-data\PowerNext_Networks_v3_ValidationOracles_20261010.zip -Algorithm SHA256
Get-Content .\training-data\PowerNext_Networks_v3_ValidationOracles_20261010.zip.sha256
Expand-Archive .\training-data\PowerNext_Networks_v3_ValidationOracles_20261010.zip -DestinationPath <separate-checkout-root>
```

The catalog reconciliation and old/new scientific replay comparison are
recorded in `evidence/phase_b/oracle_catalog_reconciliation.json` and
`evidence/phase_b/oracle_scientific_comparison.json`.
