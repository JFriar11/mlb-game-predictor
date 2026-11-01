# Completion readiness and remaining milestones

Audit date: 2026-11-01. This is a repository readiness audit, not a new model
evaluation or a production acceptance result.

## Verified starting point

- Research and live CLI implementation extend through Sprint 10A.5. The original
  Sprint 0 handoff text in AGENTS.md no longer describes implementation progress.
- Local verification: Ruff passed, all 99 Python files passed formatting, and
  pytest reported **31 passed**. CLI help loads successfully.
- The local `data/processed/accepted_model_v1.joblib` exists and matches the
  frozen SHA-256 enforced by `verify_accepted_artifact`.
- Tests use an in-memory SQLite fixture. Passing tests do not establish PostgreSQL
  migration compatibility, production concurrency behavior, or database health.
- Docker daemon was unavailable. Persisted database contents, Alembic state,
  watcher health, and prospective prediction counts were not reverified.
- Added GitHub Actions quality checks for Python 3.11 and 3.12. The workflow has
  not run remotely; nothing was committed or pushed. It performs no ingestion,
  deployment, or scheduled prediction collection.

## Definition of a finished portfolio release

The local product must reproduce setup, serve predictions through a documented API
and React application, explain uncertainty and data limitations, and expose model,
feature, cutoff, and timing provenance. A public production release additionally
requires approved hosting, tested recovery, monitoring, and observed operation.
Model research need not expand to complete this release.

Completion gates, in order; stop for review after each milestone:

Sprint 10B completed 2026-11-01. See `SPRINT10B_RUNTIME_AUDIT.md`: isolated
PostgreSQL, backup/restore, installed runtime, and frozen-model portability passed.
The original readiness audit above remains a record of the starting state.

Sprint 10C completed 2026-11-01. The read-only API and its validation, PostgreSQL,
and container HTTP checks are documented in `API.md` and `SPRINT10C_API_AUDIT.md`.

Sprint 10D completed 2026-11-01. Retained input summaries, qualified uncertainty,
uncensored ranges, and local migration acceptance are documented in
`EXPLANATIONS.md` and `SPRINT10D_EXPLANATION_AUDIT.md`.

Sprint 10E completed 2026-11-01. The local React dashboard, explicit synthetic
demo, production build, and browser/API acceptance are documented in
`../frontend/README.md` and `SPRINT10E_DASHBOARD_AUDIT.md`.

1. **Sprint 10B — Reproducible runtime and database acceptance.** Add container
   packaging, a reproducible dependency strategy, and isolated PostgreSQL acceptance
   checks. Verify migrations on an empty database, repeat-safe prediction/settlement,
   preserved forecasts, and a backup/restore rehearsal. Preserve the accepted model
   checksum; do not refit it to satisfy packaging. Document how a fresh checkout
   obtains the ignored frozen artifact and required normalized history.
2. **Sprint 10C — Prediction API.** Add typed read-only FastAPI endpoints for dated
   predictions, game detail, model metadata, and health/readiness. Test missing dates,
   absent artifacts, unavailable database, response validation, and provenance.
   Keep administrative ingestion and model fitting outside public routes.
3. **Sprint 10D — Product semantics and explanations.** Specify and validate
   baseball-grounded factors and confidence reporting. Distinguish input quality,
   calibrated win probability, and run uncertainty; do not invent an unvalidated
   confidence percentage. The current PMF uses a censored 12+ bin: label the tail
   explicitly and prevent it from appearing as an exact final score. Explain that
   paired score probabilities and calibrated win probabilities use different steps.
4. **Sprint 10E — React application.** Deliver a usable dated game view and detail
   page with runs, win probabilities, distributions, 80%/95% ranges, score labels,
   factors, uncertainty, versions, and timestamps. Cover loading, empty, skipped,
   stale, and error states; verify accessibility and responsive layouts.
5. **Sprint 10F — Release and hosting.** Prepare reviewable infrastructure and
   deployment instructions, then obtain the outstanding infrastructure approval
   before provisioning. Verify secrets handling, startup, scheduler idempotency,
   monitoring, recovery, and an eligible live game day. Historical cost estimates
   from August require fresh verification before choosing a provider.
6. **Sprint 11 — Portfolio handoff.** Publish a model card, concise architecture and
   evaluation narrative, screenshots/demo, fresh-clone instructions, operational
   runbook, release checklist, and explicit limitations. Verify every advertised
   output and command. Commit, push, or publish only when explicitly requested.

## Scientific and operational boundaries

All 2021–2025 performance remains retrospective development evidence. Do not fill
missing 2026 predictions retroactively or imply the launch timestamp proves the
watcher ran. Inspect the actual ledger before reporting prospective results. The
CLI currently limits historical ingestion to 2021–2026; readiness for a later
regular season requires an explicit cutoff/state review, not a date substitution.

Observed weather and unpromoted research components remain excluded. Historical
lineup reconstruction, independent scoring, approximate extra innings, and censored
tails remain disclosed limitations. New model promotion retains the existing
prospective evidence requirements.

## Next action and manual prerequisites

Recommend Sprint 10F next: concrete release packaging and hosting preparation.
The local dashboard/API are implemented. Hosting provider/cost, account, region,
registry, secrets, public-access policy, and monitoring still require the existing
infrastructure decision before provisioning. Do not treat local build acceptance
as approval to purchase, provision, publish, commit, or push.
Hosting choice, subscription, region, registry, and secret configuration are required
only before deployment. No cloud resources were created by this audit.

2026-11-01: approved dashboard preserved; release preparation now includes a
private combined image, offline private/manual infrastructure checks, and a
successful normalized-state recovery rehearsal. See `RELEASE.md` for deployment,
monitoring, season readiness and prospective acceptance gates. The portfolio
project is not yet a deployed or prospectively validated production system.

2026-11-01 local-operation decision: Cloud deployment is deferred by the user.
The local lineup sandbox now supports offseason hypothetical inference with the
frozen model and strict separation from official predictions. Local user acceptance
is the next step. Fresh 2027 ingestion/season readiness and prospective validation
remain separate future milestones. See `SANDBOX.md`.
