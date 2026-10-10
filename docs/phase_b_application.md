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
sets a low Physics bound. This prevents a six-part or one-module audit request
from being presented as representative while it has only sampled a handful of
known candidates. The saved search counters and `catalog_complete` flag make
that decision visible; larger catalogues still honor the requested adaptive
and Physics limits.

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

The UI is available from the `Network optimizer` navigation item. The research
3 µF/stage profile is marked in the page and in every saved request as a
research comparison domain.
