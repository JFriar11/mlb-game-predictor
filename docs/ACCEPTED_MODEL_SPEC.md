# Accepted Model Specification

**Version:** `accepted_v1_2026_prospective`

- Features: immutable `sprint3_5_v1`.
- Mean: stabilized histogram gradient boosting with Poisson loss and frozen parameters in
  `config/accepted_model_v1.json`.
- Distribution: independent home/away negative binomial with one training-only dispersion.
- Win probability: exact independent-distribution convolution.
- Extra innings: prior-training extra-inning home-win-rate approximation.
- Calibration: Platt logistic regression fitted on a distinct chronological block.
- Prospective reserve: 2026; completed outcomes cannot tune this version.

Observed weather and Sprint 4–6 component features are not accepted run-model inputs.
Future promotion requires prospective multi-metric improvement over at least 500 games or
one completed season, with no meaningful calibration or coverage regression.

Sprint 9 materializes the fitted generated artifact under `data/processed/` and records
model, calibration, distribution, feature, code, retrieval, and cutoff provenance.
