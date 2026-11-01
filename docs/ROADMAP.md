# Roadmap

## Resumption — 2026-11-01

Repository readiness audit completed: 31 tests, Ruff, formatting, CLI loading, and
the local frozen-artifact checksum passed. Docker was unavailable, so persisted
database and live-operation state remain unverified. See
[COMPLETION_PLAN.md](COMPLETION_PLAN.md) for the remaining release gates, beginning
with Sprint 10B reproducible runtime and PostgreSQL acceptance. Hosting approval
remains outstanding; this resumption does not authorize paid infrastructure.

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

**Completed and approved 2026-08-04.** Chronologically compared six
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

**Completed and approved 2026-08-04.** Added separately cached and hashed 2021–2024
seasons, rule-era metadata, versioned prior-history features, and rolling-origin 2022–2025
development backtests. See `docs/MULTISEASON_2021_2025_AUDIT.md`.

## Sprint 4 — Confirmed-lineup matchup engine

**Completed and approved 2026-08-12.** Added a separately versioned,
leakage-safe confirmed-lineup matchup layer from cached feeds. The full feature bundle
did not improve the combined rolling-origin backtest and was not promoted. See
`docs/SPRINT4_MATCHUP_AUDIT.md`.

Add:

- Empirical batting-order weights
- Handedness splits with shrinkage
- Projected lineup plate appearances
- Pitch mix and batter pitch-type performance
- Sample-size fallback hierarchy

## Sprint 5 — Starter and bullpen models

**Completed and approved 2026-08-12 as a component milestone.** Built leakage-safe starter
length, pitch-count, hook, bullpen workload, availability, role-proxy, and quality-mixture
state. Simple pitcher rolling forecasts beat gradient boosting, and the full downstream
state bundle was not promoted. See `docs/SPRINT5_PITCHING_AUDIT.md`.

## Sprint 5.5 — Downstream pitching-state ablation

**Completed and approved 2026-08-12.** Compared eleven predeclared
pitching subsets against immutable `sprint3_5_v1`. No subset improved robustly enough for
promotion; no new feature/model version was created. See
`docs/SPRINT5_5_DOWNSTREAM_ABLATION.md`.

Add:

- Starter outs distribution
- Pitch-count estimate
- Manager hook tendencies
- Bullpen availability
- Reliever role inference
- Expected bullpen innings and quality mixture

## Sprint 6 — Run environment

**Completed and approved 2026-08-13 as component research.** Built prior-date park context
and audited venue/weather proxies. Observed weather showed retrospective signal but was
not production-compatible; park adjustments worsened. See `docs/SPRINT6_ENVIRONMENT_AUDIT.md`.

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

**Completed and approved 2026-08-13.** Selected a fold-only global
negative-binomial distribution, found negligible paired residual dependence, and validated
analytic and simulated win probabilities. See `docs/SPRINT7_DISTRIBUTION_SIMULATION_AUDIT.md`.

Compare:

- Poisson
- Negative binomial
- Feature-dependent dispersion
- Direct run probability classification
- Correlated or joint score approaches

Handle ties and extra innings.

## Sprint 8 — Calibration and final backtest

**Completed 2026-08-13; awaiting review.** Selected nested chronological Platt calibration,
froze the prospective specification, and added the prediction-record contract. See
`docs/SPRINT8_FINAL_RETROSPECTIVE_AUDIT.md`.

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

**Completed 2026-08-13; awaiting review.** Added CLI discovery, confirmed-lineup gating,
frozen-model prediction, immutable official records, settlement, and prospective scoring.

Automate:

- Daily game discovery
- Confirmed lineup detection
- Starter confirmation
- Weather retrieval
- Bullpen state
- Feature generation
- Predictions
- Data-quality warnings

## Sprint 9.5 — 2026 state bootstrap and prospective launch

**Completed 2026-08-13; awaiting review.** Bootstrapped and audited 2026 state, persisted
the launch boundary, and added repeat-safe daily and settlement commands.

## Sprint 10A — Automated live prediction operations

**Completed 2026-08-13; awaiting hosting approval.** Added restart-safe polling, timing
classes, checksum enforcement, watcher health, prospective ledger separation, and operations
commands. No cloud resources were created.

## Sprint 10A.5 — Hosting and cost decision

**Completed 2026-08-13; awaiting architecture approval.** Priced the measured watcher
workload and selected Azure Container Apps scheduled Jobs with Azure PostgreSQL Flexible
Server as the best overall/easiest operational architecture. A slim Neon database is the
documented cheapest acceptable alternative. No resources were provisioned. See
`docs/SPRINT10A_5_HOSTING_COST_DECISION.md`.

## Sprint 10 — Application and deployment

**Sprint 10B completed and approved 2026-11-01.** Added pinned runtime and
wheel/container packaging, isolated PostgreSQL persistence and dump/restore
acceptance, and frozen-artifact host/container inference checks. See
`SPRINT10B_RUNTIME_AUDIT.md`.

**Sprint 10C completed and approved 2026-11-01.** Added a typed read-only
FastAPI service for accepted official predictions, game detail, model metadata,
and health/readiness. Verified PostgreSQL read-only enforcement and real container
HTTP operation. See `SPRINT10C_API_AUDIT.md`. Next: Sprint 10D explanations,
confidence reporting, and product semantics.

**Sprint 10D completed and approved 2026-11-01.** Added immutable optional
prediction-time input evidence, baseball input summaries, qualified confidence
components, and uncensored marginal run ranges. Isolated acceptance and additive
local database migration passed; no old inputs were reconstructed. See
`SPRINT10D_EXPLANATION_AUDIT.md`. Next: Sprint 10E React dashboard.

**Sprint 10E completed 2026-11-01; awaiting review.** Added the local React
dashboard with typed/runtime-validated API reads, date/game navigation, probability
and evidence views, honest missing/stale/error states, and an explicit synthetic
demo. Production build, browser/accessibility checks, and the real local API proxy
passed. See `SPRINT10E_DASHBOARD_AUDIT.md`. Next: Sprint 10F release/hosting preparation.

Build:

- FastAPI
- React
- PostgreSQL
- Azure deployment
- Scheduling
- Monitoring
- Model and pipeline version display

**Sprint 10E approved; Sprint 10F release preparation completed 2026-11-01.**
Private release packaging, offline infrastructure policy checks and normalized
state recovery are prepared. Hosting deployment, monitoring configuration,
season rollover review and genuine prospective acceptance remain outstanding.
See `RELEASE.md` and `HOSTING_REVIEW_2026_11.md`. Stop for provider/budget/access
selection before creating resources or publishing images.

**Local sandbox milestone (2026-11-01):** User selected local operation. Optional
custom-lineup inference is implemented over the accepted model with known-player
entry, retained-lineup suggestions, prior-date cutoffs and clearly hypothetical,
unsaved results. Cloud deployment is deferred. See `SANDBOX.md` for use/limits;
next recommended action is local user acceptance, not new modeling or ingestion.
