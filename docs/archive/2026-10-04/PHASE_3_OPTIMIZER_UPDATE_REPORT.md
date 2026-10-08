# Phase 3 - Optimizer update

Phase gate: PASS for the declared provisional catalog. No hardware or operating approval is established. This report was created after both independent acceptance runs completed and before application changes.

## Changes and boundaries

The default single-component hypothesis enumerates 14 stage counts x 6 fronts x 6 tails = 504 candidates for each fixed mode/topology. Explicit LI/GSHUNT selection can add the named 180 || 520 ohm tail hypothesis (84 candidates), for 588 total. The parallel hypothesis is off by default; selecting only it yields 84. Approved-only scope contains zero approved recipes. No arbitrary resistance or connection synthesis occurs.

All resistor parts come from the six confirmed component values. Availability filters require both 180 and 520 for the parallel tail. Equivalent resistance 133.7142857 ohm is derived, never treated as a purchasable component. Bills of material count overlapping front and tail component values correctly; quantity availability, holders and pulse ratings remain unresolved.

Topology, DUT/load, inductance and tolerances remain fixed request conditions. Each candidate is evaluated using physics; no ML pruning occurs. Charging is solved against legal upper limits and the full crest band. The unknown practical minimum and resolution remain explicit. Cache fingerprints cover transitive forward serving code, physics, equipment profile, topology specification and selected model artifacts.

## Verification

89 optimizer tests passed (`evidence/phase3_optimizer_tests.log`). A separate oracle independently enumerated recipes, solved charge, assessed compliance and ranked the complete catalog for 16 requests. It did not import production catalog, charge or ranking helpers. Every catalog/order comparison passed. 6,720 saved waveform artifacts were hash-checked and re-evaluated; all 63 numerical passes were independently re-integrated with Radau and 7,000 output samples, agreeing within 1e-6 relative on crest and applicable times. Invalid input was rejected. The physics backend is shared with the oracle, so this is software independence, not independent laboratory evidence.

| Request | Catalog | Numerical passes | Best provisional configuration |
|---|---:|---:|---|
| LI_request | 504 | 0 | None |
| LI_parallel_request | 588 | 3 | N=9, 184.238331 kV/stage; front 30, tail [180, 520] ohm |
| SI_request | 504 | 14 | N=9, 164.366294 kV/stage; front 3700, tail [5000] ohm |
| SI_crest_change | 504 | 5 | N=11, 195.558658 kV/stage; front 3700, tail [3700] ohm |
| SI_load_change | 504 | 3 | N=8, 196.173535 kV/stage; front 3700, tail [3700] ohm |
| SI_ood | 504 | 0 | None |
| SI_infeasible | 504 | 0 | None |
| SI_output_shunt | 504 | 7 | N=15, 187.198850 kV/stage; front 3700, tail [3700] ohm |
| SI_tolerance_band | 504 | 2 | N=13, 194.130411 kV/stage; front 3700, tail [3700] ohm |
| SI_approved_only | 0 | 0 | None |
| LI_rare_timing_pass | 504 | 1 | N=7, 137.978317 kV/stage; front 30, tail [180] ohm |
| SI_current_setting | 504 | 3 | N=8, 196.173535 kV/stage; front 3700, tail [3700] ohm |
| SI_invalid_request | None | None | None |
| LI_inductance_change | 504 | 0 | None |
| SI_low_voltage | 504 | 19 | N=7, 8.102765 kV/stage; front 5000, tail [5000] ohm |
| LI_disagreement_request | 84 | 6 | N=10, 126.792567 kV/stage; front 30, tail [180, 520] ohm |

## Interpretation

At the unchanged illustrative 1.98 nF load, the 1,550 kV LI request has no pass under the default single-resistor hypothesis. It has three conditional passes under the explicitly selected parallel-tail hypothesis. Its best candidate uses nine stages, 30 ohm fronts and one 180 ohm plus one 520 ohm tail component per stage. This is not proof of the briefing's physical setup: its complete load and erected connections remain unknown.

The expanded SI component space changes the 1.8 MV and larger-load recommendations to 3,700 ohm tail components. OOD and infeasible cases retain no-solution outcomes. The low-voltage SI example is numerically feasible but does not establish reliable firing at low stage charge. A heldout synthetic crest-boundary case preserves a meaningful ML false acceptance (about 0.747% gain overprediction); physics remains authoritative and rejects that candidate. Other candidates in its full declared catalog can still pass.

Evidence: `evidence/phase3_acceptance/summary.json`, `evidence/phase3_supplemental/summary.json`, current request/result pairs with hashed waveform assets, and `ML_boundary_disagreement.json`. Earlier examples are preserved outside the runtime under `evidence/historical_optimizer_examples`; their old catalog and model outputs are historical.

Unresolved: CPRI fired schematic, approved wiring recipes, module counts/placements, pulse ratings, low-charge reliability, charge increments, basic-capacitance coverage and actual measured validation. All operational gates remain closed.
