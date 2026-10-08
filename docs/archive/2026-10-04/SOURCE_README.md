# POWERNEXT

PowerNext is an offline hybrid physics and machine-learning tool for exploring lightning-impulse (LI) and switching-impulse (SI) generator settings. This repository records the accepted Track 1 competition build dated 4 October 2026: application `0.4.0+cpri20261004`, equipment profile `CPRI_IVG_OCT04_2026_v2`.

The release is a numerical engineering demonstration. It does not approve a CPRI firing recipe, certify the generator, replace laboratory measurement, or authorize hardware operation.

## Release

The complete portable Windows release is [`release/PowerNext_Track1_Competition_v2.zip`](release/PowerNext_Track1_Competition_v2.zip). It contains the bundled Python 3.12 runtime, application, source, trained models, generated training data, waveform assets, tests, evidence and the 53,011-file release manifest.

| Item | Value |
| --- | --- |
| ZIP size | 1,721,822,565 bytes |
| SHA-256 | `2b19ea4882b732fc1654ace7de2a8f7175c9f230a6f72074e424c6f8aaa8b9dd` |
| Release status | `READY WITH CONDITIONS` |
| Regression result | 383 checks passed |

Clone with Git LFS so the release, dataset and model binaries are downloaded instead of pointer files:

```powershell
git lfs install
git clone https://github.com/legoambarish/POWERNEXT.git
cd POWERNEXT
```

Extract the release ZIP to a writable Windows x64 folder and run from the extracted folder:

```powershell
.\runtime\python.exe -m powernext_app
```

Then open `http://127.0.0.1:8765/`. No package download, account, API key or internet connection is required.

Verify the downloaded release before extraction:

```powershell
Get-FileHash .\release\PowerNext_Track1_Competition_v2.zip -Algorithm SHA256
Get-Content .\release\PowerNext_Track1_Competition_v2.zip.sha256
```

## Repository map

| Path | Contents |
| --- | --- |
| `powernext/physics/` | RLC simulator, evaluator, equipment profile, topology and recipe definitions, SPICE references and physics tests |
| `powernext/ml/` | Dataset generation, residual-model training, inference, selection evidence, registry and ML tests |
| `powernext/optimizer/` | Exhaustive candidate catalog, assessment, ranking, persistence and optimizer tests |
| `powernext_app/` | Loopback HTTP service and application integration |
| `ui/` | Browser interface served by the application |
| `models/` | Four selected ExtraTrees residual models, separated by LI/SI route and topology |
| `training-data/` | Complete `clarification_v2` training dataset archive and checksum |
| `competition-materials/` | Original problem statement, IVG workbook, parameter sheet, clarifications, briefing, questions, PRD and application previews |
| `tests/` | Integrated application, frontend, red-team and release checks |
| `docs/` | Phase reports, final regression report, claims, limits and judge Q&A |
| `evidence/` | Acceptance outputs, source copies, hashes and phase logs |
| `release/` | Exact portable release, acceptance record and SHA-256 file |

The browsable tree omits the bundled runtime and tens of thousands of repeated waveform files to keep normal Git operations workable. Nothing from the accepted build is lost: the exact release ZIP contains the full tree, and `training-data/clarification_v2_training_data.zip` contains every generated training record and waveform.

## Models

The current routes use four residual ExtraTrees models. Each folder contains the serialized estimator and its full model card.

| Route | Registry model | Validation score |
| --- | --- | ---: |
| `LI:GSHUNT_v0` | `model_3d7f2939e0983060b100` | 0.0135971 |
| `LI:OSHUNT_v0` | `model_772eb9870cdc64349cff` | 0.0219552 |
| `SI:GSHUNT_v0` | `model_954960c4e8fe1695fbfd` | 0.00684196 |
| `SI:OSHUNT_v0` | `model_920f8e81d2279b3b8b78` | 0.00666058 |

ML screens fixed configurations and can abstain outside its supported domain. It does not prune the exhaustive physics search, and a surrogate prediction cannot override a physics failure.

## Training data

`clarification_v2` was generated from the versioned physics stack after the October CPRI resistor clarification:

- 18,339 attempted cases
- 18,332 simulated cases
- 18,028 eligible labels
- 36,664 waveform files
- grouped setup splits retained in `powernext/ml/results/simulation_v2/split_assignments.csv`

The dataset is synthetic. The legacy workbook is retained as separately labelled regression evidence and is not used to train or route current recommendations. See [`training-data/README.md`](training-data/README.md) for the archive hash and layout.

## Physics and hardware boundaries

Confirmed inventory values are 30, 46, 180, 520, 3,700 and 5,000 ohms. Inventory does not establish the fired connection, quantity, slot, pulse rating or auxiliary branch state. `GSHUNT_v0` and `OSHUNT_v0` remain provisional topologies. `HYP_LI_TAIL_180_PAR_520_v1` is an explicit, off-by-default hypothesis; it is not a CPRI-approved connection.

The 1,550 kV LI example has no passing single-resistor setting in the enumerated catalog. Enabling the unapproved parallel-tail hypothesis produces three conditional numerical passes. These are software results under the stated model assumptions, not operating instructions.

No genuine CPRI waveform measurements were available for this release. Hardware topology approval, component ratings and quantities, minimum reliable charge, setup parasitics, metrology qualification and laboratory validation remain unresolved.

## Validation record

The accepted build passed 383 checks: Physics 47, ML 30, Optimizer 89, Application 61, Frontend 61, red-team 86, UI race 1 and final-release 8. Independent acceptance covered 6,720 waveform replays, 63 Radau positive rechecks, 12 demonstrations, 5,208 fresh waveform responses, exports, restart/history behavior, provenance gates and SQLite integrity.

The final evidence is in:

- `docs/FINAL_REGRESSION_REPORT.md`
- `docs/FINAL_COMPETITION_READINESS.md`
- `docs/FINAL_CLAIMS_AND_LIMITATIONS.md`
- `docs/UPDATED_JUDGE_QA.md`
- `release/FINAL_ZIP_ACCEPTANCE.json`

## Source checks

The portable release contains its own tested runtime. For development from the browsable source tree, install the pinned requirements into a separate Python 3.12 environment; do not commit that environment or generated application databases.

From a full extracted release:

```powershell
.\runtime\python.exe tests\run_all.py local_check
.\runtime\python.exe tests\verify_manifest.py
```

Use a new log label for each run. `tests/offline_acceptance.py` requires a fresh extraction because it intentionally creates application history and acceptance outputs.
