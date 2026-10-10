# Phase B implementation record

## Authorization and baseline

Approved scope: uniform canonical series/parallel recipes up to FOUR modules per
front or tail branch; separate 0.5 and 3 uF domains; four specified ML candidates;
adaptive ML priority with detailed Physics verification; complete-search baseline;
datasets, Excel comparison, judging workflow and tested offline release.

- Baseline commit: `5ed4b6a31c40201959146bd677f8c181d4935712` (main).
- Implementation branch: `phase-b/networks-ml-v3`.
- Accepted release is preserved at `../release/PowerNext_Track1_Offline`.
- Accepted ZIP SHA256: `297c6b3530f7933436ce2daf4b503ea5307873d291884e5f45ae2cc1ef047f98`.
- No original workbook, source evidence, v2 dataset, model or release is overwritten.

## Architecture contract

New code resides in `powernext_v3`, reusing the legacy graph, trajectory sampler and
waveform evaluator. Legacy scientific source files remain unchanged so their
existing model compatibility hashes remain valid. New artifacts have independent
source fingerprints, domains and paths.

Domain IDs are `cpri_0p5uf` and `research_3uf`. The latter uses explicitly
hypothetical 200 kV/stage, 60 kJ/stage and 900 kJ total limits, derived from 3 uF;
these are NOT CPRI equipment ratings. Both topologies remain declared hypotheses.
Actual inventory, mounting and pulse-rating approval remain unknown.

Physics API: `powernext_v3.physics.simulate(configuration, setup, domain_id=...)`.
Configuration includes equivalent front/tail resistance and optional exact trees;
setup uses the existing SI-unit field names. Research equivalent-only simulations
do not create physical resistor parts. Optimizer recommendations require recipes.

## Work in progress

- Lead: profiles, verified Physics integration, search contracts and integration.
- Worker networks (5.6 Luna MAX): exact canonical networks and unit tests.
- Worker datasets (5.6 Luna MAX): staged grouped data and Excel comparison.
- Worker ML (5.6 Luna MAX): batch features, four-model evaluation and serving.

## Acceptance still outstanding

New scientific regression, generated dataset coverage and split integrity,
eight trained routes with selection evidence, rare-feasible retention, benchmark
comparisons, UI and unseen-reference workflow, full regression, release extraction,
manifests and commit. Nothing in this file claims those gates already passed.

## First verified increment

Profile-aware Physics integration: seven new tests passed (legacy single-response equivalence in both modes/topologies, two-domain energy, independent zero-L oracle, full-stage GSHUNT reduction, exact charge/polarity reuse, invalid constraints). Legacy scientific files remain unchanged.

