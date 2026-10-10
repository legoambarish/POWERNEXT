# PowerNext — offline impulse engineering workbench

Current implementation: **3.0.0+networks20261010**. The Network optimizer uses
route-specific ML to prioritize bounded resistor-network configurations, then
verifies recommendations with the detailed RLC Physics engine. The original
recommendation, rapid-discovery and waveform-evidence workspaces remain available.

Double-click **Launch_PowerNext.cmd**, open **http://127.0.0.1:8765/**, and choose
**Network optimizer**. The packaged application uses its local Python, Node,
scientific dependencies and model artifacts. Stop with **Stop_PowerNext.cmd**
or Ctrl+C in the launcher console.

```powershell
.\Launch_PowerNext.cmd
.\runtime\python.exe -B tests\verify_networks_release.py
.\runtime\python.exe -B tests\run_all.py
.\Stop_PowerNext.cmd
```

The release verifier checks immutable assets and selected models, blocks outbound
network use during its execution checks, and exercises frozen predictions and
small complete catalogs. Run it from the new extracted release. The development
checkout's in-progress acceptance ledger is [Phase B acceptance](docs/PHASE_B_ACCEPTANCE.md);
an implementation or a fallback smoke test alone is not release acceptance.

## Engineering workflows

- **Network optimizer:** choose CPRI 0.5 uF or the separate research 3 uF profile,
  LI or SI, explicit requested impulse crest, and a fixed electrical setup.
  Select up-to-two or up-to-three modules per front/tail branch from
  30, 46, 180, 520, 3700 and 5000 ohms. All active stages use the same recipes.
  Results show exact composition, component demand, charge, individual conformity,
  ML predictions, detailed Physics and search coverage.
- **Fixed settings and unseen reference:** save a prediction before importing
  later scalar reference values or a supported raw waveform. Original inputs,
  model identity and prediction remain frozen. Comparisons do not retrain models.
- **Original workspaces:** retain the prior small-catalog recommendations, rapid
  scenario discovery, waveform review, history and evidence export. Their
  historical models and source contracts remain separate from v3.

The supported three-module catalog has 412 physical recipes and 407 exact
resistance groups per branch: 2,319,086 electrical configurations across stages
2–15. Two-module mode has 48 recipes/groups and 32,256 configurations over the
same stages. Each mode includes simpler networks.
The controller indexes and streams this space. Small catalogs use complete
Physics verification; bounded large searches report partial coverage and the
best verified candidate found. They do not establish a global optimum or prove
that an unexplored catalog has no solution. Failed diagnostics are marked
**NOT RECOMMENDED** and never substituted for a passing recommendation.

Eight ML routes keep capacitance domain, impulse type and topology separate.
Each compares Physics-guided and residual formulations using ExtraTrees and
HistGradientBoosting. The serving selection is
`powernext/ml/results/networks_v3/selected_models.json`; versioned cards and
binaries are in `powernext/ml/registry/networks_v3/`. Detailed Physics remains the
final authority for simulated conformity. Missing/incompatible models and
unsupported ML inputs produce explicit fallback/support status.

The supported scope was revised to two/three modules after the initial dataset
and model training completed. Existing models were trained on electrical shapes
from one through four modules; those immutable artifacts are preserved and this
provenance is disclosed. Four-module application work and further data generation
or training are stopped. See the [scope revision](docs/PHASE_B_SCOPE_REVISION.md)
and [model evaluation](docs/PHASE_B_MODEL_REPORT.md). No dedicated two/three-only
retraining is implied by restricting the application's search scope.

## Evidence and limits

The confirmed parameter profile is 0.5 uF per stage, 200 kV/stage and 15 stages,
with 10 kJ/stage and 150 kJ total rated stored energy. The 3 uF profile is a
hypothetical research comparison environment with separately derived energy
limits. It is not a second confirmed CPRI machine. The supplied Excel is an
independent synthetic reference, not measured laboratory truth.

LI uses virtual T1 1.2/50 us; SI uses the competition's physical time-to-peak
250/2500 us convention. Equipment voltage class is distinct from requested
impulse crest. An allowed 50–2400 kV input does not guarantee an achievable
waveform. DUT and setup parameters remain fixed during each search.

Numerical conformity is conditional on the declared ideal linear circuit.
Tail connectivity, auxiliary branches, mounting, actual resistor quantities,
pulse ratings, parasitics and charge adjustment limits need external
confirmation. The 480 pF inclusion boundary is explicit. No real-machine
calibration, laboratory approval, formal IEC measurement-software qualification
or high-voltage actuation is claimed. The supplied two-pulses/minute value is a
planning reference, not a thermal or timing controller.

Use the [demonstration guide](docs/PHASE_B_DEMONSTRATION_GUIDE.md),
[data contract](docs/phase_b_data.md), [ML contract](docs/phase_b_ml.md),
[network representation](docs/phase_b_networks.md), and
[application workflow](docs/phase_b_application.md).
The [Excel comparison](evidence/phase_b/excel_comparison.md) separates equation
reproduction from detailed-transient discrepancies. Earlier source and standards
assessments remain in [integration documentation](docs/integration/IEC_AND_PS_COMPLIANCE_VERIFICATION.md).

The original accepted `../release/PowerNext_Track1_Offline/` package and ZIP are
preserved as rollback artifacts. The new release uses a separate name and
manifest. Training corpora, rejected attempts, pilots, validation oracles and
unselected models are reproducibility artifacts; the portable package excludes
new corpora and includes all eight selected routes. Large JSONL and model files
use the repository's Git LFS rules. No remote push is part of this work.

`data/` holds writable local evidence. Stop the server before moving the whole
application folder, and retain that directory to preserve saved runs. Never
overwrite original source documents, historical results or frozen predictions.
