# Complete IVG parameter coverage

Primary source: `Parameter values ivg.docx`, the complete 20-row table and SI note; reconciled with `questions.txt` response §§1–7 and the 4 October `clarifications.txt` reply. All source bytes preserved. Profile: `powernext/physics/CPRI_EQUIPMENT_PROFILE.json`, `CPRI_IVG_OCT04_2026_v2`.

P = Physics equations/validation; O = catalog/optimizer constraints; M = ML inputs, features or targets. “No fired connection” means the magnitude is confirmed while its role in the erected circuit is not. No extra resistor has been placed on a guessed node.

| Sheet row / parameter | Engineering purpose | Profile representation | P / O / M | Interface / documentation | Connection established? / assessment |
|---|---|---|---|---|---|
| 1 ΣU = 3000 kV | Rated total charging ceiling, not DUT crest | summed-stage-charge maximum | P validates N·U; O cap; M amplitude scaling | Settings/constraints | Rating confirmed; correct |
| 2 W = 150 kJ | Total stored-energy ceiling | total rated energy | P energy; O cap; M physical-output bound | Constraints/BOM | Confirmed; correct |
| 3 S = 15 | Physical stage count | stages maximum | P validates; O enumerates2..15; M stage feature | Configuration/profile | Confirmed; actual stage-node topology provisional |
| 4 U = 200 kV | Per-stage charging rating | stage charge maximum | P validates; O cap; M output scale | Charge/stage display | Confirmed; reliable minimum and increments absent |
| 5 Ws = 10 kJ | Per-stage energy at rating | stage rated energy | P/O E=CsU²/2; M energy bound through derived storage | Constraints | Consistent with0.5µF and200kV; correct |
| 6 Cs = 0.5 µF | Energy storage / wave shape | stage impulse capacitance | P Cg=Cs/N; O charge feasibility; M Cg, capacitance ratio and RC features | Profile / derived values | Value confirmed; uniform erected equivalent is a declared assumption |
| 7 LI 1.2/50 µs IEC60-1 | Required waveform | LI waveform profile | P evaluator; O limits/rank; M T1/T2 labels | Targets/plots | CPRI target confirmed; qualification separate |
| 8 Rs1 = 30 Ω | Available front component | six-value physical inventory | P Rf/Rt recipe; O enumerates; M resistor/reduced-R features | Components/BOM | Value confirmed; placement not confirmed |
| 9 Rs2 = 46 Ω | Available front component | same | P/O/M as above | Components/BOM | Correct, provisional placement |
| 10 Rs3 = 3700 Ω | Available front component | same | P/O/M as above | Components/BOM | Correct, provisional placement |
| 11 Rs4 = 5000 Ω | Available front component | same | P/O/M as above | Components/BOM | Correct; also supplied as SI tail value |
| 12 Rp1 = 180 Ω LI tail | Available tail component | six-value inventory / LI tail candidates | P/O/M via recipe | Components/BOM | Correct; sheet alone does not establish a 180||520 branch |
| 13 Rp2 = 5 kΩ SI tail | Available tail component | six-value inventory / SI tail candidates | P/O/M via recipe | Components/BOM | Same5000Ω value, not two invented inventory values |
| 14 RL = 135 kΩ per stage | Charging path; may influence recharge or fired waveform if connected | auxiliary charging-per-stage value | P omitted from fired circuit; O no invented recharge constraint; M no unjustified feature | Equipment coverage, technical detail | Magnitude confirmed; switching state/nodes unknown. Correct conditional omission, unresolved physical completeness |
| 15 Rpot = 2 MΩ | Potential/divider/balancing/leakage role requires schematic | auxiliary potential value | P omitted; O/M no invented connection | Equipment coverage | Node pair, count and fired state unconfirmed; cannot assume output loading |
| 16 Rerd1 = 5.45 kΩ | Discharge/earthing path | auxiliary discharge values | P omitted; O/M none without connection | Equipment coverage | Switch state/nodes absent; cannot infer safe discharge time |
| 17 Rerd2 = 13 kΩ | Alternate/additional discharge path | auxiliary discharge values | Same | Equipment coverage | Not silently merged with5.45kΩ or assigned arbitrary placement |
| 18 k = 2/min | Nominal repetition/duty reference | pulse-sequence value | No effect on isolated single-shot linear equations; no learned input; not a search variable | 30s average-interval planning reference | Does not establish safe recovery, thermal duty or automatic firing schedule |
| 19 Cbo = 480 pF | Basic capacitive load seen by impulse circuit | basic-load capacitance with unresolved coverage | P explicit add/include; O feasibility through Physics; M basic/total C feature | Main setup control and profile | Value confirmed; contribution boundary unknown. Required explicit coverage avoids double count |
| 20 Sphere diameter25cm | Gap geometry relevant to switching/breakdown | sphere diameter | P ideal switch only; O no fabricated firing law; M none | Equipment coverage | Diameter insufficient: spacing, configuration, atmosphere and trigger absent |
| Sheet SI note250/2500 | Required switching waveform | legacy SI Tp/T2 profile | P/O/M consistent | Targetstrip/discovery/report | Retain CPRI convention; do not substitute2025 front descriptor |
| Later CPRI520Ω | Sixth real available resistor | present in both mode inventories and ML actual-profile data | P recipes; O all singles plus optional explicit parallel; M features/support | Inventory/BOM | Confirmed physical value; not a “virtual” harmonic resistor. All six available values reconciled |

## Integration disposition

No confirmed value was missing from the current profile. The genuine product omission was that auxiliary values and their unresolved connection states were not readily visible. The Equipment & technical details view now lists their engineering treatment alongside the existing complete profile. Main workflows retain the 480 pF coverage choice, actual component BOM and explicit connection hypotheses.

A 135kΩ×0.5µF product is **not** promoted into a machine recharge-time or repetition constraint: the charging supply, ladder structure and switches are unknown. Likewise 2MΩ is not assigned as a DUT shunt, and discharge resistors are not attached during firing without evidence. These omissions can materially affect actual-machine accuracy if those branches remain connected; the application says so, keeps hardware approval false, and offers a specific annotated-schematic request as informative next evidence. This is the maximum defensible integration with the supplied facts.

The complete parameter trace to tests, source precedence, current IEC edition difference and unqualified waveform handling is in `IEC_AND_PS_COMPLIANCE_VERIFICATION.md`. The original sheet is not overwritten or “corrected” to include520Ω; the later clarification is preserved separately as its authority.
