# Sprint 10A Automated Operations Audit

The watcher reuses the frozen Sprint 9 prediction path. It refreshes only newly completed
2026 games, polls live feeds, isolates each game failure, enforces the accepted SHA-256 before
official writes, preserves the partial unique official-record constraint, settles completed
records, and reports prospective metrics.

Timing classes are primary (20–40 minutes), late (under 20 but pregame), early diagnostic
(over 40), and backfill/retrospective (post-start). Only primary and late official records
after launch count. Scheduled and later actual start timestamps are retained separately.

August 14 dry-run: 14 scheduled games discovered, all early diagnostic and awaiting lineups;
four also had a starter listed as TBD. Incremental 2026 refresh discovered 1,822 completed
games and ingested zero duplicates. No official predictions were recorded.

Verification: Ruff and formatting passed, 31 tests passed, migration `0013` applied, and
Alembic reported no drift. Prospective count remains zero.

Recommended hosting is Azure Container Apps scheduled Jobs plus hosted PostgreSQL, pending
explicit approval. Current Azure documentation provides per-execution Consumption billing
and monthly compute free grants. Expected watcher compute is likely within the grant; hosted
PostgreSQL, registry/storage, logging, and network choices determine actual recurring cost.
