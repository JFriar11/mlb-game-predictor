# Sprint 3 Baseline Model Audit

## Result

**PASS — completed 2026-08-03 using immutable feature version `sprint2_v1`.**

The reproducible modeling dataset has 4,860 stacked offense-team rows for 2,430 games,
with `runs_scored` as a nonnegative count target. Sprint 3 did not rebuild features, alter
the frozen raw cache, or ingest another season.

This is a one-season development evaluation, not final model performance.

## Chronological protocol

- Warm-up and initial training: March 18–May 31.
- Fold 1: train through May 31; evaluate June.
- Fold 2: train through June 30; evaluate July.
- Fold 3: train through July 31; evaluate August.
- Final untouched block: train through August 31; evaluate September 1–28.

No random split is used. Selection uses only aggregate development Poisson deviance.
September was evaluated after selection and was not used to revise the winner.

## Development comparison

| Model | MAE | RMSE | Bias | Poisson deviance | Count NLL |
| --- | ---: | ---: | ---: | ---: | ---: |
| League average | **2.554** | **3.269** | -0.182 | **2.413** | 2.727 Poisson |
| Team rolling average | 2.697 | 3.429 | -0.025 | 2.666 | 2.853 Poisson |
| Poisson, raw | 2.620 | 3.306 | 0.131 | 2.453 | 2.747 Poisson |
| Poisson, stabilized | 2.572 | 3.273 | -0.040 | 2.419 | 2.730 Poisson |
| Negative binomial, stabilized | 2.580 | 3.282 | -0.029 | 2.430 | **2.492 NB** |
| Gradient boosting, stabilized | 2.596 | 3.330 | -0.149 | 2.508 | 2.774 Poisson |

League average wins the declared selection metric. Stabilized Poisson is the best
nonconstant model and improves raw Poisson in every listed point metric and NLL, showing
value from leakage-safe small-sample treatment, but it does not beat league average.
Negative-binomial NLL uses its fitted NB distribution and is labeled separately.

## Untouched September result

| Model | MAE | RMSE | Bias | Poisson deviance | Count NLL |
| --- | ---: | ---: | ---: | ---: | ---: |
| League average | 2.446 | **3.087** | 0.055 | **2.239** | 2.631 Poisson |
| Team rolling average | 2.558 | 3.265 | 0.155 | 2.482 | 2.752 Poisson |
| Poisson, raw | 2.516 | 3.152 | 0.459 | 2.311 | 2.667 Poisson |
| Poisson, stabilized | 2.468 | 3.116 | 0.320 | 2.269 | 2.646 Poisson |
| Negative binomial, stabilized | 2.479 | 3.127 | 0.344 | 2.282 | **2.449 NB** |
| Gradient boosting, stabilized | **2.445** | 3.113 | 0.049 | 2.284 | 2.653 Poisson |

Gradient boosting's MAE is lower than league average by only 0.0004 runs, while league
average remains better on RMSE and Poisson deviance. This does not justify changing the
development-selected model after opening the test block.

## Small samples and nonnegative predictions

Raw Poisson uses accepted values exactly as stored. Stabilized variants shrink lineup,
starter, and bullpen rates toward fixed priors using only each row's prior sample size,
clip rate extremes, and transform sample sizes with `log1p`. Constants are not estimated
from validation or future data.

League and rolling baselines use positive means. Poisson and negative-binomial GLMs use
log links. Gradient boosting uses Poisson loss. Prediction paths also apply a small
positive numerical floor; all audit predictions were positive.

## Error analysis

Complete slices for the selected league baseline and best nonconstant stabilized Poisson
are in `metadata.json`. Stabilized Poisson diagnostics across June–September show:

- Monthly deviance: June 2.480, July 2.292, August 2.472, September 2.269.
- Home rows were better than away rows: 2.244 versus 2.523 deviance.
- Rows using fallbacks were worse: 2.564 versus 2.366 without fallbacks.
- Starter histories of 0, 1–4, and 5+ starts had deviance 2.256, 2.396, and 2.388.
- Predictions below 3 runs were sparse (22 rows) and scored 3.431 deviance; predictions
  at 6+ runs overpredicted by 0.949 runs on average.

These slices are diagnostic; small groups are not stable causal findings.

## Reproducibility and artifacts

From the accepted local 2025 database, run:

```bash
make sprint3-audit
```

Ignored `data/processed/sprint3/` contains `modeling_dataset.csv`, `predictions.csv`,
`final_models.joblib`, and `metadata.json`. Metadata includes feature version, target,
dates, configuration, selection rule, random seed, metrics, error slices, dependency
versions, and limitations.

A complete second evaluation produced byte-identical CSVs: dataset SHA-256
`f65d19ea9f6bc70cbfb9010f936dcbc418f06cab8ea44d2af425af43ee348845` and prediction
SHA-256 `44056c5b409d441dc709f85bc9037afd6987e51434f5aea9ca0e0603ba89e200`.

Automated tests prove strict chronological boundaries, structural exclusion of target and
future/identity columns from fitting, deterministic predictions, positive forecasts, and
that changing a target game's outcome does not change its pregame features.

## Limitations

- Only 2025 is available. September is useful development evidence, not a multi-season or
  future-season generalization estimate.
- Historical lineups are reconstructed, not archived T-minus-30 observations.
- Equal lineup weighting, Statcast, weather, clustering, simulation, APIs, and dashboards
  are deliberately outside Sprint 3.
- Fixed priors are transparent but not jointly tuned; that requires nested chronological
  validation and more seasons.
- No model beat league average on the declared development metric. Advanced complexity is
  not yet supported by the evidence.
