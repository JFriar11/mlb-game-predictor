# Sprint 8 Calibration and Final Retrospective Audit

**Completed:** 2026-08-13  
**Evidence:** retrospective 2021–2025 development  
**Prospective reserve:** 2026

## Calibration

For each 2022–2025 origin, prior seasons fit the accepted model/distribution, the first
40% of season dates fit calibration, and remaining dates evaluate it (5,928 games).

| Method | Brier | Log loss | ECE | Slope | Intercept |
|---|---:|---:|---:|---:|---:|
| Raw | 0.24558 | 0.68432 | 0.02944 | 0.801 | 0.114 |
| Platt | **0.24485** | **0.68266** | **0.01717** | **0.859** | **0.018** |
| Beta | 0.24545 | 0.68403 | 0.01939 | 0.788 | 0.027 |
| Isotonic | 0.24770 | 0.73238 | 0.03280 | 0.146 | 0.104 |

Platt is selected. Its predicted home-win rate is 52.87% versus 52.92% observed. It
improves log loss in 2022, 2024, and 2025 and nearly ties raw in 2023. Isotonic creates
unsupported 0/1 extremes. Only four Platt evaluation predictions exceed 0.8, so extreme
buckets do not drive selection.

## Final retrospective system

- Point: MAE 2.4488, RMSE 3.1304, bias -0.0387, Poisson deviance 2.2765.
- Global fold-only NB: NLL 2.4132 and RPS 1.6582; Poisson NLL 2.5746 and RPS 1.7089.
- NB coverage: 56.1%/81.8%/97.0% for nominal 50%/80%/95%. The intervals are mildly
  conservative; no additional reviewed-data dispersion adjustment is justified.
- Nested calibrated wins: Brier 0.24485 and log loss 0.68266.
- Simple run references: league-average Poisson deviance 2.3313; team rolling 2.5951.

Season, favorite/underdog, probability range, fallback, early/late evaluation, uncertainty,
calibration tables, and sharpness are stored in ignored Sprint 8 metadata.

## Frozen contract and limitations

`config/accepted_model_v1.json` is the frozen specification. Migration `0010` stores
prediction/game times, lineup state, starter IDs, versions, means, distribution parameters,
raw/calibrated wins, intervals, extra-inning adjustment, warnings, and observed outcomes.
It does not implement live automation.

Historical lineup timing, independent regulation scoring, approximate extra innings,
censored 12+, and repeated review of 2021–2025 remain limitations. This is not prospective
validation.

## Reproduction

```bash
make sprint8-audit
```
