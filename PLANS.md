# Execution Plans

Use this file for substantial multi-step work. Keep the active plan updated as work proceeds.

## Completed plan: Sprint 0 — Foundation and controlled ingestion

**Status:** Completed 2026-08-03 and approved for Sprint 1.

**Cleanup/reproducibility pass:** Completed 2026-08-03. The legacy Python 3.10
environment was removed from the Git index without deleting its local files. Docker
Compose is now the sole supported PostgreSQL workflow, and `make sprint0-acceptance`
reproduces installation through the twice-ingested five-game audit.

Cleanup acceptance ran successfully through that exact Make target using Docker Engine
29.3.1 and PostgreSQL 16. Ruff and formatting passed, pytest reported 7 passed, Alembic
reported no pending upgrade operations, both ingestion passes completed, and validation
reported `PASS (5 games)` with 10 starters and 90 lineup entries.

The earlier agent-created `/tmp/mlb-sprint0-pg` server was stopped after it was found to
conflict with the Compose port. Final acceptance applied migration `0001` to the Compose
container itself and verified its table counts from inside that container.

### Goal

Create a reliable repository foundation and prove that MLB game identity, results, starting pitchers, starting lineups, teams, players, and venues can be reconstructed and joined for a small historical sample.

### Inputs already available

- Local project folder
- Git repository
- Python virtual environment
- PostgreSQL installation
- Private GitHub repository

### Work sequence

1. Inspect the existing repository and report what already exists.
2. Reconcile the repository with the target structure in `docs/ARCHITECTURE.md`.
3. Add dependency and development-tool configuration.
4. Add safe environment configuration.
5. Add SQLAlchemy database connection and Alembic.
6. Define the initial relational schema.
7. Implement an MLB Stats API client with timeout, retries, and validation.
8. Implement controlled ingestion for five selected completed regular-season games.
9. Populate teams, venues, players, games, starting pitchers, and starting lineups.
10. Add data-quality checks.
11. Run tests and display a human-readable sample game.
12. Update documentation and stop for user review.

### Five-game sample requirements

The sample should include, where practical:

- A normal nine-inning game
- A game that reached extra innings
- One game from a doubleheader
- A game in a retractable-roof venue
- A game involving the Chicago Cubs

If a selected game creates unnecessary API edge-case work before the basic path functions, begin with five ordinary completed games, then add edge cases one at a time.

### Acceptance criteria

- Five unique completed games are stored.
- Each game has exactly one home and one away team.
- Final team runs are nonnegative.
- Each game has one starting pitcher per team, or an explicitly logged exception.
- Each team has nine unique starting batting-order slots, or an explicitly logged exception.
- Starting players and pitchers resolve to MLB player IDs.
- Venue and team IDs resolve.
- Re-running ingestion does not create duplicates.
- A command can print one game with date, teams, score, venue, starters, and lineups.
- Tests pass.

### Stop condition

Do not ingest a full season until the user reviews the five-game audit.

### Completion record

- Promoted the handoff agreement, plan, and docs into the repository root.
- Added a Python 3.11+ `src/` package, environment settings, JSON logging, Ruff,
  pytest, pre-commit, and a local PostgreSQL Compose definition.
- Added SQLAlchemy models and Alembic revision `0001` for teams, players, venues,
  games, starting pitchers, and starting lineups.
- Added database constraints and cross-row acceptance validation for distinct teams,
  nonnegative scores, one starter on each side, and complete batting slots 1–9.
- Added an MLB Stats API client with timeouts and bounded retries, final/regular-season
  feed validation, per-game transactions, and idempotent child-row replacement.
- Bound `ingest-five` to exactly five unique IDs in `config/sprint0_games.json`.
- Ingested the manifest twice into PostgreSQL; counts remained 5 games, 10 starters,
  and 90 lineup entries.
- Acceptance validation passed and game 778552 was reconstructed successfully.
- Ruff and formatting checks passed; pytest passed 7 tests.

### Known limitations

- Historical records use the current MLB live-feed representation, not a captured
  T-minus-30 snapshot. Only actual starters and starting batting order are retained.
- Sprint 0 does not cache raw API responses; raw-source caching is scheduled for Sprint 1.
- Starter identity is the first pitcher in each completed game's boxscore pitcher list.
  This held for all five acceptance games but should be audited at season scale.
- The initial acceptance used an isolated PostgreSQL cluster because Docker was not
  running and Homebrew PostgreSQL was unhealthy. Docker Compose is now the only supported
  reproducible workflow; Homebrew and temporary clusters are explicitly unsupported.
- The legacy Python 3.10 `.venv` remains on the developer's disk but has been removed from
  Git's index and is ignored. Reproduction uses the separate ignored `.venv-sprint0`.

## Completed plan: Sprint 1 — One-season historical foundation

**Status:** Completed 2026-08-03. Awaiting review before Sprint 2 feature engineering.

After Sprint 0 approval:

1. Ingest the 2025 regular season.
2. Validate counts and exceptions.
3. Add player-game batting and pitching records.
4. Add raw-source caching.
5. Produce a season data-audit notebook or report.
6. Freeze the raw historical layer before feature engineering.

### Completion record

- Added Alembic revision `0002` and SQLAlchemy models for player-game batting and pitching.
- Added gzip-compressed atomic caching for the schedule and each game feed.
- Restricted discovery and the CLI to the 2025 completed MLB regular season.
- Ingested 2,430 games with zero exceptions, then reran all 2,430 from cache with stable counts.
- Stored 50,887 player-game batting and 20,865 player-game pitching records.
- Verified 30 teams at 162 games each, 4,860 starters, and 43,740 lineup entries.
- Reconciled batting runs and pitching runs allowed to every final team score with zero differences.
- Created a deterministic SHA-256 manifest for 2,431 raw cache objects.
- Published the detailed results and limitations in `docs/SEASON_2025_AUDIT.md`.
- Final verification: Ruff passed, format check passed, 10 tests passed, Alembic reported
  no pending operations, and the expanded season audit passed.

### Stop condition

Do not begin Sprint 2 feature engineering until the user reviews the 2025 season audit.

## Completed plan: Sprint 2 — Leakage-safe feature engine

**Status:** Completed 2026-08-03. Awaiting review before Sprint 3 model training.

### Completion record

- Added Alembic revision `0003` and versioned `pregame_feature_snapshots`.
- Built 4,860 stacked team-game rows covering all 2,430 games.
- Added prior team offense, lineup, opposing starter, opposing bullpen, venue/home, rest,
  sample-size, fallback, as-of, and source-date fields.
- Conservatively excluded every same-day outcome, including Game 1 from doubleheader Game 2.
- Added fixed and expanding-league cold-start fallbacks with explicit fallback counts.
- Verified zero as-of violations, zero source-date violations, and zero non-finite rows.
- Rebuilt the complete table with the same value checksum (`ad1b24be20ea4779c7fb249e0c948388`).
- Final verification: Ruff passed, formatting passed, 11 tests passed, and Alembic reported
  no schema drift.
- Published feature definitions, ranges, limitations, and audit results in
  `docs/FEATURE_2025_AUDIT.md`.

### Stop condition

Do not begin Sprint 3 baseline model training until the user reviews the feature audit.

## Completed plan: Sprint 3 — Baseline forecasting and chronological evaluation

**Status:** Completed 2026-08-03. Awaiting review before any Sprint 4 work.

### Completion record

- Consumed `sprint2_v1` without rebuilding or changing the feature store or frozen raw data.
- Produced a deterministic 4,860-row stacked team-game dataset with `runs_scored` target.
- Used expanding June, July, and August development folds after a March 18–May 31 warm-up,
  then opened an untouched September 1–28 test block only after development selection.
- Compared league-average, team rolling-average, raw and stabilized Poisson, stabilized
  negative-binomial, and stabilized histogram gradient-boosting models.
- Evaluated MAE, RMSE, mean bias, Poisson deviance, and distribution-appropriate NLL.
- Selected the league-average baseline on development Poisson deviance. Stabilized Poisson
  was the best nonconstant model and improved materially over raw Poisson, but did not beat
  the simple baseline.
- Added month, home/away, fallback, starter-history, and predicted-range error slices.
- Saved the dataset, predictions, models, configuration, dates, seed, dependencies,
  metrics, and limitations under ignored `data/processed/sprint3/`.
- Added split, fitting-boundary, reproducibility, nonnegative-prediction, and target-outcome
  invariance tests. Full results are in `docs/MODEL_2025_AUDIT.md`.

### Stop condition

Do not begin advanced lineup weighting, Statcast, weather, pitcher clustering, simulation,
API, dashboard, or other Sprint 4+ work until the user reviews this Sprint 3 audit.
