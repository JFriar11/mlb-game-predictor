# Data and Modeling Rules

## As-of principle

Every training feature must be reproducible from records with effective timestamps before the scheduled prediction time.

Preferred interface:

```python
build_game_features(game_pk: int, as_of: datetime) -> GameFeatures
```

## Historical snapshots

When exact historical pregame snapshots do not exist:

1. Use the best available proxy.
2. Label the proxy explicitly.
3. Prevent postgame outcomes from entering the feature.
4. Run sensitivity tests where possible.
5. Do not overstate the historical backtest's realism.

## Lineups

Allowed:

- Actual starting players
- Actual starting batting order
- Starting defensive positions

Not allowed:

- Substitutions
- Pinch hitters
- Postgame lineup changes
- Performance in the target game

Sprint 0 reconstructs the actual starting batting order from the completed MLB game feed.
It does not claim that the feed is a historical T-minus-30 snapshot. Only the nine initial
batting-order IDs and their initial boxscore positions are stored; substitutions are not.

Live confirmation means the MLB live feed exposes nine initial batting-order IDs for both
teams. The feed lacks a dependable separate confirmation boolean. Only official records
generated before first pitch after deployment count as prospective; dry-run, diagnostic,
and backfill records never do.

## Rolling metrics

All rolling metrics must:

- End before the target game
- Define the lookback window
- Define minimum sample requirements
- Include shrinkage or fallback logic where appropriate
- Treat same-day doubleheaders carefully

For Game 2 of a doubleheader, explicitly decide whether Game 1 data would have been available and processed by the production system. Document the choice.

Sprint 2 policy: exclude all same-calendar-date outcomes. Game 2 does not use Game 1. This
is conservative and remains in force until historical timing data proves Game 1 completion
and pipeline availability before Game 2's as-of timestamp.

## Cold starts

Fallback hierarchy may use:

1. Current-season MLB sample
2. Prior MLB seasons
3. Minor-league translated metrics
4. External preseason projection prior
5. Similar-player prior
6. League average

The specific implementation should be tested and documented.

Sprint 2 uses expanding prior-season league rates and fixed initial priors when 2025 has no
earlier observations. Every snapshot retains sample sizes and a fallback count.

## Weather

The production system will use a pregame forecast.

Historical observed weather may be used only as a temporary proxy and must be labeled. Historical forecast snapshots are preferred when practical.

## Park factors

Prefer multi-year, handedness-aware factors shrunk toward neutral. Avoid using future-season information without an explicit experiment and disclosure.

## Bullpen roles

Infer historical roles from information available before the game. Do not assign a player's end-of-season role retroactively.

## Defense

Avoid applying full-season OAA or other defensive totals to early-season games without leakage-safe rolling or prior-season treatment.

## Evaluation

- No random game split.
- Use chronological validation.
- Compare against simple baselines.
- Preserve a final untouched period.
- Evaluate both point and probability predictions.
- Report interval coverage.
- Evaluate relevant baseball slices.

## Reproducibility

Persist or record:

- Data source
- Retrieval timestamp
- Effective timestamp
- Feature version
- Model version
- Training period
- Evaluation period
- Random seed
- Dependency lockfile

## Player-game outcomes

`player_game_batting` and `player_game_pitching` are postgame outcome records. They may be
used to calculate rolling history only when the source game's effective time is before the
target game's as-of cutoff. They must never be joined directly as same-game pregame features.

The 2025 raw source layer is cached and checksum-manifested. A changed checksum requires a
new audit and an explicit explanation before rebuilding features.
