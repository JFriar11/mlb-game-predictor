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
