# 2025 Regular-Season Data Audit

## Result

**PASS — completed 2026-08-03.**

The MLB Stats API schedule returned 2,430 unique completed 2025 regular-season games.
All 2,430 were cached and normalized without an ingestion exception. A second complete
pass read the same feeds from cache and produced unchanged table counts.

## Normalized counts

| Measure | Count |
| --- | ---: |
| Games | 2,430 |
| Teams | 30 |
| Venues | 33 |
| Players | 1,470 |
| Starting pitchers | 4,860 |
| Starting-lineup entries | 43,740 |
| Player-game batting rows | 50,887 |
| Player-game pitching rows | 20,865 |

The stored date range is March 18 through September 28, 2025. Every team has 162 games.
Every game has two starters, two complete nine-player starting lineups, batting records,
and pitching records.

## Reconciliation

- Ingestion exceptions: 0.
- Incomplete starter games: 0.
- Incomplete lineup sides: 0.
- Games without batting records: 0.
- Games without pitching records: 0.
- Team-game batting run totals differing from final scores: 0.
- Team-game pitching runs allowed differing from opponent final scores: 0.
- Negative counting statistics are rejected by PostgreSQL constraints.
- Stable IDs and per-game unique constraints prevent duplicate normalized records.

## Raw-layer freeze

The ignored raw cache contains one schedule response and 2,430 gzip-compressed game feeds:

- Files: 2,431
- Compressed bytes: 314,256,757 (approximately 304 MiB on disk)
- Per-file hash algorithm: SHA-256
- Deterministic manifest: `data/interim/2025_raw_manifest.json` (ignored)
- Manifest SHA-256: `e5f8ed31f807fde051d632957f50da97638871f178bfee040a7317b53bd7b60e`

The raw and interim artifacts remain outside Git by design. Run `freeze-raw` again and
compare the manifest checksum before feature engineering if any cached response changes.

## Commands

```bash
export MLB_DATABASE_URL=postgresql+psycopg://mlb:mlb@localhost:55432/mlb_predictor
.venv-sprint0/bin/alembic upgrade head
.venv-sprint0/bin/mlb-predictor ingest-season --season 2025
.venv-sprint0/bin/mlb-predictor audit-season --season 2025 \
  --output data/interim/2025_season_audit.json
.venv-sprint0/bin/mlb-predictor freeze-raw --season 2025 \
  --output data/interim/2025_raw_manifest.json
```

## Limitations

- The source is the MLB completed-game live feed as retrieved in August 2026, not a
  contemporaneous 2025 pregame snapshot.
- Starting lineups and starters are historical reconstruction fields. Player-game batting
  and pitching statistics are outcomes and must never enter a target game's pregame features.
- The raw cache is immutable by convention and checksum audit, not filesystem enforcement.
- Dependency versions are bounded in `pyproject.toml`, but a cross-platform lockfile has
  not yet been added.

