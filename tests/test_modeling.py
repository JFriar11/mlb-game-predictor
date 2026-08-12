from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from mlb_predictor.modeling.dataset import FEATURE_COLUMNS, model_features
from mlb_predictor.modeling.models import MODEL_SPECS
from mlb_predictor.modeling.multiseason import rolling_origin_split
from mlb_predictor.modeling.pitching_ablation import ABLATION_GROUPS
from mlb_predictor.modeling.pitching_evaluation import FEATURE_COLUMNS as PITCHING_COLUMNS
from mlb_predictor.modeling.splits import DEVELOPMENT_FOLDS, split_frame
from mlb_predictor.modeling.stabilization import stabilize_small_samples


def _synthetic_frame(rows: int = 120) -> pd.DataFrame:
    rng = np.random.default_rng(20250318)
    start = date(2025, 3, 18)
    data: dict[str, object] = {
        "game_pk": np.arange(rows),
        "game_date": [start + timedelta(days=index) for index in range(rows)],
        "runs_scored": rng.poisson(4.5, rows),
    }
    for column in FEATURE_COLUMNS:
        if column == "venue_id":
            data[column] = rng.integers(1, 5, rows)
        elif column == "is_home":
            data[column] = np.arange(rows) % 2 == 0
        else:
            data[column] = rng.uniform(0.1, 5.0, rows)
    return pd.DataFrame(data)


def test_chronological_split_integrity_and_future_rows_excluded() -> None:
    frame = _synthetic_frame(140)
    train, evaluation = split_frame(frame, DEVELOPMENT_FOLDS[0])
    assert max(train["game_date"]) < min(evaluation["game_date"])
    assert set(train.index).isdisjoint(evaluation.index)
    assert max(train["game_pk"]) < min(evaluation["game_pk"])


def test_model_input_structurally_excludes_target_and_identifiers() -> None:
    features = model_features(_synthetic_frame())
    assert list(features.columns) == FEATURE_COLUMNS
    assert "runs_scored" not in features
    assert "game_pk" not in features
    assert "game_date" not in features


def test_gradient_boosting_predictions_are_reproducible_and_nonnegative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOKY_MAX_CPU_COUNT", "1")
    frame = _synthetic_frame()
    features = stabilize_small_samples(model_features(frame))
    target = frame["runs_scored"]
    spec = next(item for item in MODEL_SPECS if item.name == "gradient_boosting_stabilized")
    first = spec.factory().fit(features, target).predict(features)
    second = spec.factory().fit(features, target).predict(features)
    np.testing.assert_allclose(first, second, rtol=0, atol=0)
    assert np.all(first >= 0)


def test_multiseason_rolling_origin_excludes_future_seasons() -> None:
    frame = pd.DataFrame(
        {
            "season": [2021, 2022, 2023, 2024],
            "game_date": [date(year, 4, 1) for year in range(2021, 2025)],
            "runs_scored": [1, 2, 3, 4],
        }
    )
    train, evaluation = rolling_origin_split(frame, 2023)
    assert set(train["season"]) == {2021, 2022}
    assert set(evaluation["season"]) == {2023}
    assert 2024 not in set(train["season"])


def test_pitching_model_features_exclude_component_targets_and_future_identifiers() -> None:
    assert "starter_outs" not in PITCHING_COLUMNS
    assert "starter_pitches" not in PITCHING_COLUMNS
    assert "bullpen_outs" not in PITCHING_COLUMNS
    assert "game_pk" not in PITCHING_COLUMNS
    assert "season" not in PITCHING_COLUMNS


def test_sprint5_5_ablation_matrix_is_fixed_and_target_free() -> None:
    assert len(ABLATION_GROUPS) == 12  # baseline plus eleven requested additions
    assert ABLATION_GROUPS["expected_starter_outs"] == ("expected_starter_outs",)
    assert ABLATION_GROUPS["expected_bullpen_outs"] == ("expected_bullpen_outs",)
    flattened = {item for group in ABLATION_GROUPS.values() for item in group}
    assert "runs_scored" not in flattened
    assert "starter_outs" not in flattened
    assert "starter_pitches" not in flattened
    assert "bullpen_outs" not in flattened
