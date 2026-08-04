# First prompt to paste into Codex

Open the `mlb-game-predictor` repository and read `AGENTS.md`, `PLANS.md`, and every file in `docs/`.

We are beginning Sprint 0. First inspect the repository exactly as it currently exists. Do not overwrite useful work and do not begin a full-season download.

Then:

1. Report what is already present and what differs from the documented target foundation.
2. Propose a concise implementation plan for Sprint 0.
3. Implement the repository foundation and a controlled five-game MLB Stats API ingestion milestone.
4. Use PostgreSQL, typed Python, SQLAlchemy, Alembic, pytest, Ruff, environment-based configuration, structured logging, retries, and idempotent ingestion.
5. Add the initial teams, players, venues, games, starting pitchers, and starting lineups schema.
6. Add validation for unique games, two teams, nonnegative scores, one starter per team, and batting-order slots 1–9.
7. Run the tests and show one human-readable reconstructed game.
8. Update `PLANS.md` and relevant docs with what was completed and any limitations.
9. Stop after the five-game acceptance test and ask me to review the results before ingesting 2025.

Important: execute the work in the repository rather than merely telling me which files to create. Explain major decisions and show command output or test results. Do not commit or push unless I ask.
