# Final resistor scope: exactly two modules per branch

Final user instruction dated 10 October 2026 supersedes the earlier maximum-two recommendation: **exactly two physical resistors per front network and exactly two per tail network**, each connected in series or parallel. Singles, three-part and four-part networks are excluded from final training and public optimization. Front and tail are jointly optimized, with one uniform front recipe and one uniform tail recipe across active stages.

There are 42 recipes per branch (21 series and 21 parallel), 1,764 front/tail pairs per stage and 24,696 response candidates across stages 2 through 15. Both domains retain separate models. Historical larger catalogs and data remain preserved. The independent comparison below addresses the earlier up-to-two versus up-to-three question and does not redefine the exact-two production boundary.

## Evidence and decision

The five fixed CPRI 0.5 uF cases have identical conditions between catalogs.
Each two-module baseline is the best supported, verified result from a complete
6,912-response search at stages 6/9/12. The three-module pool includes that exact
baseline plus 24 sampled candidates; its results are best-found, not proven
optimal. Numerical unsupported candidates prevent broader feasibility claims.

| Case | Crest kV, both | Two: front / tail us | Three: front / tail us | J two -> three | Crest/front/tail, both |
|---|---:|---:|---:|---:|---|
| LI GSHUNT 1.0 MV | 1000 | 1.2117 / 48.5052 | 1.2071 / 49.9039 | 0.023404 -> 0.000478 | PASS/PASS/PASS |
| LI GSHUNT 0.75 MV | 750 | 1.2070 / 49.8050 | unchanged | 0.000755 -> 0.000755 | PASS/PASS/PASS |
| LI OSHUNT 1.55 MV | 1550 | 1.2484 / 46.1905 | unchanged | 0.163198 -> 0.163198 | PASS/PASS/PASS |
| SI GSHUNT 1.3 MV | 1300 | 260.2321 / 2232.8243 | 257.5354 / 2226.8556 | 0.073604 -> 0.055872 | PASS/PASS/PASS |
| SI OSHUNT 0.75 MV | 750 | 244.4612 / 2934.2534 | 244.3042 / 2932.3111 | 0.096083 -> 0.096040 | PASS/PASS/PASS |

Lower J is better: the existing Physics conformity score sums squared crest,
front and tail deviations normalized by their tolerance half-widths. It is not
a full-trace distance or an equivalent-resistance matching score. Full-trace
and fixed-stage/fixed-charge post-selection replay errors are separately
reported in [the preliminary study](TWO_VS_THREE_PRELIMINARY.md).

Three modules improve LI 1.0 MV tail timing materially relative to the nominal
target. In SI 1.3 MV, front timing improves while tail timing becomes slightly
worse; the combined score improves. The last SI score change is negligible.
No failed two-module result becomes passing in these five cases. The actual
two-versus-three trace RMSE divided by requested crest is respectively
0.4292%, 0%, 0%, 0.0490%, and 0.0104%, on the declared common physical-time grid.
These trace differences are not percentages of conformity improvement.

The catalog grows from 48 to 407 distinct branch resistances, or from 6,912 to
496,947 responses at the same three stages (71.90 times). At all fourteen stage
counts it grows from 32,256 to 2,319,086 responses. Each three-module branch can
also require an additional physical component per active stage, subject to
unverified inventory and pulse ratings.

**Earlier engineering recommendation: maximum two.** It satisfies the highest-priority requirement in all
five cases with much smaller search and hardware-composition complexity. The
observed improvements do not establish enough additional compliance benefit
to justify making the larger catalog the final architecture. Confidence is
moderate for this engineering tradeoff and limited for unseen difficult cases.
This is not proof that a third module can never enable a pass. The user requested
an immediate bounded decision; the completed bounded comparison remains an independent side task. No exhaustive extension is required for final training.

The final evidence version is `evidence/two_vs_three/preliminary_v4`, whose
hardened-script replay reproduces every selected scientific metric and recipe
from v3. The Physics equations were unchanged. The plots use an explicitly
non-unique nominal reference, physical firing time zero, no peak alignment and
no amplitude normalization of the simulated traces.

## New training and release gate

The former 1-4-module models are historical, not final serving models. Filter
raw rows by actual front and tail tree leaf counts ==2 before canonical
deduplication, preserving their original split identities and domain labels.
Record parent hashes, rejected counts and filter provenance in a new version.
Fit the four agreed approaches separately for each of eight routes. Freeze
selection from validation before reporting test performance. Former held-out
rows remain never fitted but have previously been inspected; fresh independent
optimization request seeds are 20261201 (validation) and 20261202 (test).
Do not use fresh final-test outcomes for selection or dataset enrichment.

Final serving artifacts belong to `networks_exact2_v5`. The offline release must
pass with those eight actual selected models and the exact-two public boundary;
historical model loading cannot substitute for that acceptance gate.

The clean corpus must represent all four front/tail operation combinations (SS, SP, PS, PP), all 42 recipes in each role and joint pairing coverage. Any unsupported Physics labels remain explicit exclusions from regression, with coverage reported rather than invented. Additional design groups are frozen before labeling; final held-out optimization requests are not used to enrich the data or choose models.
