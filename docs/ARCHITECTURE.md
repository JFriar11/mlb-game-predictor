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

Sprint 0 records retain normalized source and retrieval timestamps. Sprint 1 adds the raw
response cache needed to replay the 2025 ingestion offline.

## Sprint 1 historical layer

Sprint 1 adds `player_game_batting` and `player_game_pitching` to PostgreSQL. The source
cache stores gzip-compressed schedule and completed-game JSON under the ignored
`data/raw/mlb_stats_api/<season>/` tree. Cache writes are atomic, season ingestion is
resumable, and each normalized game is committed independently.

The cached 2025 layer is frozen by a deterministic per-file SHA-256 manifest in the ignored
interim data directory. `docs/SEASON_2025_AUDIT.md` records its aggregate counts and
manifest checksum. Outcome tables remain historical facts and are inputs to future
as-of feature builders only through a cutoff strictly before the target game.

## Sprint 2 feature layer

`pregame_feature_snapshots` stores two versioned rows per game. The chronological builder
loads the frozen normalized season, groups targets by date, emits every snapshot for the
date, and only then updates its rolling state. This state-transition boundary prevents
same-day and doubleheader leakage by construction.

The table retains `as_of`, `max_source_game_date`, feature version, sample sizes, and a
fallback count. The audit checks row cardinality, cutoff ordering, source ordering, numeric
finiteness, and deterministic rebuilds. See `docs/FEATURE_2025_AUDIT.md`.

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

Sprint 3 implements this as a reproducible 4,860-row dataset read from immutable
`sprint2_v1`. Modeling-only stabilization, chronological folds, six count-model
specifications, common metrics, and artifact writing live under `mlb_predictor.modeling`.
Generated data and model files are ignored; metadata records feature version, dates,
configuration, seed, dependencies, and results. No output is written into frozen layers.

## Sprint 4 matchup layer

Sprint 4 replays frozen cached feeds into compact `player_game_handed_batting` and
`player_game_pitch_group` aggregates. A chronological builder copies accepted
`sprint3_5_v1` rows into `sprint4_v1` and adds lineup weighting, handedness, and pitch-mix
features. All target-date snapshots are emitted before that date updates state, preserving
the same doubleheader boundary as earlier feature versions. Samples, fallbacks, as-of
dates, and source dates remain stored with each row. The source cache is read-only.

## Sprint 5 pitching component layer

`pitching_feature_snapshots` stores one versioned pregame row per defensive team-game.
The date-batched builder derives starter length and pitch history, team-level hook proxies,
reliever workload, prior-usage role proxies, availability flags, and an available-bullpen
quality mixture from strictly earlier dates. Component evaluation joins postgame targets
only after feature construction. Expected bullpen length is scheduled team outs minus the
selected starter-outs forecast; it is not an in-game outcome feature.

Sprint 5.5 joins this accepted state to `sprint3_5_v1` only in the modeling dataset. It
runs a fixed subset matrix without persisting a new feature version. Because no subset met
the promotion standard, the production/reference feature graph remains unchanged.

## Sprint 6 environment layer

`environment_feature_snapshots` stores prior-date shrunk park context and cached-feed
venue/weather metadata. Weather is explicitly an observed proxy. Raw and modular park
architectures are evaluated separately; no environment subset enters the reference graph.

## Sprint 7 distribution and simulation layer

The accepted mean forecast feeds a fold-calibrated negative-binomial probability mass
function. Analytic convolution produces regulation tie and win probabilities; a training-
only extra-inning home-win rate resolves ties. Deterministic Monte Carlo generates score
frequencies and total-run ranges and is tested against the analytic result.

## Sprint 8 calibration and prospective record

Platt calibration fits on a chronological block distinct from mean/distribution training
and evaluation. `live_prediction_records` is the append-only prospective contract for raw
and calibrated predictions plus later outcomes; Sprint 8 does not automate its population.

## Specialized-model dependency order

1. Build pregame bullpen usage state.
2. Predict starter outs or expected starter length.
3. Estimate expected bullpen innings.
4. Estimate bullpen quality over those innings.
5. Combine matchup, starter, bullpen, defense, and environment information.
6. Produce run distributions.
7. Simulate regulation and resolve ties or extra innings.

Avoid circular dependencies unless an explicitly tested iterative method is introduced.
