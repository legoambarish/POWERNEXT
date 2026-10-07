# Judge questions and evidence-led answers

## Five hardest remaining questions

**1. Did CPRI actually confirm your parallel tail, and can technicians install the recommendation?**

No complete recipe was confirmed. CPRI confirmed the six components, including both 180 and 520 Ω. Our bounded LI/GSHUNT hypothesis explicitly connects separate 180 and 520 Ω branches per stage, reports the BOM, requires both component values, and is disabled by default. We have proved the stated uniform circuit reduction numerically, not the identity of CPRI's fired circuit. The software correctly reports no approved setting until wiring, quantities, slots, pulse ratings and operation are confirmed. Evidence: profile, topology specification, phase 1 full-stage tests, and the app's separate status axes.

**2. Does the 1550 kV success demonstrate the actual 400 kV equipment test?**

It demonstrates a conditional numerical result for a clearly stated illustrative 1.98 nF load and 18.5 µH loop. That same load is retained in the failed single-resistor case and successful optional hypothesis; it was not optimized to manufacture a pass. The best conditional result is N=9, 184.238331 kV/stage, 30 Ω fronts, 180 || 520 Ω tails, 1550 kV crest, T1=1.296891 µs and T2=50.908673 µs. The briefing does not identify enough of the physical test setup to equate this with a measured 400 kV equipment test. Show both LI scenarios and their unchanged input fields.

**3. Why use ML if a physics model and analytical formulas already work?**

ML is a trained finite-inductance surrogate for bulk scenario exploration, with separate scalar estimates alongside reference physics. In the warm measured 128-case experiment, the real model/OOD/integrity/serialization path took 0.446 s versus 1.455 s for the current modal simulator (3.26×). LI/GSHUNT grouped front MAE improved from the analytical baseline's 0.06215 µs to 0.00834 µs. The analytical approximation remains much faster and has slightly lower SI tail errors. We retain that negative comparison. Final recommendations are exhaustive physics; the grid is unverified ML exploration. Cold-load performance and waveform-quality limits prevent a universal acceleration claim.

**4. How accurate is this on the real generator?**

Unknown until real data are acquired. Our accuracy figures measure emulation of the declared simulator on grouped synthetic holdouts. The supplied workbook is also synthetic. Model provenance, OOD rejection, independent numerical solvers, repeatability and source separation make the software defensible, but cannot substitute for laboratory calibration. The importer preserves raw bytes, labels synthetic/bench/claimed CPRI evidence, calculates explicitly unqualified clean-trace timing diagnostics, and compares the declared actual settings without fitting. It does not self-qualify uploaded labels or train a model.

**5. How can you promise practical optimization when firing limits and resistor ratings are unknown?**

We do not promise operational feasibility. We exhaustively optimize a declared catalog of actual-valued components subject to known stage, voltage and energy bounds, while keeping unknown quantities/rating/firing gates closed. Approved-only search returns an empty catalog. The 50 kV SI example exposes a mathematically valid approximately 8.103 kV/stage result with the unknown minimum visible. The next engineering step is CPRI's connection/operating confirmation and instrumented validation, not an invented minimum voltage or hidden hardware approval flag.

## Additional questions

**What did the clarification change beyond adding one number?**

Both resistor roles now enumerate all six confirmed component values under a documented single-component hypothesis, growing 56 configurations to 504 per topology and mode. The optional LI hypothesis adds 84. The profile and label-generating physics were versioned, data regenerated, all model formulations retrained, model selection repeated, optimizer results and 12 scenarios rebuilt, and downstream schema/UI/evidence updated. The same-request SI inventory counterfactual increases six numerical passes to fourteen. LI single-resistor failure is preserved.

**Why not search every series/parallel combination?**

That would generate electrically possible networks without evidence of quantities, holders or ratings. We instead use a bounded uniform catalog and one explicit hypothesis motivated by the stated LI tail parts and physical branch construction. A 180+520 series tail was retained as a negative diagnostic, not silently selected. The real assembly may require a future recipe once CPRI provides the schematic.

**Is 133.714 Ω a fabricated available resistor?**

No. It is 180×520/(180+520), the equivalent of two distinct actual parts under a stated hypothesis. The graph stamps both branches, and the BOM lists the physical parts. A request that presents 133.714 Ω as an available component is rejected.

**Can an attractive ML output override a failed waveform?**

No. The deliberately marginal heldout LI regression exposes a 0.747% gain overprediction: ML crest approximately 1157.498 kV passes, while physics crest approximately 1148.913 kV falls below the required lower bound of approximately 1152.464 kV. The candidate remains failed. Other candidates can pass the same request; this is not a claim that the whole request is infeasible.

**Are your reported tests independent?**

The optimizer oracle independently constructs the complete candidate catalog, legal charge interval, compliance and rank order. Sixteen requests, 6,720 stored waveform replays and 63 independent Radau positive rechecks passed in phase 3. The oracle still uses our physics backend, so it is numerical software validation. Other physics checks use full-stage graphs, dimensional LSODA, matrix exponential and analytic RC relations. The final regression report separately records the all-module suite and fresh offline HTTP acceptance; counts are not mixed with laboratory evidence.

**What prevents leakage or stale models?**

Physical-shape/setup grouping keeps amplitude, polarity and equivalent capacitance partitions together. Validation chooses the model before heldout test prediction. Unsupported labels remain null. Model cards and inference verify the profile, simulator, evaluator, topology and model bytes; the optimizer fingerprints transitive forward code. Historical incompatible artifacts remain historical, and current startup verifies all four routes. The imported measurement source is never promoted by an uploaded boolean.

**Are the target curves decorative, and do you implement the newest IEC SI?**

The mathematical targets solve rates against the same waveform evaluator, including LI virtual origin, and are checked before display. They are not hardware outputs. SI intentionally follows the competition's Tp 250/2500 definition and declared bands. We explicitly qualify its distinction from the revised IEC 60060-1:2025 standard SI definition; we claim neither full standard implementation nor certification.

**Can the package run on the presentation machine?**

It carries isolated Windows x64 Python, scientific libraries, models and local UI assets and needs one launcher. The final regression report states the exact clean/moved offline checks and remaining machine-specific limits. The actual presentation laptop was not available, so a dry run on it is still required. No external Python, network model or API key is part of the application workflow.
