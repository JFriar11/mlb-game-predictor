# Roadmap

## Sprint 0 — Repository and five-game ingestion

**Completed and approved 2026-08-03.** Delivered the typed local foundation and
reconstructed five historical games, including ordinary, extra-inning, doubleheader,
retractable-roof, and Cubs cases. Acceptance passed after an idempotent rerun.

## Sprint 1 — 2025 historical data foundation

**Completed and approved 2026-08-03.** Ingested all 2,430 games with
starters, lineups, player-game batting, player-game pitching, raw caching, an idempotent
rerun, and a passing season audit. See `docs/SEASON_2025_AUDIT.md`.

## Sprint 2 — Leakage-safe feature engine

**Completed and approved 2026-08-03.** Built and audited 4,860
versioned pregame feature rows with strict prior-date cutoffs and explicit fallbacks. See
`docs/FEATURE_2025_AUDIT.md`.

Create as-of rolling features using only information available before each game.

Initial features:

- Team offense rolling averages
- Batter rolling metrics
- Starter rolling metrics
- Basic bullpen rolling quality and workload
- Home-field indicator
- Venue and basic park context
- Rest and schedule context

## Sprint 3 — Baseline forecasting system

**Completed 2026-08-03; awaiting review before Sprint 4.** Chronologically compared six
baseline/model variants on immutable `sprint2_v1`. The league-average baseline won the
development selection metric; stabilized Poisson was the best nonconstant model. See
`docs/MODEL_2025_AUDIT.md`.

Build and compare:

- League-average baseline
- Rolling-average baseline
- Poisson regression
- Negative-binomial regression
- Gradient boosting

Use chronological validation.

## Sprint 3.5 — Multi-season data and evaluation foundation

**Completed 2026-08-03; awaiting review.** Added separately cached and hashed 2021–2024
seasons, rule-era metadata, versioned prior-history features, and rolling-origin 2022–2025
development backtests. See `docs/MULTISEASON_2021_2025_AUDIT.md`.

## Sprint 4 — Confirmed-lineup matchup engine

Sprint 4 remains deferred pending review of Sprint 3.5.

Add:

- Empirical batting-order weights
- Handedness splits with shrinkage
- Projected lineup plate appearances
- Pitch mix and batter pitch-type performance
- Sample-size fallback hierarchy

## Sprint 5 — Starter and bullpen models

Add:

- Starter outs distribution
- Pitch-count estimate
- Manager hook tendencies
- Bullpen availability
- Reliever role inference
- Expected bullpen innings and quality mixture

## Sprint 6 — Run environment

Add:

- Park factors
- Roof state
- Temperature
- Humidity
- Pressure
- Stadium-oriented wind components
- Altitude
- Defense

Compare raw-feature and modular adjustment architectures to avoid double counting.

## Sprint 7 — Run distributions and simulation

Compare:

- Poisson
- Negative binomial
- Feature-dependent dispersion
- Direct run probability classification
- Correlated or joint score approaches

Handle ties and extra innings.

## Sprint 8 — Calibration and final backtest

Evaluate:

- MAE and RMSE
- Poisson deviance
- Log likelihood
- Brier score
- Log loss
- Calibration
- Prediction interval coverage
- Performance slices

Freeze an untouched final test period.

## Sprint 9 — Live prediction pipeline

Automate:

- Daily game discovery
- Confirmed lineup detection
- Starter confirmation
- Weather retrieval
- Bullpen state
- Feature generation
- Predictions
- Data-quality warnings

## Sprint 10 — Application and deployment

Build:

- FastAPI
- React
- PostgreSQL
- Azure deployment
- Scheduling
- Monitoring
- Model and pipeline version display
