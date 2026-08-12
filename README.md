# MLB Game Predictor

A typed, PostgreSQL-backed foundation for a leakage-controlled MLB pregame forecasting
system. Sprint 0 reconstructs exactly five completed games from the MLB Stats API.

## Supported local setup

The supported PostgreSQL workflow is the repository's Docker Compose service. It requires
Python 3.11+ and Docker Desktop (or another Docker engine with Compose). Homebrew
PostgreSQL and ad hoc temporary clusters are not supported project workflows.

Start Docker Desktop first and wait until its engine reports ready. From a fresh clone,
run the complete Sprint 0 acceptance workflow with one command:

```bash
make sprint0-acceptance
```

This creates the ignored `.venv-sprint0`, installs development dependencies, starts and
health-checks PostgreSQL, runs Ruff and pytest, upgrades and checks Alembic, ingests the
same five games twice, validates exact counts, and prints game 778552. The Compose
database persists in the named `mlb_postgres_data` volume and listens on port 55432. The
Make target explicitly binds commands to that database so an existing ignored `.env`
cannot redirect acceptance to another local PostgreSQL instance.

The equivalent explicit commands are:

```bash
python3.12 -m venv .venv-sprint0
.venv-sprint0/bin/python -m pip install -e '.[dev]'
docker compose up -d --wait postgres
export MLB_DATABASE_URL=postgresql+psycopg://mlb:mlb@localhost:55432/mlb_predictor
.venv-sprint0/bin/ruff check .
.venv-sprint0/bin/ruff format --check .
.venv-sprint0/bin/pytest -q
.venv-sprint0/bin/alembic upgrade head
.venv-sprint0/bin/alembic check
.venv-sprint0/bin/mlb-predictor ingest-five
.venv-sprint0/bin/mlb-predictor ingest-five
.venv-sprint0/bin/mlb-predictor validate --expected-games 5
.venv-sprint0/bin/mlb-predictor show-game 778552
```

The ingestion command is deliberately bound to the five IDs in
`config/sprint0_games.json`; it cannot trigger a season download.

## 2025 historical layer

After Sprint 0 approval, the 2025 regular season can be reproduced and audited with:

```bash
export MLB_DATABASE_URL=postgresql+psycopg://mlb:mlb@localhost:55432/mlb_predictor
.venv-sprint0/bin/alembic upgrade head
.venv-sprint0/bin/mlb-predictor ingest-season --season 2025
.venv-sprint0/bin/mlb-predictor audit-season --season 2025 \
  --output data/interim/2025_season_audit.json
.venv-sprint0/bin/mlb-predictor freeze-raw --season 2025 \
  --output data/interim/2025_raw_manifest.json
```

The ingestion is restricted to 2025, caches responses under ignored `data/raw/`, and is
safe to rerun. The accepted counts and limitations are in `docs/SEASON_2025_AUDIT.md`.

## Leakage-safe 2025 features

```bash
export MLB_DATABASE_URL=postgresql+psycopg://mlb:mlb@localhost:55432/mlb_predictor
.venv-sprint0/bin/alembic upgrade head
.venv-sprint0/bin/mlb-predictor build-features --season 2025 --version sprint2_v1
.venv-sprint0/bin/mlb-predictor audit-features --version sprint2_v1 \
  --output data/interim/2025_feature_audit.json
```

The builder emits two rows per game and excludes all same-day outcomes. Definitions,
fallbacks, observed ranges, and limitations are in `docs/FEATURE_2025_AUDIT.md`.

## Sprint 3 chronological baseline evaluation

With the accepted 2025 database and immutable `sprint2_v1` snapshots present, reproduce
the complete modeling audit with:

```bash
make sprint3-audit
```

This installs bounded dependencies, starts PostgreSQL, runs Ruff, formatting, pytest,
and Alembic checks, re-audits `sprint2_v1`, then writes the ignored modeling dataset,
predictions, fitted models, and metadata under `data/processed/sprint3/`. It does not
rebuild features, mutate the frozen raw layer, or ingest data. See
`docs/MODEL_2025_AUDIT.md` for the split policy, comparisons, and limitations.

## Sprint 3.5 multi-season foundation

Seasons 2021–2025 are cached and audited independently. After those accepted database
rows and the three `sprint3_5_*` feature versions exist, reproduce the feature audit and
rolling-origin model audit with:

```bash
make sprint3-5-audit
```

All 2022–2025 evaluation origins are retrospective development evidence. The project
reserves 2026 live predictions, or another future locked period, for prospective testing.
See `docs/MULTISEASON_2021_2025_AUDIT.md`.

## Sprint 4 confirmed-lineup matchup layer

From the accepted 2021–2025 database and frozen raw caches, reproduce the normalized
matchup aggregates, versioned features, validation, and rolling-origin ablation with:

```bash
make sprint4-audit
```

The command reads cached completed-game feeds and does not download data or mutate the
frozen raw layer. It creates compact handedness and pitch-group aggregates, rebuilds
`sprint4_v1`, and writes ignored evaluation artifacts under `data/processed/sprint4/`.
The full feature bundle did not improve combined backtest Poisson deviance, so it is not
promoted over `sprint3_5_v1`. See `docs/SPRINT4_MATCHUP_AUDIT.md`.

## Sprint 5 starter and bullpen models

From the accepted normalized 2021–2025 database, reproduce the versioned pitching state,
component forecasts, validation, and downstream run-model ablation with:

```bash
make sprint5-audit
```

This does not download or modify raw data. Pitcher rolling history beat gradient boosting
for starter outs and pitch count; adding the complete bullpen/state bundle slightly
worsened combined run-model Poisson deviance, so it is not promoted wholesale. See
`docs/SPRINT5_PITCHING_AUDIT.md`.

## Sprint 5.5 downstream pitching ablation

Run the fixed eleven-subset downstream comparison from accepted `sprint3_5_v1` and
`sprint5_v1` with:

```bash
make sprint5-5-audit
```

No subset met the robust promotion standard. Available-reliever quality had the best
combined Poisson-deviance change but worsened three of four season origins, so no new
feature/model version was created. See `docs/SPRINT5_5_DOWNSTREAM_ABLATION.md`.

## Quality checks

```bash
.venv-sprint0/bin/ruff check .
.venv-sprint0/bin/ruff format --check .
.venv-sprint0/bin/pytest
```

Configuration is environment-based; see `.env.example`. The values committed in Compose
and `.env.example` are local-development defaults, not production credentials. Never
commit `.env`, real credentials, database files, raw/generated data, or environment folders.
