# Reproducible local runtime

The frozen-model runtime uses Python 3.12 and exact dependency versions in
`requirements/runtime.txt`. NumPy, pandas, SciPy, and scikit-learn match the
accepted research artifact's recorded environment. General source compatibility
remains Python 3.11+, but the pinned artifact runtime is supported on 3.12 only.

From the repository root, with Python 3.12 and Docker running:

```bash
make install
make quality
make runtime-acceptance
```

`make install` installs pinned development and build dependencies before performing
an editable install without dependency resolution or an isolated backend download.
The runtime image installs a wheel, runs as UID 10001, and pins the Python base by
digest. Its default command prints CLI help. These pins control dependency versions;
they are not a hash-verified, offline wheel archive or a promise of byte-identical
container builds. Keep a trusted package mirror/wheel archive if offline recovery
is required. Update pins only with the full acceptance suite and artifact inference
comparison; never refit the frozen model to accommodate a dependency upgrade.

## Acceptance behavior

`make runtime-acceptance` builds `mlb-predictor:local` and runs
`scripts/runtime_acceptance.py --image mlb-predictor:local`. The harness creates a
uniquely named PostgreSQL 16 container on a loopback-only random port. It ignores the
configured project database URL, attaches no existing project volume, and uses
synthetic fixtures only. It checks:

- All migrations from an empty database, a repeated upgrade, and schema drift.
- Repeated normalized ingestion, discovery, and launch-state persistence.
- One official prediction per game/model, multiple diagnostic records, and
  PostgreSQL's partial unique index in an independent transaction.
- Repeated settlement without changing any forecast or provenance fields.
- A custom-format `pg_dump` restored into a second empty database, with row counts,
  SHA-256 hashes of all table contents, sequence states, and schema checks matched.
- Installed-wheel CLI/resource loading, dependency consistency, frozen artifact
  checksum, finite normalized distributions, repeatable inference, and agreement
  between host and container predictions at `rtol=1e-9, atol=1e-12`.

The inference check is read-only and verifies no database state changed. It uses a
synthetic feature-history fixture and makes no MLB requests. This demonstrates
runtime portability, not predictive accuracy or production-history completeness.
The harness removes its own container and anonymous data volume on exit. A forced
process kill may require removing that run's `mlb-acceptance-*` container manually;
inspect its `mlb-purpose=acceptance` label first. Never prune project volumes.

For migration/persistence/recovery checks without an artifact:

```bash
.venv-sprint0/bin/python scripts/runtime_acceptance.py
```

The default pytest run skips the PostgreSQL test. The harness explicitly runs it
against its disposable database. CI runs this artifact-free acceptance and builds
the wheel image. The private frozen artifact is not uploaded to CI; full model
portability acceptance remains a local release gate.

## Restore the accepted artifact on a fresh checkout

Git intentionally excludes model binaries and historical data. A clone can run
tests and artifact-free acceptance, but cannot make accepted-model forecasts until
the owner supplies trusted artifacts and normalized history.

1. Obtain the owner's existing `accepted_model_v1.joblib` and accompanying metadata
   through a trusted private transfer or backup. Do not download arbitrary joblib
   files: loading them executes Python code. The local copy remains under ignored
   `data/processed/`; no artifact hosting has been configured.
2. Place it at `data/processed/accepted_model_v1.joblib`, or set `MLB_ARTIFACT_PATH`
   to an absolute path. Its accepted SHA-256 is
   `2d2f6bdd557bb9f4fa981fd88358774617fc246810f2efb2e4c79917ba9df945`.
   The acceptance harness supports `--artifact /absolute/path/model.joblib`.
3. Run full runtime acceptance. It verifies the checksum before loading the model.
   Do not run `freeze-accepted-model` as a setup or recovery step.
4. Restore normalized history and operational state from a trusted PostgreSQL
   backup into a **new** database. Use PostgreSQL 16 client tools, `pg_dump -Fc
   --no-owner --no-acl`, then `pg_restore --exit-on-error --no-owner --no-acl`
   against that new database. Supply authentication through local client settings
   or a secret environment; never commit connection strings or dumps. Never use
   `--clean` against the existing project database.
5. Verify migration head/schema drift, relevant season audits, game/history counts,
   accepted artifact hash, original launch timestamp, prediction counts, and stored
   forecast values against the backup manifest before switching connections.
   Preserve original prediction timestamps and launch state. Backfilled outcomes
   must never become prospective predictions. A live-only export should retain
   reference entities, games, starting lineups/pitchers, player-game batting and
   pitching, live discovery, predictions, operational state, watcher events, and
   Alembic state. Research feature tables are not needed for live inference, but
   retain their empty migrated schemas and preserve the full research backup.

The frozen 2021–2025 raw caches stay local and read-only. A cloud state transfer and
production-size recovery rehearsal remain deployment gates; the synthetic acceptance
test does not certify the owner's current persisted data or prove any live collection.

## Container operation

The build context excludes `.env`, Git history, all raw/generated data, and virtual
environments. The model is mounted read-only at runtime. Run from the repository root:

```bash
docker build -t mlb-predictor:local .
docker run --rm mlb-predictor:local --help
```

To operate against the existing Compose database, first start its `postgres` service.
Supply `MLB_DATABASE_URL` using a private environment file with container-visible host
`host.docker.internal` and port `55432` on Docker Desktop, plus any other MLB settings.
Mount the trusted artifact at `/app/data/processed/accepted_model_v1.joblib:ro`.
Pass `watcher-status` first to inspect connectivity before a write-capable operation.
The installed CLI resolves generated data relative to its working directory (`/app`
in Docker). Mount a writable cache directory for runs requiring persistent raw feeds.
Do not mount the canonical frozen raw archive writable. `alembic` is available via
`--entrypoint alembic`; apply upgrades intentionally before starting the watcher.

The image has no Git checkout, so current code provenance reports `unknown` there.
A release revision/image-digest provenance mechanism, deployment secrets, monitoring,
and production scheduling remain subsequent release work. This milestone provisions
no cloud resources and starts no live watcher.

Sprint 10C adds `mlb-predictor-api` to the same pinned image; see `API.md` for
local HTTP operation. Full runtime acceptance now also starts Uvicorn in a
temporary container and exercises all five API routes over HTTP. PostgreSQL
acceptance verifies that API transactions reject writes with SQLSTATE `25006`.
