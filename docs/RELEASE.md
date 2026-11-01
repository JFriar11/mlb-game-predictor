# Release preparation — 2026-11-01

The approved dashboard appearance is preserved. A local release image combines
its static build, read-only FastAPI API, and trusted frozen model. No cloud
resources, public endpoint, scheduled polling, commit, or registry push were made.
Deployment and genuine prospective acceptance remain outstanding.

## Reproduce and identify

Run `make release-build VENV=.venv-sprint10b`, then
`make release-acceptance VENV=.venv-sprint10b`. Docker must be running. The explicit
release target supplies the private accepted artifact through a BuildKit secret;
only that target includes the verified model, root-owned and read-only. The
ordinary default runtime image remains artifact-free. Never publish this private
image to a public registry. Database and registry credentials are runtime secrets.

The ignored `data/processed/release/manifest.json` records source revision,
build-input hash, model checksum, and local image ID. A dirty revision is explicitly
labeled; it is not an immutable committed release. Registry digest remains null
until authorized publication; a local image ID is not a registry manifest digest.
Rebuild after changing build inputs. No credentials belong in the build context.

The same-origin web image runs as UID 10001. It serves self-hosted assets, applies
security headers, and disables CDN-dependent interactive API docs in web mode.
`/openapi.json` remains available. Unknown API paths do not fall back to HTML.
Inline styles are allowed for probability bars; scripts remain same-origin.
Use a loopback-only port for local review. Production still needs an approved
access/authentication policy; private ingress is the prepared default.

## Infrastructure packet

`infra/azure/app.bicep` is an offline-compiled module, not a complete deployment.
It expects an existing approved Container Apps environment, private registry and
PostgreSQL instance. It creates only a private web app and a manually triggered
worker. The worker runs `watcher-status`, with no timer or polling. API and worker
use separate database secrets; registry credentials are separate secret references.
Web resources are 0.25 CPU/0.5 GiB with zero-to-two replicas; worker resources are
1 CPU/2 GiB with one execution at a time. Run `make infra-check` with Bicep installed.
An Azure authenticated what-if/provider validation has not been performed.

A release-container as-of feature replay peaked at 784.4 MiB Linux RSS under a
1-GiB limit. The 2-GiB worker setting supplies headroom; it is not a full-day polling
capacity result. The web review process used approximately 171 MiB. Full polling,
model-load concurrency, database transfer and failure recovery need measurement
before enabling a schedule. The current feature builder reads historical batting
and pitching rows repeatedly; cross-provider transfer must be benchmarked.

**`poll-live --dry-run` still ingests live state.** It suppresses prediction and
settlement writes, not all database writes. Do not use it as a read-only readiness
check. Season handling currently references 2026; review the season rollover before
2027 activation. No retrospective forecasts may be inserted as prospective results.

## Recovery rehearsal

Run `make recovery-rehearsal VENV=.venv-sprint10b` against the supported local Compose
database. It exports 13 normalized live-state tables from one read-only repeatable
snapshot, restores after migrations into a disposable PostgreSQL 16 instance, and
compares row counts, ledger/input/launch-state hashes and deterministic as-of
features. It excludes research feature tables and does not generate predictions.
The source is never restored over. Temporary restore containers are removed.

The successful rehearsal is recorded in the ignored directory
`data/processed/release/recovery-20261101T194047Z/`: 13,970 games, 302,595 batting
rows, 120,061 pitching rows and zero prediction records. The 7,854,753-byte archive
has SHA256 `30b375d46579d0d9128578a3250d1c83da6710d06ac24a32e1b13f4ed9828cda`.
Source and restored as-of feature hash matched
`eb71f81e6c9bfef85e8c931d7bd77147b0923e5586a748fabfd840d40a67f196`.
The launch boundary and empty prospective ledger were preserved. Archive files are
mode 0600. Encrypted off-machine storage, retention policy, restore access and
periodic restore testing still require an approved operational storage policy.

## Deployment gates and rollback

1. Select provider, region, subscription/account, monthly budget, registry, and
   public/private access policy. See `HOSTING_REVIEW_2026_11.md`.
2. Prepare least-privilege database roles and runtime secret references without
   printing credentials. Review authenticated Azure what-if and estimated costs.
3. After authorization, push the private image, capture its registry digest and
   deploy private ingress first. Run only manual status/readiness checks initially.
4. Compare schema, accepted model checksum, launch boundary and ledger counts.
   Verify database restore and approved HTTPS/access behavior before public access.
5. Configure an identified monitoring owner: job failures/missing heartbeat,
   missed primary windows, unsettled rows, database capacity/transfer, budget
   alerts and backup failures. No alert destination has been configured.
6. Approve season readiness and a genuine upcoming-game acceptance run before
   enabling polling. Primary and late predictions remain separate. The actual
   prospective ledger is empty, so prospective accuracy is unproven.

Rollback uses the previous verified registry digest and compatible schema.
Do not automatically downgrade migrations or overwrite the live database. Preserve
new prediction records and their immutable evidence. Restore into a separate
instance first; an operator must review any actual data replacement.

## Acceptance evidence

Local checks passed: Ruff lint/format; 82 Python tests (one opt-in PostgreSQL skip);
15 Chromium checks against the combined release, including real API reads,
mobile/keyboard behavior and automated accessibility; offline Bicep compilation
and private/manual policy assertions; final image migrations, immutable ledger,
19-table persistence/restore, frozen inference and five HTTP API routes (16.0 s).
Runtime checks confirmed UID 10001, root-owned mode-0444 model, and absence of
source `.env`, Git metadata and the temporary BuildKit secret. The owned review
container was removed. Existing user services were left running.

Known debt: prospective sample remains zero; full-day worker/transfer profiling,
cloud provider validation, operational alerting, encrypted off-machine backup and
season rollover remain open. The existing Starlette test-client deprecation
warning persists. Newly added GitHub infrastructure checks are prepared locally;
the remote workflow has not been run or pushed.
