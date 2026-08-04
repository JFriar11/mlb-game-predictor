# 2025 Pregame Feature Audit

## Result

**PASS — feature version `sprint2_v1`, completed 2026-08-03.**

The builder produced exactly two stacked offense rows for every 2025 regular-season game:
one home offense row and one away offense row. Every snapshot is timestamped 30 minutes
before scheduled start and uses outcome records only from strictly earlier calendar dates.

## Coverage and leakage checks

| Measure | Result |
| --- | ---: |
| Feature rows | 4,860 |
| Unique games | 2,430 |
| Games without exactly two rows | 0 |
| As-of violations | 0 |
| Source-date violations | 0 |
| Non-finite numeric rows | 0 |
| Opening-series full-fallback rows | 30 |
| Rows requiring no fallback | 4,196 |
| Team prior-game range | 0–161 |

The deterministic value checksum remained identical after a complete rebuild:
`ad1b24be20ea4779c7fb249e0c948388`.

## Features

Each row stores:

- Identity: game, offense, opponent, opposing starter, venue, home/away, as-of time.
- Team form: runs scored and allowed over the prior 10 games and season-to-date runs.
- Confirmed historical lineup: equal-weight aggregate prior on-base, strikeout, and home-run
  rates for the nine actual starters, plus total prior plate appearances.
- Opposing starter: prior starts, ERA, strikeout rate, walk rate, and outs per start.
- Opposing bullpen: prior-30-day ERA, strikeout and walk rates, prior outs, and outs worked
  in the preceding three calendar days.
- Schedule: days without a game since the offense team's previous game, capped at seven.
- Provenance: feature version, latest source game date, sample sizes, and fallback count.

## Cutoff policy

Features are constructed chronologically by calendar date. All snapshots for a date are
created before any outcomes from that date update state. Consequently, Game 2 of a
doubleheader does not use Game 1. This is deliberately conservative because the current
historical layer does not prove that Game 1 was final, processed, and available at Game 2's
T-minus-30 cutoff.

`max_source_game_date` is null before the first 2025 games and otherwise must be strictly
less than the target `game_date`. `as_of` is scheduled start minus 30 minutes and must be
strictly earlier than scheduled start.

## Fallbacks

- Team offense with no prior games: prior league runs per team-game, or 4.5 before any game.
- Batter with no prior plate appearances: prior league rate; initial fixed rates are .320
  simplified on-base, .225 strikeout, and .030 home run.
- Starter with no prior start: prior league starter rates; initial ERA 4.5 and 15 outs.
- Bullpen without prior-30-day outs: prior league reliever rates or fixed initial rates.
- Team without a prior game: seven days rest.

Sample-size fields and `fallback_count` are retained so later models can learn or disclose
uncertainty rather than treating fallbacks as equally reliable observations.

## Observed ranges

| Feature | Minimum | Mean | Maximum |
| --- | ---: | ---: | ---: |
| Team runs, prior 10 | 1.000 | 4.451 | 12.000 |
| Lineup simplified on-base rate | 0.150 | 0.310 | 0.475 |
| Opposing starter ERA | 0.000 | 4.059 | 81.000 |
| Opposing bullpen 30-day ERA | 0.000 | 4.119 | 22.500 |
| Days without a game | 0 | 0.216 | 7 |

Extreme rate values are retained rather than clipped because the accompanying sample sizes
make their small-sample origin observable. Shrinkage and clipping are modeling decisions for
the next milestone and must be evaluated chronologically.

## Limitations

- Only 2025 data is available, so early-season priors cannot yet use previous MLB seasons.
- Lineup rates are equally weighted; empirical batting-order weights are deferred to Sprint 4.
- Simplified on-base rate excludes hit-by-pitch and sacrifice-fly denominator adjustments
  because Sprint 1 did not store those fields.
- Bullpen features aggregate the opposing team's relievers rather than predicting which
  individual relievers will appear.
- Park is represented by stable venue identity; learned park effects are deferred.
- Actual historical starters and lineups remain reconstruction fields, not proven T-minus-30 snapshots.

## Commands

```bash
export MLB_DATABASE_URL=postgresql+psycopg://mlb:mlb@localhost:55432/mlb_predictor
.venv-sprint0/bin/alembic upgrade head
.venv-sprint0/bin/mlb-predictor build-features --season 2025 --version sprint2_v1
.venv-sprint0/bin/mlb-predictor audit-features --version sprint2_v1 \
  --output data/interim/2025_feature_audit.json
```

