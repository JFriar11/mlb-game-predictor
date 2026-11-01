# Sprint 10D — Retained inputs and qualified uncertainty

Date: 2026-11-01. Presentation and provenance milestone; no model refitting or promotion.

## Delivered

- Migration `0014` and `prediction_input_snapshots`, capturing new predictions'
  exact accepted raw/stabilized numeric inputs, game/team/starter/lineup IDs,
  feature cutoff, artifact hash, source, and version in the forecast transaction.
- Optional input capture in `save_prediction`, wired into the CLI generation path.
  Official reruns retain the original evidence and never fill legacy gaps.
- API `explanation`: four fixed-order baseball input summaries per offense with
  raw/model values, sample sizes when known, opposing-pitcher role labels, and
  explicit fallback/proxy limitations. These are not causal or ranked attributions.
- API `confidence`: calibrated favorite probability, separate recorded input-quality
  flags, and rounded Sprint 8 retrospective calibration evidence. No invented
  composite score, per-game reliability estimate, or prospective validation claim.
- API `run_ranges`: uncensored marginal 80%/95% count quantiles derived from saved
  distribution parameters, with nominal/model mass. Stored PMFs, bin intervals,
  scores, and win probabilities remain unchanged.
- Fail-closed snapshot provenance checks and accepted-version checks; missing legacy
  evidence remains valid and explicitly unavailable. See `EXPLANATIONS.md`.

## Verification

```bash
make quality VENV=.venv-sprint10b
make runtime-acceptance VENV=.venv-sprint10b
```

- Ruff and formatting passed. Pytest reported **78 passed, 1 skipped**, with the
  existing Starlette TestClient deprecation warning. The opt-in PostgreSQL test
  passed separately in the full runtime harness.
- Tests reject unaccepted/target columns, malformed rates/counts/nonfinite values,
  wrong-side inputs, mismatched game/starter/artifact/cutoff/source/version binding,
  and invalid accepted-version metadata. Invalid capture leaves no partial forecast
  or snapshot in the transaction.
- Tests verify raw/stabilized lineup values, opposing pitching interpretation,
  missing legacy evidence, data-quality flag separation, and persistence of input
  evidence through discovery changes, reruns, and settlement.
- Count-range tests independently enumerate the NB CDF, verify nominal/model mass,
  nesting, zero-mean/Poisson-limit behavior, invalid parameters, and 95% bounds
  greater than 12. These are mathematical checks, not empirical coverage claims.
- The full runtime harness passed in **16.7 seconds** on the final game-ID binding
  build. All migrations through `0014`, repeat upgrades, PostgreSQL read-only
  enforcement, and schema checks passed. Dump/restore matched all **19 tables**
  and sequence states, including the input snapshots.
- Real container HTTP exposed retained explanations and uncertainty fields. The
  HTTP smoke left table contents and sequences unchanged. Frozen artifact checksum
  and host/container inference agreement passed without modifying model outputs.
- Host/container dependency checks passed. No dependencies were added in this sprint.

## Local database acceptance

After isolated acceptance, started the existing Compose PostgreSQL service and
applied only the tested additive `0013` → `0014` migration, explicitly bound to
the local Compose endpoint. Alembic reported no pending upgrade operations.

- All **17 pre-existing domain-table counts** remained identical.
- The database retains **13,970 games** and **zero prediction records**; this is
  not evidence of prospective forecasting performance.
- Forecast and operational/launch-state payload hashes remained identical.
- The new input-snapshot table has **zero rows**. No explanations were backfilled.
- API readiness returned **200**, and the dated prediction GET returned **200**.
- The accepted artifact checksum remained unchanged. No ingestion or historical
  feature rebuilding occurred. Temporary acceptance containers were removed; the
  supported local Compose database remains available.

## Limits and next step

These explanations describe inputs, not learned per-feature contributions. Input
quality flags are not calibrated reliability grades. Calibration evidence remains
retrospective and weak in extreme probability regions. Derived uncensored ranges
have no new empirical coverage audit. Missing snapshots cannot be reconstructed
honestly from current data. Supported pipeline immutability does not restrict
direct database administration.

Local acceptance checks schema, preserved counts, ledger/launch hashes, and API
readability; it is not a fresh season-wide data-quality audit or production-size
recovery rehearsal. The current ledger is empty. A future genuine pregame collection
period is still needed for prospective evidence.

Recommend Sprint 10E, the React dashboard, using explicit empty and missing-evidence
states. No manual task is needed before that local milestone. No commit, push,
public deployment, paid resource, or live watcher was started. Stop for review.
