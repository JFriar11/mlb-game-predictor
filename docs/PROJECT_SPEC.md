# MLB Game Predictor — Project Specification

## Product definition

A confirmed-lineup MLB pregame prediction system that runs approximately 30 minutes before first pitch.

## Primary outputs

For each scheduled game:

- Expected home-team runs
- Expected away-team runs
- Home win probability
- Away win probability
- Run probability distribution for each team
- Most likely final scores
- 80% and 95% run ranges
- Key prediction factors
- Confidence or uncertainty measure grounded in calibration and data quality

## Initial historical scope

Recommended starting period:

- 2021–2025 regular seasons
- Begin implementation with 2025 only
- Expand earlier only after one-season ingestion and evaluation are sound

Postseason games are excluded from the first version because roster usage, starter hooks, and bullpen behavior differ.

## Historical-lineup assumption

Historical training will use actual starting lineups from game records. The project will not claim that those lineups were necessarily confirmed exactly 30 minutes before first pitch.

This is acceptable for the first confirmed-lineup model because:

- Only starters and batting order are used.
- Substitutions and postgame performance are excluded.
- Live production predictions will wait for confirmed lineups.

This limitation must be disclosed in project documentation and model reports.

## Initial targets

- `home_team_runs`
- `away_team_runs`

Runs are nonnegative count outcomes.

## MVP definition

The MVP is complete when the system can:

1. Reconstruct historical games, starters, and lineups.
2. Calculate leakage-safe rolling team, batter, starter, and bullpen features.
3. Train simple baselines and at least one gradient-boosting model.
4. Produce probabilistic run forecasts.
5. Backtest chronologically.
6. Report calibrated win probabilities.
7. Generate a prediction from a command-line interface for a scheduled date.

The dashboard is not part of the MVP.

## Full vision

The advanced system may add:

- Handedness-adjusted lineup quality
- Pitch-arsenal matchup features
- Similar-pitcher embeddings or clusters
- Starter outs and pitch-count distributions
- Bullpen availability and reliever appearance probabilities
- Park, roof, weather, and field-oriented wind adjustments
- Defense and catcher effects
- Joint score dependence
- Extra-inning simulation
- FastAPI backend
- React frontend
- Azure deployment and scheduled jobs

## Success criteria

The project succeeds by demonstrating:

- Correct historical reconstruction
- Strong leakage controls
- Honest chronological evaluation
- Calibrated probabilities
- Reproducible pipelines
- Clear baseball interpretation
- Maintainable engineering

A complex model is not considered successful solely because it uses advanced algorithms.

## Explanation and confidence semantics

New predictions retain prediction-time input evidence for deterministic baseball
summaries; older predictions without that evidence remain explicitly unexplained.
Summaries show raw/stabilized inputs and sample sizes, not causal or ranked model
contributions. Confidence presentation separates calibrated outcome probability,
recorded input-quality limitations, and retrospective calibration evidence. It
does not assign an unvalidated combined confidence grade. Uncensored 80%/95% count
ranges are derived from saved distribution parameters alongside the explicitly
censored 12+ score representation. See `EXPLANATIONS.md` for limits.

## Optional local what-if mode

User-approved offseason scope adds a lineup sandbox over the frozen accepted model.
Custom teams, nine hitters per side, pitchers, park and history cutoff generate
an explicitly hypothetical, unsaved result. The confirmed-lineup prospective
product remains separate. No custom lineup enters model evaluation or the official
ledger. Local operation is the selected hosting approach for now. See `SANDBOX.md`.
