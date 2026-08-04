# Architecture

## Logical data flow

```text
External Sources
    |
    v
Raw Ingestion and Source Cache
    |
    v
Normalized Historical Database
    |
    v
As-Of Snapshot Builder
    |
    v
Pregame Feature Store
    |
    +--> Baseline Models
    +--> Starter Model
    +--> Bullpen Model
    +--> Matchup Engine
    +--> Environment Features
    |
    v
Team Run Distribution Model
    |
    v
Joint Game Simulation and Calibration
    |
    v
Prediction API / CLI / Dashboard
```

## Recommended repository layout

```text
mlb-game-predictor/
├── AGENTS.md
├── PLANS.md
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── alembic.ini
├── config/
├── data/
│   ├── raw/
│   ├── interim/
│   └── processed/
├── docs/
│   ├── PROJECT_SPEC.md
│   ├── ARCHITECTURE.md
│   ├── ROADMAP.md
│   ├── DATA_RULES.md
│   └── DECISIONS.md
├── migrations/
├── notebooks/
├── scripts/
├── src/
│   └── mlb_predictor/
│       ├── config.py
│       ├── logging.py
│       ├── db/
│       ├── ingestion/
│       ├── validation/
│       ├── features/
│       ├── models/
│       ├── simulation/
│       └── cli/
└── tests/
```

Codex should preserve useful existing files rather than forcing this exact tree blindly.

## Sprint 0 implementation

The repository now implements the first normalized slice under `src/mlb_predictor/`:

```text
CLI -> bounded five-game manifest -> retrying MLB Stats API client
    -> feed parser/validation -> per-game SQLAlchemy transaction
    -> PostgreSQL tables -> acceptance validator / reconstruction report
```

Each game transaction upserts reference entities and the game, then replaces that game's
starter and starting-lineup children. Database constraints prevent invalid values and
duplicates; the validator checks cross-row completeness that a row constraint cannot.

## Initial normalized tables

### Reference tables

- `teams`
- `players`
- `venues`

### Game tables

- `games`
- `game_starting_pitchers`
- `game_starting_lineups`

### Later additions

- `player_game_batting`
- `player_game_pitching`
- `pitches`
- `weather_snapshots`
- `roster_snapshots`
- `injury_snapshots`
- `park_factors`
- `bullpen_usage`
- `pregame_feature_snapshots`
- `model_predictions`
- `model_versions`

## Initial key fields

### games

- `game_pk`
- `game_date`
- `scheduled_start_time_utc`
- `actual_start_time_utc`
- `season`
- `game_type`
- `status`
- `home_team_id`
- `away_team_id`
- `venue_id`
- `home_team_runs`
- `away_team_runs`
- `innings_played`
- `doubleheader_code`
- `game_number`
- `source`
- `retrieved_at`

### game_starting_lineups

- `game_pk`
- `team_id`
- `player_id`
- `batting_order`
- `defensive_position`
- `bat_side`
- `is_home`
- `source`
- `retrieved_at`

### game_starting_pitchers

- `game_pk`
- `team_id`
- `pitcher_id`
- `throws`
- `is_home`
- `source`
- `retrieved_at`

## Storage strategy

- PostgreSQL: normalized entities, game records, features, predictions, metadata.
- Parquet: large raw or semi-processed pitch-level datasets.
- Git: code, migrations, configuration templates, documentation.
- Never commit raw data, secrets, model binaries, or database dumps by default.

Raw response caching is intentionally deferred to Sprint 1. Sprint 0 retains normalized
source and retrieval timestamps but cannot replay the original API payload offline.

## Modeling architecture

Begin with a stacked team-game training table:

Each MLB game produces two training rows:

- One row for the home offense against the away defense/pitching context.
- One row for the away offense against the home defense/pitching context.

Fields include:

- `game_pk`
- `offense_team_id`
- `opponent_team_id`
- `is_home`
- `runs_scored`
- Pregame features

This structure allows consistent treatment of home and away offenses and can later support one shared run model.

## Specialized-model dependency order

1. Build pregame bullpen usage state.
2. Predict starter outs or expected starter length.
3. Estimate expected bullpen innings.
4. Estimate bullpen quality over those innings.
5. Combine matchup, starter, bullpen, defense, and environment information.
6. Produce run distributions.
7. Simulate regulation and resolve ties or extra innings.

Avoid circular dependencies unless an explicitly tested iterative method is introduced.
