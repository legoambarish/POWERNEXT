# Current trained ML package

The application routes only to registry/simulation_v2 using results/simulation_v2/selected_models.json. Four residual Extra Trees models (LI/SI x GSHUNT/OSHUNT), 128 trees and leaf minimum 2, were selected on validation data after comparing direct, physics-guided and residual alternatives. Cards retain grouped train/validation/test identities, hashes, OOD support and empirical error bounds. The bounds are not calibrated confidence intervals.

data/clarification_v2 contains 18,339 predeclared attempted synthetic cases (seed 20261004; 8 samples per base stratum), 18,332 successful simulations and 18,028 eligible labels. Unsupported or invalid cases retain null regression targets. Grouping keeps equivalent physical shapes and amplitude/polarity variants together. These data emulate the declared simulator; no CPRI measured traces are present.

Final inference runs physics, reports both learned scalar estimates and reference metrics, and leaves compliance authoritative to the saved physics curve. The operational ML job is batch scenario screening through powernext_ml.screening.screen_batch and the application grid. It performs zero simulations and never prunes the exhaustive final catalog. Warm 128-case screening measured 3.26x faster than current modal physics; analytical L=0 estimates remain much faster and have lower SI tail error. No universal ML advantage is claimed.

evidence/legacy is explicitly historical workbook reproduction retained for regression only. It uses the supplied synthetic workbook's separate 3 microfarad domain. It is never an active model route or CPRI measured evidence. All old simulation v1 models/data and old example predictions were preserved outside this release. Current examples use the new profile and selected models.

Measured ingestion archives untouched bytes, explicit source labels and unqualified clean-trace diagnostics; no calibration or real-data training is enabled. Read the root reports for validation counts, speed controls, uncertainty and limitations.

To reproduce the current dataset in a NEW directory, use the release root command: `runtime\python.exe -m powernext_ml generate --output data_rebuild --samples-per-stratum 8 --seed 20261004 --workers 4 --n-points 1600`. Never overwrite the frozen dataset or model identity.
