# Current exhaustive optimizer

The default development catalog is 14 stage counts x 6 actual front values x 6 actual tail values = 504 configurations per mode and topology. Explicitly enabling HYP_LI_TAIL_180_PAR_520_v1 in LI/GSHUNT adds 84, giving 588. No approved CPRI recipe is known; approved scope therefore has an empty catalog. Component availability must include BOTH 180 and 520 for the parallel hypothesis. Derived 133.714 ohm is not an inventory value.

Every declared candidate receives physics evaluation. Linear amplitude scaling determines the exact-target charge when possible, or a legal charge inside the tolerance band; stage voltage, total voltage and energy bounds are enforced. Feasibility uses each unchanged crest/time limit, then deterministic lexicographic ranking starts with conformity score J. No ML screen removes a candidate. Low-charge results are numerical only because the reliable minimum firing voltage and charge increment are unknown.

examples contains current requests, full candidate records and reproducible NPZ curves. LI_request is the honest single-resistor failure; LI_parallel_request is the explicit conditional 1550 kV success; LI_disagreement_request deliberately exercises an actual ML crest false acceptance. That target is a regression stress case, not a reported CPRI experiment. The same fixed illustrative load is used for the principal before/after comparison.

Sixteen requests were independently checked against the full catalog/charge/compliance/ranking oracle, all 6,720 saved curves replayed, and 63 positive configurations independently re-simulated using Radau. See the root phase 3 report and final regression report for limits and final package acceptance.
