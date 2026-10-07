# CPRI clarification impact report — 4 October 2026

Status: inspection complete; implementation authorized in this new folder only. Original sources, packages, archives and the previous final release remain preserved.

## Evidence and precedence

The recursive census found 43,462 files, including bundled dependencies and repeated releases. The content inspection excluded runtime/library internals from semantic review, deduplicated 7,836 distinct contents, parsed source/JSON records, checked 3,198 distinct NPZ waveform records, checked 18 SQLite databases read-only, and CRC-tested all six root release ZIPs. No structural error was found in those checks. Critical current code, tests, source documents, registries, demonstrations, and historical archive differences were then traced through the dependency chain. This is an inspection of the full tree, not a claim that every third-party library was audited.

The actual October 4 reply is in `clarifications.txt`; earlier correspondence is in `questions.txt`. The original problem PDF, parameter DOCX, PRD DOCX, briefing transcript and all six sheets of the supplied workbook were inspected. The workbook contains a 3 µF assumption, invented rounded resistor selections and 2,000 synthetic rows; it is historical input, not a measured CPRI calibration set. No separately identifiable supplied Track 1 ZIP or independent Claude audit file was found. The audit concerns in the new objective were checked against current implementation; an absent report is not represented as independently read. No genuine measured CPRI waveform export was found.

| Statement | Classification | Consequence |
|---|---|---|
| Available discrete resistors are 30, 46, 180, 520, 3700 and 5000 Ω; both 180 and 520 are real | CONFIRMED CPRI FACT | Remove the 520 prohibition; use all six component values in documented front/tail arrangements |
| Values may be used in appropriate front/tail arrangements; document the equivalent Marx circuit | CONFIRMED CPRI FACT | Component availability does not establish connectivity, quantity, sockets or ratings |
| 15 stages, 0.5 µF per stage, 200 kV maximum per stage, 150 kJ total rating | CONFIRMED CPRI FACT | Retain limits, charge and energy checks |
| Offline physics + trained ML + optimization, fixed requested load, target/predicted comparison | PROBLEM-STATEMENT REQUIREMENT | Retain integrated architecture; close presentation and ML-use gaps |
| Cg = Cs/N under equal ideal erection; equivalent parallel resistance from two explicit branches | DERIVED ENGINEERING RESULT | Verify against independently stamped full stage circuits and numerical solvers |
| Marx systems can have multiple front/tail resistor positions | EXTERNAL TECHNICAL EVIDENCE | Supports investigating a named hypothesis; does not identify CPRI hardware |
| Uniform single component per stage; optional 180 Ω and 520 Ω local parallel tail branches | PROVISIONAL MODEL ASSUMPTION | Version separately; parallel recipe is explicitly selected, never silently enabled |
| Actual erected schematic, permitted allocations, counts, minimum charge, pulse ratings, 480 pF coverage, auxiliary states | UNRESOLVED | Operator-ready gate remains closed |

Newest direct CPRI facts override older generated documents. The waveform evaluator and declared competition tolerances remain unchanged: LI 0.84–1.56 µs / 40–60 µs; SI Tp 200–300 µs / T2 1000–4000 µs; crest ±3%. SI and crest interpretations remain explicitly qualified. This is not unqualified certification to the latest IEC edition.

## Dependency impact and disposition

| Artifact | Retain | Change or regenerate |
|---|---|---|
| Primary sources and original ZIPs | All originals, hashes, negative findings | Add newest source to current provenance |
| Passive circuit graph, shared waveform evaluator, energy checks | Existing algorithms and independent tests | New profile and explicit component recipes; validated linear-system backend if needed for expanded catalog |
| Original single-tail 180 Ω LI simulations | Valid historical results under their original assumptions | Ineligible as evidence for new recipes; new profile identity must not relabel them |
| Legacy workbook and its trained reproduction | Historical synthetic domain | No new label generation from the workbook; do not treat it as current equipment data |
| Simulation dataset / four current model routes | Splitting, leakage guards, benchmark design | Expand component/recipe coverage; rebuild affected dataset and retrain with new provenance |
| Optimizer charge/ranking rules and fixed load | Exhaustive enumeration and physics authority | New catalog, inventory accounting, recipe selection, counts, independent oracle and demos |
| App transport, SQLite history, immutable result checks, UI design/race guard | Existing verified structure | Current metadata, assumptions, target curve, useful imported-trace diagnostics, ML screening, wording |
| Historical runs | Immutable old evidence | Never serve as current compatible results; current demos regenerated |
| Release manifests and acceptance reports | Previous versions as historical | New full regression, clean/moved/offline checks and final ZIP |

## Phase plan and decision criteria

1. Physics: six-value single-component recipe plus separately selected two-branch LI hypothesis. Prove reduced/full-stage equivalence under stated assumptions; compare modal, Radau, matrix exponential and analytic RC cases. Evaluate the 1550 kV illustrative case with exactly the existing 850/500/150 pF load contributions, additional 480 pF scenario and 18.5 µH. These are declared example assumptions, not a measured briefing setup.
2. ML: freeze physics before generation. Retain failed cases, grouped holdouts and OOD checks. Compare direct/guided/residual models to the analytic baseline. Choose and measure an honest operational role after results are known.
3. Optimizer: enumerate only named recipes, every declared candidate, fixed topology/setup; require both real components for a parallel recipe. No arbitrary network synthesis and no ML pruning of final search.
4. App: expose assumptions and component bill of materials, consistent target curve, separately labelled diagnostic imports, and any justified batch ML role. Preserve design.
5–6. Full regression and independent replay, then package only current runtime/model/demo assets with evidence and launch from a clean moved extraction.

Parallel tails are investigated because the two values were originally listed specifically together for LI tail shaping, both are now confirmed real, parallel branches are a physically meaningful passive connection, and real Marx designs use multiple resistor positions. This is a bounded engineering hypothesis, not an inference that CPRI approved it. Series connection of 180+520 increases the tail resistance and is retained as a diagnostic comparison, not a new optimizer recipe. Other arbitrary combinations are outside scope. A numerical LI pass will remain conditional on hardware review and measured validation.

Primary external references: [University of Moratuwa impulse-generator circuit derivations](https://uom.lk/sites/default/files/elect/files/HV_Chap8.pdf), [HAEFELY SGVA system](https://www.pfiffner-group.com/products-solutions/details/sgva), and [manufacturer SGVA brochure](https://nissin-pulse.jp/product/doc/product-01-05-03.pdf). They support generic circuit engineering only.
