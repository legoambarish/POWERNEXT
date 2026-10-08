# Current project and preserved history

The project root is `C:\Users\User\Downloads\Powernext`.

| Location | Authority and purpose |
|---|---|
| `POWERNEXT/` | Current Git checkout, source, tests and engineering evidence. Git history is retained in place; no remote changes were made |
| `release/PowerNext_Track1_Offline/` | The one current portable Windows application |
| `release/PowerNext_Track1_Offline.zip` | Fresh-extraction distribution of that application; adjacent SHA-256 checksum |
| `sources/original/` | Original root-supplied PS, IVG sheet, workbook, clarification texts, briefing and PRD, moved without rewriting |
| `sources/ORIGINAL_SOURCE_MANIFEST.json` | Original and final paths, byte sizes and SHA-256 checksums |
| `documentation/training/` | Retained October 7 training/deep-dive documents |
| `archive/` | Prior component packages, complete previous releases, red-team work, previous example identities and independent architecture audit. Historical evidence, not the current launch target |

## Inside the current application

| Location | Purpose |
|---|---|
| `powernext/physics/` | Simulator/evaluator, **current** `CPRI_EQUIPMENT_PROFILE.json`, topology specification and source register |
| `powernext/ml/registry/simulation_v2/` | **Current** four trained model artifacts and cards |
| `powernext/ml/data/clarification_v2/` | Versioned design, 18,339 attempted-case records and manifest used for training/evaluation evidence |
| `powernext/ml/results/` | Model-selection and validation evidence |
| `powernext/optimizer/` | Complete catalog construction, charging, ranking, recipes and example result/curve assets |
| `powernext_app/`, `ui/` | Offline HTTP service and browser product |
| `runtime/` | Bundled isolated Windows Python, scientific libraries and Node test runner; no installation required |
| `data/` | Writable local history, measurements, discoveries, SQLite index and caches; survives restart and folder moves |
| `examples/` | Requests and waveform-import examples with explicit source labels |
| `tests/` | Application, integration, red-team, frontend and release tests |
| `docs/integration/` | Current compliance, IVG coverage, change, performance, release and run reports |
| `docs/archive/2026-10-04/` | Previous reports preserved under their original dates and claims |
| `evidence/sources/` | Byte-preserved primary source copies used by the existing source register; these paths intentionally remain stable |
| `evidence/integration/` | Current independent checks, benchmarks, preservation receipts and acceptance evidence |
| `competition-materials/` | Existing source copies retained for repository/release self-containment |
| `tools/` | Repeatable benchmark, example refresh, packaging and preservation utilities |

The source checkout additionally retains `archive/` (old tracked release and model mirror) and `training-data/` (complete synthetic waveform archive). These large historical/reproduction assets are not duplicated inside the portable application. The portable contains all data, models and dependencies required to run and test it. Full retraining waveforms remain recoverable from the source training archive and the archived complete October 4 release.

The older `physics_engine/dataset.py` is a historical dataset utility, not the current six-resistor training pipeline. Use `powernext_ml/design_v2.py` and the versioned ML pipeline for the current dataset; never reinterpret an old fixture as current inventory authority.

## Preservation rules

Do not edit primary sources or historical manifests. Do not overwrite a historical result to give it the current serving fingerprint. Do not delete archived packages merely because they look redundant: hard-linked packages and Git LFS objects can have multiple provenance roles. `evidence/integration/reorganization.json` records the exact moves. Runtime duplication was limited to the development runtime and the current deliverable; earlier self-contained releases were preserved for reproducibility.

The Git LFS rules cover both the current registry/data and moved historical model/release assets. No history rewrite, remote push, LFS prune or garbage collection was performed.
