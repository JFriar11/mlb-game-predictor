# Sprint 10B — Runtime and PostgreSQL acceptance

Date: 2026-11-01. Local engineering acceptance; no new model evaluation or live launch.

## Delivered

- Exact runtime, development, and build dependency pins, with a Python 3.12 frozen
  model profile and Linux-specific SQLAlchemy dependency coverage.
- A digest-pinned, non-root Docker runtime containing the installed wheel,
  migrations, and configuration manifests. Secrets and data are excluded from its
  build context; the accepted artifact is supplied read-only at execution.
- Packaged five-game manifest support and configurable `MLB_ARTIFACT_PATH` so an
  installed wheel does not depend on repository-relative package paths.
- `make runtime-acceptance`: isolated migrations, ingestion/prediction idempotency,
  official-index enforcement, settlement invariance, full logical dump/restore,
  and frozen-model host/container inference checks.
- CI coverage for artifact-free PostgreSQL acceptance and installed-wheel packaging.
  See `docs/RUNTIME.md` for reproduction and trusted artifact/history recovery.

## Verified evidence

- Fresh setup via `make install VENV=.venv-sprint10b` succeeded. In that new
  environment, `make quality VENV=.venv-sprint10b` passed lint, formatting, and
  **31 tests**; the one opt-in PostgreSQL test was skipped there and passed
  separately in the acceptance harness. Host `pip check` passed.

- All migrations `0001` through `0013` applied from an empty PostgreSQL 16 database;
  repeated upgrade succeeded and Alembic detected no pending upgrade operations.
- PostgreSQL acceptance test passed. Repeated official generation retained the
  original values/ID; a direct duplicate official insert was rejected by
  `uq_live_official_prediction`; two diagnostics were allowed.
- Repeated settlement preserved every forecast/provenance field while recording
  synthetic final outcomes and actual-start timing.
- Dump/restore matched all **18 tables** and sequence states. Restored Alembic
  schema check passed.
- Container `pip check` passed. Installed manifest and CLI worked. Frozen artifact
  checksum matched; synthetic inference repeated exactly in each environment and
  agreed across macOS/Python 3.12.1 and Linux/Python 3.12 within the declared tolerance.
- Full runtime harness reported **PASS** in 13.5 seconds on the initial complete run.
  The exact `make runtime-acceptance VENV=.venv-sprint10b` target also passed from
  the fresh environment (38.7 seconds for the harness). No official production
  predictions or MLB requests were made. Temporary acceptance containers and their
  anonymous volumes were removed; existing project volumes were not attached.

## Limits and remaining work

This verifies synthetic persistence and artifact portability, not the existing
development database, prospective ledger, production-size backup recovery, or
predictive performance. Linux arm64 was tested locally; Linux amd64 and Python 3.11
source compatibility remain remote CI checks, which have not run. Dependency pins
have no wheel hashes/offline archive. Artifact distribution remains a trusted manual
transfer. Container code revision remains `unknown` without Git metadata. API,
frontend, explanations/confidence presentation, hosted scheduling, and monitoring
are still unfinished. Hosting approval remains required.

Recommend proceeding to Sprint 10C, the read-only prediction API. No manual account
setup is required for that milestone. Stop for review before starting it.
