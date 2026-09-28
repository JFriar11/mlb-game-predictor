# MLB Game Predictor

An end-to-end MLB pregame forecasting system that predicts **team run distributions and game win probabilities** using only information available before first pitch.

The project covers the complete modeling lifecycle: MLB data ingestion, PostgreSQL storage, leakage-safe feature engineering, model development, chronological validation, run-distribution modeling, simulation, probability calibration, and live prediction.

## Overview

The goal of this project is to build a reproducible MLB game prediction system while treating the problem as more than a binary win/loss classification task.

The modeling pipeline is:

**MLB data → Pregame features → Expected runs → Run distributions → Win probability → Calibration**

Rather than directly predicting which team will win, the system first estimates each team's expected runs. Those estimates are converted into full scoring distributions, which can then be used to calculate game win probabilities and other probabilistic outputs.

A major focus throughout development is **data integrity and leakage prevention**. Features are constructed using only information that would have been available before the game being predicted, and model evaluation uses chronological rather than random train/test splits.

## Modeling Approach

### 1. Expected Runs — Gradient Boosting

The accepted mean model uses **gradient-boosted trees** to estimate expected runs for each team.

Gradient boosting was selected because baseball performance contains nonlinear relationships and interactions between offensive, pitching, bullpen, park, and game-context variables that are difficult to specify manually.

Model development also compared simpler alternatives, including:

* League-average baselines
* Team rolling averages
* Poisson regression
* Negative-binomial regression
* Gradient boosting

Importantly, model complexity was only retained when supported by chronological evaluation. Several feature additions and model variants were rejected because they failed to improve out-of-sample performance consistently.

### 2. Run Distributions — Negative Binomial

A point estimate of expected runs does not capture the uncertainty inherent in baseball scoring.

Historical scoring data was substantially overdispersed:

| Statistic       |   Runs |
| --------------- | -----: |
| Mean            |  4.435 |
| Variance        | 10.037 |
| Variance / Mean |  2.263 |

Because the variance substantially exceeds the mean, a **negative-binomial distribution** provides a better representation of run scoring than the standard Poisson assumption.

Across rolling-origin evaluation:

| Distribution      |  Count NLL |        RPS |
| ----------------- | ---------: | ---------: |
| Poisson           |     2.5746 |     1.7089 |
| Negative Binomial | **2.4132** | **1.6582** |

Negative binomial outperformed Poisson on both metrics in all four evaluated seasons.

### 3. Win Probability

Home and away run distributions are combined to calculate regulation game probabilities.

Historical analysis found little evidence that an additional shared-game scoring dependence adjustment was justified, so regulation scoring distributions are modeled independently.

Regulation ties are handled using the historical home win rate in prior extra-inning games from the applicable training data.

The system supports both:

* Analytic win-probability calculation
* Monte Carlo game simulation

Analytic probabilities are preferred for displayed win probabilities, while simulation can be used for score-frequency and distribution analysis.

### 4. Probability Calibration

Raw game probabilities were evaluated using nested chronological calibration.

The project compared:

* Raw probabilities
* Platt scaling
* Beta calibration
* Isotonic regression

Platt scaling produced the strongest overall calibration results:

| Method    |       Brier |    Log Loss |         ECE |
| --------- | ----------: | ----------: | ----------: |
| Raw       |     0.24558 |     0.68432 |     0.02944 |
| **Platt** | **0.24485** | **0.68266** | **0.01717** |
| Beta      |     0.24545 |     0.68403 |     0.01939 |
| Isotonic  |     0.24770 |     0.73238 |     0.03280 |

Platt scaling was therefore selected for the frozen model specification.

## Final Retrospective Results

The final accepted system was evaluated retrospectively using MLB data from **2021–2025**, with rolling chronological evaluation beginning in 2022.

### Run Prediction

| Metric           |      Result |
| ---------------- | ----------: |
| MAE              |  **2.4488** |
| RMSE             |  **3.1304** |
| Bias             | **-0.0387** |
| Poisson Deviance |  **2.2765** |

For comparison, the league-average reference produced a Poisson deviance of **2.3313**.

### Run Distribution

| Metric    | Negative Binomial | Poisson |
| --------- | ----------------: | ------: |
| Count NLL |        **2.4132** |  2.5746 |
| RPS       |        **1.6582** |  1.7089 |

Negative-binomial interval coverage was:

* 50% interval → **56.1% observed coverage**
* 80% interval → **81.8% observed coverage**
* 95% interval → **97.0% observed coverage**

### Win Probability

After nested Platt calibration:

* **Brier Score:** 0.24485
* **Log Loss:** 0.68266
* **Expected home-win rate:** 52.87%
* **Observed home-win rate:** 52.92%

All 2021–2025 results are treated as **retrospective development evidence**. The 2026 season was reserved for prospective evaluation rather than repeatedly used during model development.

## Feature Engineering

The system builds pregame features covering several areas of team and game performance, including:

### Offense

* Prior team offensive performance
* Starting-lineup information
* Player-level historical production
* Sample-size stabilization

### Starting Pitching

* Starter historical performance
* Recent workload
* Rest
* Expected workload proxies

### Bullpen

* Recent bullpen workload
* Reliever availability
* Reliever quality
* Pitching-state features

### Game Environment

* Home/away context
* Venue
* Prior-date park effects
* Available environmental context

All features follow a strict rule:

> **A prediction may only use information that would have been available before the game being predicted.**

Same-day outcomes and future information are excluded from feature construction.

## Evaluation Strategy

Random train/test splitting is intentionally avoided.

Baseball data is inherently temporal, so random splitting can allow future information or future data distributions to influence evaluation unrealistically.

Instead, the project uses **rolling-origin chronological validation**:

1. Train using historical seasons/data.
2. Predict a future chronological period.
3. Advance the training boundary.
4. Repeat.
5. Aggregate performance across evaluation origins.

Calibration follows the same principle and is fit only using data available before its corresponding evaluation period.

This produces a more realistic approximation of how the system would have performed if deployed at that point in time.

## Model Development Philosophy

An important goal of this project is not simply to add as many baseball features or complex models as possible.

New components are promoted only when supported by out-of-sample evidence.

During development, several seemingly useful additions failed to meet that standard. For example:

* Confirmed-lineup matchup features did not improve combined backtest Poisson deviance.
* The complete starter/bullpen feature bundle slightly worsened downstream run prediction.
* No pitching-feature subset met the required promotion standard.
* Observed historical weather was not promoted because it was not equivalent to an archived pregame weather forecast.
* More complex dispersion approaches produced negligible improvements over the simpler global negative-binomial specification.

These experiments remain documented because unsuccessful modeling decisions are still useful evidence about the problem.

## Technology

The project is built primarily with:

* **Python 3.11+**
* **PostgreSQL**
* **SQLAlchemy**
* **Alembic**
* **scikit-learn**
* **MLB Stats API**
* **Docker / Docker Compose**
* **pytest**
* **Ruff**

The codebase uses versioned feature sets, database migrations, reproducible evaluation commands, structured configuration, automated testing, and deterministic model artifacts.

## Project Development

The system was developed incrementally through a series of audited stages:

| Stage            | Focus                                  |
| ---------------- | -------------------------------------- |
| Sprint 0         | Database and ingestion foundation      |
| Historical Layer | 2025 season ingestion and auditing     |
| Sprint 2         | Leakage-safe feature engineering       |
| Sprint 3         | Initial chronological model evaluation |
| Sprint 3.5       | Multi-season modeling foundation       |
| Sprint 4         | Lineup and matchup features            |
| Sprint 5         | Starter and bullpen models             |
| Sprint 5.5       | Pitching-feature ablation              |
| Sprint 6         | Park and environmental context         |
| Sprint 7         | Run distributions and simulation       |
| Sprint 8         | Calibration and frozen specification   |
| Live Pipeline    | Pregame prediction workflow            |

Detailed methodology, results, rejected experiments, and limitations are available in the corresponding files under `docs/`.

## Reproducing the Model

### Requirements

* Python 3.11+
* Docker Desktop or another Docker engine with Compose
* PostgreSQL through the repository's Docker Compose configuration

### Initial Setup

Start Docker and run:

```bash
make sprint0-acceptance
```

This creates the project environment, installs development dependencies, starts PostgreSQL, runs quality checks and tests, applies database migrations, and validates the initial ingestion workflow.

### Historical Data

To ingest and audit the 2025 regular season:

```bash
export MLB_DATABASE_URL=postgresql+psycopg://mlb:mlb@localhost:55432/mlb_predictor

.venv-sprint0/bin/alembic upgrade head
.venv-sprint0/bin/mlb-predictor ingest-season --season 2025
.venv-sprint0/bin/mlb-predictor audit-season --season 2025 \
  --output data/interim/2025_season_audit.json
```

### Modeling Audits

Major stages can be reproduced using:

```bash
make sprint3-audit
make sprint3-5-audit
make sprint4-audit
make sprint5-audit
make sprint5-5-audit
make sprint6-audit
make sprint7-audit
make sprint8-audit
```

Each stage preserves accepted upstream artifacts and writes its own evaluation outputs.

## Documentation

More detailed technical documentation is available in `docs/`, including:

* `SEASON_2025_AUDIT.md` — historical ingestion and data-quality audit
* `FEATURE_2025_AUDIT.md` — feature definitions and leakage controls
* `MODEL_2025_AUDIT.md` — initial chronological modeling evaluation
* `MULTISEASON_2021_2025_AUDIT.md` — multi-season evaluation
* `SPRINT4_MATCHUP_AUDIT.md` — lineup and matchup experiments
* `SPRINT5_PITCHING_AUDIT.md` — starter and bullpen modeling
* `SPRINT5_5_DOWNSTREAM_ABLATION.md` — pitching-feature ablations
* `SPRINT6_ENVIRONMENT_AUDIT.md` — park/environment analysis
* `SPRINT7_DISTRIBUTION_SIMULATION_AUDIT.md` — run distributions and simulation
* `SPRINT8_FINAL_RETROSPECTIVE_AUDIT.md` — calibration and final retrospective system
* `LIVE_OPERATIONS.md` — live prediction operations

## Quality Checks

```bash
.venv-sprint0/bin/ruff check .
.venv-sprint0/bin/ruff format --check .
.venv-sprint0/bin/pytest
```

Automated tests cover areas including chronological boundaries, feature leakage, deterministic predictions, positive run forecasts, database behavior, and reproducibility.

## Limitations

The project has several important limitations:

* Historical lineups are reconstructed rather than archived snapshots from a specific pregame timestamp.
* Regulation home and away scoring distributions are modeled independently.
* Extra innings use an approximation rather than explicitly modeling innings, ghost runners, and reliever usage.
* The terminal 12+ run bucket is censored.
* Historical observed weather is not treated as equivalent to information that would have been available from a pregame forecast.
* Retrospective 2021–2025 results should not be interpreted as prospective performance.

These limitations are intentionally documented rather than hidden, and the system is designed so that future versions can address them without contaminating previous evaluation evidence.

## Repository Principles

This project prioritizes:

**Leakage prevention · Chronological validation · Reproducibility · Calibration · Honest model comparison · Baseball-specific feature engineering**

The goal is not simply to produce a winning prediction, but to build a forecasting system whose assumptions, uncertainty, and performance can be examined and reproduced.
