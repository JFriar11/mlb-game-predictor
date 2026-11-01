"""Read-only frozen-artifact inference check; makes no MLB requests or prediction writes."""

import json
import warnings
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from sklearn.exceptions import InconsistentVersionWarning
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from mlb_predictor.cli import _load_sprint0_ids
from mlb_predictor.config import get_settings
from mlb_predictor.live import predict_from_features, verify_accepted_artifact
from mlb_predictor.live_features import build_live_feature_pair


def main() -> None:
    """Check the installed wheel, trusted artifact, and database feature path together."""
    settings = get_settings()
    verify_accepted_artifact(settings.artifact_path)
    assert len(_load_sprint0_ids()) == 5
    engine = create_engine(settings.database_url)
    try:
        with Session(engine) as session:
            away, home, _ = build_live_feature_pair(
                session,
                game_pk=999002,
                home_team_id=20,
                away_team_id=10,
                venue_id=30,
                home_starter_id=250,
                away_starter_id=150,
                home_lineup=tuple(range(201, 210)),
                away_lineup=tuple(range(101, 110)),
                as_of=datetime(2026, 8, 14, tzinfo=UTC),
            )
        with warnings.catch_warnings():
            warnings.simplefilter("error", InconsistentVersionWarning)
            result = predict_from_features(away, home, Path(settings.artifact_path))
        assert result == predict_from_features(away, home, settings.artifact_path)
        for side in ("away", "home"):
            pmf = result[f"{side}_pmf"]
            assert len(pmf) == 13 and np.all(np.isfinite(pmf)) and min(pmf) >= 0
            assert np.isclose(sum(pmf), 1)
            assert result[f"expected_{side}_runs"] > 0
        assert np.isclose(
            result["away_win_probability"] + result["calibrated_home_win_probability"], 1
        )
        print(json.dumps({"status": "PASS", "synthetic_inference": result}, sort_keys=True))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
