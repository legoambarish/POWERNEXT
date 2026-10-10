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

## Extracted release acceptance

`tests/verify_networks_release.py` is the read-only acceptance harness for a
new extracted v3 release. Run it from the release directory with the embedded
runtime; use an output path outside that directory so the package cannot be
changed while its manifest is being checked:

```powershell
runtime\python.exe -B tests\verify_networks_release.py `
  --output C:\Temp\powernext-v3-release-acceptance.json
```

The harness checks that imports resolve to the embedded runtime or release
root, outbound sockets are denied, every selected route has both `card.json`
and `model.joblib` and passes strict registry loading, and the immutable
manifest remains byte-for-byte unchanged after execution. It also performs a
fixed Physics prediction and scalar-reference freeze for all eight routes.
The complete catalogue gate evaluates the LI rare timing fixture and the SI
fixture over stages 2 through 15 with one module per branch: 504 theoretical
recipes, 504 distinct response candidates, and 504 Physics evaluations per
fixture.

Before trained v3 artifacts and a v3 package manifest exist, the normal exit
status is `BLOCKED` (exit code 2). `--allow-pending` returns zero only to make
the Physics fallback smoke and catalogue checks usable during development; it
does not convert `PHYSICS_FALLBACK` into an ML acceptance. The current source
checkout is intentionally in that pending state: it has the legacy v2
manifest and no `powernext/ml/registry/networks_v3` or selected-model file.
The release builder's route selection now applies the strict card gate before
copying selected models. The acceptance harness independently requires both
`card.json` and `model.joblib`, then performs registry card/hash/route checks;
it does not modify the builder.
