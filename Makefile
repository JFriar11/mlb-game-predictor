PYTHON ?= python3.12
VENV ?= .venv-sprint0
BIN := $(VENV)/bin
SPRINT0_DATABASE_URL := postgresql+psycopg://mlb:mlb@localhost:55432/mlb_predictor
export MLB_DATABASE_URL := $(SPRINT0_DATABASE_URL)

.PHONY: sprint0-acceptance install postgres quality migrate ingest validate show

# One-command Sprint 0 reproduction from a fresh clone (with Docker running).
sprint0-acceptance: install postgres quality migrate ingest validate show

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
