# Sprint 5 Starter and Bullpen Audit

**Completed:** 2026-08-12  
**Feature version:** `sprint5_v1`  
**Run-model reference:** immutable `sprint3_5_v1`  
**Status:** component layer accepted; full downstream bundle not promoted

## Scope and integrity

Sprint 5 used only normalized 2021–2025 outcomes and did not alter frozen caches or prior
feature versions. It built 24,296 pregame pitching rows for 12,148 games. Validation found
no source-date violations, invalid starter values, or invalid bullpen rates.

All games on a calendar date are snapshotted before any of that date's outcomes update
state. Features include decayed starter outs and pitches, starter rest, team-level hook
history, bullpen pitch workload over one and three days, available/unavailable reliever
counts, prior-usage roles, and available-reliever ERA/strikeout/walk mixtures. One unstable
32-pitches-per-out opener history is clipped at the documented 20.0 guardrail.

The role and availability definitions are proxies: the three largest prior appearance
counts identify high-usage relievers; 30 pitches yesterday or 50 over three days marks a
reliever unavailable. No future saves, holds, leverage, or roster assignments are used.

## Component results

Rolling origins train only on seasons before each 2022–2025 evaluation season. Of 24,296
feature rows, nine lack a component target because the listed starter recorded zero outs
and faced zero batters; 19,430 evaluated rows remain after the 2021 training season.

| Target and method | MAE | RMSE | Bias |
|---|---:|---:|---:|
| Starter outs — league mean | 3.2595 | 4.3121 | -0.2588 |
| Starter outs — pitcher rolling | **2.9611** | **3.9332** | 0.0688 |
| Starter outs — gradient boosting | 3.0682 | 3.9650 | -0.4529 |
| Starter pitches — league mean | 12.4748 | 17.2845 | -1.3169 |
| Starter pitches — pitcher rolling | **10.2040** | **14.5401** | 0.1053 |
| Starter pitches — gradient boosting | 11.2898 | 15.1313 | -2.9700 |
| Expected bullpen outs — selected rolling method | 3.1809 | 4.1341 | 0.3305 |

Pitcher rolling history is selected. Residual intervals were slightly conservative:
80% interval coverage ranged from 82.6% to 83.7% by season, and 95% coverage ranged from
96.0% to 96.4%. These are retrospective development intervals, not live calibration.

## Downstream run ablation

The exact rolling-origin gradient-boosting comparison used the same run targets and
`sprint3_5_v1` base features.

| Features | MAE | RMSE | Poisson deviance | Count NLL |
|---|---:|---:|---:|---:|
| `sprint3_5_v1` | 2.4488 | 3.1304 | **2.27647** | **2.64698** |
| Base plus Sprint 5 pitching state | **2.4474** | 3.1328 | 2.28171 | 2.64960 |

Poisson deviance worsened by 0.00525. The small MAE change does not justify promoting the
entire bundle. Component outputs remain useful and can be tested individually later under
a predeclared ablation.

## Limitations

- Team history proxies for manager hook tendency because historical manager identity is
  not stored; midseason manager changes are not represented.
- Availability ignores injuries, transactions, options, travel, warm-up activity, and
  explicit manager statements.
- Role inference measures usage volume, not leverage or inning-specific assignment.
- Expected bullpen outs does not model walk-off shortened defensive innings directly.
- Nine zero-batter/zero-out listed starters lack normalized component targets.
- All 2021–2025 evidence is retrospective. The prospective reserve remains 2026 live
  predictions or another future locked period.

## Reproduction

With the accepted 2021–2025 normalized database present:

```bash
make sprint5-audit
```

The command installs dependencies, starts PostgreSQL, runs Ruff, formatting, pytest,
Alembic checks, rebuilds `sprint5_v1`, validates it, and writes ignored datasets,
predictions, and dependency-rich metadata under `data/processed/sprint5/`.
