# Roadmap

## Sprint 0 — Repository and five-game ingestion

**Completed 2026-08-03; awaiting review.** Delivered the typed local foundation and
reconstructed five historical games, including ordinary, extra-inning, doubleheader,
retractable-roof, and Cubs cases. Acceptance passed after an idempotent rerun.

## Sprint 1 — 2025 historical data foundation

**Do not begin until the user approves Sprint 0.**

Ingest 2025 regular-season games, starters, lineups, player-game batting, player-game pitching, and relevant reference data.

## Sprint 2 — Leakage-safe feature engine

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

Build and compare:

- League-average baseline
- Rolling-average baseline
- Poisson regression
- Negative-binomial regression
- Gradient boosting

Use chronological validation.

## Sprint 4 — Confirmed-lineup matchup engine

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
