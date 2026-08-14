# Sprint 10A.5 Hosting and Cost Decision

**Decision date:** 2026-08-13  
**Scope:** Operate the frozen `accepted_model_v1` watcher through the remainder of the
2026 regular season. No resources were provisioned by this sprint.

## Measured workload

These estimates use the current repository and database rather than a generic production
service:

- A normal full MLB date has about 15 games; the August 14 discovery returned 14.
- The recommended schedule is one state refresh outside the game window and a five-minute
  poll from about three hours before the first game through 45 minutes after the last. A
  typical date therefore produces 100–120 polling cycles, or 3,000–3,600 executions/month.
- One warm incremental cycle normally lasts seconds. Budgeting 30 seconds per cold
  container execution at 0.25 vCPU/0.5 GiB gives only 27,000 vCPU-seconds and 54,000
  GiB-seconds/month at 120 executions/day.
- A busy day makes at most about 15 immutable prediction inserts, 15 settlements, and 15
  completed-game state updates. Most polls write only watcher health/events.
- The current local PostgreSQL database is 445,168,663 bytes (about 425 MiB). It includes
  research/component tables not needed by the watcher. A live-only database containing
  migrations, reference data, games, starting lineups/starters, batting/pitching history,
  and prospective operations state is expected to remain about 150–250 MiB in 2026.
- The compressed raw MLB cache is 1.7 GiB for 2021–2026, including 225 MiB for 2026. The
  frozen accepted model/configuration is under 1 MiB.

Five-minute scheduling supplies four nominal attempts in the primary T-minus 20–40 window.
The job must remain idempotent, have a single replica, reject an invalid model checksum,
and retry a failed execution. The watcher already enforces the prediction eligibility and
immutability rules; hosting does not change them.

## Cost and operations comparison

Prices are planning estimates in USD as of 2026-08-13. Region, tax, account eligibility,
and provider changes can alter the invoice.

| Option | Expected monthly cost | Scheduling and window reliability | Operations, failure behavior, and lock-in |
|---|---:|---|---|
| Azure Container Apps scheduled Job + Azure PostgreSQL Flexible Server B1ms | **$16–18** after free offer; possibly **$0** for the first eligible 12 months | Native five-field UTC cron supports every five minutes. Four primary-window attempts, replica retry, execution history, and same-cloud connectivity make this the strongest option. | Compute is inside the Container Apps monthly grant. PostgreSQL is about $12.41 compute + $3.68 for the 32-GiB minimum; up to provisioned storage in backup space is included. Container Apps secrets are sufficient; Key Vault is optional. Low complexity, good retry visibility, moderate Azure lock-in. B1ms is burstable and not an HA production tier. |
| Azure Container Apps scheduled Job + Neon Free/Launch PostgreSQL | **$0 expected on Free**; about **$8–15** on Launch | Same reliable Azure cron and retry behavior. Cross-cloud TLS adds small latency but not enough to threaten the window. Neon may cold-start after idle periods. | Cheapest acceptable. Free includes 100 CU-hours and 0.5 GB/project; the live-only database must stay below that hard storage allowance. Launch is usage based. Use pooled TLS connection URL in a Container Apps secret. Two vendors and no Free/Launch SLA increase operational risk and vendor surface. |
| GitHub Actions schedule + hosted PostgreSQL | **$0–10** with included minutes plus Neon Free; **$18–22** for all 3,000–3,600 Linux minutes at $0.006/min | Five minutes is GitHub's minimum interval, but GitHub documents that scheduled jobs can be delayed and, under sufficient load, dropped. It may still hit a late attempt, but it is not reliable enough to be the sole prospective recorder. | Easiest CI-style YAML and GitHub secrets, but every ephemeral job checks out code and installs or pulls dependencies. Failures need workflow retries/manual dispatch. A public TLS database is required. Strong GitHub workflow lock-in and minute rounding. |
| Azure Functions Consumption timer + Neon | **$0 expected** | Timer execution is adequate and Functions grants dwarf this workload. A five-minute timer can hit the window if the function remains healthy. | Compute is inexpensive, but packaging the existing scientific Python/container application as a Function is a code and deployment redesign. It adds a required Azure Storage account and more cold-start/package troubleshooting. Similar DB tradeoffs to Neon. Not cheaper enough than Container Apps to justify the change. |
| Local Mac watcher + local PostgreSQL | **$0 incremental** | Reliable only while the laptop, Docker, network, and watcher remain awake. Sleep, reboot, travel, or home connectivity can lose the complete window. | Simplest current workflow and useful recovery/baseline path. Local `.env` secrets and Compose PostgreSQL. No cloud lock-in, but it fails the unattended-hosting goal and is not recommended as production. |

### Ancillary charges

- **Compute:** Container Apps jobs are billed only while an execution runs. The estimated
  27,000 vCPU-seconds and 54,000 GiB-seconds are well below the monthly 180,000 and 360,000
  free grants respectively. Job request charges do not apply.
- **Database:** Azure B1ms plus minimum storage dominates the all-Azure price. Its 35 user
  connection limit is ample because each job uses one process. Seven-day backup retention
  is sufficient for this ledger; backup usage up to 100% of provisioned storage is free.
- **Registry:** Prefer GitHub Container Registry for the one small private image, subject to
  the GitHub account's package allowance. Azure Container Registry Basic would add roughly
  $5/month and is unnecessary at this scale.
- **Logs:** Keep concise structured logs and short retention. The expected few megabytes per
  month should cost effectively $0; configure a budget/retention cap rather than assuming
  unlimited free Log Analytics ingestion.
- **Storage:** The job needs only ephemeral scratch space. Optional object storage for new
  2026 raw feeds is well under 1 GiB and should cost cents, not dollars.
- **Network:** MLB responses are inbound to Azure and DB traffic is small. A cross-cloud
  database adds public TLS traffic, but expected transfer is within Neon's included egress.
  An Azure database in the same region avoids cross-vendor networking.
- **Secrets:** For one job, encrypted Container Apps secrets are the least expensive and
  simplest choice. Key Vault plus managed identity is an optional hardening step, not a
  prerequisite; it adds another resource and small transaction charges.

## Hosted PostgreSQL decision

The full 425-MiB development database is too close to either Neon's 0.5-GB Free allowance
or Supabase's 500-MB read-only threshold to migrate unchanged. Supabase Free can also pause
low-activity projects and has no automatic backups, so it is not selected.

Neon Free is technically sufficient only after producing and verifying a live-state export
that excludes feature experiments, model audits, component snapshots, and other research
tables. Daily use should prevent long inactivity, but the database may scale to zero between
game windows. A monthly size/CU-hours alert and tested PostgreSQL dump are mandatory. If the
free limits are approached, upgrade the same database to Launch; at a conservative 0.25 CU
for ten active hours/day, compute is about $7.95/month plus cents for storage and restore
history. This is the **cheapest acceptable** architecture, not the highest-assurance one.

Azure Flexible Server B1ms is the **best overall** and **easiest to operate** because the
watcher, database, logs, identity, and future app can stay in one provider. Its 32-GiB
minimum is wasteful for a sub-gigabyte database, but the resulting $16–18/month buys managed
backups and avoids a fragile free-tier ceiling. It is the recommended production choice if
that recurring spend is acceptable. Do not enable zone-redundant HA for this portfolio-scale
watcher; keep local/export backups and use the repeated five-minute attempts.

## Raw-cache deployment boundary

The hosted runtime does **not** need the 1.7-GiB 2021–2026 raw cache. It needs:

1. the frozen model specification/artifacts embedded read-only in the image;
2. the normalized historical rows required by live feature construction;
3. live schedule/feed responses for the current execution; and
4. the prospective prediction, settlement, and watcher-event tables.

The canonical historical cache can remain local and checksum-manifested. A job can use
ephemeral storage for current feeds because completed-state ingestion is idempotent and
PostgreSQL is the operational system of record. Optionally archive only newly observed 2026
feeds to object storage for disaster recovery; do not make that archive a prediction-path
dependency.

## Recommendation

- **Cheapest acceptable:** Container Apps scheduled Job + slim Neon Free PostgreSQL,
  expected $0/month, with a preconfigured upgrade path to Launch.
- **Best overall:** Container Apps scheduled Job + Azure PostgreSQL Flexible Server B1ms,
  expected $16–18/month after introductory credits.
- **Easiest to operate:** the all-Azure option.
- **Recommended for approval:** **best overall/all-Azure**, unless keeping recurring cost
  essentially zero is the controlling requirement. The prospective ledger is harder to
  recreate than the compute, and it should not sit within a nearly full free-tier quota.

## Resources and accounts required

For the recommended all-Azure architecture:

1. A Microsoft Azure account with a pay-as-you-go subscription and billing alert.
2. One US-region resource group (choose the nearest region supporting both services).
3. One Azure Container Apps Consumption environment and one scheduled Job.
4. One Azure PostgreSQL Flexible Server, Burstable B1ms, 32 GiB, seven-day backups, TLS,
   public access restricted to the job path where practical.
5. One private GitHub Container Registry package and pull credential, or ACR Basic only if
   Azure-native registry/managed identity is preferred despite its added cost.
6. Container Apps secrets; optionally one Key Vault and managed identity later.
7. Log Analytics/workspace diagnostics with capped retention and a cost alert.

For the cheapest alternative, replace items 4 with a Neon account/project and pooled TLS
connection string; retain a verified dump and storage/CU-hour alerts.

## Runtime configuration and secrets

Required non-secret environment variables:

```text
MLB_LOG_LEVEL=INFO
MLB_API_BASE_URL=https://statsapi.mlb.com/api
MLB_HTTP_TIMEOUT_SECONDS=15
MLB_HTTP_MAX_ATTEMPTS=3
MLB_WATCHER_IDLE_SECONDS=900
MLB_WATCHER_APPROACHING_SECONDS=300
```

Required secret:

```text
MLB_DATABASE_URL=postgresql+psycopg://<user>:<password>@<host>:5432/<database>?sslmode=require
```

Optional secret:

```text
MLB_NOTIFICATION_WEBHOOK_URL=<HTTPS webhook URL>
```

The accepted-model checksum and prospective launch timestamp remain repository/database
state, not editable deployment secrets. Registry credentials are infrastructure secrets and
must not be passed to the application container. Azure subscription/tenant IDs are needed
by deployment tooling but not by the running watcher.

## Exact post-approval deployment sequence

No step below was executed during Sprint 10A.5.

1. Add a minimal Docker image and infrastructure manifest without changing model code.
2. Build the image locally; run Ruff, formatting, pytest, Alembic check, and a containerized
   dry-run against an isolated database.
3. Create a live-only `pg_dump` from the accepted normalized/history and operations tables;
   restore it locally and prove feature vectors and artifact checksums match.
4. Create the Azure subscription budget, resource group, region, Container Apps environment,
   PostgreSQL B1ms server, database/user, and restricted networking.
5. Apply Alembic migrations to the hosted database, restore the verified live-state export,
   and compare row counts, launch timestamp, artifact hash, and prospective count.
6. Publish the immutable image digest to GHCR (or ACR), then configure the Container Apps job
   at 0.25 vCPU/0.5 GiB, one replica, timeout, and retry limit.
7. Store `MLB_DATABASE_URL` and any webhook as secrets; set the non-secret environment
   values; never copy `.env` into the image.
8. Run one manual `poll-live --dry-run`, inspect watcher status/upcoming discovery, and run
   one manual settlement dry run. Confirm zero unintended official writes.
9. Enable a UTC five-minute schedule during the daily MLB window plus an off-window refresh.
   Until dynamic scheduling is added, using every five minutes all day is still within the
   compute grant but makes unnecessary MLB requests; prefer two scheduled job definitions or
   a cheap gate that exits outside the window.
10. Add alerts for failed/missing executions, stale heartbeat, database/storage pressure,
    unsettled predictions, and monthly cost. Preserve local manual recovery commands.
11. Observe at least one complete game day and verify that an eligible pre-first-pitch record
    is immutable and settles without altering its forecast values.

## Free-tier and operational risks

- Azure's PostgreSQL B1ms/32-GB/32-GB-backup free offer is for the first 12 months of an
  eligible new account; the server becomes a roughly $16–18/month resource afterward. The
  $200 introductory credit expires sooner and should not be confused with the service grant.
- Container Apps' monthly grant is account/subscription-wide and pricing can change. Another
  workload in the subscription can consume it.
- Neon Free currently has no time limit, but quotas and terms can change. Its 0.5-GB storage
  cap, 100 CU-hours, short restore window, scale-to-zero behavior, and absence of an SLA are
  the primary risks. Launch is usage based rather than a fixed $15 charge.
- GitHub included Actions minutes depend on the account plan, partial minutes round up, and
  scheduled execution is explicitly not guaranteed on time.
- B1ms is a burstable, non-HA choice. Monitor CPU credits and retain a current logical dump.
- MLB schedule changes, missing lineups, source outages, postponed games, and container cold
  starts remain operational risks regardless of host. The existing eligibility gate should
  skip rather than fabricate a prediction.

