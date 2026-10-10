# Network workspace demonstration

Launch the offline application and open **Network optimizer** from the existing
workbench. The original recommendation, discovery, and waveform-review screens
remain available. The new workspace uses a separate versioned result store.

## Current evidence state

The current checkout has 506 integrated checks recorded in
evidence/phase_b/integrated_regression_summary.json. The corrected R2 data-stage
receipt records 122,000 attempts, 99,852 eligible rows and 92,662 canonical
eligible response shapes. Four candidates per route were trained, and the frozen
serving set contains 8 selected models from 32 candidates.

The selected-model application audit passed all eight fixed routes. It checked
loaded model and card identity, separate ML and detailed Physics output, ML
support/OOD status and later-reference immutability. Before the active-scope
change, it also completed a historical four-module asynchronous search.
The fresh 16-request scientific oracle replay had zero configuration or
scientific-field mismatches and zero numeric differences outside tolerance.
Receipts are in evidence/phase_b/production_application_audit.json and
evidence/phase_b/oracle_scientific_comparison.json.

The current active UI and public application scope supports maximum branch bounds
of 2 or 3 modules, defaulting to 3; both bounds include single-part recipes.
Four-module search and fixed-recipe requests are rejected with an explicit
UNSUPPORTED_CURRENT_SCOPE reason before a job or prediction artifact is saved.
Historical four-module network, Physics and model artifacts remain retained for
archival replay.

The four-policy benchmark and extracted-package acceptance are still pending.
The current checkout therefore does not establish moved-folder or package-manifest
acceptance. Keep those gates separate from this application demonstration.

## Launch from the checkout

From the repository root, create a fresh local result directory and launch the
bundled runtime:

    New-Item -ItemType Directory -Force "$env:TEMP\PowerNext-v3-demo" | Out-Null
    .\runtime\python.exe -B -m powernext_app --port 18767 --data-dir "$env:TEMP\PowerNext-v3-demo" --no-browser

Open http://127.0.0.1:18767/ and select **Network optimizer**. The serving
mapping is powernext/ml/results/networks_v3/selected_models.json and the checked
cards and models are under powernext/ml/registry/networks_v3. Keep the selected
domain, impulse mode, topology, polarity and stage range visible in the request.

## Choose the evidence domain first

Use **CPRI 0.5 uF** for the supplied generator parameter set. **Research 3 uF**
is a hypothetical simulation profile for comparison with the supplied workbook;
its energy limits are research assumptions. Neither selection establishes
mounting approval, pulse-stress qualification, or real-machine calibration.

The equipment voltage class and impulse crest are different quantities. Enter
the requested crest explicitly. Do not turn the 400 kV equipment class into an
assumed 400 kV impulse test. The allowed request range does not guarantee that
every crest/setup combination is achievable.

## Requested test to generator settings

1. Select domain, LI or SI, and the declared tail connection.
2. Enter the fixed DUT, divider, stray capacitance and connection parameters.
   State whether the 480 pF basic load is already covered by the other values.
3. Choose the bounded recipe size and search budget. Every active stage uses
   the same selected front recipe and the same selected tail recipe.
4. Start the search and watch candidate scoring and detailed verification.
5. Inspect the exact recipes, per-stage equivalents, total component demand,
   legal charge and individual waveform conformity of each passing result.

ML estimates order candidates. A recommendation requires detailed Physics
verification. Large catalogs normally have partial coverage; the best verified
candidate is not a proof of the global optimum. Small catalogs use complete
verification even when the adaptive mode was requested.

Unknown inventory and ratings remain unknown. Supplying known quantities lets the
optimizer reject insufficient bills of materials, but quantities alone do not
establish pulse ratings or a permissible mounting arrangement. Failed
alternatives are diagnostic results marked **NOT RECOMMENDED**.

## Fixed settings to a frozen prediction

Enter the actual stage count, per-stage charge, front/tail trees and electrical
setup before revealing the reference answer. Save the prediction. Its record
contains the original inputs, domain, predictor identity, support status,
separate detailed Physics metrics and an integrity hash.

For the audited small fixed smoke case, use front R180, tail R30, two active
stages and 50,000 V per stage. A loaded route should show the ML prediction and
support status separately from the detailed Physics metrics and saved Physics
waveform. This is a reproducibility fixture for the evidence flow, not a
hardware recommendation.

If ML is unavailable or the input is outside its supported contract, the
workspace discloses the fallback or support limitation. Do not describe a
fallback response as a successful ML prediction.

## Reveal a reference afterward

Attach the later reference crest and LI T1/SI Tp and tail values, or import a
supported raw waveform with the correct units and timebase. Reference comparison
does not retrain the predictor or revise the frozen prediction. Inspect signed,
absolute, reference-relative and tolerance-normalized errors separately.

Establish what the reference represents: a measured shot, the workbook's
simplified equations, its synthetic observed columns, or another circuit
simulation. These are different comparison targets. The independent workbook
report documents why a correct 3-uF transient prediction can differ markedly
from its formula-based reference. A single agreement is not universal hardware
validation; a disagreement must retain its inputs and evidence for diagnosis.

The competition SI convention remains physical time-to-peak 250/2500 us.
Recorded-waveform processing retains its existing declared limitations and
does not imply IEC measurement-software qualification.

## Recovery and reproducibility

Keep the accepted `PowerNext_Track1_Offline` release as the rollback package.
After the lead finalizes the extracted package, run its manifest verifier and
selected-model acceptance script from a moved extraction. The package gate is
pending while this guide is being handed off. Preserve local `data/` records when
moving the app.
Do not change training artifacts, profile values or reference answers during a
scored unseen-case prediction. No laboratory control or high-voltage actuation
is connected to this application.
