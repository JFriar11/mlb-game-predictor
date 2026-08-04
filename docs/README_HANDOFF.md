# Codex Handoff Package

Copy these files into the root of your existing `mlb-game-predictor` repository:

- `AGENTS.md`
- `PLANS.md`
- the entire `docs/` directory

Then open the repository root in VS Code, open the Codex extension, and paste the contents of:

- `docs/CODEX_START_PROMPT.md`

Codex reads `AGENTS.md` before it works, so this file carries the standing engineering, modeling, and collaboration rules for the project.

Use the same Codex thread for the active sprint when convenient, but do not rely on chat history as the only project memory. Keep `AGENTS.md`, `PLANS.md`, and the documents current.

At the end of every milestone, ask Codex to:

- Run tests and validation
- Update the active plan
- Update the decision log if a decision changed
- Summarize files changed
- State known limitations
- Stop for review

Recommended recurring prompt:

> Read AGENTS.md and the active plan. Inspect the current repository state, continue only the next incomplete milestone, run all relevant tests, update the project docs, and stop at the milestone boundary for my review.
