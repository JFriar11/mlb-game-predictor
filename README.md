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

## Quality checks

```bash
.venv-sprint0/bin/ruff check .
.venv-sprint0/bin/ruff format --check .
.venv-sprint0/bin/pytest
```

Configuration is environment-based; see `.env.example`. The values committed in Compose
and `.env.example` are local-development defaults, not production credentials. Never
commit `.env`, real credentials, database files, raw/generated data, or environment folders.
