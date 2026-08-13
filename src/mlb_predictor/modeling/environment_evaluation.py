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

from mlb_predictor.db.models import EnvironmentFeatureSnapshot
from mlb_predictor.modeling.dataset import (
    MULTISEASON_FEATURE_COLUMNS,
    build_multiseason_modeling_dataset,
)
from mlb_predictor.modeling.metrics import evaluate_predictions
from mlb_predictor.modeling.models import RANDOM_SEED, SklearnCountModel
from mlb_predictor.modeling.multiseason import EVALUATION_SEASONS, rolling_origin_split
from mlb_predictor.modeling.stabilization import stabilize_small_samples

ENVIRONMENT_GROUPS: Final = {
    "baseline": (),
    "rolling_park_factor": ("park_factor", "park_prior_games"),
    "venue_physical": (
        "elevation_ft",
        "roof_retractable",
        "roof_fixed_or_dome",
        "artificial_turf",
    ),
    "observed_weather_proxy": (
        "temperature_f",
        "wind_speed_mph",
        "wind_out_component",
        "wind_cross_component",
        "roof_closed_proxy",
        "day_game",
    ),
    "raw_environment_bundle": (
        "park_factor",
        "park_prior_games",
        "elevation_ft",
        "roof_retractable",
        "roof_fixed_or_dome",
        "artificial_turf",
        "temperature_f",
        "wind_speed_mph",
        "wind_out_component",
        "wind_cross_component",
        "roof_closed_proxy",
        "day_game",
    ),
}


def build_environment_dataset(session: Any) -> pd.DataFrame:
    runs = build_multiseason_modeling_dataset(session, "sprint3_5_v1")
    rows = session.scalars(
        select(EnvironmentFeatureSnapshot).where(
            EnvironmentFeatureSnapshot.feature_version == "sprint6_v1"
        )
    )
    records = []
    for row in rows:
        records.append(
            {
                "game_pk": row.game_pk,
                "park_factor": row.park_factor,
                "park_prior_games": row.park_prior_games,
                "elevation_ft": row.elevation_ft,
                "roof_retractable": row.roof_type == "Retractable",
                "roof_fixed_or_dome": row.roof_type in {"Fixed", "Dome"},
                "artificial_turf": row.artificial_turf,
                "temperature_f": row.temperature_f,
                "wind_speed_mph": row.wind_speed_mph,
                "wind_out_component": row.wind_out_component,
                "wind_cross_component": row.wind_cross_component,
                "roof_closed_proxy": row.roof_closed_proxy,
                "day_game": row.day_game,
            }
        )
    frame = runs.merge(pd.DataFrame(records), on="game_pk", validate="m:1")
    if len(frame) != len(runs) or frame.isna().any().any():
        raise ValueError("Sprint 6 environment join is incomplete")
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


def run_environment_evaluation(session: Any, output_dir: Path) -> dict[str, Any]:
    frame = build_environment_dataset(session)
    frame["temperature_slice"] = pd.cut(
        frame["temperature_f"], [-np.inf, 60, 85, np.inf], labels=["cold", "mild", "hot"]
    ).astype(str)
    frame["wind_slice"] = pd.cut(
        frame["wind_speed_mph"], [-1, 5, 15, np.inf], labels=["calm", "moderate", "strong"]
    ).astype(str)
    frame["roof_slice"] = np.where(frame["roof_closed_proxy"], "closed_proxy", "other")
    frame["elevation_slice"] = np.where(frame["elevation_ft"] >= 3000, "high", "normal")
    results = {}
    predictions = []
    for label, additions in ENVIRONMENT_GROUPS.items():
        columns = [*MULTISEASON_FEATURE_COLUMNS, *additions]
        by_season = {}
        parts = []
        for season in EVALUATION_SEASONS:
            train, evaluation = rolling_origin_split(frame, season)
            model = _model(columns).fit(
                stabilize_small_samples(train[columns]), train["runs_scored"]
            )
            prediction = model.predict(stabilize_small_samples(evaluation[columns]))
            by_season[str(season)] = evaluate_predictions(
                evaluation["runs_scored"].to_numpy(), prediction
            )
            parts.append(
                evaluation[
                    [
                        "game_pk",
                        "season",
                        "runs_scored",
                        "park_factor",
                        "temperature_slice",
                        "wind_slice",
                        "roof_slice",
                        "elevation_slice",
                    ]
                ].assign(prediction=prediction, architecture=label)
            )
        combined_frame = pd.concat(parts, ignore_index=True)
        results[label] = {
            "combined": evaluate_predictions(
                combined_frame["runs_scored"].to_numpy(),
                combined_frame["prediction"].to_numpy(),
            ),
            "by_season": by_season,
        }
        predictions.append(combined_frame)

    # Modular park adjustment keeps the accepted model fixed, then applies the strictly
    # prior-date, shrunk park factor multiplicatively.
    baseline_predictions = predictions[0].copy()
    modular_prediction = np.clip(
        baseline_predictions["prediction"].to_numpy()
        * baseline_predictions["park_factor"].to_numpy(),
        1e-6,
        None,
    )
    modular_by_season = {
        str(season): evaluate_predictions(
            group["runs_scored"].to_numpy(),
            modular_prediction[group.index.to_numpy()],
        )
        for season, group in baseline_predictions.groupby("season")
    }
    results["modular_park_adjustment"] = {
        "combined": evaluate_predictions(
            baseline_predictions["runs_scored"].to_numpy(), modular_prediction
        ),
        "by_season": modular_by_season,
    }
    predictions.append(
        baseline_predictions.assign(
            prediction=modular_prediction, architecture="modular_park_adjustment"
        )
    )
    rolling_prediction = np.clip(
        frame.loc[frame["season"].isin(EVALUATION_SEASONS), "team_runs_avg_10"].to_numpy()
        * baseline_predictions["park_factor"].to_numpy(),
        1e-6,
        None,
    )
    rolling_actual = baseline_predictions["runs_scored"].to_numpy()
    results["park_adjusted_team_rolling_baseline"] = {
        "combined": evaluate_predictions(rolling_actual, rolling_prediction),
        "by_season": {
            str(season): evaluate_predictions(
                rolling_actual[baseline_predictions["season"].to_numpy() == season],
                rolling_prediction[baseline_predictions["season"].to_numpy() == season],
            )
            for season in EVALUATION_SEASONS
        },
    }
    base_deviance = results["baseline"]["combined"]["poisson_deviance"]
    for result in results.values():
        result["poisson_deviance_change"] = result["combined"]["poisson_deviance"] - base_deviance
    weather_predictions = predictions[3]
    results["observed_weather_proxy"]["slices"] = {
        column: {
            str(value): evaluate_predictions(
                group["runs_scored"].to_numpy(), group["prediction"].to_numpy()
            )
            for value, group in weather_predictions.groupby(column)
        }
        for column in ("temperature_slice", "wind_slice", "roof_slice", "elevation_slice")
    }
    metadata = {
        "created_at": datetime.now(UTC).isoformat(),
        "feature_version": "sprint6_v1",
        "baseline_feature_version": "sprint3_5_v1",
        "protocol": "rolling-origin train prior seasons; evaluate 2022-2025",
        "primary_metric": "poisson_deviance",
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
        "results": results,
        "dependencies": {
            "python": platform.python_version(),
            **{
                package: importlib.metadata.version(package)
                for package in ("numpy", "pandas", "scikit-learn", "sqlalchemy")
            },
        },
        "limitations": [
            "Feed weather is an observed completed-game proxy, not an archived forecast.",
            "Humidity and pressure are unavailable.",
            "Roof-closed state is inferred only from weather condition labels.",
            "No new independent leakage-safe defense metric is available.",
        ],
        "prospective_reserve": "2026 live predictions or another future locked period",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, default=str) + "\n", encoding="utf-8"
    )
    pd.concat(predictions, ignore_index=True).to_csv(output_dir / "predictions.csv", index=False)
    return metadata
