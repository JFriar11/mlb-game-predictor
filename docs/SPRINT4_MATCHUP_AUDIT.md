# Sprint 4 Confirmed-Lineup Matchup Audit

**Completed:** 2026-08-04  
**Feature version:** `sprint4_v1`  
**Base version:** immutable `sprint3_5_v1`  
**Status:** technically accepted; feature bundle not promoted

## Scope and data integrity

Sprint 4 read the separately frozen 2021–2025 completed-game caches; it did not download,
rewrite, or re-freeze raw data. Cached plays were normalized idempotently into 353,466
batter-by-pitcher-hand game rows and 891,145 player-by-pitch-group game rows covering all
12,148 games. The feature builder emitted 24,296 stacked team-game rows for 12,148 games.

Pitch codes are grouped as fastball, breaking, offspeed, or other. Batter outcomes are
aggregated by the opposing pitcher's throwing hand. These are historical facts and enter
a target snapshot only through state accumulated on strictly earlier dates.

## Features and stabilization

- Empirical batting-order weights use strictly prior starting-player plate appearances by
  slot; the cold-start fallback is 4.25 projected plate appearances per slot.
- Overall batter rates use strength-100 shrinkage; hand splits use strength 50.
- Starter pitch mixtures use strength-200 shrinkage; batter pitch-group response uses
  strength 100.
- The existing 0.5 offseason decay is applied transparently.
- Sample-size columns and a matchup fallback count accompany the derived rates.

The audit found 24,296 rows, no null required feature values, no rates outside `[0, 1]`,
and no pitch mixtures that failed to sum to one. Projected lineup plate appearances were
within the configured 20–60 guardrail.

## Chronological development results

Each origin fits only prior seasons and evaluates the next season (2022 through 2025).
These are retrospective development results, not prospective evidence.

| Model | MAE | RMSE | Bias | Poisson deviance | Count NLL |
|---|---:|---:|---:|---:|---:|
| League average | 2.5002 | 3.1703 | 0.0326 | 2.3313 | 2.6744 |
| Team rolling average | 2.5858 | 3.3068 | 0.0090 | 2.5951 | 2.8063 |
| Stabilized Poisson | 2.4844 | 3.1777 | -0.0528 | 2.3543 | 2.6859 |
| Stabilized negative binomial | 2.4785 | 3.1669 | -0.0317 | 2.3344 | 2.4656 |
| Stabilized gradient boosting | 2.4519 | 3.1337 | -0.0455 | 2.2811 | 2.6493 |

Gradient boosting was the best Sprint 4 development model by combined Poisson deviance,
but the relevant decision is the exact feature ablation:

| Model | `sprint3_5_v1` | `sprint4_v1` | Change |
|---|---:|---:|---:|
| Stabilized Poisson | 2.3134 | 2.3543 | +0.0409 |
| Gradient boosting | 2.2765 | 2.2811 | +0.00465 |

Lower is better. Gradient boosting improved slightly in 2022 and 2025 but worsened in
2023 and 2024. The full matchup bundle is therefore not promoted.

## Limitations

- Completed-game feeds reconstruct actual starting lineups, not archived T-minus-30
  lineup forecasts. This is unsuitable for evaluating lineup-availability uncertainty.
- MLB feed pitch labels and the four broad groups are not a Statcast-quality pitch model.
- Contact outcomes are assigned to the plate appearance's terminal pitch group.
- Projected plate appearances use empirical slot history but do not yet model substitutions,
  game state, or opponent bullpen transitions.
- Switch hitters are evaluated against pitcher hand; batter-side mechanics are not modeled
  separately.
- Component-level effects are confounded in this bundle. Any retry should predeclare a
  smaller ablation rather than tune against all reviewed seasons.
- The prospective reserve remains 2026 live predictions or another future locked period.

## Reproduction

With the accepted 2021–2025 cache and database present:

```bash
make sprint4-audit
```

This runs dependency installation, PostgreSQL startup, Ruff, formatting, pytest, Alembic,
aggregate rebuild, feature rebuild, validation, and rolling-origin evaluation. Generated
artifacts under `data/processed/sprint4/` remain intentionally ignored.
