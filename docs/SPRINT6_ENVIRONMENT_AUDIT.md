# Sprint 6 Run-Environment Audit

**Completed:** 2026-08-12  
**Environment version:** `sprint6_v1`  
**Baseline:** immutable `sprint3_5_v1`  
**Decision:** component layer accepted; promote none

## Coverage and controls

The frozen feeds provide temperature for all 12,148 normalized games, wind for 12,147,
roof/field metadata for 12,147, and elevation for 12,128. The builder produced 12,148
valid snapshots with no source-date violations. Park factors use strictly prior dates,
exclude same-day outcomes, and shrink toward 1.0 with 50 games of prior strength.

Weather values are completed-feed observations, not archived T-minus-30 forecasts. Roof
closed is inferred only from `Roof Closed` or `Dome` labels. Humidity and pressure are
absent. No independent leakage-safe defense data is available; accepted rolling runs
allowed remains the only defense/run-prevention proxy.

## Rolling-origin results

| Architecture | MAE | RMSE | Bias | Poisson deviance | Count NLL | Change |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 2.4488 | 3.1304 | -0.0387 | 2.27647 | 2.64698 | — |
| Rolling park factor | 2.4577 | 3.1319 | 0.0172 | 2.27817 | 2.64783 | +0.00170 |
| Venue physical | 2.4471 | 3.1273 | -0.0385 | 2.27245 | 2.64497 | -0.00402 |
| Observed weather proxy | 2.4454 | 3.1250 | -0.0298 | **2.26871** | **2.64310** | **-0.00775** |
| Raw environment bundle | 2.4476 | 3.1312 | -0.0525 | 2.27840 | 2.64795 | +0.00193 |
| Modular park adjustment | 2.4572 | 3.1403 | -0.0278 | 2.28809 | 2.65279 | +0.01162 |
| Park-adjusted team rolling | — | — | — | 2.58680 | — | — |

Observed weather improved 2022–2024 but was essentially flat/slightly worse in 2025.
Venue physical attributes improved 2022, 2023, and 2025 but worsened 2024. The full bundle
underperformed its parts. Both park adjustments worsened, consistent with venue identity
already learning park context and demonstrating double-counting risk.

## Decision and limitations

No environment input is promoted and `sprint3_5_v1` remains the reference. Weather needs
timestamped pregame forecasts for temperature, humidity, pressure, wind, and precipitation
before retesting. Explicit roof decisions, stadium orientation, and time-valid defensive
metrics are also needed. All 2021–2025 evidence remains retrospective development evidence.

## Reproduction

```bash
make sprint6-audit
```

Generated metadata and predictions remain ignored under `data/processed/sprint6/`.
