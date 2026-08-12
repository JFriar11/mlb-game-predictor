import importlib.metadata
import json
import platform
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sqlalchemy import select

from mlb_predictor.db.models import PitchingFeatureSnapshot
from mlb_predictor.modeling.dataset import (
    MULTISEASON_FEATURE_COLUMNS,
    build_multiseason_modeling_dataset,
)
from mlb_predictor.modeling.metrics import evaluate_predictions
from mlb_predictor.modeling.models import RANDOM_SEED, SklearnCountModel
from mlb_predictor.modeling.multiseason import EVALUATION_SEASONS, rolling_origin_split
from mlb_predictor.modeling.stabilization import stabilize_small_samples

PREFIX: Final = "s5_"
BASELINE: Final = "sprint3_5_v1"

# Fixed before results are run. "Best" means the baseball-justified compact group, not
# whichever post-hoc combination happens to score best.
ABLATION_GROUPS: Final[dict[str, tuple[str, ...]]] = {
    "baseline": (),
    "expected_starter_outs": ("expected_starter_outs",),
    "expected_starter_pitches": ("expected_starter_pitches",),
    "expected_starter_outs_and_pitches": (
        "expected_starter_outs",
        "expected_starter_pitches",
    ),
    "starter_rest_workload_history": (
        "starter_days_rest",
        "starter_prior_starts",
        "starter_pitches_per_out",
        "manager_avg_starter_outs",
        "manager_avg_starter_pitches",
    ),
    "bullpen_recent_workload": ("bullpen_workload_1d", "bullpen_workload_3d"),
    "bullpen_availability_counts": (
        "available_reliever_count",
        "unavailable_reliever_count",
        "high_usage_available",
    ),
    "bullpen_available_quality": (
        "available_bullpen_era",
        "available_bullpen_strikeout_rate",
        "available_bullpen_walk_rate",
    ),
    "expected_bullpen_outs": ("expected_bullpen_outs",),
    "starter_compact_group": (
        "expected_starter_outs",
        "expected_starter_pitches",
        "starter_days_rest",
        "starter_prior_starts",
        "manager_avg_starter_outs",
    ),
    "bullpen_compact_group": (
        "expected_bullpen_outs",
        "bullpen_workload_1d",
        "bullpen_workload_3d",
        "available_reliever_count",
        "unavailable_reliever_count",
        "high_usage_available",
        "available_bullpen_era",
        "available_bullpen_strikeout_rate",
        "available_bullpen_walk_rate",
    ),
    "starter_and_bullpen_compact_groups": (
        "expected_starter_outs",
        "expected_starter_pitches",
        "starter_days_rest",
        "starter_prior_starts",
        "manager_avg_starter_outs",
        "expected_bullpen_outs",
        "bullpen_workload_1d",
        "bullpen_workload_3d",
        "available_reliever_count",
        "unavailable_reliever_count",
        "high_usage_available",
        "available_bullpen_era",
        "available_bullpen_strikeout_rate",
        "available_bullpen_walk_rate",
    ),
}


def build_ablation_dataset(session: Any) -> pd.DataFrame:
    runs = build_multiseason_modeling_dataset(session, BASELINE)
    snapshots = session.scalars(
        select(PitchingFeatureSnapshot).where(
            PitchingFeatureSnapshot.feature_version == "sprint5_v1"
        )
    )
    records = []
    for row in snapshots:
        values = {
            "game_pk": row.game_pk,
            "opponent_team_id": row.team_id,
            **{
                name: getattr(row, name)
                for name in {item for group in ABLATION_GROUPS.values() for item in group}
                if not name.startswith("expected_")
            },
            "expected_starter_outs": row.starter_avg_outs,
            "expected_starter_pitches": row.starter_avg_pitches,
        }
        records.append(values)
    state = pd.DataFrame(records).rename(
        columns={
            column: f"{PREFIX}{column}"
            for column in records[0]
            if column not in ("game_pk", "opponent_team_id")
        }
    )
    frame = runs.merge(state, on=["game_pk", "opponent_team_id"], validate="1:1")
    if len(frame) != len(runs) or frame.isna().any().any():
        raise ValueError("Sprint 5.5 ablation join is incomplete")
    frame[f"{PREFIX}expected_bullpen_outs"] = (
        frame["scheduled_innings"] * 3 - frame[f"{PREFIX}expected_starter_outs"]
    ).clip(0, 27)
    frame["starter_outing_slice"] = np.where(
        frame[f"{PREFIX}expected_starter_outs"] < 15, "short", "long"
    )
    frame["bullpen_workload_slice"] = np.where(
        frame[f"{PREFIX}bullpen_workload_3d"] >= 50, "high", "low"
    )
    frame["starter_history_slice"] = np.where(
        frame[f"{PREFIX}starter_prior_starts"] < 5, "low", "high"
    )
    frame["home_away_slice"] = np.where(frame["is_home"], "home", "away")
    return frame


def _model(columns: list[str]) -> SklearnCountModel:
    return SklearnCountModel(
        HistGradientBoostingRegressor(
            loss="poisson",
            learning_rate=0.05,
            max_iter=200,
            max_leaf_nodes=15,
            min_samples_leaf=30,
            l2_regularization=1.0,
            random_state=RANDOM_SEED,
        ),
        columns,
    )


def _slices(frame: pd.DataFrame) -> dict[str, Any]:
    output = {}
    for column in (
        "starter_outing_slice",
        "bullpen_workload_slice",
        "starter_history_slice",
        "home_away_slice",
    ):
        output[column] = {
            str(value): evaluate_predictions(
                group["runs_scored"].to_numpy(), group["prediction"].to_numpy()
            )
            for value, group in frame.groupby(column)
        }
    return output


def run_pitching_ablation(session: Any, output_dir: Path) -> dict[str, Any]:
    frame = build_ablation_dataset(session)
    results: dict[str, Any] = {}
    predictions = []
    for label, additions in ABLATION_GROUPS.items():
        columns = [*MULTISEASON_FEATURE_COLUMNS, *(f"{PREFIX}{item}" for item in additions)]
        seasonal = {}
        parts = []
        for season in EVALUATION_SEASONS:
            train, evaluation = rolling_origin_split(frame, season)
            train_x = stabilize_small_samples(train[columns].copy())
            evaluation_x = stabilize_small_samples(evaluation[columns].copy())
            model = _model(columns).fit(train_x, train["runs_scored"])
            predicted = model.predict(evaluation_x)
            seasonal[str(season)] = evaluate_predictions(
                evaluation["runs_scored"].to_numpy(), predicted
            )
            parts.append(
                evaluation[
                    [
                        "game_pk",
                        "season",
                        "runs_scored",
                        "starter_outing_slice",
                        "bullpen_workload_slice",
                        "starter_history_slice",
                        "home_away_slice",
                    ]
                ].assign(prediction=predicted, ablation=label)
            )
        combined_frame = pd.concat(parts, ignore_index=True)
        combined = evaluate_predictions(
            combined_frame["runs_scored"].to_numpy(), combined_frame["prediction"].to_numpy()
        )
        results[label] = {
            "features": list(additions),
            "combined": combined,
            "by_season": seasonal,
            "slices": _slices(combined_frame),
        }
        predictions.append(combined_frame)

    baseline_deviance = results["baseline"]["combined"]["poisson_deviance"]
    for result in results.values():
        result["poisson_deviance_change"] = (
            result["combined"]["poisson_deviance"] - baseline_deviance
        )
    promoted = [
        label
        for label, result in results.items()
        if label != "baseline" and result["poisson_deviance_change"] < 0
    ]
    metadata = {
        "created_at": datetime.now(UTC).isoformat(),
        "milestone": "sprint5_5",
        "baseline_feature_version": BASELINE,
        "component_feature_version": "sprint5_v1",
        "model_configuration": {
            "estimator": "HistGradientBoostingRegressor",
            "loss": "poisson",
            "learning_rate": 0.05,
            "max_iter": 200,
            "max_leaf_nodes": 15,
            "min_samples_leaf": 30,
            "l2_regularization": 1.0,
            "random_seed": RANDOM_SEED,
        },
        "protocol": "rolling-origin train prior seasons; evaluate 2022-2025",
        "primary_metric": "poisson_deviance",
        "slice_thresholds": {
            "short_starter_outing": "expected starter outs < 15",
            "high_bullpen_workload": "prior-three-day pitches >= 50",
            "low_starter_history": "prior starts < 5",
        },
        "results": results,
        "poisson_deviance_improving_predeclared_subsets": promoted,
        "dependencies": {
            "python": platform.python_version(),
            **{
                package: importlib.metadata.version(package)
                for package in ("numpy", "pandas", "scikit-learn", "sqlalchemy")
            },
        },
        "prospective_reserve": "2026 live predictions or another future locked period",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, default=str) + "\n", encoding="utf-8"
    )
    pd.concat(predictions, ignore_index=True).to_csv(output_dir / "predictions.csv", index=False)
    return metadata
