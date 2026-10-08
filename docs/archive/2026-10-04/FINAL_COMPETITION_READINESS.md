# Final competition readiness

**READY WITH CONDITIONS for an offline numerical software demonstration. Hardware operation and real-generator accuracy remain unvalidated.**

The updated clarification is integrated from profile through explicit circuit recipes, independent physics checks, regenerated data, retrained models, exhaustive optimization, app workflows and current demonstrations. All 383 suite checks passed. Sixteen independent optimizer requests, 6,720 waveform replays and 63 Radau positive rechecks passed. The clean moved candidate reproduced all 12 demos, exports, screening, synthetic import gating and history persistence with outbound application connections blocked. See FINAL_REGRESSION_REPORT.md for exact scope, counts and limits.

| Area | Decision | Evidence or condition |
|---|---|---|
| Clarification and discrete inventory | Ready | All six confirmed component values; original source hashes preserved. |
| Numerical physics | Ready within declared assumptions | Frozen source/profile; independent graph and solver checks; unchanged waveform tolerances. |
| 1550 kV LI | Conditional | No single-resistor pass at fixed illustrative load; three passes under the explicit off-by-default parallel-tail hypothesis. |
| SI optimization | Ready within declared assumptions | Expanded catalog; same-request passes increase from 6 to 14; crest/load changes can select 3700 Ω tails. |
| ML requirement | Ready with bounded evidence | Four retrained routes, grouped holdouts, real scenario grid; 3.26x warm batch gain over current physics, no universal advantage. |
| Exhaustive catalog / ranking | Ready | 504 default / 588 explicit LI candidates; no ML pruning; independent oracle agreement. |
| Application and offline portability | Ready on tested Windows x64 environment | Current models/demos, target comparison, source labels, history/export, clean moved acceptance. |
| Hardware allocation and reliable firing | Unresolved | Need schematic, quantities, slots, pulse ratings, minimum reliable charge and increments. No operational approval. |
| Real CPRI accuracy and calibration | Unvalidated | No genuine traces; synthetic emulation metrics cannot establish it. |
| Presentation laptop | Dry run still needed | The actual device was not available. Bundled runtime and moved path were tested on this host. |

## Recommended demonstration order

Start with SI and show a stable numerical recommendation, its requested load, actual part values, waveform limits and complete search. Then show the failed single-resistor 1550 kV LI case beside the conditional parallel-tail case with unchanged load. Explain the new CPRI inventory fact separately from the wiring hypothesis. Show the actual ML crest false acceptance and how physics rejects it. Finish with the real model-only scenario grid, mathematical nominal target, synthetic import diagnostics, provenance/history and offline exports.

## What could prevent a winning submission

1. CPRI's actual fired circuit or allowed placements may invalidate the optional LI hypothesis or require nonuniform recipes outside this catalog.
2. Real waveform errors may be materially larger than grouped simulator-emulation errors; no empirical calibration is available.
3. Unknown minimum firing voltage, component quantities and pulse ratings prevent an operator-ready recommendation even when numerical limits pass.
4. Judges may require a larger ML contribution. Its demonstrated value is bounded scenario exploration; analytical formulas remain superior in some SI metrics and speed.
5. Noise/overshoot qualification and instrument uncertainty are not implemented to a certified metrology standard. The competition-versus-latest-IEC SI definition must be explained accurately.
6. An untested presentation laptop, archive extraction problem or rushed claim could weaken an otherwise reproducible demonstration.

The highest-value next evidence is CPRI's actual connection/operating definition followed by authenticated, instrumented repeat shots and independent heldout setups. More synthetic examples cannot establish those missing physical facts. No action on hardware, outbound message, submission or publication was performed in this cycle.

The delivered ZIP has a single root, bundled runtime and root launcher. Its immutable-file manifest and sibling FINAL_ZIP_ACCEPTANCE.json identify the delivery bytes and final extraction check. The prior release, sources and historical negative evidence remain preserved in the integration audit folder.
