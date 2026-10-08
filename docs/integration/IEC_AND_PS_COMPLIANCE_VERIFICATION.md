# IEC and original problem-statement verification

Verification date: 8 October 2026. Product profile: `CPRI_COMPETITION_LI_1p2_50_SI_Tp250_T2_2500_v1`.

## Decision and scope

The application retains CPRI's explicitly requested LI 1.2/50 µs and SI **Tp** 250/2500 µs convention. The current clean-waveform equations, time origins, target generator and tolerance arithmetic are internally consistent. This integration did not change those equations, labels, trained models or their Physics provenance. Independent analytic and matrix-equation checks were added; final execution evidence is in `INTEGRATION_AND_REGRESSION_REPORT.md` and `evidence/test_logs`.

This is a verified implementation of its **declared competition profile and ideal equivalent circuits**, not IEC software qualification, a qualified measuring system, an approved fired CPRI circuit, or laboratory certification. Full licensed IEC normative texts and the IEC 61083-2 Test Data Generator/reference test suite were not available locally. Those external qualification gates remain open. Imported measured traces therefore never receive a qualified laboratory pass or training authority.

## Primary sources reviewed

All four pages of `HV IG Problem Statement.pdf` were extracted and visually inspected, including the page 4 HAEFELY illustration. All 20 parameter rows and the note in `Parameter values ivg.docx`, the complete written CPRI replies in `questions.txt` (1 October, response sections 1–14) and `clarifications.txt` (4 October), and the supplied briefing transcript were reviewed. The workbook's six sheets, formulas and 2,000 synthetic records are a separate historical baseline. The local seven-page PRD and 70-page 7 October independent architecture audit are secondary interpretations, not primary equipment authority.

Originals and their hashes are preserved in `competition-materials`, `evidence/sources`, `SOURCE_REGISTER.json` and the workspace source-preservation manifest. The sheet supersedes the illustrative nameplate's 12 stages, 0.125 µF, 545 pF and resistor list. The latest CPRI reply supersedes any earlier interpretation that 520 Ω was unavailable. Neither reply confirms the fired circuit or parallel connection recipe.

Standards evidence accessed on 8 October:

* [IEC 60060-1:2010, edition 3](https://webstore.iec.ch/en/publication/300): historical standard matching the competition's SI designation.
* [IEC 60060-1:2025, edition 4](https://webstore.iec.ch/en/publication/65088) and the [IEC publisher's redline preview, foreword](https://assets.vde-verlag.de/iec-normen/preview-pdf/info_iec60060-1%7Bed4.0.RLV%7Den.pdf): replaces 2010; introduces SI front-time 170/2500. The LI positive-front tolerance extension is conditional on **Um > 800 kV**, not the entered impulse crest. It is not silently applied to CPRI's explicit LI ±30% band.
* [IEC 60060-2:2025, edition 4](https://webstore.iec.ch/en/publication/65089), replacing [2010 edition 3](https://webstore.iec.ch/en/publication/301): complete measuring systems, uncertainty and approval require evidence beyond this waveform solver. The official description confirms the SI descriptor change and revised LI front-time measurement uncertainty.
* [IEC 61083-2:2013, edition 2](https://webstore.iec.ch/en/publication/4471): impulse-evaluation software testing requires reference waveforms/values and uncertainty assessment. Merely implementing crossings does not establish conformity.
* [PTB-hosted CIGRE 2022 paper, section 2, PDF pages 3–4](https://oar.ptb.de/files/download/EMPIR.19NRM07.CA.20230119.pdf): primary metrology publication corroborates legacy LI crest ±3%, front ±30%, tail ±20%; SI time-to-peak ±20%, tail ±60%, crest ±3%. This supports the selected interpretation; it does not turn those SI/crest numbers into a written CPRI confirmation.
* [ITU-T K.96 (2014), Appendix I.3.1, printed pages 13–15, figure I.2](https://www.itu.int/rec/dologin_pub.asp?id=T-REC-K.96-201402-I!!PDF-E&lang=e&type=items): authoritative reproduction of the 30/90% voltage front construction, virtual origin and half-value interval, referring to IEC 60060-1. This corroborates the clean LI mathematics, not the full IEC overshoot evaluation procedure.

Only the accessible descriptions/previews and cited technical material were used. No inaccessible clause text, permissible overshoot thresholds, uncertainty budgets or reference-test results have been invented. Normative clause numbers are deliberately not guessed.

## Exact selected definitions

Let signed DUT voltage be `v(t)`, declared baseline `b`, and declared polarity `p ∈ {-1,+1}`. Evaluate the magnitude curve `u(t)=p(v(t)-b)`. The positive crest is the maximum of this curve; the plotted voltage retains its actual sign. A requested crest is an **output DUT crest**, not `N × stage charge`.

| Quantity | Selected definition | Target / inclusive interval | Authority |
|---|---|---|---|
| LI crest | Clean-curve peak magnitude | Request × [0.97, 1.03] | Legacy IEC interpretation; CPRI numeric tolerance not explicit |
| LI T1 | `(t90↑ − t30↑)/0.6` | 1.2 µs / [0.84, 1.56] µs | PS p1–2; CPRI §5 explicitly ±30%; independent construction above |
| LI virtual origin O1 | `t30↑ − 0.3 T1` | Derived, may precede physical start | 30/90 line extrapolation |
| LI T2 | `t50↓ − O1` | 50 µs / [40, 60] µs | CPRI §5 explicitly ±20% |
| LI physical peak time | `t_peak` diagnostic; not T1 | No substitution into front check | Distinct variable in evaluator/plots |
| SI crest | Clean-curve peak magnitude | Request × [0.97, 1.03] | Legacy IEC interpretation |
| SI Tp | `t_peak − declared impulse beginning` | 250 µs / [200, 300] µs | PS p1–2 and CPRI §5 target; legacy tolerance interpretation |
| SI T2 | `t50↓ − declared impulse beginning` | 2500 µs / [1000, 4000] µs | Legacy competition convention |
| SI additional front descriptor | No LI T1 relabelled as SI Tp | Not used in ranking/training | CPRI/2025 distinction retained |

All limits are inclusive without an artificial epsilon that broadens acceptance. Floating-point values just outside an interval fail. Charging is selected against the entire allowed crest band, including legal boundary charge; waveform duration must contain the descending 50% crossing.

The 2025 SI **front-time** 170/2500 designation is a different profile, not a new name for Tp 250 µs. A second selectable 2025 profile was not added because the complete normative procedure, test cases and competition request for it are absent. The existing models were trained for legacy Tp. Mixing a 2025 label into those outputs would be incorrect. Obtain CPRI's explicit edition/descriptor confirmation before adding and separately validating such a profile.

## Physics, extraction, charging and ML trace

`physics_engine/engine.py::build` assembles a declared linear RLC equivalent: `Cg=0.5 µF/N`, `U0=p N Ustage`; front resistance `N Rfront + Rloop`; tail `N Rtail` (or the explicit LI parallel recipe); terminal capacitance from DUT, divider, stray and the declared treatment of 480 pF. `network.py` stamps capacitances, conductances and RL branches, eliminates algebraic nodes and solves the state equations. Modal integration is checked; the numerical alternative is Radau. Stored energy is `N Cs Ustage²/2`; resistor dissipation and residual stored energy are checked. This does not model erection, spark breakdown, saturation, temperature or unknown auxiliary branches.

`engine.py::simulate` adds stationary points and threshold events to the sampled curve; the evaluator uses shape-preserving PCHIP bracketed roots, does not identify LI front time with time-to-peak, and gates invalid/noisy/oscillatory/flat/truncated or ambiguous records. Its numerical prominence thresholds are conservative implementation gates, **not IEC overshoot allowances**. Every measured source is explicitly unqualified; a separate clean-trace assumption produces useful diagnostics only. No automatic filtering, test-voltage-factor processing, deconvolution or optimized time shift is claimed.

`target.py::nominal_target` solves double-exponential parameters using these exact time definitions, then re-evaluates the resulting waveform. It is a mathematical reference, not a simulation of available hardware or a measured trace.

`powernext_optimizer/charge.py` derives charge from the linear crest-per-stage-charge gain, capped by 200 kV/stage, 3 MV summed charge, 10 kJ/stage and 150 kJ total. Unknown reliable firing minimum and charge increment stay unknown. The selected actual charge is re-simulated. `service.py` enumerates every declared candidate; `assessment.py` uses Physics validity and conformity before tolerance-normalized score. ML never prunes or overrides ranking.

The four preserved model cards target gain, LI T1 or SI Tp, and T2. Features include actual stage capacitance, resistor recipe, capacitance partitions, loop L/R and an independent RC baseline. Amplitude scaling uses `N × Ustage × predicted gain`. Profile, simulator, evaluator and label provenance remain unchanged, so retraining was neither required nor performed. New discovery uses the existing batch predictor and retains explicit scenarios, OOD abstention, fixed configuration/charge and separate Physics checks.

## PS-to-implementation traceability matrix

Paths below are relative to the current application root. `tests/integration/test_engineering.py` contains the new independent checks; existing Physics, ML, optimizer, application and red-team tests remain in the comprehensive runner.

| Original requirement / exact PS locator | CPRI clarification / IEC evidence | Implementation | Status | Evidence / correction / unresolved dependency |
|---|---|---|---|---|
| p1 objective: predict generator settings and waveform, reduce trial work | §10–14 software focus | optimizer `catalog`, `service`; application `service`; UI `views` | Implemented numerically | Full catalog and new-request browser/HTTP acceptance; physical usefulness awaits measured validation |
| p1 waveform bullet: LI 1.2/50 | §5 confirms bands; legacy 60060-1 construction | Physics `evaluator.evaluate`, `target.nominal_target` | Implemented | Independent analytic roots, nominal target and boundary tests |
| p1 waveform bullet: SI 250/2500 | §5 confirms requested target; 2025 front definition differs | evaluator `Tp_s`, `T2_s`; ML adapter/training; UI | Implemented declared profile; edition externally unverified | Retains legacy Tp; does not call it 2025 170 µs front time |
| p1 optimize Rfront, Rtail, N and charging | Oct4 six physical values; no arbitrary resistances | optimizer `catalog.entries_for_request`, `charge` | Implemented within declared catalog | 504 singles; optional 84 parallel cases. Catalog completeness, not all possible hardware arrangements |
| p1 minimize mismatch / rank feasible settings | No authorized electrical-input retuning | `assessment.rank_key`, `parameter_score` | Implemented | Whole-catalog before/after rank comparison; unchanged J and tier policy |
| p1 account for physical limitations | §1–4 actual sheet supersedes illustration | `charge.hardware_checks`; Physics validation | Partial physical approval | Declared charge/energy enforced; missing pulse ratings, quantities, slots and firing limits remain explicit |
| p2 inputs: LI/SI and desired test voltage | §2 output crest, not charge sum | `catalog.normalize_request`, UI `readForm` | Implemented | Separate target crest, stage charge and summed-charge output |
| p2 DUT/load capacitance | §7 explicitly relevant | `Setup`, `build`, ML `features` | Implemented | Fixed request setup copied unchanged through complete search |
| p2 divider capacitance | §7; 60060-2 measuring system relevant | `Setup.divider_capacitance_F`; importer scaling/IDs | Implemented as circuit input; metrology external | Divider transfer function, calibration uncertainty and bandwidth not fabricated |
| p2 stray C | §7 | `Setup.stray_capacitance_F`; ML features | Implemented | Explicit units and coverage; scenarios keep primary request unchanged |
| p2 available front/tail resistances | Oct4 confirms 30/46/180/520/3700/5000 Ω | `recipes.py`; catalog availability filtering; UI inventory | Implemented | Empty inventory produces no candidates; corrected UI explanation |
| p2 output: N / charging voltage | §1–2 | selected configuration and charge solution | Implemented | BOM/settings visible; charge never labelled output crest |
| p2 output: front/tail values and arrangements | Oct4 values, no wiring approval | `recipes.resolve_recipe`; UI BOM | Implemented provisional | Single per-stage and opt-in LI parallel connection explicitly distinguished from approved hardware |
| p2 output: waveform, front/peak/tail/crest | Legacy LI/SI definitions above | evaluator, stored NPZ, waveform UI, report | Implemented | Actual saved arrays; no decorative ML curve; correct µs/ms and signed V/kV |
| p2 ML performance / comparison dashboard | Workbook synthetic only; no qualified CPRI waveforms | `models`, `registry`, `inference`, `screening`; discovery UI | Implemented | Four routes, model support, actual scalar differences, held-out evidence; no lab-accuracy claim |
| p3 account for connection/stray inductance | §7; briefing lead/return effects | `network` RL branches; `Setup.loop_inductance_H` | Implemented lumped representation | Independent matrix and solver checks; distributed leads and erection remain outside model |
| p3 variation with setup/physical arrangement | Fixed known values; not search knobs | discovery saved scenarios and selected Physics checks | Implemented numerical exploration | Fixed-setting invariants tested; no scenario fraction treated as laboratory probability |
| p3 generator charging voltage limits | Actual sheet §1 | `charge_policy`, legal interval | Implemented | 200 kV/stage / 3 MV total; no assumed firing minimum |
| p3 energy limits | Sheet150kJ/10kJ/Cs | `hardware_checks`, energy residual | Implemented | E=½CV² independently coherent; no fabricated pulse-resistor ratings |
| p3 stage capacitance | Sheet0.5µF; §1 actual source | `engine.build`, ML Cg features | Implemented | Historical 3µF workbook is not current model training authority |
| p3 charging resistor | Sheet135kΩ/stage | profile; equipment coverage; omitted fired branch | Provisional connectivity | Cannot attach arbitrary nodes; request fired-state circuit |
| p3 potential resistor | Sheet2MΩ | profile; equipment coverage | Provisional connectivity | Unknown divider/balancing/leakage placement; not silently treated as output shunt |
| p3 discharge resistors | Sheet5.45/13kΩ | profile; equipment coverage | Provisional connectivity | Switch/earth state absent; no safety discharge time inferred |
| p3 external resistors where applicable | §4 actual components/discrete selection | measured actual setting retained; optional declared loop R/leakage | Partially implemented | No unrestricted external-resistor optimizer catalog without inventory/connection evidence |
| p3 basic load capacitance | Sheet480pF; §7 coverage unanswered | `Setup.total_capacitance_F`, UI choice, ML feature | Implemented assumption | Additional/disjoint vs already included; no double counting forced |
| p3 sphere dimensions/configuration | Sheet25cm diameter | profile and equipment view | Externally unverified configuration | Diameter known; spacing, arrangement, pressure/temperature/humidity absent |
| p4 ~50–2400kV output range | §2 output crest, §1 actual limits | request normalization and charge/hardware checks | Implemented subject to feasibility | No-solution and upper-charge tolerance-band cases retained |
| p4 minimum two stages | §1 sheetmax15 | catalog2..15 and Physics validation | Implemented | Complete count and bounds tests |
| p4 illustrative nameplate equipment table | §1/actual sheet supersede 12-stage example | versioned actual profile | Implemented source precedence | PS illustration retained byte-for-byte, not silently edited |
| p4 future measured-data calibration/validation when supplied | §8–14 data conditional; user excludes F4/F10 | measured archive, diagnostics, comparison; no fitting | Partial by explicit scope | Qualified real data absent; no empty/fake calibration layer |
| PS waveform conformity generally | IEC60060-1/61083-2 qualified test-curve evaluation | conservative evaluator and unqualified import path | Partial / externally unverified | Full clean impulses only; overshoot/oscillation/chopping/noise conservatively abstain; TDG absent |
| Polarity relevant to waveform evaluation (PS waveform output, p2; no separate PS tolerance) | Declared engineering input | `p(v-b)`, signed plots, metadata diagnostics | Implemented | Positive/negative analytic tests; fixed inconsistent negative overlay; no assumed polarity-specific standard relaxations |
| Measuring-system quality (supporting p2 divider/input) | IEC60060-2:2010/2025 | metadata units, divider factor, instrument IDs, calibration reference | Partially implemented | No approved measuring-system status without calibration/uncertainty evidence |
| Software evaluation qualification (supporting PS conformity) | IEC61083-2:2013 | independent numerical tests; raw measured gate | Externally unverified | No official TDG/reference qualification or expanded uncertainty claim |

## Discrepancies and implemented corrections

1. **SI edition ambiguity:** explicitly documented throughout technical details; no mixture of legacy Tp and 2025 front labels. The actual mathematics did not need changing.
2. **Measurement export gap:** prior ZIP omitted imported records. Complete bundles now include raw bytes, source metadata, normalized waveform, diagnostics, comparison, application integrity index and a bundle manifest. Reopen checks all references before writing.
3. **Negative polarity overlay:** an omitted configuration polarity formerly defaulted to positive despite negative measurement metadata. Prediction now uses the declared measurement polarity when configuration polarity is omitted; contradictory declarations withhold the overlay and produce a quality flag. Raw metadata remains unchanged.
4. **No-solution explanation:** empty component/recipe selections no longer imply missing approved recipes in every case. A crest-only failure is no longer described as a timing failure.
5. **Change-count display:** charging adjustment is separated from changed hardware fields, matching the optimizer tie-break.
6. **Low-voltage units:** waveform axes and imported-trace metrics choose V for small signals instead of rounding 5 V traces to integer kV labels.
7. **Serving integrity overhead:** request-scoped immutable artifact bytes replace repeated reads; complete hashes are checked before and after calculation. Same-size/same-mtime changes are tested. Physics/model identities remain intact.
8. **Source-byte reproducibility:** Git attributes preserve the exact hashed Physics/profile/spec/serving bytes; original supplied sources retain existing byte-preserving attributes.
9. **Historical utility:** `physics_engine/dataset.py` is an obsolete phase-0 dataset generator, not the current `powernext_ml/design_v2.py` pipeline. Its historical 520 Ω rejection fixture is obsolete after the October 4 clarification. It is retained unchanged for old provenance/replay and is not presented as the current inventory or training command. The current inventory and all four models include the clarified six-value catalog. Editing that historical file would unnecessarily invalidate the existing simulator-wide model hashes.

## Independent verification and remaining external dependencies

New tests independently solve analytical double exponentials with scalar roots, check virtual origins under time shifts and baselines, both polarities, nominal targets, immediately-outside tolerance values, and compare Physics output against a separately stamped two-node capacitor matrix exponential for both topologies. Existing tests cover finite L, energy conservation, numerical references, shape abstention, charge limits, complete catalogs, ML support and measured-data gates. Whole-catalog ranking snapshots are compared before/after serving changes. None of these are substituted for IEC reference qualification.

Unresolved: fired-state topology/auxiliaries, physical recipes and module quantities/pulse ratings, 480 pF coverage, reliable charging minimum/resolution, sphere gap/trigger parameters, actual duty/thermal limits, calibrated divider/digitizer uncertainty, genuine CPRI validation records, exact competition standard edition and explicit numerical confirmation of crest/SI tolerance interpretation. These are documented external uncertainties, not internally testable defects concealed by a pass label.

Release gate: run the comprehensive test runner, independent integration tests, current-model compatibility validation, full-catalog benchmark comparison and moved/extracted offline acceptance. Their final results are recorded in the integration report. The declared competition profile may pass these software gates while all external IEC/hardware-qualification flags remain false.

## Release gate outcome

Established, internally testable competition-profile requirements pass the independent analytical and regression checks. Combined final coverage is 405 checks, with actual moved-folder Windows application acceptance, full SI/LI/no-solution searches, fixed-charge discovery verification and byte-preserving evidence round trips. See the integration report and adjacent distribution acceptance receipt for the actual extraction and launcher results. External IEC software-reference qualification and unresolved CPRI connectivity remain explicitly external; the application does not label them resolved.
