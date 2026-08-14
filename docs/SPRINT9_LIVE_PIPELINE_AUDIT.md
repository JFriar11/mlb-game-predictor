# Sprint 9 Live Pipeline Audit

The artifact was fit only on 24,296 accepted 2021–2025 rows. SHA-256:
`2d2f6bdd557bb9f4fa981fd88358774617fc246810f2efb2e4c79917ba9df945`.
Dispersion is 0.2293093, extra-inning home-win rate 0.4995340, and Platt parameters are
intercept 0.1135168 and coefficient 0.8013951.

Ruff and formatting passed, 30 tests passed, migration `0011` applied, and Alembic reported
no drift. The August 13 dry run retrieved nine completed feeds and intentionally wrote zero
states or predictions. Prospective count remains zero; no historical state was fabricated.

Limitations: prior-date state is conservative for same-day doubleheaders; 2026 history must
be ingested for useful rolling features; batting-order presence is the confirmation proxy;
no scheduler exists; weather remains excluded.
