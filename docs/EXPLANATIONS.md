# Prediction explanations and uncertainty

Sprint 10D adds deterministic presentation fields to each official API prediction:
`explanation`, `confidence`, and `run_ranges`. The accepted model, feature graph,
probabilities, stored intervals, and historical prediction records are unchanged.

## Prediction-time evidence

Migration `0014` creates `prediction_input_snapshots`, keyed by prediction ID. It
contains the explicit cutoff, source/version, artifact hash, team/starter/starting
lineup IDs, exact accepted raw feature values, and the existing small-sample
stabilization output. New CLI predictions create this optional snapshot in the
same transaction as their forecast. Capture performs no fitting or MLB requests.

The supported pipeline writes each snapshot once. Repeating an official prediction
returns the original record without replacing or filling its evidence. Settlement
only updates outcome fields. Direct database administration is outside this
application-level write-once contract. Old records remain without snapshots;
there is no retrospective reconstruction or backfill command.

Before reading new evidence, migrate the configured database intentionally:

```bash
.venv-sprint10b/bin/alembic upgrade head
```

This is additive: it creates a new table and foreign key without rewriting existing
forecasts or historical features. Runtime acceptance applies it in a disposable
database. After that acceptance passed, the local Compose database was also upgraded
from `0013` to `0014`. All 17 pre-existing domain-table counts and the forecast/launch
state hashes were unchanged; the new snapshot table is empty. No manual migration
is needed for that local database. Other checkouts/connections must apply it before
using the updated API; choose the intended connection before running the command.

## Baseball input summaries

When evidence exists, `explanation.status` is `available`. Four factors appear for
each offense, in a fixed order:

| Factor | Retained evidence | Interpretation |
| --- | --- | --- |
| Lineup on-base proxy | Prior lineup plate appearances, raw proxy, stabilized proxy | `(hits + walks) / (at-bats + walks)` across retained prior MLB history. This excludes HBP and sacrifice flies and is not official OBP. |
| Opposing starter ERA | Opposing starter's prior starts, raw ERA, stabilized ERA | Pitching inputs belong to the defense faced by that offense. No listed-start current-game outcome enters the snapshot. |
| Opposing bullpen ERA | Prior-30-date team reliever outs, raw ERA, stabilized ERA | Team reliever history, not a confirmed available-reliever mixture or current roster projection. |
| Recent team scoring | Raw and model runs-per-game inputs | Up to ten retained games with early/empty-history fallbacks. The exact window sample count is not retained, so none is invented. |

Empty-history values can be priors rather than observed player performance.
`raw_value` shows the feature-builder value; `model_value` shows the value after
the existing accepted stabilization. Sample sizes are raw counts, not logged model
features. A small sample can pull an apparently extreme raw rate toward its prior.

These are model input summaries, not ranked importance, causal effects, SHAP
values, or additive run contributions. The system does not infer an effect's sign
or size from a baseball statistic alone. It does not manufacture explanations from
latest discovery, future outcomes, observed weather, or unpromoted components.
Captured team/lineup IDs distinguish prediction-time context from mutable discovery.

Without evidence, `explanation.status` is `not_retained`, factors are empty, and
the snapshot date/IDs are null. A missing snapshot is valid legacy state. A present
but malformed or mismatched snapshot fails the API request with 503, consistently
with malformed forecast records. Artifact hash, starter IDs, cutoff, record ID,
source, and version binding are checked. Exact feature-column allowlists exclude
targets and other unaccepted columns.

## Confidence has separate components

No combined confidence percentage or high/medium/low confidence grade is assigned.

- **Outcome forecast:** `favorite_win_probability` is the larger calibrated win
  probability. `probability_margin_over_even` is its distance from 0.5. These
  describe the predicted outcome, not the probability the model is reliable.
- **Recorded input quality:** missing snapshots produce `unknown`. Retained
  snapshots with fallbacks or recorded warnings produce `limited`. Otherwise the
  status is `no_recorded_limitations`, which does not certify complete/current
  data. Raw fallback counts are reported separately for each offense; recorded
  warnings remain visible even when overall quality is unknown. These are
  deterministic data flags, not statistically calibrated correctness grades.
- **Calibration evidence:** report the rounded Sprint 8 nested chronological
  results for 5,928 evaluation games across 2022–2025: Brier 0.24485, log loss
  0.68266, and ECE 0.01717. All are retrospective development evidence. Local
  reliability is `not_estimated`; no game-level error bar is derived from aggregate
  ECE. Only four evaluated home probabilities exceeded 0.8, so extreme home-win
  forecasts have little support in that audit.

The source is `SPRINT8_FINAL_RETROSPECTIVE_AUDIT.md`. This presentation does not
assert prospective performance, re-evaluate the current ledger, recalibrate the
accepted probabilities, or tune thresholds using later outcomes. A new held-out
evaluation remains necessary to support future model/quality claims.

## Count ranges and censored score bins

The stored PMF still contains 0–11 and a censored **12+** bin. Stored bin intervals
and `most_likely_score_bins` remain unchanged and explicitly labeled. Tied score
categories are possible; these categories are not resolved exact final scores.
Platt-calibrated wins remain separate from independent joint scoring categories.

`run_ranges` derives uncensored marginal 80% and 95% equal-tailed count quantiles
from the saved mean and dispersion: `n = 1 / dispersion`, `p = n / (n + mean)`.
Consequently an upper endpoint may exceed 12. Each range reports its nominal mass
and actual probability mass under that saved count distribution. Count discreteness
can make model mass exceed the nominal level. Dispersion zero uses the mathematical
Poisson limit. Invalid/nonfinite parameters fail validation; the model is not refit
or silently repaired.

These are derived presentation values, not overwritten historical intervals and
not measured real-world interval coverage. The Sprint 8 censored-bin coverage audit
does not establish uncensored range coverage. No outcome is consulted to construct
a range. Parameterization and quantiles follow the official
[SciPy negative-binomial documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.nbinom.html)
and its [Poisson distribution](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.poisson.html).

## Verification and remaining scope

Use `make quality VENV=.venv-sprint10b` and
`make runtime-acceptance VENV=.venv-sprint10b`. Checks cover evidence integrity,
raw/stabilized role mapping, legacy behavior, input validation, idempotency,
outcome/discovery independence, uncensored quantiles beyond 12, PostgreSQL
migrations/persistence/recovery, real container HTTP, and unchanged frozen inference.

The React dashboard, authentication/hosting, production-size recovery, prospective
collection, and validation of any future per-game confidence grade remain outside
this milestone. No historical records or retrospective explanations are populated here.
