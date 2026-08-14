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
