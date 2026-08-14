# Live Operations

One-time preparation uses `ingest-season --season 2026`, `audit-season --season 2026`,
then `launch-prospective`. Do not rerun `freeze-accepted-model`; it is frozen.

Daily repeat-safe command:

```bash
.venv-sprint0/bin/mlb-predictor daily-live --date YYYY-MM-DD
```

Run at roughly T-minus-30. Add `--dry-run` to avoid prediction writes or `--game-pk ID`
for one game. Both nine-player batting orders are required.

The 2026 ingestion command adds only currently completed games and is idempotent. Those
outcomes supply rolling feature state; the frozen artifact never trains from them.

```bash
.venv-sprint0/bin/mlb-predictor settle-live --date YYYY-MM-DD
.venv-sprint0/bin/mlb-predictor inspect-prediction GAME_PK
```

Never backdate the host clock or describe a post-start diagnostic as prospective.

## Automated operations

Run one complete idempotent cycle:

```bash
.venv-sprint0/bin/mlb-predictor poll-live --date YYYY-MM-DD
```

Start the local watcher and inspect it:

```bash
.venv-sprint0/bin/mlb-predictor watch-live --date YYYY-MM-DD
.venv-sprint0/bin/mlb-predictor watcher-status
.venv-sprint0/bin/mlb-predictor today-predictions --date YYYY-MM-DD
```

The default cadence is five minutes while watching a game day. A hosted scheduler should
run every five minutes from roughly three hours before the first game until 45 minutes after
the last scheduled start; outside that interval one daily state refresh is sufficient. This
provides four chances inside the primary 20-minute window without polling continuously.

Optional `MLB_NOTIFICATION_WEBHOOK_URL` receives generic JSON events. No paid provider is
required. The database watcher event table and structured logs remain the system of record.

## Hosting recommendation

Sprint 10A.5 recommends an Azure Container Apps scheduled Job on the Consumption plan plus
Azure PostgreSQL Flexible Server B1ms as the best overall/easiest option. Expected cost is
$16–18/month after any eligible 12-month database grant. The cheapest acceptable alternative
uses a verified slim Neon database and is expected to fit its $0 Free plan, with a usage-based
Launch upgrade path. See `docs/SPRINT10A_5_HOSTING_COST_DECISION.md` for assumptions, the full
comparison, secrets, and exact post-approval deployment sequence.

Do not upload the full historical raw cache. The host needs normalized feature history,
frozen artifacts, and prospective operations tables; current feeds may use ephemeral scratch
space. Do not deploy until the user approves the database/cost choice, Azure subscription,
region, registry, and secrets.

Local/manual operation costs no additional money but requires an awake laptop and is not
reliable prospective collection. GitHub Actions is easy but a poor system of record: its
ephemeral runners still require externally reachable PostgreSQL, private-repository minutes
are metered, and scheduled runs can be less operationally controllable. Azure keeps compute,
database networking, identity, secrets, job history, and future application hosting together.
