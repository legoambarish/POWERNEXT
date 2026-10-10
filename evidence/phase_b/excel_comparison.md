# Phase B Excel comparison

This report is an independent model comparison against the preserved workbook
`evidence/sources/Hybrid_Physics_ML_Impulse_Generator_Optimiser.xlsx`.  The
source SHA-256 is
`e855eadbe4d6da2579316e89e025e6990f9ba3c522a5af96d1dd2a5522d77480`, and the
post-run hash is unchanged.

The formula pass found 7,029 formula cells, of which all 7,026 cached numeric
formula cells were reproduced exactly within the numeric tolerance.  This
includes the calculator heuristics (1.67 front, 0.693 tail, and 0.82
efficiency input) and the ML Helper calculations.  Formula reproduction is
kept separate from the model comparison and does not fit corrections to the
workbook values.

An independent all-row static check then rebuilt the historical 3-uF equations
from every one of the 2,000 `Synthetic Dataset` inputs.  The front equation is
`1.67 sqrt((Front_R_Stage * Stages * CL)^2 + 2.5 L CL)`, the tail equation is
`0.693 Tail_R_Stage * Stages * (3 uF / Stages + CL)`, crest is `Test_kV`, and
stage charge is `Test_kV / (Stages * Efficiency)`.  All 2,000 rows passed each
check and all stored residuals equal observed minus their corresponding
theoretical value.  Both relative and absolute tolerances were `1e-12`; the
maximum absolute errors were `2.22e-16 us` for front timing and `4.55e-13 us`
for tail timing, with zero error for crest, charge, and all three residual
identities.  This verifies the static workbook construction without using its
observed values to fit any correction.

The comparison sampled 12 original synthetic inputs stratified by impulse,
workbook split, and stage band, then evaluated each input under both
`GSHUNT_v0` and `OSHUNT_v0` using the research 3-uF detailed RLC model.  Each
row in `excel_comparison.json` contains separate workbook theoretical values,
synthetic observed values, detailed RLC values, and explicit deltas for
`front_us`, `tail_us`, and `crest_kV` against each reference.

Six of 24 detailed simulations were retained as unsupported because they
exceeded the physics reference time scope (`TIME_DOMAIN_OUTSIDE_REFERENCE_SCOPE`);
all six are SI/OSHUNT cases.  No unexpected exception was classified as a
physics result.

| Route | Simulated | Unsupported | Observed delta MAE: front / tail / crest |
| --- | ---: | ---: | --- |
| LI / GSHUNT | 6 | 0 | 0.547 us / 3.690 us / 226.116 kV |
| LI / OSHUNT | 6 | 0 | 0.487 us / 91.616 us / 788.231 kV |
| SI / GSHUNT | 6 | 0 | 243.790 us / 618.713 us / 39.131 kV |
| SI / OSHUNT | 0 | 6 | n/a / n/a / n/a |

The observed columns are synthetic workbook observations, retained as a
separate diagnostic reference.  They are not used to train, enrich, or select
any Phase B generated row.  The detailed comparison is model-to-model evidence
and does not establish laboratory or hardware validation.

## Interpretation of differences

Exact agreement is required for the independent spreadsheet implementation:
its front heuristic is `1.67 sqrt((Rf CL)^2 + 2.5 L CL)`, its tail heuristic is
`0.693 Rt (Cg + CL)`, and its theoretical crest is the requested workbook
crest. These equations and their declared units are reproduced independently;
the formula-cell checks include the separate historical kNN calculations.

The transient simulator instead solves the declared coupled circuit, obtains
crest from its response, and extracts LI virtual T1 or SI physical time-to-peak
and tail crossings. In particular, the worksheet front heuristic is not an
identity for either circuit's SI time-to-peak. Its fixed 0.82 efficiency is an
assumption used to set charge, whereas the transient circuit's efficiency
depends on the capacitors, resistors, inductance, and tail connection. Moving
the tail resistor from the generator side to the load side changes the circuit
equations; it is not a harmless renaming. These differences explain why exact
spreadsheet formula agreement and substantial transient disagreement can
coexist without proving a coding defect.

The replay uses the workbook's visible capacitance sum, with no additional
480 pF added, and its supplied per-stage charge and resistor equivalents.
Arbitrary workbook equivalents are admitted only for this reference-model
comparison; they are not treated as available physical resistor parts by the
configuration optimizer. The 3-uF profile's energy limits are explicitly
hypothetical research limits, not the confirmed 0.5-uF generator ratings.

The six unsupported SI/output-shunt cases provide no numerical error estimate.
Their absence must not be converted into zero error, a pass, or proof that
either model is correct. The remaining sample is a diagnostic cross-comparison,
not a statistically representative accuracy estimate for the entire workbook.
Independent held-out 3-uF ML-to-transient results are reported separately in
the model-selection evidence when training completes.
