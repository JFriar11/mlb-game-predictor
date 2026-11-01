# Local lineup sandbox

This is a what-if tool backed by the accepted frozen model, not the synthetic
demo. User-supplied inputs generate real model inference without saving a game,
forecast, evidence snapshot, operational state or evaluation result. PostgreSQL
transactions remain read-only. No network ingestion or fitting occurs.

## Start and use

From the repository root, with the existing virtual environment, PostgreSQL and
accepted artifact available:

```bash
make sandbox VENV=.venv-sprint10b
```

Open <http://127.0.0.1:8020/?sandbox=1>. This command builds the approved notebook
UI and serves it with FastAPI on loopback. Stop with Ctrl+C. It does not restart
other servers or create cloud resources. If the supported PostgreSQL container is
stopped, run `make postgres` first. Install frontend dependencies with
`make dashboard-install` only if missing. Existing `.env` database settings and
`MLB_ARTIFACT_PATH` apply; credentials never enter browser code.

1. Select the two teams, park and history cutoff.
2. Load each side's retained starting lineup as an editable starting point, or
   type player names and select suggestions. Select both starting pitchers.
3. Enter nine different hitters on each team and select **Predict this matchup**.
4. Review expected runs, win probabilities, full censored-bin distributions,
   uncensored 80%/95% count ranges, most likely score combinations, baseball input
   summaries and input-quality warnings. Editing any input clears the result.

The page is also linked from **Lineup sandbox** in the notebook navigation.
When using the separate Vite dev server, start its API with
`MLB_SANDBOX_ENABLED=true` and point `MLB_DASHBOARD_API_TARGET` at that API.
Sandbox endpoints are absent unless explicitly enabled. Ordinary API/release
behavior remains the read-only official ledger. Do not enable public hosting for
this CPU/memory-intensive local tool without a separate access/resource design.
One inference at a time is allowed per API process; additional requests get 503.
The browser times out a prediction after two minutes; cancellation can discard a
response without stopping server computation immediately.

## Scientific boundaries

- The model is trained on 2021–2025. Cutoffs must be timezone-aware, between
  2026-01-01 and now; this is not a backtest interface for training-period games.
  Browser date entry means midnight UTC. Offset timestamps normalize to UTC.
- Features reuse `build_live_feature_pair`, excluding all same-UTC-calendar-date
  results. Retained lineup suggestions also come from strictly prior dates and
  initial starters only. They are not confirmed lineups or current rosters.
- Local history currently ends **2026-08-13**. The default cutoff is the next day,
  rather than pretending the offseason has fresh bullpen data. Later dates are
  allowed through today, with stale-history/rest/bullpen warnings. No new data
  is fetched. Individual cold starts retain the accepted fallback treatment.
- All known players can be combined, regardless of roster membership, including
  hypothetical trades. IDs must exist locally; no invented player projections.
  Eighteen hitters must be unique across teams. Pitchers must be different and
  cannot bat for the opposing team; a two-way player may bat for their own team.
- The accepted model aggregates the nine hitters. Reordering the same hitters
  does not change its inputs or prediction. No order-sensitive simulation is added.
- The historical Field of Dreams sentinel venue ID -1 is excluded from selectable
  parks. No new venue mapping is inferred.
- This is a nine-inning regular-season model, with the accepted extra-innings
  approximation. Custom/postseason matchups are not separately validated.
- 12+ is a censored bucket in distributions and score combinations. Count ranges
  are model quantiles, not empirical coverage guarantees. Calibrated probabilities
  retain retrospective evidence only; confidence in hypothetical lineups is not
  established. Baseball summaries describe inputs, not causal contributions.
- No official/prospective result or settlement is created. Reloading loses the
  scenario and result. The frozen artifact and launch boundary remain unchanged.

## API

With `MLB_SANDBOX_ENABLED=true`:

- `GET /api/v1/sandbox/catalog`: known teams, players, positive-ID parks, retained
  history endpoint and suggested cutoff. Names do not establish roster eligibility.
- `GET /api/v1/sandbox/lineup?team_id=...&as_of=...`: a prior retained initial lineup,
  pitcher and game park; 404 when none is available.
- `POST /api/v1/sandbox/predict`: JSON `as_of`, `home_team_id`, `away_team_id`,
  `venue_id`, `home_starter_id`, `away_starter_id`, `home_lineup`, `away_lineup`.
  Each lineup has exactly nine positive integer IDs. The distinct response contract
  requires `kind=hypothetical`, `is_official=false`, `saved=false`; it includes
  echoed inputs, timestamp, frozen artifact checksum, model version, predictions,
  freshness, input-quality and explanation fields. No official game ID is assigned.

Missing/mismatched artifacts fail closed with 503 before deserialization. Only
checksum-verified trusted local bytes may be loaded. A virtual ID exists solely
inside the existing feature-evidence interface; it is never persisted or exposed
as an official game. Unknown IDs and conflicting lineups return 422.

## Acceptance

Ruff and the production TypeScript/Vite build pass. Python regression suite:
99 passed, one opt-in PostgreSQL skip. Browser acceptance includes actual local
PostgreSQL/accepted-artifact inference (22 browser checks passed), plus malformed/error/stale-response,
mobile keyboard and automated accessibility checks. See `PLANS.md` for final count.

A real scenario using retained Arizona Diamondbacks and Athletics lineups at the
2026-08-14 UTC cutoff produced approximately 4.730 away runs, 4.599 home runs and
51.92% home win probability. All 18 domain table row counts were unchanged and
`live_prediction_records` remained zero. The API's PostgreSQL read-only transaction
provides write protection in addition to the row-count check. Tests independently
reject DML and verify the prior-date lineup/cutoff boundary.

Known debt: feature building reads substantial history per request; model loading
is per prediction, with no trained-model changes or performance optimization in
this milestone. No cloud deployment, scheduling, commits or pushes were made.
