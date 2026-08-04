# MLB Game Predictor — Codex Working Agreement

## Mission

Build a production-quality, leakage-controlled MLB pregame forecasting system that produces predictions approximately 30 minutes before first pitch, after confirmed starting lineups are available.

The final system should estimate:

- Expected runs for each team
- Full run distributions
- Home and away win probabilities
- Most likely scores
- 80% and 95% run ranges
- Baseball-grounded key factors
- A calibrated confidence indicator

The project is intended to be a flagship portfolio project for sports analytics, MLB R&D, applied AI, data science, and ML engineering roles.

## Required working style

Work collaboratively and incrementally.

For every milestone:

1. Inspect the repository and relevant documentation.
2. Explain the proposed approach before making large architectural changes.
3. Implement one coherent milestone at a time.
4. Run tests, validation checks, and relevant commands.
5. Summarize what changed, what was verified, and what remains.
6. Stop at the milestone boundary unless explicitly asked to continue.

Do not silently expand scope. Do not skip validation to move faster.

When a requirement is ambiguous but does not block safe progress, make a reasonable assumption, document it, and continue. Ask a question only when the answer materially changes architecture, data validity, cost, security, or the scientific meaning of the model.

## Source-of-truth documents

Read these before significant work:

- `docs/PROJECT_SPEC.md`
- `docs/ARCHITECTURE.md`
- `docs/ROADMAP.md`
- `docs/DATA_RULES.md`
- `docs/DECISIONS.md`
- `PLANS.md`

Update the relevant document whenever an architectural, modeling, data, or scope decision changes.

## Current project state

The user has already:

- Created the local project folder and Git repository
- Confirmed Python availability
- Created a virtual environment
- Confirmed PostgreSQL availability
- Created a private GitHub repository

Do not redo those steps unless repository inspection shows they are incomplete.

The next milestone is Sprint 0: inspect the current repository, establish the professional project foundation, and prepare a controlled five-game MLB Stats API ingestion test.

## Non-negotiable modeling rules

### Prediction definition

The primary product is a confirmed-lineup pregame model run approximately 30 minutes before first pitch.

Historical training may use the actual starting lineup because exact historical T-minus-30 lineup snapshots may not be available. Document this as a historical reconstruction limitation. Never use substitutions or postgame lineup information.

### Leakage prevention

Every historical feature must be calculable using information available before the game.

Feature-building interfaces should accept an `as_of` timestamp or equivalent cutoff.

Never use:

- Full-season statistics for an earlier game
- Postgame data
- Future bullpen appearances
- Future injury status
- End-of-season defensive metrics without an explicit prior/shrinkage treatment
- Actual in-game weather when the production feature is a pregame forecast, unless clearly labeled as a temporary proxy
- Final-season park factors without documenting their timing limitation

### Chronological evaluation

Never use random train/test splits for game-level model evaluation.

Use chronological validation, rolling-origin validation, and an untouched final test period.

### Targets

Use `home_team_runs` and `away_team_runs`, not `home_runs` and `away_runs`, to avoid confusion with home runs hit.

### Data provenance

Important tables should retain:

- Source
- Retrieval time
- Effective time or as-of time
- Pipeline version when practical

### Baselines first

Before advanced models, build and evaluate simple baselines:

- League-average runs
- Rolling team-average runs
- Park-adjusted rolling average
- Poisson or negative-binomial regression
- Gradient boosting

Advanced complexity must earn its place through out-of-sample improvement or meaningful interpretability.

## Engineering standards

- Python 3.11+.
- Use typed Python for public functions.
- Prefer small, testable modules over large notebooks or scripts.
- PostgreSQL is the system of record.
- Use SQLAlchemy and Alembic unless repository inspection justifies another choice.
- Store large raw pitch-level data in partitioned Parquet where appropriate rather than forcing all raw Statcast rows into PostgreSQL.
- Use configuration files and environment variables. Never hard-code secrets.
- Keep `.env` out of Git.
- Use structured logging.
- Add retry, timeout, and error-handling behavior to external requests.
- Make ingestion idempotent.
- Use stable MLB IDs for games, players, teams, and venues.
- Add data-quality tests alongside ingestion logic.
- Avoid introducing paid services or cloud infrastructure before the local MVP proves the need.

## Preferred tools

Initial foundation:

- Python
- PostgreSQL
- pandas
- requests or httpx
- SQLAlchemy
- Alembic
- pydantic-settings
- pytest
- Ruff
- pre-commit

Modeling later:

- NumPy
- scikit-learn
- XGBoost
- statsmodels
- SciPy
- SHAP
- joblib

Application later:

- FastAPI
- React
- PostgreSQL
- Azure

## Safety and repository rules

- Never print or commit credentials.
- Before destructive database operations, explain the impact.
- Do not delete user work or rewrite Git history.
- Prefer migrations over manual schema mutation.
- Do not make a Git commit or push unless explicitly asked.
- Do not install paid services or create cloud resources.
- Do not ingest multiple seasons until the five-game and one-season acceptance tests pass.

## Definition of done for each change

A change is complete only when:

- The code is implemented.
- Relevant tests pass.
- Relevant validation output is shown.
- Documentation is updated.
- Known limitations are stated.
- The next recommended action is clear.


## Ending of every task

After every completed milestone, pause automatically, summarize the work, list any risks or technical debt, recommend whether to proceed, list any manual tasks needed to be completed, and wait for explicit approval before starting the next milestone.