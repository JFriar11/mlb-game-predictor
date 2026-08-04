# Sprint 3.5 Multi-Season Audit

## Result

**PASS WITH ONE DOCUMENTED SOURCE RECONCILIATION EXCEPTION — 2026-08-03.**

The normalized database contains 12,148 played regular-season games and 24,296 stacked
team-game feature rows across 2021–2025. Raw caches and manifests remain partitioned by
season. No advanced Sprint 4 feature was started.

## Seasonal data audit

| Season | Games | Teams | Venues | Players | Starters | Lineups | Batting | Pitching | Exceptions | Score failures |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2021 | 2,429 | 30 | 34 | 1,508 | 4,858 | 43,722 | 61,317 | 21,540 | 0 | 0 |
| 2022 | 2,430 | 30 | 32 | 1,495 | 4,860 | 43,740 | 50,290 | 20,877 | 0 | 0 |
| 2023 | 2,430 | 30 | 33 | 1,457 | 4,860 | 43,740 | 50,754 | 20,627 | 0 | 1 pitching |
| 2024 | 2,429 | 30 | 35 | 1,454 | 4,858 | 43,722 | 50,748 | 20,688 | 0 | 0 |
| 2025 | 2,430 | 30 | 33 | 1,470 | 4,860 | 43,740 | 50,887 | 20,865 | 0 | 0 |
| Combined | 12,148 | 30 | 42 | 2,692 | 24,296 | 218,664 | 263,996 | 104,597 | 0 | 1 pitching |

Every normalized game has two starters, 18 starting-lineup rows, batting and pitching
records, and a unique game ID. Duplicate IDs and incomplete records are zero. Batting
runs reconcile to all 24,296 team scores.

Game 716881 (August 23, 2023) ended 5–4 in 10 innings. The losing side's player pitching
lines sum to four runs allowed while the opponent scored five. This is retained as an
explicit automatic-runner/team-unearned source accounting exception; no player statistic
was altered to manufacture reconciliation.

The 2021 and 2024 schedules each contain one cancelled entry, so 28 clubs played 162 and
two involved clubs played 161 games in those seasons. Cancelled source feeds remain hashed
but are excluded from normalized played games.

## Raw manifests

| Season | Cached objects | Manifest SHA-256 |
| --- | ---: | --- |
| 2021 | 2,431 | `ce108502e0a8d8f50b2a14c9e6d0abc3e2212e09c9c9e36a9ff7793ed3879155` |
| 2022 | 2,431 | `092d714f1715802be4e2ce493db69d334b9764c7fa5b3ae31e57b44f38a60c50` |
| 2023 | 2,431 | `0dee00dd62f6004726938c352ea033861801901e454d19fdf89be1e6674fa583` |
| 2024 | 2,430 | `2e1ebf871119892371e872a8b6244979bf89501baf59c178b32fcd7a23052299` |
| 2025 | 2,431 | `e5f8ed31f807fde051d632957f50da97638871f178bfee040a7317b53bd7b60e` |

The accepted 2025 manifest checksum is unchanged.

## Rule-era and structural findings

- 2021 contains 121 scheduled seven-inning games. Seven-inning doubleheaders ended after
  2021; later doubleheaders are scheduled for nine innings.
- The regular-season automatic runner applies throughout this dataset. In 2021 it began
  after the seventh in scheduled seven-inning doubleheaders; otherwise it begins after the
  ninth. MLB made the regular-season rule permanent for 2023.
- The National League did not use a universal DH in 2021. Universal DH begins in 2022 and
  is represented by a season-derived modeling indicator.
- Stable MLB team IDs preserve continuity through the Cleveland Indians/Guardians name
  change. Player histories follow MLB player ID across team changes; no future assignment
  table is joined.
- Forty-two venue IDs occur across the five seasons. The two Field of Dreams feeds omit
  venue objects and share one documented synthetic venue ID. Toronto's temporary venues
  and other special sites remain distinct MLB venue IDs.
- Original date, reschedule date, resume date, scheduled innings, doubleheader code, game
  number, and suspended-resumption indicator are stored where the archived feed supplies
  them. All same-day games update feature state only after that date's snapshots are built.

Official MLB materials confirm the
[2021 seven-inning and automatic-runner rules](https://www.mlb.com/news/mlb-players-union-agree-covid-protocols),
the [2022 universal DH](https://www.mlb.com/press-release/press-release-mlb-mlbpa-announce-rule-changes-for-2022-season),
and the [permanent regular-season automatic runner from 2023](https://www.mlb.com/news/automatic-runner-permanent-new-mlb-rules-for-position-players-pitching).

## Feature audit

`sprint3_5_v1` has 24,296 rows across 12,148 games, no as-of or source-date violations,
and no non-finite rows. It applies fixed 0.5 decay each offseason. Previous MLB batter and
starter history follows player ID; missing-year players retain older history with another
decay; rookies use league/fixed fallbacks. Team and bullpen history follows team ID.

Controls are separately persisted as `sprint3_5_nodecay_v1` and
`sprint3_5_coldstart_v1`. The original `sprint2_v1` still passes its independent 4,860-row
audit.

## Rolling-origin model audit

Each origin trains on all earlier seasons: 2021→2022, 2021–22→2023,
2021–23→2024, and 2021–24→2025. There is no random split and no untouched 2025 claim.

| Model | MAE | RMSE | Bias | Poisson deviance | Count NLL |
| --- | ---: | ---: | ---: | ---: | ---: |
| League average | 2.500 | 3.170 | 0.033 | 2.331 | 2.674 Poisson |
| Team rolling | 2.586 | 3.307 | 0.009 | 2.595 | 2.806 Poisson |
| Stabilized Poisson | 2.466 | 3.155 | -0.063 | 2.313 | 2.665 Poisson |
| Stabilized negative binomial | 2.463 | 3.150 | -0.049 | 2.304 | 2.457 NB |
| Stabilized gradient boosting | **2.449** | **3.130** | -0.039 | **2.276** | 2.647 Poisson |

Gradient-boosting deviance by season is 2.275 (2022), 2.285 (2023), 2.194 (2024), and
2.353 (2025), better than the matching league baseline in every origin. This is still
development evidence and does not authorize advanced modeling.

Poisson treatment deviance was 2.316 for cold starts, 2.313 with prior history but no
decay, 2.292 with 0.5 decay, and 2.290 after adding explicit prior-sample provenance.
Adding a raw numeric season indicator worsened deviance to 2.313; it is not supported.

## Error analysis

For gradient boosting, away deviance (2.375) remains worse than home (2.178). Fallback
rows are worse than no-fallback rows (2.447 versus 2.265). First-30-day deviance is 2.297
versus 2.273 later. Predictions below three runs remain sparse (118 rows; 2.568 deviance).
Predictions of six-plus runs overpredict by 0.506 runs and have 2.942 deviance. These
slices remain priority diagnostics.

## Reproduction and prospective boundary

After the accepted season data and feature variants exist:

```bash
make sprint3-5-audit
```

Generated metadata, predictions, dataset, and fitted models are ignored under
`data/processed/sprint3_5/`. Reserve 2026 live predictions, or another future period locked
before inspection, for true prospective evaluation.

An idempotent rebuild retained dataset SHA-256
`bf73e3f3df50a3fd0d673722791fdd32658cdb33f0456231a2d2e0a087bb2ee7`.
The rolling-origin prediction CSV SHA-256 is
`393c78455dcd7e3fa9cb3f9cdc4daaaddc06a49381733972caff724d32aaf2ab`.

## Limitations

- Historical starting lineups remain completed-feed reconstructions, not archived
  T-minus-30 snapshots.
- Rule indicators are based on archived feed metadata plus documented season rules; the
  failed 2025 cache-only metadata replay left additive 2025 resumption fields at safe
  migration defaults. This does not affect the accepted Sprint 3.5 features or outcomes.
- No transaction/roster history is used, avoiding future assignment leakage but limiting
  team-context interpretation for traded players.
- Advanced lineup weighting, Statcast, weather, pitcher similarity, specialized models,
  simulation, API, and dashboard work remain deferred.
