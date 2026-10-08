# Phase 1 — physics gate passed

The October 4 source is integrated as `CPRI_IVG_OCT04_2026_v2`; simulator version is 0.2.0. All six confirmed resistor values can be used as actual front or tail components. Connection recipes remain provisional. The passive graph kernel, shared waveform definitions, load inputs, charge/energy constraints and competition tolerances are preserved.

`DEV_UNIFORM_SINGLE_v2` considers one front and one tail component per stage. `HYP_LI_TAIL_180_PAR_520_v1` explicitly stamps separate 180 Ω and 520 Ω tail branches, only for LI/GSHUNT and only when selected. Its equivalent 133.714285714 Ω per stage is a derived value, never an inventory part. Required quantities are shown by component, including overlap between front and tail values. Ideal sharing stress proxies do not establish hardware ratings.

## Fixed-load result

The illustrative setup is unchanged: DUT 850 pF, divider 500 pF, stray 150 pF, additional-disjoint basic 480 pF (total 1.98 nF), loop 18.5 µH. This is not a measured definition of the briefing's equipment.

| Target / topology / recipe | Exhaustively evaluated | Numerical passes |
|---|---:|---:|
| 1550 kV LI / GSHUNT / single component | 504 | 0 |
| 1550 kV LI / OSHUNT / single component | 504 | 0 |
| 1550 kV LI / GSHUNT / explicit parallel hypothesis | 84 | 3 |
| 1300 kV SI / GSHUNT / single component | 504 | 14 |
| 1300 kV SI / OSHUNT / single component | 504 | 7 |

The conditional LI passes use 8, 9 or 10 stages with 30 Ω front components and both tail components. At 9 stages and about 184.2383 kV/stage, crest is 1550 kV, T1 is 1.296891 µs and T2 is 50.908673 µs. The same setup with a single 180 Ω tail gives about 67.65 µs; 520 Ω alone gives about 190.16 µs. The explicit 180+520 series diagnostic gives about 254.89 µs at nine stages. Thus **confirmation of 520 enables a defensible hypothesis with a conditional LI pass; availability alone does not prove that the real generator uses it or that LI is experimentally solved**.

Unsupported waveforms remain in the sweep (27 GSHUNT and 21 OSHUNT single-component cases per mode; four parallel cases). They are not converted into passes or discarded from evidence. Full rows are in `evidence/phase1_catalog_probe.json`.

## Independent validation

47 physics tests passed (`evidence/phase1_tests_final.log`): retained 34 tests with the obsolete 520 rejection replaced by an unlisted 521 rejection, plus 13 current tests. These cover both explicit resistor branches, all six values, quantity accounting, forbidden equivalent-component inputs, recipe domain restrictions, full-stage equivalence at 2/9/15 stages, independent dimensional LSODA, matrix exponential, Radau, charge/polarity/refinement invariance, energy balance and target-curve consistency. The full-stage fixture proves the stated uniform circuit reduction, not CPRI topology identity.

The expanded sweep exposed a zero-current root-bracket roundoff issue. Scalar bracket rechecking fixes the exception without changing the waveform or tolerances; a dedicated regression passes. The unchanged evaluator still rejects unsupported traces.

For expanded enumeration, a guarded modal solution of the same linear ODE was added. It rejects an ill-conditioned eigensystem and falls back to Radau. In an eight-run local benchmark at 1600 samples, median complete simulation was 12.28 ms modal versus 600.80 ms Radau. This is solver acceleration, **not an ML benefit**. Timings are local and workload dependent.

The nominal mathematical target is solved against the same LI virtual-origin / SI time-to-peak definitions and then re-evaluated. It is ready for the later app phase and is labelled a mathematical reference, not a hardware prediction.

## Remaining limits and downstream decision

No CPRI connection recipe, fired topology, quantities, ratings, auxiliary states, minimum reliable charge or measured waveform response has been confirmed. The operational gate stays closed. The physics profile and recipe definitions are now stable enough to generate a new versioned simulation dataset and train new model routes. Existing simulations retain their original meaning; old models must not serve the new profile. Legacy synthetic workbook data remain unchanged and separate.
