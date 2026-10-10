# Exact two resistor branch dataset

The final exact scope is the immutable composite dataset at
`powernext/ml/data/networks_exact2_v5_aug1`.  Every front and tail branch is a
canonical series or parallel tree with exactly two leaves, selected from the
42 recipe catalogue.  The supplement covers the complete 42 × 42 Cartesian
pair grid for each of the eight domain/mode/topology routes.  The original
filtered rows remain in the same artifact with their original split labels
and statuses.

The composite has 78,244 raw rows: 7,684 rows copied from the exact2 filter
and 70,560 deterministic Physics simulations (1,764 pairs × five setup
contexts × eight routes).  The five contexts are `train_a`, `train_b`, and
`train_c` (three independent train setup groups), plus independent
`validation` and `test` setup groups.  Setup groups and explicit split labels
were frozen before simulation.  No ML predictions, workbook observations, or
waveform files were used; worker waveform arrays were discarded after each
bounded result.

Within each context, stages are distributed deterministically across the
approved 2–15 range.  This is complete pair coverage in every context, with
stage variation across the grid; it is not 1,764 pairs repeated at every
stage.  Rows sharing a setup context are intentionally correlated Physics
experiments, so canonical row counts do not imply the same number of
independent laboratory trials.  The copied parent test rows were already
part of the historical R2 selection; only the supplemental test context was
held out from this augmentation's own fitting inputs.

| Route | Raw | Eligible | Canonical | Eligible pairs / 1,764 | Unsupported pairs | Canonical train / validation / test | Raw setup groups |
|---|---:|---:|---:|---:|---:|---|---:|
| cpri_0p5uf LI GSHUNT_v0 | 9,652 | 8,967 | 8,913 | 1,764 | 0 | 5,275 / 1,778 / 1,860 | 689 (5 supplement) |
| cpri_0p5uf LI OSHUNT_v0 | 9,726 | 9,124 | 9,043 | 1,764 | 0 | 5,373 / 1,805 / 1,865 | 771 (5 supplement) |
| cpri_0p5uf SI GSHUNT_v0 | 9,552 | 8,945 | 8,898 | 1,764 | 0 | 5,221 / 1,793 / 1,884 | 618 (5 supplement) |
| cpri_0p5uf SI OSHUNT_v0 | 9,618 | 9,081 | 9,032 | 1,764 | 0 | 5,359 / 1,795 / 1,878 | 660 (5 supplement) |
| research_3uf LI GSHUNT_v0 | 9,843 | 8,306 | 8,225 | 1,634 | 130 | 4,923 / 1,612 / 1,690 | 858 (5 supplement) |
| research_3uf LI OSHUNT_v0 | 9,832 | 6,961 | 6,877 | 1,332 | 432 | 4,055 / 1,388 / 1,434 | 850 (5 supplement) |
| research_3uf SI GSHUNT_v0 | 9,663 | 8,228 | 8,192 | 1,636 | 128 | 4,911 / 1,607 / 1,674 | 692 (5 supplement) |
| research_3uf SI OSHUNT_v0 | 10,358 | 7,070 | 7,064 | 1,332 | 432 | 4,194 / 1,401 / 1,469 | 1,304 (5 supplement) |

The setup-group totals above count all attempted rows, including unsupported attempts. Usable train/validation/test family counts are reported separately in the model report and actual-model audit; many waveform rows within a family are correlated.

All eight routes contain all 42 front recipes, all 42 tail recipes, and all
1,764 pair keys.  Each route contains all four operation combinations
(`S::S`, `S::P`, `P::S`, and `P::P`).  The `Eligible pairs` column counts pairs
with at least one valid labelled row; the pair grid itself remains complete
even when a pair has no eligible Physics result.

The 1,122 route/pair combinations with no usable label in the sampled conditions are confined to the research 3 µF domain. This count is summed across routes; it is not a proof that those physical pairs are unsupported under every setup.  The
dominant retained error is `TIME_DOMAIN_OUTSIDE_REFERENCE_SCOPE`, meaning the
reduced detailed Physics trace would exceed the 200 ms reference window.  The
rows remain present with `INVALID_OR_UNSUPPORTED` status and null regression
labels.  This is negative evidence, rather than a fabricated target.

The final loader audit reports 66,682 eligible rows and 66,244 canonical rows
after response-equivalent deduplication.  Explicit split validation passes
with no response or setup identity crossing partitions.  The parent filtered
dataset is preserved through `parent_dataset_id`, parent manifest/rows/design
hashes, and the numerical Physics source fingerprint in the composite
manifest.

The byte-level source records are:

- rows SHA256: `57145d51b3a7d7e7b5e0e165c68bee53cbc074e367619bc2b8bd148b73ddf3eb`
- design JSONL SHA256: `264d85045213467a6f5a22b0c5696409ddd99a16603bec5b01b3f5d18c27f47c`
- normalized audit: [normalized_coverage_audit.json](../powernext/ml/data/networks_exact2_v5_aug1/normalized_coverage_audit.json)
- normalized audit SHA256: `775e0c4e9d15a95f6e4343750a3facb6ff3ca09c8f978cc59bce24767b6eec70`
- generation source snapshot: [augment_exact2_dataset_run_20261010.py](../evidence/phase_b/augment_exact2_dataset_run_20261010.py), SHA256 `a006029a845b14153e7d1cf665179f816d460b80618df4d2c2f9d1d730c0e077`

The original `coverage_audit.json` is retained for provenance.  It is marked
superseded by the normalized audit because its first diagnostic view mixed
numeric resistance keys from copied parent rows with recipe IDs from the
supplement.  The normalized audit derives every recipe key from the actual
canonical tree before counting.

This dataset establishes numerical scope and split integrity.  It does not
establish hardware mounting, component pulse ratings, auxiliary topology
state, or production feasibility.
