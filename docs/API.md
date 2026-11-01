# Read-only prediction API

Sprint 10C serves saved official predictions for `accepted_v1_2026_prospective`.
Requests never call MLB, generate predictions, settle games, fit models, or migrate
the database. Existing CLI/watchers remain responsible for writing the ledger.

## Run locally

Use Python 3.12, an already migrated PostgreSQL database, and the environment
configuration described in `RUNTIME.md`. From the repository root:

```bash
make install
.venv-sprint0/bin/mlb-predictor-api
```

The default address is `http://127.0.0.1:8000`. Interactive OpenAPI documentation is
available at `/docs`, with the schema at `/openapi.json`. `MLB_API_HOST` and
`MLB_API_PORT` override the listener. The API reads `MLB_DATABASE_URL` and
`MLB_ARTIFACT_PATH` using the existing settings mechanism. Never commit real
credentials. Alternate launch:

```bash
.venv-sprint0/bin/uvicorn mlb_predictor.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

The `mlb-predictor-api` entry point configures repository JSON logging. A direct
Uvicorn launch uses Uvicorn's logging defaults.

## Endpoints

| GET endpoint | Behavior |
| --- | --- |
| `/api/v1/predictions?date=YYYY-MM-DD` | Official accepted-model forecasts for one MLB official date, ordered by saved start time and game ID. Empty dates return 200 with `count: 0` and `predictions: []`. |
| `/api/v1/games/{game_pk}` | Latest retained discovery and official prediction. Discovered games without a forecast return `prediction_status: "not_recorded"` and a null prediction. Unknown IDs return 404. |
| `/api/v1/model` | Accepted model/feature/calibration/distribution versions, training seasons, limitations, expected artifact checksum, and current artifact status. Does not query performance or claim prospective success. |
| `/health/live` | Process liveness, independent of database or artifact availability. |
| `/health/ready` | 200 only when forecast/discovery table columns are readable and the local frozen artifact checksum matches; otherwise 503 with separate database/artifact states. |

For example:

```bash
curl 'http://127.0.0.1:8000/api/v1/predictions?date=2026-08-14'
curl 'http://127.0.0.1:8000/api/v1/games/999002'
curl 'http://127.0.0.1:8000/health/ready'
```

`999002` is the isolated acceptance fixture ID, not a production MLB game. Ordinary
databases will return 404 for it. Historical dates with no genuine recorded
predictions remain empty; the API never backfills a forecast.

## Response meaning

- Only `is_official = true` records from the accepted model are returned. Diagnostic
  and other-model rows are excluded. Official `prediction_kind` and timing classes
  are reported exactly as stored, including backfills; serving a row does not make
  it prospective. The API does not recompute prospective eligibility.
- `game_date` uses the latest retained MLB discovery's official date. If discovery
  is absent, the saved scheduled-start UTC date is used with
  `date_basis: "scheduled_start_utc"` and null discovery. This prevents silently
  hiding an otherwise retained prediction. Rescheduled discovery dates can change
  which date lists a prediction; its saved start and provenance remain unchanged.
- `latest_discovery` is mutable schedule/team/venue/lineup-status context with its
  own source and retrieval timestamp. It is not a reconstructed prediction-time
  lineup snapshot. `provenance` contains the saved prediction/start/cutoff/source
  timestamps, starter IDs, versions, official flag, and timing classifications.
  Timestamps are returned in UTC.
- `home` and `away` expose saved means, 13 run probabilities, and 50%/80%/95% intervals.
  Labels are `0` through `11`, then **`12+`**. The terminal bin includes all scores
  of at least 12. Interval endpoint 12 is marked `upper_is_censored: true`; it must
  not be displayed as an exact finite maximum. These are the stored censored-bin
  intervals, not newly calculated unbounded-count quantiles.
- `most_likely_score_bins` contains labeled independent joint scoring categories,
  including possible tied categories. These are not exact resolved final scores.
  Win probabilities separately include the extra-inning approximation and Platt
  calibration. The API preserves these values without claiming the calibrated
  wins are the sum of the displayed joint score bins.
- Outcomes appear only in `observed_outcome`, separately from the forecast. No
  outcome is synthesized from a discovery status. The original forecast remains
  unchanged after settlement.
- `data_quality_warnings` preserves recorded warning strings. An empty warning list
  is not a validated confidence score. Sprint 10D adds recorded input summaries,
  separate probability/input-quality/calibration components, and uncensored
  `run_ranges`. See `EXPLANATIONS.md` for their semantics and missing-evidence behavior.

## Availability and validation

Retained forecasts and model metadata can be read without a model binary. Health
readiness deliberately checks the broader installed predictor runtime, so it can
return 503 for a missing/mismatched/unreadable artifact while ledger GETs work.
Artifact checks hash bytes; they never deserialize a model.

Readiness checks forecast/discovery/input-snapshot table and column accessibility,
not every stored record, historical
coverage, watcher freshness, prospective eligibility, or predictive accuracy.
Per-response validation rejects malformed JSON, invalid/nonfinite probabilities,
unnormalized PMFs, inconsistent calibrated complements, invalid intervals, invalid
score bins, post-prediction feature cutoffs, and incomplete observed outcomes.
Present input snapshots also require valid binding to their original forecast,
cutoff, artifact, starters, and accepted feature columns. Missing snapshots remain
valid legacy state. An invalid selected record makes the request fail with 503;
it is never silently dropped from a date's results. Feature, calibration, and
distribution versions must match the accepted contract before its calibration
evidence is presented.

Advertised data-route errors use `{"error":{"code":"...","message":"..."}}`:

| Status | Code | Meaning |
| --- | --- | --- |
| 422 | `invalid_request` | Required date missing, non-ISO/impossible date, or invalid game ID. |
| 404 | `game_not_found` | No retained discovery or accepted official prediction for the ID. |
| 503 | `database_unavailable` | Database/required schema cannot be read. |
| 503 | `invalid_stored_prediction` | A selected stored record violates the response contract. |

Readiness returns its typed health body instead of the data-route error envelope.
Database errors and stored payloads are not echoed into responses or application
error logs. Responses use `Cache-Control: no-store` so new forecasts, discovery
updates, and settlement are not hidden by stale HTTP caches.

## Database and container behavior

Each request uses a session that closes with rollback. PostgreSQL additionally
enforces `SET TRANSACTION READ ONLY`. The API pool has two persistent connections
and up to three overflow connections, a three-second pool/connect timeout, and a
five-second statement timeout. Startup creates only an engine; no connection,
schema creation, migration, or background task runs until needed. Use a separately
managed read-only database role for a hosted release.

The same runtime image supports CLI and API. For Docker Desktop, prepare an ignored
`.env.api` whose database hostname is `host.docker.internal` rather than container
localhost. With the Compose database already running:

```bash
docker build -t mlb-predictor:local .
docker run --rm --entrypoint mlb-predictor-api \
  --env-file .env.api -e MLB_API_HOST=0.0.0.0 \
  -p 127.0.0.1:8000:8000 \
  -v "$PWD/data/processed/accepted_model_v1.joblib:/app/data/processed/accepted_model_v1.joblib:ro" \
  mlb-predictor:local
```

The service is a local read-only interface with no authentication, frontend, or
cross-origin configuration. Public authentication/network policy, hosting,
monitoring, and production load testing remain release work. No public listener or
cloud resource is provisioned by this milestone.

## Verification

```bash
make quality
make runtime-acceptance
```

The full harness checks PostgreSQL-enforced rejection of writes, official versus
diagnostic selection, migration/recovery equivalence, unchanged frozen inference,
and actual HTTP requests to Uvicorn inside an isolated container. It uses synthetic
data and removes its temporary containers and volumes. It does not inspect or
alter the developer's current historical database.

Implementation references: [FastAPI lifespan management](https://fastapi.tiangolo.com/advanced/events/)
and [request-scoped dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/).
