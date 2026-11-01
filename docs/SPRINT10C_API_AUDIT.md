# Sprint 10C — Read-only prediction API

Date: 2026-11-01. Local application milestone; no new model evaluation or deployment.

## Delivered

- `mlb_predictor.api` with an application factory, validated Pydantic contracts,
  request-scoped sessions, and five GET routes: dated official predictions,
  game detail, accepted-model metadata, liveness, and readiness.
- Official accepted-model filtering, explicit empty/not-recorded/not-found states,
  MLB official-date selection with a disclosed orphan-record UTC fallback,
  preserved prediction provenance, and separate discovery/outcome context.
- Censored `12+` distribution/score labels and interval flags; no new score,
  explanation, or confidence claims. Saved win probabilities remain unchanged.
- PostgreSQL-enforced read-only transactions, bounded pool/connection/query waits,
  sanitized data/storage errors, and no-store HTTP responses. No startup schema
  mutation, external MLB requests, inference, fitting, or settlement.
- Pinned FastAPI/Uvicorn dependencies without changing accepted scientific-library
  versions; an API console entry point in the existing non-root runtime image.
- Local/container operation and response semantics in `API.md`, plus CI checks
  for installed API schema/entry-point availability.

## Verified results

Commands used the pinned `.venv-sprint10b` environment:

```bash
make install VENV=.venv-sprint10b
make quality VENV=.venv-sprint10b
make runtime-acceptance VENV=.venv-sprint10b
```

- Ruff and formatting passed. Pytest: **50 passed, 1 skipped**. The skipped
  PostgreSQL acceptance test passed separately in the full runtime harness.
- Nineteen API tests cover empty dates, strict ISO dates and boundary inputs,
  unknown IDs, official/diagnostic/model filtering, mutable discovery versus saved
  provenance, absent discovery, separate settlement, malformed/nonfinite stored
  data, cutoff ordering, missing/mismatched/unreadable artifacts, database failures,
  startup behavior, and read-only HTTP routes. No SQL/password details appeared in
  simulated dependency-failure responses or application logs.
- PostgreSQL acceptance served the saved synthetic official prediction while
  excluding two diagnostics. An attempted write inside the API transaction was
  rejected with SQLSTATE **25006** (`read_only_sql_transaction`).
- All migrations and schema checks passed, including restored state. Dump/restore
  continued to match all **18 tables** and sequence states.
- The installed non-root container ran `mlb-predictor-api` with Uvicorn. Real HTTP
  requests exercised all five routes, OpenAPI, empty dates, and 404/422/405 paths.
  HTTP smoke reported **PASS**. The full harness reported **PASS** in 17.1 seconds.
- Host/container dependency checks passed. The unchanged frozen artifact's checksum
  matched, and host/container synthetic inference continued to agree within the
  Sprint 10B tolerance. HTTP smoke left database contents and sequences unchanged.
- Temporary API/database containers were removed. No existing project database or
  volume was attached. No real predictions, historical-data writes, commits,
  pushes, or cloud resources were created.

## Limitations and next step

This milestone verifies synthetic application behavior, not the developer's
current persisted history/ledger, prospective performance, production load, or
unattended availability. Readiness checks table accessibility and artifact bytes;
it does not certify watcher freshness or record completeness. Current discovery
dates can change a rescheduled game's date listing; immutable provenance remains
separate. Missing artifacts can make readiness return 503 while retained forecasts
remain readable.

The API has no authentication, browser cross-origin policy, UI, or deployment.
Container revision provenance remains `unknown` as recorded in Sprint 10B.
The pinned Starlette TestClient emits one deprecation warning for its httpx adapter;
tests pass, and a later development-tool update can address that adapter separately.
Remote Linux amd64/Python 3.11 CI has not run. Artifact distribution remains a
trusted manual transfer; no frozen artifact is uploaded to CI.

Recommend Sprint 10D next: baseball-grounded factors and validated confidence/data
quality presentation. No manual account setup is required to begin that local
milestone. Stop for review before proceeding to Sprint 10D or React/hosting work.
