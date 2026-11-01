# Sprint 10E — Local React dashboard

Date: 2026-11-01. Local application milestone; no hosting deployment or model changes.

## Delivered

- A React/TypeScript/Vite dashboard under `frontend/`, with committed npm lockfile
  and a responsive scorebook design. All browser data reads use the existing API
  through a same-origin, server-configured local proxy.
- Date navigation, URL-backed game selection/deep links and lookup, expected runs,
  calibrated wins, interactive 80%/95% ranges, distribution charts and accessible
  data tables, score-bin labels, input summaries, qualified confidence components,
  provenance, model notes, and separate settlement outcomes.
- Runtime validation of rendered response fields; cancellation of superseded
  requests; distinct loading, empty, missing-evidence, not-recorded, unknown-game,
  API-error, invalid-response, and stale-refresh states.
- An explicitly selected, persistently labeled synthetic demo with no API calls,
  real model inference, ledger writes, or fallback-on-error behavior. Its generator
  uses an in-memory database and serializes current Python response models with
  the public field aliases. A Python test checks fixture/schema compatibility.
- Make targets, a frontend CI job, operating instructions in `frontend/README.md`,
  and ignored build/browser artifacts. Local Sites workflow only; no Site identity,
  source synchronization, publication, or cloud resources.

## Validation evidence

- `npm run build` passed TypeScript checking and a production Vite build. Output
  was approximately 396 KiB on disk; the main JS asset was about 108 KiB gzip.
  Two third-party Zod/Rollup comment-annotation warnings do not prevent the build.
- **15 browser tests passed**, including an opt-in actual-API proxy check. The 14
  controlled browser scenarios cover demo isolation, honest empty dates, URL/back
  navigation, lookup, missing evidence, API failures, malformed data, explicit stale
  warnings, missing artifacts, settlement/censoring, loading, request races, mobile
  layout, keyboard navigation, and automated accessibility checks.
- Automated WCAG 2 A/AA and 2.1 AA checks found no violations on the tested expanded
  desktop view. Corrected the two contrast findings encountered during development.
  Mobile at 375×812 had no horizontal overflow; keyboard skip navigation and range
  controls passed. Screenshots were inspected for desktop and mobile layouts.
- Browser acceptance uses Playwright's supported `chromium` channel. The separately
  distributed headless-shell bundle crashed with ICU/GPU initialization errors on
  the local Mac; full Chromium passed the same tests.
- The default API port 8000 was occupied. Preserved that existing service and
  started the current read-only API temporarily on **8010**, explicitly connected
  to the local Compose database. The preview proxy exercised real dated GET,
  readiness, and model metadata endpoints with 200 responses. The actual empty
  ledger rendered as empty, without synthetic substitution.
- Python regression suite: **79 passed, 1 skipped**, with the existing Starlette
  TestClient warning. The skipped opt-in PostgreSQL harness was already accepted
  in Sprint 10D; this client milestone changes no backend schema/model runtime.
  The new fixture contract check also passed after final fixture regeneration.
- Ruff, formatting, and `git diff --check` passed. Frozen artifact checksum remains
  unchanged. No API write calls, ingestion, fitting, migration, or live collection.
- Playwright stopped its preview servers. The owned API process on 8010 was shut
  down after acceptance; the pre-existing service on 8000 was not changed.

Final integrated browser command, with the verification API running on 8010:

```bash
cd frontend
PLAYWRIGHT_BROWSERS_PATH=0 MLB_DASHBOARD_REAL_API=1 \
  MLB_DASHBOARD_API_TARGET=http://127.0.0.1:8010 npm test
```

The default CI/browser run skips the actual-API test unless explicitly enabled;
it needs no private model artifact, persistent database, or external MLB request.
Remote CI has not been executed because no commit or push was requested.

## Limitations and handoff

Chromium acceptance is not a full assistive-technology review or Safari/Firefox
compatibility claim. Refresh is manual, not a real-time data subscription. The
underlying ledger remains empty and no prospective model success is established.
Synthetic means/probabilities are stipulated examples, not fitted-model results.
Input summaries remain noncausal, and count categories retain the 12+ tail and
extra-inning/calibration limitations documented in previous milestones.

The built static assets do not yet have production hosting, authentication,
monitoring, or reverse-proxy deployment packaging. Vite preview is local QA, not a
production host. The Python Docker image continues to serve API/CLI only. Hosting
provider/cost, account, region, registry, secret, access, and operations decisions
remain subject to explicit approval; no Site/cloud project was provisioned.

To view locally, follow the two-terminal commands in `frontend/README.md`. No
additional account setup is needed. Recommend Sprint 10F release/hosting
preparation next, then pause for infrastructure approval before provisioning.
