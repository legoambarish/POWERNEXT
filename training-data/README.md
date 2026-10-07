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

