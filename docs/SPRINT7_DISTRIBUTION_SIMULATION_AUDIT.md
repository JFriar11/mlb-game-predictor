# Sprint 7 Run-Distribution and Simulation Audit

**Completed:** 2026-08-13  
**Mean model/features:** immutable `sprint3_5_v1` gradient boosting  
**Selected distribution:** global training-fold negative binomial

## Distribution comparison

Runs are materially overdispersed: empirical mean is 4.435 and variance is 10.037
(variance/mean 2.263). Every prediction bucket has variance/mean above 2.1.

| Distribution | Count NLL | RPS | 50% coverage/width | 80% coverage/width | 95% coverage/width |
|---|---:|---:|---:|---:|---:|
| Poisson | 2.5746 | 1.7089 | 46.1% / 2.78 | 69.1% / 5.26 | 86.8% / 7.95 |
| NB, global fold-only | 2.4132 | 1.6582 | 56.1% / 3.68 | 81.8% / 6.97 | 97.0% / 10.63 |
| NB, recent training season | **2.4123** | **1.6580** | 56.2% / 3.69 | 81.9% / 6.99 | 97.1% / 10.65 |
| Direct 0–12+ | 2.4649 | 1.7229 | 53.9% / 3.58 | 80.0% / 6.72 | 95.2% / 9.91 |

Negative binomial beats Poisson in NLL and RPS in all four seasons. The direct model
improves NLL but not RPS. Global fold-only NB is selected because recent-season dispersion
adds complexity for a negligible combined gain and is worse in 2025. Fold dispersions range
from 0.096 to 0.229. Mean-model MAE remains 2.4488 and Poisson deviance 2.2765.

## Dependence and win probabilities

Raw home/away run correlations range from -0.024 to 0.014. Conditional residual
correlations range from -0.025 to 0.015. This does not justify a shared-game dependence
adjustment, so regulation distributions remain independent.

Regulation ties are resolved with the home win rate among prior training extra-inning
games, not counted as wins or losses. This is an approximation. Rolling-origin home-win
probabilities have Brier score 0.2454 and log loss 0.6840. Middle buckets are reasonably
ordered, while extreme buckets contain few games and are overconfident. No qualitative
confidence labels are created.

## Simulation validation

Analytic convolution is exact for the independent truncated distributions. For three 2025
examples, absolute Monte Carlo home-win error versus analytic probability was:

| Simulations | Observed error range |
|---:|---:|
| 1,000 | 0.0109–0.0275 |
| 10,000 | 0.0006–0.0086 |
| 100,000 | 0.0011–0.0017 |

Ten thousand simulations are adequate for routine summaries at roughly sub-one-percentage-
point error in these examples; analytic probabilities remain preferred for displayed win
probability. Use 100,000 when stable tail/score-frequency reporting matters.

## Example outputs

- Game 776135: away/home means 4.28/4.40; 80% ranges 1–8/1–8; 95% ranges 0–11/0–11;
  home win 51.0%; regulation tie 10.7%.
- Game 776136: away/home means 6.42/3.99; 80% ranges 2–12+/1–8; home win 31.0%;
  regulation tie 8.5%.
- Game 776137: away/home means 3.62/4.91; 80% ranges 1–7/1–9; home win 62.0%;
  regulation tie 10.4%.

Artifacts include top exact-score frequencies, total-run means/ranges, extra-inning
adjustment, and 1K/10K/100K stability results.

## Limitations

- The 12+ terminal bucket makes its score label censored, not exactly 12.
- Regulation dependence is omitted based on small historical correlations.
- Extra innings do not model innings, ghost runners, or relievers explicitly.
- Win probabilities are not yet post-hoc calibrated; that belongs to Sprint 8.
- All 2021–2025 evidence is retrospective development evidence.

## Reproduction

```bash
make sprint7-audit
```

Generated metadata and game probabilities remain ignored under `data/processed/sprint7/`.
