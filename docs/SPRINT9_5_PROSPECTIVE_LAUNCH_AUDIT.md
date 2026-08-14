# Sprint 9.5 Prospective Launch Audit

The accepted artifact stayed byte-identical at SHA-256
`2d2f6bdd557bb9f4fa981fd88358774617fc246810f2efb2e4c79917ba9df945`.
No 2026 outcome entered fitting, calibration, dispersion, selection, or tuning.

The feature-history bootstrap ingested 1,822 games through August 13: 3,644 starters,
32,796 lineups, 38,599 batting rows, and 15,464 pitching rows. Exceptions, incomplete
records, duplicate IDs, and score reconciliation failures were zero. Latest completed-game
timestamp was `2026-08-13T20:05:00+00:00`.

Three diagnostic feature vectors had 120–122 current-season team games, 7,545–17,468
lineup PA, 22–182 starter starts, 221–321 bullpen outs, zero fallbacks, exact frozen-model
column order, and finite stabilized inputs.

Launch is `2026-08-14T00:25:28.171973+00:00`. Fourteen August 14 games were discovered;
all awaited lineups. Eligibility requires two nine-player orders, both starter IDs, a game
starting after launch, and generation 20–40 minutes before pitch. Prospective count is zero.
