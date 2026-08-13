# Decision Log

Record important project decisions here. Add dates and reasons.

## D001 — Prediction timing

**Decision:** The primary system predicts approximately 30 minutes before first pitch after confirmed starting lineups are available.

**Reason:** Lineups materially affect offensive quality and can usually be incorporated close to game time.

## D002 — Historical lineup reconstruction

**Decision:** Use actual historical starting lineups for the first version.

**Constraint:** Exact proof that each lineup was publicly confirmed at T-minus-30 may be unavailable.

**Safeguard:** Use only starting players and batting order. Exclude substitutions and target-game performance. Describe the model as a confirmed-lineup historical reconstruction.

## D003 — Initial game scope

**Decision:** Begin with regular-season games. Exclude postseason from the initial model.

**Reason:** Postseason pitcher usage and roster behavior differ.

## D004 — Initial season

**Decision:** Prove ingestion on five games, then ingest 2025, then expand toward 2021–2025.

**Reason:** This limits wasted work and exposes ID, lineup, starter, doubleheader, and venue issues early.

## D005 — System of record

**Decision:** Use PostgreSQL for normalized historical entities, features, and predictions. Use Parquet for large pitch-level raw datasets.

## D006 — Evaluation

**Decision:** Use chronological evaluation only for model selection and final reporting.

## D007 — Development order

**Decision:** Correct data reconstruction and leakage-safe baselines come before advanced matchup features, simulation, dashboard work, or cloud deployment.

## D008 — Sprint 0 ingestion boundary

**Date:** 2026-08-03

**Decision:** The Sprint 0 CLI accepts only the exactly five unique game IDs stored in a
reviewable manifest. Each game is a separate transaction, and reruns replace its starter
and lineup children while upserting stable-ID entities.

**Reason:** An explicit manifest makes the acceptance sample reproducible, prevents an
accidental season download, and provides straightforward idempotency when MLB corrects a
historical feed.

## D009 — Cross-row validation

**Date:** 2026-08-03

**Decision:** Enforce scalar and uniqueness invariants in PostgreSQL and check completeness
(two starter sides and two complete 1–9 lineups) in an acceptance validator.

**Reason:** SQL checks and unique constraints reliably reject invalid rows, while exact
cross-row cardinality is clearer and easier to audit in application validation.

## D010 — Supported local PostgreSQL and reproducibility workflow

**Date:** 2026-08-03

**Decision:** Docker Compose is the sole supported local PostgreSQL setup. A fresh clone
can run `make sprint0-acceptance`, which creates an isolated Python environment, installs
dependencies, health-checks PostgreSQL, runs quality and migration checks, ingests the
five-game manifest twice, validates it, and prints one reconstruction.

The Make workflow explicitly exports the Compose database URL; ignored developer `.env`
files cannot redirect the acceptance run to another local database.

## D011 — Player-game outcome storage

**Date:** 2026-08-03

**Decision:** Store normalized player-game batting and pitching counting statistics in
PostgreSQL, including pitching innings as integer outs rather than baseball-decimal text.

**Reason:** Integer outs are unambiguous and aggregatable. Normalized outcomes support
future as-of rolling features while database constraints and stable IDs preserve quality.

## D012 — Raw cache and season freeze

**Date:** 2026-08-03

**Decision:** Cache the 2025 schedule and completed-game feeds as ignored gzip JSON files,
write them atomically, and freeze the layer with a deterministic SHA-256 manifest.

**Reason:** A local raw layer makes ingestion resumable and repeatable without repeated API
requests. The manifest detects source changes while keeping large source data out of Git.

## D013 — Same-day outcomes are excluded

**Date:** 2026-08-03

**Decision:** Build every target-date snapshot before updating state with any game from that
date. Game 2 of a doubleheader cannot use Game 1 in `sprint2_v1`.

**Reason:** The historical layer does not establish when Game 1 became final and processed
relative to Game 2's T-minus-30 cutoff. Exclusion is the defensible leakage-safe default.

## D014 — Versioned feature snapshots and fallbacks

**Date:** 2026-08-03

**Decision:** Persist two versioned rows per game with explicit as-of/source dates, sample
sizes, and fallback counts. Use expanding prior league values and documented fixed priors
for 2025 cold starts.

**Reason:** Persisted metadata makes leakage and cold-start behavior auditable. Feature
versions prevent silent changes from invalidating later chronological comparisons.

**Reason:** One repository-owned workflow avoids machine-specific Homebrew service state
and makes the acceptance sequence reviewable. The local Compose credentials are explicitly
development-only defaults; real credentials stay in ignored environment configuration.

## D015 — One-season chronological development protocol

**Date:** 2026-08-03

**Decision:** Use March 18–May 31 as warm-up/initial training, expanding June, July, and
August validation origins for selection, and September 1–28 as an untouched final test.
Select only on aggregate development Poisson deviance.

**Reason:** This preserves ordering and gives repeated in-season evidence while only 2025
exists. September is not a final estimate of generalization across seasons.

## D016 — Immutable feature input and small-sample treatment

**Date:** 2026-08-03

**Decision:** Sprint 3 consumes `sprint2_v1` unchanged. Raw models see persisted values;
stabilized models apply fixed-prior, sample-size-weighted shrinkage, clipping, and log
sample sizes inside the modeling pipeline. Corrections require a new feature version.

**Reason:** Downstream stabilization permits a fair chronological raw-versus-treated
comparison without silently changing the accepted feature contract.

## D017 — Baseline remains the selected model

**Date:** 2026-08-03

**Decision:** Retain league average as the Sprint 3 selected model because it had the
lowest aggregate development Poisson deviance. Report stabilized Poisson separately as
the best nonconstant model; do not promote complexity based on the final test.

**Reason:** The selection rule includes simple baselines, and the final test cannot be
used to revise model choice after it is opened.

## D018 — Season-partitioned expansion and cancelled games

**Date:** 2026-08-03

**Decision:** Cache and hash each season separately. Normalize only regular-season feeds
with coded state `F`; retain but do not normalize cancelled schedule entries.

**Reason:** MLB can label cancelled entries abstractly Final. Coded status distinguishes
played games without deleting source evidence.

## D019 — Offseason history treatment

**Date:** 2026-08-03

**Decision:** `sprint3_5_v1` carries MLB player history across teams and missing seasons
with fixed 0.5 decay at each offseason, carries the immediately previous team season for
Opening Day, and records prior-history sample provenance. No-decay and cold-start controls
are separate feature versions.

**Reason:** Versioned controls make the value of history and decay testable without future
assignments, target-season totals, or silent changes to `sprint2_v1`.

## D020 — Prospective evaluation reserve

**Date:** 2026-08-03

**Decision:** Treat every 2021–2025 result as development/backtesting evidence. Reserve
2026 live predictions, or another future locked period, for prospective evaluation.

**Reason:** The team has already inspected and made decisions using 2025 results.

## D021 — Compact matchup aggregates from frozen feeds

**Date:** 2026-08-04

**Decision:** Replay the accepted cached completed-game feeds into normalized
batter-by-pitcher-hand and player-by-pitch-group game aggregates. Do not alter the cache
or add a second pitch-level raw store during Sprint 4.

**Reason:** The feeds contain the plate-appearance and pitch classifications needed for
the planned experiment. Compact aggregates are idempotent, auditable, and avoid millions
of redundant PostgreSQL pitch rows.

## D022 — Versioned, prior-date matchup state

**Date:** 2026-08-04

**Decision:** Add `sprint4_v1` alongside `sprint3_5_v1`. Estimate batting-order weights,
handedness rates, starter pitch mix, and batter pitch-group response only from prior dates,
with fixed shrinkage strengths, offseason decay, sample sizes, and fallback counts.

**Reason:** A new version preserves the accepted foundation and makes every small-sample
treatment explicit. Date-batched updates prevent target-game and same-day leakage.

## D023 — Do not promote the Sprint 4 bundle

**Date:** 2026-08-04

**Decision:** Retain `sprint3_5_v1` as the modeling reference. Preserve `sprint4_v1` as an
audited experiment, but do not promote the complete bundle into later models without a
new, predeclared component ablation.

**Reason:** Relative to `sprint3_5_v1`, combined Poisson deviance worsened by 0.0409 for
stabilized Poisson and 0.00465 for gradient boosting. Small seasonal improvements were
not consistent enough to justify added complexity.

## D024 — Prior-usage bullpen roles and availability

**Date:** 2026-08-12

**Decision:** Define high-usage relievers from the three largest strictly prior appearance
counts. Treat a reliever as workload-unavailable after at least 30 pitches yesterday or 50
pitches over the prior three days. Build the quality mixture from remaining relievers.

**Reason:** Saves, holds, leverage index, roster transactions, and manager declarations are
not normalized. A transparent pregame workload proxy avoids leaking end-of-season roles.

## D025 — Rolling starter forecast remains selected

**Date:** 2026-08-12

**Decision:** Select decayed pitcher rolling history for starter outs and pitch count rather
than Sprint 5 gradient boosting. Derive expected bullpen outs from scheduled innings minus
the rolling starter-outs estimate.

**Reason:** Across rolling 2022–2025 origins, rolling history had lower MAE and RMSE for
both targets. Complexity did not earn promotion.

## D026 — Do not promote the complete pitching-state bundle

**Date:** 2026-08-12

**Decision:** Preserve `sprint5_v1` for component use and future declared ablations, but
retain `sprint3_5_v1` as the run-model reference.

**Reason:** Adding all Sprint 5 state fields increased combined run Poisson deviance from
2.27647 to 2.28171. Improvements in 2022 and 2024 were not consistent across seasons.

## D027 — No Sprint 5.5 downstream promotion

**Date:** 2026-08-12

**Decision:** Create no new run feature/model version from Sprint 5.5. Keep all Sprint 5
features component-only. Preserve available-reliever quality as a prospective-confirmation
candidate, not as a promoted run-model input.

**Reason:** Its combined Poisson deviance improved from 2.27647 to 2.27310, but the gain
was concentrated in 2022 and the subset worsened 2023, 2024, and 2025. Other improvements
were smaller, while every predeclared compact group worsened the primary metric. Selecting
on the combined result alone would overstate evidence after repeated historical review.

## D028 — Environment proxies are not promoted

**Date:** 2026-08-12

**Decision:** Retain `sprint6_v1` as an audited component layer. Do not add its weather
proxies or park adjustments to the accepted run-model version.

**Reason:** Completed-feed temperature/wind improved retrospective deviance but are not
archived pregame forecasts. Park adjustments worsened. Static venue attributes improved
modestly but overlap the baseline's categorical venue feature.

## D029 — Global fold-only negative binomial for run distributions

**Date:** 2026-08-13

**Decision:** Keep the accepted mean model unchanged and use a negative-binomial run
distribution whose single dispersion parameter is estimated only from each training fold.

**Reason:** Runs are materially overdispersed. Negative binomial improved NLL and ranked
probability score over Poisson in every season. Recent-season dispersion was only
marginally better combined and worse in 2025, so the global training estimate is sturdier.

## D030 — Independent regulation distributions and approximate extra innings

**Date:** 2026-08-13

**Decision:** Simulate home and away regulation runs independently. Resolve regulation ties
with the home-win rate from prior extra-inning training games. Prefer analytic win
probabilities when available and use simulation for score/total summaries.

**Reason:** Scoring residual correlations range from -0.025 to 0.015, too small to justify
a joint adjustment. The extra-inning method is transparent and avoids counting ties as a
win or loss, but remains an approximation.
