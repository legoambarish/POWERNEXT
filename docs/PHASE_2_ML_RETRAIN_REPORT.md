# Phase 2 — data and ML gate passed

Classification: DERIVED ENGINEERING RESULT from PROVISIONAL MODEL ASSUMPTION and synthetic simulation. Measured CPRI traces: **zero**. Neither training accuracy nor test accuracy is laboratory accuracy.

## Data disposition

The old waveform records remain valid for their original circuits, but their inventory coverage and profile identity are insufficient for current serving. They are preserved, as are the supplied workbook and separate legacy reproduction. They were not relabelled. A fresh design was required for the six-value front/tail catalog, explicit parallel-tail recipe, near-boundary LI/SI coverage and grouped evaluation.

Dataset `sim_1f2992ccb93c5d9d` contains 18,339 attempts: 18,332 simulations, seven invalid inputs, 18,028 clean eligible labels and 304 unsupported waveform records. All 311 ineligible rows retain null regression labels and reason codes. There are 17 full numerical passes for the randomly assigned requested crests. Shape compliance is assessed separately because amplitude is subsequently solved by the optimizer.

The design uses eight Latin-hypercube samples per discrete configuration, predeclared LI/SI neighborhoods, matched single-tail controls, analytic input boundary probes, amplitude/polarity equivalences and explicit invalid/truncated records. No output is repaired or forced to pass. Files include original request, waveform, metadata, checksums and provenance. Dataset row SHA-256: `14fdf1b748d73b8e7154a501cb6f3f125c12206811de0f6eef3c3dabdd60bf71`.

LI shape positives increased from one in the old design to **167**: one single-tail GSHUNT case and 166 explicit parallel-tail cases. LI/OSHUNT retains zero positives; that coverage limitation is not hidden. SI has 424 shape positives across the two topologies. These counts reflect an expanded, deliberately stratified synthetic design and are not estimates of laboratory success probability.

## Model comparison and validation

All nine combinations of direct / physics-guided / residual formulation and kNN / Extra Trees / histogram gradient boosting were retrained per impulse/topology route. Validation selection was persisted before test prediction. Four residual Extra Trees models won the predefined validation criterion. There are 74 model/protocol result records, including analytic baselines and shifted-domain evaluations.

Train/validation/test groups union normalized physical shape and setup family. Charge, polarity, target crest, and equivalent partitions of terminal capacitance cannot leak a waveform family across splits. Learned transforms use training rows only. An explicit parallel feature prevents aliasing a two-branch recipe with a single 180 Ω component. OOD checks include ranges, nearest-neighbor support, stages, front/tail values and parallel-recipe coverage. Unseen parallel cases are rejected when that recipe is withheld from training.

| Grouped test route | Test rows | ML front MAE (µs) | Analytic L=0 front MAE (µs) | ML tail MAE (µs) | Shape false accept / false reject |
|---|---:|---:|---:|---:|---:|
| LI/GSHUNT | 1020 | 0.00834 | 0.06215 | 0.18213 | 1 / 0; 31 true passes, 989 true fails |
| LI/OSHUNT | 697 | 0.00927 | 0.03333 | 0.18210 | 0 / 0; no true passes, so false-rejection rate unavailable |
| SI/GSHUNT | 769 | 0.02088 | 0.04369 | 0.15441 | 1 / 1; 50 true passes, 719 true fails |
| SI/OSHUNT | 742 | 0.01473 | 0.03796 | 0.10259 | 0 / 0; 32 true passes, 710 true fails |

The analytic baseline made five false shape acceptances and six false rejections in LI/GSHUNT. In SI/GSHUNT it made neither, while ML made one of each. The three ML shape disagreements above occur at deliberately exact front-time boundaries: LI at 1.56 µs and SI at 200/300 µs, with differences of approximately 1e-12 to 7e-8 µs. Strict counts are retained without widening tolerances; their numerical scale must not be mistaken for a large timing error. SI tail error is also slightly worse with ML. Thus a lower aggregate error is **not** a guarantee of safer pass/fail decisions; ML cannot replace the evaluator. Crest/full-compliance confusion, evaluation-only crest-boundary probes, empirical validation P95 errors, grouped bootstrap intervals and shifted-domain results are retained in the model cards and results. Those empirical envelopes are not calibrated confidence intervals.

## Operational ML role and measured value

The selected role is **batch scenario exploration** for explicit what-if configurations/setups. The API performs no physics simulation, returns scalar estimates only inside learned support, labels every result `ML_SCREEN_ONLY`, and requires physics verification. It never changes the final request, chooses a physical topology, prunes the optimizer, or issues an operator-ready recommendation. This will be exposed in the application phase.

The first implementation deserialized models for every batch: 128 scenarios took 1.410 s, versus 1.419 s for current modal physics. That offered essentially no acceleration and is preserved as negative evidence. Reusing models keyed by verified content hashes, with hash rechecking on each call, reduced the warm 128-scenario API benchmark to **0.446 s versus 1.455 s for current modal physics (3.26×)**. Cold loading still costs about 1.4 s. The analytic L=0 feature/baseline batch took 0.029 s and remains much faster; ML's justification is improved finite-inductance emulation, particularly LI, rather than claiming to be the fastest possible computation. The old Radau solver was about 124× slower per scenario than the warm batch in this mixed sample; that is a secondary comparison, not the headline gain.

Timing includes model integrity checks, feature construction, OOD assessment, prediction and JSON serialization. Physics timing includes simulation and metadata serialization but omits waveform serialization. These are local warm-process measurements, not universal guarantees. Loaded models are cached by actual file hashes, never just filenames or timestamps; tampering invalidates the cached lookup.

A separate 576-case screen included 512 randomly sampled holdout rows and 64 unsupported waveforms: 566 estimates and ten abstentions. It contained no full crest-and-shape positives, so full false-rejection performance cannot be inferred from it. Of the 64 unsupported waveforms, 61 still received scalar estimates; none was predicted within all bands. This directly demonstrates why a surrogate estimate cannot certify waveform quality and why final physics stays mandatory.

## Tests and gate

**30 ML tests passed** in `evidence/phase2_tests_cached.log`. They cover feature leakage, equivalent-shape grouping, all split disjointness, null failure labels, model round trips and exact metric reproduction, provenance/route rejection, OOD and missing-model fallback, source-domain separation, measured-data qualification gates, six-value/parallel coverage, batch calls with the simulator disabled, and mutation detection for cached model bytes.

Current results are in `evidence/phase2_results_cached.json`; the first unsuccessful acceleration measurement remains `evidence/phase2_results.json`. Physics hashes are frozen in `evidence/phase1_frozen.json`. Models and the selected-model manifest use the new profile, simulator and recipe provenance. Serving cache changes do not change labels, features or learned weights; training-code hashes retain the actual training-time source, while serving identity is tracked independently.

Phase 3 may now update the optimizer. Hardware topology, component quantities/ratings, actual waveform calibration and minimum reliable stage charge remain unresolved. No measured calibration has been fitted.
