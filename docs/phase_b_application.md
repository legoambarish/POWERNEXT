# Phase B v3 network workspace

The v3 workspace is an independent offline application boundary for the bounded
series/parallel network catalogue. It is mounted beside the legacy service and
does not change the legacy `/api` routes, result bytes, model selection, or
waveform review screens.

## API contract

The server lazily creates `powernext_v3.application.V3Application` under the
existing application data root:

```text
<data-root>/v3/jobs/v3_<id>/request.json
<data-root>/v3/jobs/v3_<id>/state.json
<data-root>/v3/jobs/v3_<id>/artifact/result.json
<data-root>/v3/jobs/v3_<id>/artifact/waveforms/*.npz
<data-root>/v3/predictions/pred_v3_<id>/prediction.json
<data-root>/v3/predictions/pred_v3_<id>/physics_waveform.npz
<data-root>/v3/predictions/pred_v3_<id>/ref_v3_<id>/{comparison.json,raw_export.csv,source_metadata.json}
```

The read endpoints are:

* `GET /api/v3/meta` returns the component catalogue, profiles, model-route
  availability, fallback policy, and endpoint schema.
* `POST /api/v3/validate` accepts a `network_request_v3` object and returns
  normalized request and catalogue counts.
* `POST /api/v3/runs` accepts `{ "request": ... }` and returns `202` with a
  queued job. `GET /api/v3/runs` lists jobs; `GET /api/v3/runs/{id}` returns
  progress and exposes `result` only after an integrity-checked complete
  artifact is committed. `GET /api/v3/runs/{id}/waveform?candidate=...`
  returns an integrity-checked saved waveform.
* `POST /api/v3/predict` accepts `{ "request": ..., "configuration": ... }`
  for an unseen fixed configuration. `GET /api/v3/predictions/{id}` returns
  its immutable input, model route/fallback, source fingerprint, and forward
  prediction. `GET /api/v3/predictions/{id}/waveform` returns the saved,
  hashed Physics waveform and detailed numerical metadata when the solve is
  supported.
* `POST /api/v3/predictions/{id}/reference` accepts `csv_base64` (preferred)
  or `csv_text`, plus metadata. It creates a separate comparison record with
  absolute, relative, and tolerance errors. `GET .../reference/{comparison}`
  reads that record without changing the frozen prediction.
  `POST /api/v3/predictions/{id}/reference-metrics` accepts scalar
  `crest_magnitude_V`, `T1_s`/`Tp_s`, and `T2_s` values when a report supplies
  no waveform. It creates the same immutable comparison shape without
  claiming raw bytes.

Search records distinguish theoretical recipe configurations from distinct
electrical response candidates, ML-predicted candidates, Physics evaluations,
unsupported candidates, known inventory exclusions, and complete versus
partial catalogue coverage. A planned search budget can produce a valid
completed result with `catalog_complete: false`; an interrupted or failed job
never exposes a partial result.

For a deliberately small declared catalogue, the service uses complete
coverage as a safety fallback even when the request selects adaptive search or
sets a low Physics bound. The saved search counters and `catalog_complete` flag
make that decision visible; larger catalogues still honor the requested
adaptive and Physics limits. The live public boundary independently requires
exactly two modules in each front and tail branch.

## Model and measurement boundary

The fixed prediction flow runs detailed Physics separately from the ML/L0
prediction and freezes the normalized input hash, model route, model card (when
available), Physics metadata/waveform hash, and source fingerprint before any
reference is attached.
When the selected route artifact is unavailable, the record carries
`PHYSICS_FALLBACK` and `prediction_is_not_an_ml_claim: true`. A later reference
CSV is retained byte-for-byte with caller metadata and the existing evaluator's
limitations. The numerical comparison is evidence for review only; it does not
retrain, mutate, or certify the prediction and cannot establish CPRI or IEC
qualification.

An explicit `load_resistance_ohm` setup field is supported by detailed Physics
but is outside the versioned L0 feature contract. The fixed prediction keeps
the detailed Physics metrics and waveform, marks the fallback source as
`DETAILED_PHYSICS`, and records `ml_unsupported_reason`; it never labels that
record as an ML prediction. Explicit configuration route fields
(`domain_id`, `impulse_type`, `topology_id`, and `polarity`) must agree with the
request before Physics runs or a prediction artifact is created. Unexpected
Physics failures remain errors and are not relabeled as unsupported traces.
`PHYSICS_VERIFIED` additionally requires both `numeric_status=VALID` and
`waveform_status=VALID_CLEAN_FULL_IMPULSE`; a computed waveform with an
indeterminate or truncated evaluator status remains available for review but
is labeled `PHYSICS_UNSUPPORTED` with an explicit reason. The fixed-prediction
view displays ML OOD status and detailed Physics crest/timing independently;
its waveform action says `computed` unless the clean-full-impulse gate passed.

The UI is available from the `Network optimizer` navigation item. The research
3 µF/stage profile is marked in the page and in every saved request as a
research comparison domain.

The current active application scope requires exactly 2 modules in both the
front and tail branches. The application and CLI reject explicit 1-, 3-, or
4-module requests and fixed network trees with `UNSUPPORTED_CURRENT_SCOPE`
before creating a job or prediction artifact. The historical 1-, 3-, and
4-module enumerator, Physics paths, model artifacts and evidence remain
retained for archival and low-level replay. The product UI has no module-bound
selector and shows the exact-two S/P requirement directly.

## Extracted release acceptance

`tests/verify_networks_release.py` is the read-only acceptance harness for a
new extracted exact-two v5 release. Run it from the release directory with the embedded
runtime; use an output path outside that directory so the package cannot be
changed while its manifest is being checked:

```powershell
runtime\python.exe -B tests\verify_networks_release.py `
  --output C:\Temp\PowerNext_Track1_Exact2-acceptance.json
```

The harness checks that imports resolve to the embedded runtime or release
root, outbound sockets are denied, every selected route has both `card.json`
and `model.joblib` and passes strict registry loading, and the immutable
manifest remains byte-for-byte unchanged after execution. It also performs a
fixed Physics prediction and scalar-reference freeze for all eight routes.
The complete catalogue gate evaluates the LI rare timing fixture and the SI
fixture over the exact-two branch scope. For a single requested stage this is
42 recipes per branch and 1,764 front/tail configurations; all stages 2 through
15 contain 24,696 configurations before any search budget is applied.

The historical v3 selected artifacts remain retained, while the active serving
mapping is being regenerated under `networks_exact2_v5`. Normal selected-model
acceptance for that exact-two mapping must load eight cards/models and perform
route, hash and fixed-prediction checks without `--allow-pending` once those
artifacts are available. The final extracted package and immutable package
manifest gate remain pending until the lead-owned builder produces that
package.
The lead-owned extracted release target is `PowerNext_Track1_Exact2`; its
destination and archive must be new paths so the accepted historical release
and its manifest remain immutable.
`--allow-pending` remains useful only for a checkout or extraction intentionally
missing the final model or package gate; it keeps the Physics fallback and
catalog smoke checks usable, but it never converts `PHYSICS_FALLBACK` into an ML
acceptance. The release builder's route selection now applies the strict card
gate before copying selected models. The acceptance harness independently
requires both `card.json` and `model.joblib`, then performs registry card/hash/route
checks; it does not modify the builder.
