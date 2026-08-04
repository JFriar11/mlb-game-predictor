import importlib.metadata
import json
import platform
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from mlb_predictor.modeling.dataset import FEATURE_VERSION, build_modeling_dataset, model_features
from mlb_predictor.modeling.metrics import evaluate_predictions
from mlb_predictor.modeling.models import MODEL_SPECS, RANDOM_SEED, ModelSpec
from mlb_predictor.modeling.splits import DEVELOPMENT_FOLDS, FINAL_TEST_FOLD, split_frame
from mlb_predictor.modeling.stabilization import stabilize_small_samples


def _features(frame: pd.DataFrame, spec: ModelSpec) -> pd.DataFrame:
    selected = model_features(frame)
    return stabilize_small_samples(selected) if spec.stabilized else selected


def _prediction_rows(
    evaluation: pd.DataFrame,
    predictions: np.ndarray,
    spec: ModelSpec,
    fold_name: str,
    period: str,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "game_pk": evaluation["game_pk"].to_numpy(),
            "game_date": evaluation["game_date"].to_numpy(),
            "offense_team_id": evaluation["offense_team_id"].to_numpy(),
            "is_home": evaluation["is_home"].to_numpy(),
            "fallback_count": evaluation["fallback_count"].to_numpy(),
            "starter_prior_starts": evaluation["starter_prior_starts"].to_numpy(),
            "runs_scored": evaluation["runs_scored"].to_numpy(),
            "prediction": predictions,
            "model": spec.name,
            "fold": fold_name,
            "period": period,
        }
    )


def _aggregate_metrics(
    predictions: pd.DataFrame, fold_metrics: list[dict[str, Any]]
) -> dict[str, Any]:
    point = evaluate_predictions(
        predictions["runs_scored"].to_numpy(), predictions["prediction"].to_numpy()
    )
    point["count_nll"] = float(
        np.average(
            [item["count_nll"] for item in fold_metrics],
            weights=[item["rows"] for item in fold_metrics],
        )
    )
    point["distribution"] = fold_metrics[0]["distribution"]
    dispersions = [item["dispersion"] for item in fold_metrics if item["dispersion"] is not None]
    point["dispersion"] = float(np.mean(dispersions)) if dispersions else None
    return point


def _slice_metrics(frame: pd.DataFrame, column: str) -> list[dict[str, Any]]:
    results = []
    for value, group in frame.groupby(column, observed=True):
        metrics = evaluate_predictions(
            group["runs_scored"].to_numpy(), group["prediction"].to_numpy()
        )
        results.append({"slice": str(value), **metrics})
    return results


def _error_analysis(predictions: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    frame = predictions.copy()
    frame["month"] = pd.to_datetime(frame["game_date"]).dt.strftime("%Y-%m")
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
    return {
        column: _slice_metrics(frame, column)
        for column in (
            "month",
            "home_away",
            "fallback_usage",
            "starter_sample",
            "predicted_run_range",
        )
    }


def _dependencies() -> dict[str, str]:
    packages = ("numpy", "pandas", "scikit-learn", "scipy", "statsmodels", "joblib")
    return {package: importlib.metadata.version(package) for package in packages}


def _model_configuration() -> dict[str, dict[str, Any]]:
    return {
        "league_average": {"statistic": "training-target mean"},
        "team_rolling_average": {"feature": "team_runs_avg_10", "window_games": 10},
        "poisson_raw": {"estimator": "PoissonRegressor", "alpha": 0.01, "max_iter": 1000},
        "poisson_stabilized": {
            "estimator": "PoissonRegressor",
            "alpha": 0.01,
            "max_iter": 1000,
            "stabilization": "fixed-prior empirical-rate shrinkage and clipping",
        },
        "negative_binomial_stabilized": {
            "estimator": "statsmodels GLM NegativeBinomial",
            "dispersion": "estimated from training residual moments and clipped to [0.0001, 2]",
            "stabilization": "fixed-prior empirical-rate shrinkage and clipping",
        },
        "gradient_boosting_stabilized": {
            "estimator": "HistGradientBoostingRegressor",
            "loss": "poisson",
            "learning_rate": 0.05,
            "max_iter": 200,
            "max_leaf_nodes": 15,
            "min_samples_leaf": 30,
            "l2_regularization": 1.0,
            "random_state": RANDOM_SEED,
        },
    }


def run_sprint3_evaluation(session: Any, output_dir: Path) -> dict[str, Any]:
    frame = build_modeling_dataset(session, FEATURE_VERSION)
    output_dir.mkdir(parents=True, exist_ok=True)
    development_metrics: dict[str, Any] = {}
    development_predictions: list[pd.DataFrame] = []

    for spec in MODEL_SPECS:
        model_fold_metrics = []
        model_predictions = []
        for fold in DEVELOPMENT_FOLDS:
            train, evaluation = split_frame(frame, fold)
            model = spec.factory()
            model.fit(_features(train, spec), train["runs_scored"])
            predictions = model.predict(_features(evaluation, spec))
            metrics = evaluate_predictions(
                evaluation["runs_scored"].to_numpy(),
                predictions,
                model.distribution,
                model.dispersion,
            )
            metrics.update(
                {
                    "fold": fold.name,
                    "train_start": str(fold.train_start),
                    "train_end": str(fold.train_end),
                    "evaluation_start": str(fold.evaluation_start),
                    "evaluation_end": str(fold.evaluation_end),
                }
            )
            model_fold_metrics.append(metrics)
            model_predictions.append(
                _prediction_rows(evaluation, predictions, spec, fold.name, "development")
            )
        combined = pd.concat(model_predictions, ignore_index=True)
        development_predictions.append(combined)
        development_metrics[spec.name] = {
            "aggregate": _aggregate_metrics(combined, model_fold_metrics),
            "folds": model_fold_metrics,
            "stabilized": spec.stabilized,
            "nonnegative_method": spec.nonnegative_method,
        }

    champion = min(
        development_metrics,
        key=lambda name: development_metrics[name]["aggregate"]["poisson_deviance"],
    )
    best_nonconstant = min(
        (name for name in development_metrics if name != "league_average"),
        key=lambda name: development_metrics[name]["aggregate"]["poisson_deviance"],
    )

    final_train, final_test = split_frame(frame, FINAL_TEST_FOLD)
    final_metrics: dict[str, Any] = {}
    final_predictions: list[pd.DataFrame] = []
    final_models: dict[str, Any] = {}
    for spec in MODEL_SPECS:
        model = spec.factory()
        model.fit(_features(final_train, spec), final_train["runs_scored"])
        predictions = model.predict(_features(final_test, spec))
        final_metrics[spec.name] = {
            **evaluate_predictions(
                final_test["runs_scored"].to_numpy(),
                predictions,
                model.distribution,
                model.dispersion,
            ),
            "stabilized": spec.stabilized,
            "nonnegative_method": spec.nonnegative_method,
        }
        final_predictions.append(
            _prediction_rows(final_test, predictions, spec, FINAL_TEST_FOLD.name, "final_test")
        )
        final_models[spec.name] = model

    predictions_frame = pd.concat([*development_predictions, *final_predictions], ignore_index=True)
    champion_predictions = predictions_frame.loc[predictions_frame["model"] == champion].copy()
    nonconstant_predictions = predictions_frame.loc[
        predictions_frame["model"] == best_nonconstant
    ].copy()
    metadata = {
        "created_at": datetime.now(UTC).isoformat(),
        "feature_version": FEATURE_VERSION,
        "dataset_rows": len(frame),
        "dataset_games": int(frame["game_pk"].nunique()),
        "target": "runs_scored",
        "random_seed": RANDOM_SEED,
        "warmup_and_initial_training": {"start": "2025-03-18", "end": "2025-05-31"},
        "development_folds": [asdict(fold) for fold in DEVELOPMENT_FOLDS],
        "final_test_fold": asdict(FINAL_TEST_FOLD),
        "selection_metric": "aggregate development poisson_deviance",
        "selected_model": champion,
        "best_nonconstant_model": best_nonconstant,
        "model_configuration": _model_configuration(),
        "development_metrics": development_metrics,
        "final_test_metrics": final_metrics,
        "error_analysis": {
            champion: _error_analysis(champion_predictions),
            best_nonconstant: _error_analysis(nonconstant_predictions),
        },
        "dependencies": {"python": platform.python_version(), **_dependencies()},
        "limitations": [
            "One 2025 season only; results are development evidence, not final performance.",
            "September is untouched during model selection but is not a multi-season holdout.",
            "Historical lineups are reconstructed from completed-game feeds.",
        ],
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, default=str) + "\n", encoding="utf-8"
    )
    predictions_frame.to_csv(output_dir / "predictions.csv", index=False)
    frame.to_csv(output_dir / "modeling_dataset.csv", index=False)
    joblib.dump(final_models, output_dir / "final_models.joblib")
    return metadata
