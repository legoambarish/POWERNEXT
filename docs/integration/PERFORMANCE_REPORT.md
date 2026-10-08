# Performance and numerical preservation

## Controlled comparison

The same `tools/benchmark_integration.py` harness ran the actual October 4 portable application and the integrated application, each using its own bundled Python and **one optimizer worker**. Both used unchanged SI and LI requests and the full 504-candidate declared single-component catalog. No candidate cache or ML pruning was used. These are measured single-run wall times on this Windows computer, not statistical hardware-independent speed guarantees.

| Workload | October 4 | Integrated | Improvement |
|---|---:|---:|---:|
| SI complete 504 candidates | 288.088 s | 17.168 s | 16.78×; 94.0% less wall time |
| LI complete 504 candidates | 270.231 s | 16.137 s | 16.75×; 94.0% less wall time |
| 128 explicit ML scenarios, first batch | 130.2 ms | 71.2 ms | 1.83× |
| 128 explicit ML scenarios, warm batch | 126.5 ms | 71.3 ms | 1.77× |

Source evidence: `evidence/integration/baseline/benchmark.json` and `optimized_final/benchmark.json`. The earlier `optimized/` run records an intermediate implementation and is retained as development evidence, not selected as the final result. The final benchmark ran after the comprehensive suites, with no other full-catalog job active. Light browser verification was performed during the integration session; these are not isolated laboratory timing measurements.

## Bottleneck and correction

The baseline repeatedly opened and hashed the same profile, serving source and model files within each prediction. Instrumented hash entry points accounted for 248.3 s of SI time and 238.2 s of LI time, with 71,439 calls per search and approximately 116.9/123.4 GB of repeated logical file reads. OS caching does not remove Python hashing cost. The integrated path makes 17,009 cheap logical hash lookups, with approximately 0.70 s spent in the instrumented wrappers. **Logical lookup byte counts in the new `hash_work` field are not physical I/O.** The independently recorded boundary I/O is 132 reads / 189,542,706 bytes per one-worker search, including model/profile initialization and complete integrity boundaries.

The calculation consumes an immutable verified snapshot of the model/profile/selection bytes. Full SHA-256 hashes run at entry and exit before the result is published. Models are loaded from those verified bytes and cached by artifact identity. Workers validate their stack against the parent and hold a snapshot across their assigned candidates. Same-size/same-mtime replacements and changes during calculation fail closed; no timestamp-only trust or disabled provenance gate was introduced.

The final normal application uses four workers. Repeated per-candidate JSON cache writes were removed from the interactive path; complete run results and compressed waveform evidence remain saved. The optional research CLI cache still exists. Cold end-to-end application times, including subprocess startup, serialization and persistence, were **25.98 s for SI 504** and **29.60 s for LI 588** in the moved-folder acceptance run. The previous retained LI 588 application run took **102.554 s**: the final application is approximately **3.46 times faster / 71.1% less elapsed time** on that actual application comparison, with every candidate configuration, metric, score and rank unchanged. HTTP round-trip times are separately recorded in `portable_acceptance.json`.

Intermediate experiments remain archived: four workers with the candidate cache took 44.80 s for LI 588; one worker with cache took 78.06 s; one worker without cache took about 60 s. These are single-run engineering measurements, not a controlled distribution. Four workers without the redundant cache were retained. The measured 17-second controlled one-worker engine benchmark above excludes the full application workflow and must not be presented as its end-to-end latency.

## Result equivalence

Both complete baseline/new ranking snapshots compare exactly across all 504 candidate IDs, configurations, waveform metrics, assessments, conformity scores and ranks. SI remains 14 numerical passes / 477 evaluable / 27 unsupported; LI remains zero numerical passes / 477 evaluable / 27 unsupported. Each reports 504 evaluated and zero pruned. All 15 current example-result catalogs were regenerated with the new serving fingerprint and compared against their archived previous configurations, assessments, scores and ranks before replacement.

The rapid-discovery browser check produced 289 ML estimates in 58 ms for an explicitly stated fixed-charge DUT/inductance grid; a selected scenario was subsequently evaluated in Physics without retuning the charge. That is the batch inference time displayed by the API, not a claim that the whole HTTP/UI transaction takes 58 ms. Broader grids can encounter OOD abstention, which remains visible and never removes candidates from a later complete optimizer search.
