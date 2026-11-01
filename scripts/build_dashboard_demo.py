"""Generate explicitly synthetic dashboard fixtures in an in-memory database only.

No MLB requests, model loading/fitting, real predictions, or persistent DB writes.
Run with the repository's pinned Python environment. Commit the generated JSON.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from mlb_predictor.api.schemas import GameDetail, ModelMetadata, PredictionList
from mlb_predictor.api.service import serialize_prediction
from mlb_predictor.db.models import Base, PredictionInputSnapshot
from mlb_predictor.explanations import SNAPSHOT_SOURCE, SNAPSHOT_VERSION, capture_feature_evidence
from mlb_predictor.live import (
    ACCEPTED_ARTIFACT_SHA256,
    CALIBRATION_VERSION,
    DISTRIBUTION_VERSION,
    FEATURE_VERSION,
    MODEL_VERSION,
    DiscoveredGame,
    persist_discovery,
    save_prediction,
)
from mlb_predictor.live_features import build_live_feature_pair
from mlb_predictor.modeling.distributions import analytic_home_win, negative_binomial_pmf

ROOT = Path(__file__).resolve().parents[1]
DEMO_DATE = "2026-08-14"


def main() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    predictions = []
    details = {}
    now = datetime(2026, 8, 14, 17, 50, tzinfo=UTC)
    try:
        with Session(engine) as session:
            for index, (away_name, home_name, means) in enumerate(
                [
                    ("St. Louis Cardinals", "Chicago Cubs", [4.0, 4.8]),
                    ("New York Yankees", "Boston Red Sox", [4.7, 4.2]),
                ]
            ):
                game = DiscoveredGame(
                    game_pk=8_000_001 + index,
                    game_date=now.date(),
                    scheduled_start_time_utc=now + timedelta(minutes=30, hours=index * 5),
                    home_team_id=112 if index == 0 else 111,
                    home_team_name=home_name,
                    away_team_id=138 if index == 0 else 147,
                    away_team_name=away_name,
                    venue_id=17 if index == 0 else 3,
                    venue_name="Wrigley Field" if index == 0 else "Fenway Park",
                    home_starter_id=900_001 + index,
                    away_starter_id=900_011 + index,
                    status="Scheduled",
                    lineup_state="confirmed",
                    home_lineup=tuple(range(910_001, 910_010)),
                    away_lineup=tuple(range(920_001, 920_010)),
                    retrieved_at=now - timedelta(seconds=30),
                )
                discovery = persist_discovery(session, game)
                pmfs = negative_binomial_pmf(np.array(means), 0.23)
                raw, tie = analytic_home_win(pmfs[1], pmfs[0], 0.5)
                scores = np.outer(pmfs[0], pmfs[1])
                result = {
                    "expected_away_runs": means[0],
                    "expected_home_runs": means[1],
                    "dispersion": 0.23,
                    "raw_home_win_probability": raw,
                    "calibrated_home_win_probability": 0.565 if index == 0 else 0.46,
                    "away_win_probability": 0.435 if index == 0 else 0.54,
                    "regulation_tie_probability": tie,
                    "extra_home_win_probability": 0.5,
                    "away_pmf": pmfs[0].tolist(),
                    "home_pmf": pmfs[1].tolist(),
                    "intervals": {
                        side: {
                            str(int(level * 100)): [
                                int(np.argmax(np.cumsum(pmf) >= (1 - level) / 2)),
                                int(np.argmax(np.cumsum(pmf) >= 1 - (1 - level) / 2)),
                            ]
                            for level in (0.5, 0.8, 0.95)
                        }
                        for side, pmf in (("away", pmfs[0]), ("home", pmfs[1]))
                    },
                    "most_likely_scores": [
                        {
                            "away": int(i // 13),
                            "home": int(i % 13),
                            "probability": float(scores.ravel()[i]),
                        }
                        for i in np.argsort(scores.ravel())[::-1][:5]
                    ],
                }
                # Format a fixture through the real serializer. No official production
                # save path, trusted binary, or persistent ledger is involved.
                record = save_prediction(
                    session,
                    game,
                    result,
                    now,
                    official=False,
                    warnings=["synthetic_demo"],
                    cutoff=now,
                    launch=None,
                    artifact_path=Path("unused"),
                )
                record.is_official = True  # schema fixture only, not an official forecast
                record.prediction_kind = "synthetic_demo"
                record.timing_classification = "synthetic_example"
                record.code_version = "synthetic-demo"
                snapshot = None
                if index == 0:
                    away, home, _ = build_live_feature_pair(
                        session,
                        game_pk=game.game_pk,
                        home_team_id=game.home_team_id,
                        away_team_id=game.away_team_id,
                        venue_id=game.venue_id,
                        home_starter_id=game.home_starter_id,
                        away_starter_id=game.away_starter_id,
                        home_lineup=game.home_lineup,
                        away_lineup=game.away_lineup,
                        as_of=now,
                    )
                    home.update(
                        lineup_prior_pa=1200,
                        lineup_on_base_rate=0.344,
                        starter_prior_starts=12,
                        starter_era=4.35,
                        bullpen_prior_outs=210,
                        bullpen_era_30d=4.10,
                        team_runs_avg_10=4.9,
                        fallback_count=2,
                    )
                    away.update(
                        lineup_prior_pa=1080,
                        lineup_on_base_rate=0.318,
                        starter_prior_starts=15,
                        starter_era=3.60,
                        bullpen_prior_outs=225,
                        bullpen_era_30d=3.85,
                        team_runs_avg_10=4.2,
                        fallback_count=1,
                    )
                    evidence = capture_feature_evidence(
                        away,
                        home,
                        game_pk=game.game_pk,
                        as_of=now,
                        artifact_sha256=ACCEPTED_ARTIFACT_SHA256,
                        home_lineup=game.home_lineup,
                        away_lineup=game.away_lineup,
                        home_team_id=game.home_team_id,
                        away_team_id=game.away_team_id,
                        home_starter_id=game.home_starter_id,
                        away_starter_id=game.away_starter_id,
                    )
                    snapshot = PredictionInputSnapshot(
                        prediction_id=record.id,
                        snapshot_version=SNAPSHOT_VERSION,
                        as_of=now,
                        source=SNAPSHOT_SOURCE,
                        payload_json=evidence.model_dump_json(),
                    )
                prediction = serialize_prediction(record, discovery, snapshot)
                predictions.append(prediction)
                details[str(game.game_pk)] = GameDetail(
                    game_pk=game.game_pk,
                    model_version=MODEL_VERSION,
                    prediction_status="available",
                    latest_discovery=prediction.latest_discovery,
                    official_prediction=prediction,
                ).model_dump(mode="json", by_alias=True)
            details["8000003"] = GameDetail(
                game_pk=8_000_003,
                model_version=MODEL_VERSION,
                prediction_status="not_recorded",
                latest_discovery=None,
                official_prediction=None,
            ).model_dump(mode="json", by_alias=True)
        payload = {
            "notice": "Synthetic demonstration only. Stipulated means/probabilities; "
            "no fitted model "
            "inference, genuine MLB prediction, or real ledger record.",
            "slate": PredictionList(
                date=now.date(),
                model_version=MODEL_VERSION,
                generated_at=now,
                count=len(predictions),
                predictions=predictions,
            ).model_dump(mode="json", by_alias=True),
            "details": details,
            "model": ModelMetadata(
                model_version=MODEL_VERSION,
                feature_version=FEATURE_VERSION,
                calibration_version=CALIBRATION_VERSION,
                distribution_version=DISTRIBUTION_VERSION,
                mean_model="Stabilized histogram gradient boosting with Poisson loss",
                distribution="Independent negative binomial; 12+ is censored",
                calibration="Platt logistic calibration",
                training_start_season=2021,
                training_end_season=2025,
                retrospective_evidence_only=True,
                artifact_sha256_expected=ACCEPTED_ARTIFACT_SHA256,
                artifact_status="missing",
                known_limitations=[
                    "Historical lineups are reconstructed, not archived T-minus-30 states.",
                    "2021-2025 results are retrospective development evidence.",
                    "Run scores are conditionally independent; extra innings are approximated.",
                    "No game-specific reliability grade or causal factor attribution is claimed.",
                ],
            ).model_dump(mode="json", by_alias=True),
        }
        destination = ROOT / "frontend/src/demo-fixture.json"
        destination.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
        print(f"Wrote synthetic contract-validated demo: {destination.relative_to(ROOT)}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
