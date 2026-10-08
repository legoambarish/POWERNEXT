# Integration release — 8 October 2026

Application `1.0.0+integration20261008`; interface `1.0.0`; equipment profile `CPRI_IVG_OCT04_2026_v2` retained. No GitHub operations, model retraining, numerical tolerance changes, or physical recipe approval.

| Capability | Before this integration | Current behavior |
|---|---|---|
| Exhaustive recommendation | Working Physics-authoritative catalog, charging, ranking, alternatives | Retained in full; faster execution; clearer conformity and evidence presentation |
| Physical configuration / BOM | Component recipes and hypothesis flags existed | Accessible with recommendations, next adjustment, individual prediction, equipment coverage |
| Next legal adjustment | Hardware-change tie-break existed | New workflow compares an actual fixed current setting against the complete evaluated catalog; explains charge and hardware changes and metric tradeoffs; preserves no-solution outcomes |
| Normal ML prediction | Backend serving existed; buried in candidate details | New single-setting ML versus Physics view with numerical differences, support/abstention, model evidence and waveform |
| Rapid discovery / operating envelope | Batch-screening backend and limited candidate screen existed | New independent user-defined configuration/setup exploration, fixed-setting C/L grids, interactive map/table, selected and boundary Physics verification, saved explorations and JSON export |
| Fixed-setting sensitivity | No coherent fixed-charge workflow | Same stages, resistor recipe, charge and target across explicit perturbations; full Physics verification never retunes charge; scenario counts are not success probabilities |
| Measurement feedback | Raw import and local analysis existed | Complete run ZIP now includes raw waveform bytes, exact supplied metadata text, normalized arrays, configuration, quality diagnostics, comparisons and per-record integrity; reopen validates and preserves the evidence |
| Measurement quality / mismatch | Basic trace validity checks existed | Added unit/polarity conflict, origin/baseline, clipping/plateau, sparse front, missing tail, edge peak and abrupt-step diagnostics; no unsupported root-cause diagnosis |
| Informative next measurement | General uncertainty text | Contextual questions and comparisons tied to missing connectivity, load coverage and observed model mismatch; no automatic experiment execution |
| Historical reuse | Hash-based reuse and saved runs | Semantic request matching ignores cosmetic IDs while retaining electrical inputs, inventory, recipes and profile/stack differences; ZIP reopen and historical status made explicit |
| Waveform evaluation | Clean-waveform LI/SI evaluator and shape gates | Independent analytical/ODE/origin/polarity/boundary verification added; calculations preserved because testable definitions were consistent; standards-edition and qualification limits documented |
| Execution | Repeated multi-megabyte hashes and model reads inside candidate calls | Immutable request snapshots with strong boundary hashes and verified-byte consumption; no pruning; numerical/ranking equality verified |
| Decision interface | Existing design system and plots | Preserved design; three main engineering activities, professional labels, concise contextual status, keyboard controls, input handoffs, responsive forms and plot units |
| Low-voltage bench | No isolated product workflow | New ideal low-voltage RC calculation and raw CSV comparison/export, separate from the CPRI equipment/model routes; no hardware build claimed |
| F4 calibration / F10 measured residual correction | Unqualified import only | Deliberately not activated. Uploads do not train models or acquire numerical ranking authority |

## Compatibility

The simulator equations, evaluator, profile and training labels remain byte-identical to the October 4 authoritative implementation. The four ExtraTrees model files and cards are unchanged. The forward-serving fingerprint changes because integrity/serving implementation changes. Current saved examples were regenerated under the new fingerprint; every candidate configuration, assessment, score and rank was compared with its archived predecessor.

Historical results retain their original identity and remain reviewable. A different-stack result must not be silently presented as a new live evaluation. Old source/release snapshots, audits and original materials are archived, not deleted.

## Final presentation refinement

At the user’s request, repeated provisional/approval banners and component warnings were removed from configuration review, recommendations, comparison, history and discovery. Main results use “Model prediction” and “Declared circuit”. Numeric conformity, OOD, waveform-quality and input-error diagnostics remain actionable. Full provenance and operational-status fields remain in the equipment record, expert data and technical reports; no approval or calibration was fabricated.

Browser acceptance also corrected late-response navigation during evidence/scenario/live-search loading and preserved original metadata CRLF bytes until an explicit edit. Reopened records carry a distinct source label. The repeated browser export/reopen confirmed exact raw CSV and metadata bytes.
