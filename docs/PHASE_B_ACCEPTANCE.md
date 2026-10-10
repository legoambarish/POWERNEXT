# Exact-two production acceptance

Final scope: exactly two physical resistors in each front and tail branch, either series or parallel. Both branches are optimized together. Single-, three- and four-module recipes are excluded from the final public optimizer and new training set. The original workspaces and older artifacts remain historical compatibility features.

| Gate | Evidence / status |
|---|---|
| Exact-two joint catalog | PASS: 42 recipes per branch, 1,764 front/tail pairs per stage, 24,696 candidates over stages 2–15 |
| Dataset scope and integrity | PASS: 78,244 raw / 66,682 eligible / 66,244 canonical records; actual tree validation, hashes, grouped splits and deduplication pass |
| Joint front/tail coverage | PASS: every route attempts all 1,764 pairs in all four series/parallel combinations; unsupported labels remain excluded and documented |
| Separate domains | PASS: separate domain/mode/topology fitting and serving; the tagged storage container does not pool domains in an estimator |
| Four approaches on eight routes | PASS: 32 final candidates plus nested learning curves; eight selections frozen from validation |
| Independent selection Physics | PASS: 16 request oracles, 84,672 candidate evaluations; six routes have feasible retention/regret evidence, two research OSHUNT routes use declared regression fallback |
| Actual serving models | PASS: all eight selected exact-two models load and produce application predictions; six residual ExtraTrees, two residual HistGradientBoosting |
| Full catalog serving | PASS: all eight routes score 24,696 joint candidates and verify 256 with Physics; bounded results are labelled partial |
| Public UI / fixed settings | PASS: browser scope/count/model smoke, exact-two trees on both branches, separate ML and detailed Physics display |
| Source regression | PASS: 523 counted tests plus UI race check across ten suites; post-digest-fix ML tests separately pass 29/29 |
| Fresh four-policy final benchmark | PASS: 16 fresh requests plus one known regression; 12/12 feasible requests retained, zero observed best-score regret; ML finds 732/732 reference alternatives, combined 715/732; no test-driven selection/refit |
| Extracted offline release | PASS: extracted bundled runtime, all eight gates, no pending reasons; 16,737 immutable files verified before and after execution; [companion receipt](../evidence/exact2_v5/offline_release_acceptance.json) |
| Original accepted release | PRESERVED: original ZIP SHA256 297c6b3530f7933436ce2daf4b503ea5307873d291884e5f45ae2cc1ef047f98 verified unchanged |
| Original CPRI workbook | Independent comparison only; never used for training labels; prior formula and transient comparison evidence retained |
| Independent two-versus-three study | COMPLETE: five actual-waveform comparisons, full overlays and fixed-stage/fixed-charge diagnostics; no failed baseline becomes passing in the sample |

The active dataset is `powernext/ml/data/networks_exact2_v5_aug1`; active model and result directories are `networks_exact2_v5`. Original v3 and intermediate filter artifacts are historical. New evidence is under `evidence/exact2_v5`.

See [data report](EXACT2_DATASET_REPORT.md), [model report](EXACT2_MODEL_REPORT.md), [scope decision](FINAL_RESISTOR_SCOPE_DECISION.md), [waveform comparison](TWO_VS_THREE_PRELIMINARY.md), and the [actual-model audit](../evidence/exact2_v5/actual_model_integration.json).

Dataset rows within a setup family are correlated. The five-context supplement covers every resistor pair with stages distributed across 2–15; it does not simulate every pair at every stage and every possible setup. Numerical unsupported results and a bounded search without a pass are not proof of unrestricted infeasibility. Hardware inventory, mounting, pulse ratings and laboratory validation remain unverified. The 3 µF profile is a separate research domain, not a confirmed second CPRI machine.
