import importlib.metadata
import json
import platform
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import PoissonRegressor

from mlb_predictor.modeling.dataset import (
    FEATURE_COLUMNS,
    MULTISEASON_FEATURE_COLUMNS,
    MULTISEASON_FEATURE_VERSION,
    build_multiseason_modeling_dataset,
    model_features,
)
from mlb_predictor.modeling.metrics import evaluate_predictions
from mlb_predictor.modeling.models import (
    RANDOM_SEED,
    SklearnCountModel,
    multiseason_model_specs,
)
from mlb_predictor.modeling.stabilization import stabilize_small_samples

EVALUATION_SEASONS = (2022, 2023, 2024, 2025)


def rolling_origin_split(
    frame: pd.DataFrame, evaluation_season: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    train = frame.loc[frame["season"] < evaluation_season].copy()
    evaluation = frame.loc[frame["season"] == evaluation_season].copy()
    if train.empty or evaluation.empty:
        raise ValueError(f"Missing train or evaluation rows for {evaluation_season}")
    if train["game_date"].max() >= evaluation["game_date"].min():
        raise ValueError(f"Chronological boundary failed for {evaluation_season}")
    return train, evaluation


def _fit_predict(
    train: pd.DataFrame,
    evaluation: pd.DataFrame,
    spec: Any,
    columns: list[str],
) -> tuple[Any, np.ndarray]:
    train_features = model_features(train, columns)
    evaluation_features = model_features(evaluation, columns)
    if spec.stabilized:
        train_features = stabilize_small_samples(train_features)
        evaluation_features = stabilize_small_samples(evaluation_features)
    model = spec.factory()
    model.fit(train_features, train["runs_scored"])
    return model, model.predict(evaluation_features)


def _metric_bundle(target: pd.Series, prediction: np.ndarray, model: Any) -> dict[str, Any]:
    return evaluate_predictions(target.to_numpy(), prediction, model.distribution, model.dispersion)


def _combined_metrics(
    predictions: pd.DataFrame, seasonal: dict[str, Any] | None = None
) -> dict[str, Any]:
    metrics = evaluate_predictions(
        predictions["runs_scored"].to_numpy(), predictions["prediction"].to_numpy()
    )
    if seasonal:
        weights = [item["rows"] for item in seasonal.values()]
        metrics["count_nll"] = float(
            np.average([item["count_nll"] for item in seasonal.values()], weights=weights)
        )
        metrics["distribution"] = next(iter(seasonal.values()))["distribution"]
        dispersions = [
            item["dispersion"] for item in seasonal.values() if item["dispersion"] is not None
        ]
        metrics["dispersion"] = float(np.average(dispersions)) if dispersions else None
    return metrics


def _prediction_rows(frame: pd.DataFrame, prediction: np.ndarray, model_name: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "game_pk": frame["game_pk"].to_numpy(),
            "game_date": frame["game_date"].to_numpy(),
            "season": frame["season"].to_numpy(),
            "is_home": frame["is_home"].to_numpy(),
            "fallback_count": frame["fallback_count"].to_numpy(),
            "starter_prior_starts": frame["starter_prior_starts"].to_numpy(),
            "runs_scored": frame["runs_scored"].to_numpy(),
            "prediction": prediction,
            "model": model_name,
        }
    )


def _error_slices(predictions: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    frame = predictions.copy()
    frame["home_away"] = np.where(frame["is_home"], "home", "away")
    frame["fallback_usage"] = pd.cut(
        frame["fallback_count"], [-1, 0, 3, np.inf], labels=["none", "1-3", "4+"]
    )
    frame["starter_sample"] = pd.cut(
        frame["starter_prior_starts"], [-1, 0, 4, np.inf], labels=["0", "1-4", "5+"]
    )
    frame["predicted_run_range"] = pd.cut(
        frame["prediction"],
        [-np.inf, 3, 4, 5, 6, np.inf],
        labels=["<3", "3-4", "4-5", "5-6", "6+"],
        right=False,
    )
    season_starts = frame.groupby("season")["game_date"].transform("min")
    frame["early_season"] = np.where(
        (pd.to_datetime(frame["game_date"]) - pd.to_datetime(season_starts)).dt.days < 30,
        "first_30_days",
        "later",
    )
    output: dict[str, list[dict[str, Any]]] = {}
    for column in (
        "season",
        "home_away",
        "fallback_usage",
        "starter_sample",
        "predicted_run_range",
        "early_season",
    ):
        output[column] = []
        for value, group in frame.groupby(column, observed=True):
            output[column].append(
                {
                    "slice": str(value),
                    **evaluate_predictions(
                        group["runs_scored"].to_numpy(), group["prediction"].to_numpy()
                    ),
                }
            )
    return output


def _dependencies() -> dict[str, str]:
    packages = ("numpy", "pandas", "scikit-learn", "scipy", "statsmodels", "joblib")
    return {
        "python": platform.python_version(),
        **{package: importlib.metadata.version(package) for package in packages},
    }


def run_multiseason_evaluation(session: Any, output_dir: Path) -> dict[str, Any]:
    """Run rolling-origin development backtests; no season is called an untouched test."""
    frame = build_multiseason_modeling_dataset(session, MULTISEASON_FEATURE_VERSION)
    output_dir.mkdir(parents=True, exist_ok=True)
    specs = multiseason_model_specs(MULTISEASON_FEATURE_COLUMNS)
    model_metrics: dict[str, Any] = {}
    all_predictions: list[pd.DataFrame] = []
    final_models: dict[str, Any] = {}

    for spec in specs:
        seasonal: dict[str, Any] = {}
        model_predictions = []
        for season in EVALUATION_SEASONS:
            train, evaluation = rolling_origin_split(frame, season)
            model, prediction = _fit_predict(train, evaluation, spec, MULTISEASON_FEATURE_COLUMNS)
            seasonal[str(season)] = _metric_bundle(evaluation["runs_scored"], prediction, model)
            model_predictions.append(_prediction_rows(evaluation, prediction, spec.name))
            if season == EVALUATION_SEASONS[-1]:
                final_models[spec.name] = model
        combined = pd.concat(model_predictions, ignore_index=True)
        all_predictions.append(combined)
        model_metrics[spec.name] = {
            "combined": _combined_metrics(combined, seasonal),
            "by_season": seasonal,
            "nonnegative_method": spec.nonnegative_method,
        }

    treatment_specs = {
        "coldstart": ("sprint3_5_coldstart_v1", MULTISEASON_FEATURE_COLUMNS),
        "prior_no_decay": ("sprint3_5_nodecay_v1", MULTISEASON_FEATURE_COLUMNS),
        "decay_no_provenance_or_season": (MULTISEASON_FEATURE_VERSION, FEATURE_COLUMNS),
        "decay_with_provenance": (
            MULTISEASON_FEATURE_VERSION,
            [column for column in MULTISEASON_FEATURE_COLUMNS if column != "season"],
        ),
        "decay_with_provenance_and_season": (
            MULTISEASON_FEATURE_VERSION,
            MULTISEASON_FEATURE_COLUMNS,
        ),
    }
    treatment_metrics: dict[str, Any] = {}
    for treatment, (version, columns) in treatment_specs.items():
        treatment_frame = (
            frame
            if version == MULTISEASON_FEATURE_VERSION
            else build_multiseason_modeling_dataset(session, version)
        )
        predictions = []
        by_season = {}
        for season in EVALUATION_SEASONS:
            train, evaluation = rolling_origin_split(treatment_frame, season)
            model = SklearnCountModel(PoissonRegressor(alpha=0.01, max_iter=1000), columns)
            train_x = stabilize_small_samples(model_features(train, columns))
            evaluation_x = stabilize_small_samples(model_features(evaluation, columns))
            model.fit(train_x, train["runs_scored"])
            prediction = model.predict(evaluation_x)
            by_season[str(season)] = _metric_bundle(evaluation["runs_scored"], prediction, model)
            predictions.append(_prediction_rows(evaluation, prediction, treatment))
        combined = pd.concat(predictions, ignore_index=True)
        treatment_metrics[treatment] = {
            "combined": _combined_metrics(combined, by_season),
            "by_season": by_season,
        }

    prediction_frame = pd.concat(all_predictions, ignore_index=True)
    selected = min(
        model_metrics,
        key=lambda name: model_metrics[name]["combined"]["poisson_deviance"],
    )
    metadata = {
        "created_at": datetime.now(UTC).isoformat(),
        "feature_version": MULTISEASON_FEATURE_VERSION,
        "feature_versions_compared": [
            "sprint3_5_coldstart_v1",
            "sprint3_5_nodecay_v1",
            MULTISEASON_FEATURE_VERSION,
        ],
        "dataset_rows": len(frame),
        "dataset_games": int(frame["game_pk"].nunique()),
        "target": "runs_scored",
        "random_seed": RANDOM_SEED,
        "protocol": "rolling-origin train on all prior seasons; evaluate next season",
        "evaluation_seasons": list(EVALUATION_SEASONS),
        "prospective_reserve": "2026 live predictions or another future locked period",
        "selected_development_model": selected,
        "model_metrics": model_metrics,
        "feature_treatment_metrics": treatment_metrics,
        "error_analysis": _error_slices(
            prediction_frame.loc[prediction_frame["model"] == selected]
        ),
        "dependencies": _dependencies(),
        "limitations": [
            "All 2021-2025 results are development/backtesting evidence.",
            "2025 was previously reviewed and is not an untouched test set.",
            "The first evaluated season is 2022 because 2021 supplies initial history.",
        ],
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, default=str) + "\n", encoding="utf-8"
    )
    frame.to_csv(output_dir / "modeling_dataset.csv", index=False)
    prediction_frame.to_csv(output_dir / "predictions.csv", index=False)
    joblib.dump(final_models, output_dir / "models_through_2024.joblib")
    return metadata
