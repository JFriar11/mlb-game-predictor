PYTHON ?= python3.12
VENV ?= .venv-sprint0
BIN := $(VENV)/bin
SPRINT0_DATABASE_URL := postgresql+psycopg://mlb:mlb@localhost:55432/mlb_predictor
export MLB_DATABASE_URL := $(SPRINT0_DATABASE_URL)

.PHONY: sprint0-acceptance sprint3-audit sprint3-5-audit sprint4-audit sprint5-audit sprint5-5-audit sprint6-audit sprint7-audit sprint8-audit sprint9-audit sprint9-5-audit install postgres quality migrate ingest validate show

# One-command Sprint 0 reproduction from a fresh clone (with Docker running).
sprint0-acceptance: install postgres quality migrate ingest validate show

# Reproduce Sprint 3 from an accepted database containing sprint2_v1.
sprint3-audit: install postgres quality migrate
	$(BIN)/mlb-predictor audit-features --version sprint2_v1
	LOKY_MAX_CPU_COUNT=1 $(BIN)/mlb-predictor evaluate-baselines \
		--output-dir data/processed/sprint3

# Reproduce Sprint 3.5 after the separately audited 2021-2025 data are present.
sprint3-5-audit: install postgres quality migrate
	$(BIN)/mlb-predictor audit-features --version sprint3_5_v1
	LOKY_MAX_CPU_COUNT=1 $(BIN)/mlb-predictor evaluate-multiseason \
		--output-dir data/processed/sprint3_5

# Rebuild and audit Sprint 4 from the accepted 2021-2025 cache and database.
sprint4-audit: install postgres quality migrate
	$(BIN)/mlb-predictor build-matchup-aggregates
	$(BIN)/mlb-predictor build-matchup-features
	$(BIN)/mlb-predictor audit-matchups
	LOKY_MAX_CPU_COUNT=1 $(BIN)/mlb-predictor evaluate-matchups \
		--output-dir data/processed/sprint4

# Rebuild and audit Sprint 5 from the accepted normalized 2021-2025 database.
sprint5-audit: install postgres quality migrate
	$(BIN)/mlb-predictor build-pitching-features
	$(BIN)/mlb-predictor audit-pitching-features
	LOKY_MAX_CPU_COUNT=1 $(BIN)/mlb-predictor evaluate-pitching \
		--output-dir data/processed/sprint5

# Run the fixed Sprint 5.5 downstream ablation without rebuilding components.
sprint5-5-audit: install postgres quality migrate
	LOKY_MAX_CPU_COUNT=1 $(BIN)/mlb-predictor evaluate-pitching-ablation \
		--output-dir data/processed/sprint5_5

sprint6-audit: install postgres quality migrate
	$(BIN)/mlb-predictor build-environment-features
	$(BIN)/mlb-predictor audit-environment-features
	LOKY_MAX_CPU_COUNT=1 $(BIN)/mlb-predictor evaluate-environment \
		--output-dir data/processed/sprint6

sprint7-audit: install postgres quality migrate
	LOKY_MAX_CPU_COUNT=1 $(BIN)/mlb-predictor evaluate-distributions \
		--output-dir data/processed/sprint7

sprint8-audit: install postgres quality migrate sprint7-audit
	$(BIN)/mlb-predictor evaluate-calibration --output-dir data/processed/sprint8

sprint9-audit: install postgres quality migrate
	$(BIN)/mlb-predictor freeze-accepted-model
	$(BIN)/mlb-predictor predict-date --date 2026-08-13 --dry-run

sprint9-5-audit: install postgres quality migrate
	$(BIN)/mlb-predictor audit-season --season 2026 \
		--output data/processed/sprint9_5/season_2026_audit.json
	$(BIN)/mlb-predictor evaluate-live

install:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/python -m pip install -e '.[dev]'

postgres:
	docker compose up -d --wait postgres

quality:
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .
	$(BIN)/pytest -q

migrate:
	$(BIN)/alembic upgrade head
	$(BIN)/alembic check

ingest:
	$(BIN)/mlb-predictor ingest-five
	$(BIN)/mlb-predictor ingest-five

validate:
	$(BIN)/mlb-predictor validate --expected-games 5

show:
	$(BIN)/mlb-predictor show-game 778552
