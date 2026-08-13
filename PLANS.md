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

## Completed plan: Sprint 3.5 — Multi-season data and evaluation foundation

**Status:** Completed and approved 2026-08-04.

- Added and independently audited 2021–2024 alongside unchanged raw 2025 artifacts.
- Added rule-era game metadata and explicit cancelled/special-venue handling.
- Built 24,296 rows for each separately versioned decay, no-decay, and cold-start feature
  treatment; `sprint2_v1` remains intact.
- Ran rolling origins that train only on prior seasons and evaluate 2022, 2023, 2024,
  then 2025. No period is described as untouched prospective performance.
- Gradient boosting led combined development Poisson deviance, while prior history and
  offseason decay helped stabilized Poisson. A raw numeric season indicator did not help.
- Reserved 2026 live predictions or another future locked period for prospective evidence.

### Stop condition

Stop for review. Do not begin Sprint 4 or any advanced feature/model/application work.

## Completed plan: Sprint 4 — Confirmed-lineup matchup engine

**Status:** Completed 2026-08-04 and approved 2026-08-12.

- Preserved `sprint3_5_v1` and the frozen raw caches; created `sprint4_v1` separately.
- Replayed cached feeds into compact, idempotent batter-handedness and player pitch-group
  aggregates without downloading new data.
- Added empirical prior batting-order weights, projected lineup plate appearances,
  shrunk batter-versus-hand rates, starter pitch mix, lineup pitch-group response,
  sample sizes, and explicit fallback counts.
- Enforced prior-date state updates, including same-day doubleheader isolation, and
  retained the existing offseason decay policy.
- Ran 2022–2025 rolling-origin comparisons for all five baseline/model families and exact
  `sprint3_5_v1` versus `sprint4_v1` ablations for stabilized Poisson and gradient boosting.
- The full bundle worsened combined Poisson deviance by 0.0409 for stabilized Poisson and
  0.00465 for gradient boosting. It is retained as an audited experiment, not promoted.

### Stop condition

Stop for review. Do not begin Sprint 5 starter/bullpen modeling or later roadmap work.

## Completed plan: Sprint 5 — Starter and bullpen models

**Status:** Completed and approved 2026-08-12 as a component-model milestone.

- Added a separate `sprint5_v1` pitching-state table without modifying accepted feature
  versions or frozen raw caches.
- Built 24,296 defense-team snapshots with starter length/pitch history, team hook proxies,
  recent bullpen workload, availability proxies, prior-usage role inference, and an
  available-reliever quality mixture.
- Enforced strict prior-date updates and preserved same-day doubleheader isolation.
- Compared league means, pitcher rolling forecasts, and gradient boosting at rolling
  2022–2025 origins. Pitcher rolling history won for both starter outs and pitch count.
- Derived expected bullpen outs from scheduled game length and the selected starter-outs
  forecast; evaluated residual-based 80% and 95% starter-outs intervals.
- Adding the full pitching-state bundle to the accepted gradient-boosting run model worsened
  combined Poisson deviance by 0.00525, so the bundle was not promoted wholesale.
- Explicitly excluded nine missing component targets where the listed starter faced no
  batter and recorded no out; their pregame feature rows remain present and valid.

### Stop condition

Stop for review. Do not begin Sprint 6 run-environment work or later roadmap work.

## Completed plan: Sprint 5.5 — Downstream pitching-state ablation

**Status:** Completed and approved 2026-08-12.

- Predeclared eleven individual and compact pitching-state additions plus the immutable
  `sprint3_5_v1` baseline before evaluation.
- Reused the exact accepted histogram gradient-boosting configuration and 2022–2025
  rolling-origin protocol; component models were not redesigned or tuned.
- Reported Poisson deviance, MAE, RMSE, bias, count NLL, seasons, and four requested slices.
- Available-reliever quality had the largest combined improvement (`-0.00337` Poisson
  deviance), but worsened 2023–2025 and therefore did not meet the clear-promotion bar.
- No new feature/model version was created. All Sprint 5 additions remain component-only;
  available-reliever quality is retained as the leading prospective-confirmation candidate.

### Stop condition

Stop for review. Do not begin Sprint 6 or any weather, park, simulation, API, or dashboard work.

## Completed plan: Sprint 6 — Run environment

**Status:** Completed and approved 2026-08-13 as a component-research milestone.

- Built 12,148 versioned prior-date park and cached-feed environment snapshots.
- Compared rolling park, venue physical, observed-weather proxy, raw bundle, modular park,
  and park-adjusted rolling architectures against immutable `sprint3_5_v1`.
- Weather proxies improved combined deviance by 0.00775 but were not promoted because they
  are completed-feed observations rather than archived pregame forecasts.
- Venue physical attributes improved by 0.00402 but overlap learned venue identity.
- Rolling and modular park adjustments worsened, confirming double-counting risk.
- Humidity, pressure, explicit roof state, and independent defense data remain unavailable.

### Stop condition

Stop for review. Do not begin Sprint 7 simulation/distribution or application work.

## Completed plan: Sprint 7 — Run distribution and game simulation

**Status:** Completed and approved 2026-08-13.

- Consumed immutable `sprint3_5_v1` and its accepted gradient-boosting mean configuration.
- Compared Poisson, global fold-only negative binomial, recent-training-season negative
  binomial, and a smoothed direct 0–12+ discrete distribution.
- Selected global fold-only negative binomial for robustness: it materially improved NLL
  and ranked probability score in every season without evaluation-fold parameter fitting.
- Verified material overdispersion and near-zero paired scoring-residual dependence.
- Added exact analytic win probabilities, a prior-extra-inning home-win approximation,
  and deterministic regulation simulations validated against analytic probabilities.
- Evaluated win Brier score, log loss, calibration, intervals, and simulation stability.

### Stop condition

Stop for review. Do not begin Sprint 8 calibration/final backtest or application work.

## Completed plan: Sprint 8 — Calibration and final retrospective backtest

**Status:** Completed 2026-08-13. Awaiting review before prospective work.

- Used distinct prior-season model fitting, first-40%-of-dates calibration, and remaining-date evaluation.
- Selected Platt calibration over raw, isotonic, and beta alternatives.
- Re-audited negative-binomial intervals and retrospective point/distribution metrics.
- Froze `accepted_v1_2026_prospective` in `config/accepted_model_v1.json`.
- Added migration `0010` and the prospective prediction-record contract without automation.
- Defined prospective, multi-metric future promotion requirements.

### Stop condition

Stop for review. Do not begin live automation, APIs, dashboard, cloud, or new model research.
