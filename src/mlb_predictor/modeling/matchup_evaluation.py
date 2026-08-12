import importlib.metadata
import json
import platform
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from mlb_predictor.modeling.dataset import (
    MATCHUP_FEATURE_COLUMNS,
    MULTISEASON_FEATURE_COLUMNS,
    build_multiseason_modeling_dataset,
    model_features,
)
from mlb_predictor.modeling.metrics import evaluate_predictions
from mlb_predictor.modeling.models import RANDOM_SEED, multiseason_model_specs
from mlb_predictor.modeling.multiseason import EVALUATION_SEASONS, rolling_origin_split
from mlb_predictor.modeling.stabilization import stabilize_small_samples


def _dependencies() -> dict[str, str]:
    packages = ("numpy", "pandas", "scikit-learn", "scipy", "statsmodels", "joblib")
    return {
        "python": platform.python_version(),
        **{package: importlib.metadata.version(package) for package in packages},
    }


def _run_model(
    frame: pd.DataFrame, columns: list[str], spec: Any
) -> tuple[dict[str, Any], pd.DataFrame]:
    by_season = {}
    prediction_rows = []
    nll_values = []
    nll_weights = []
    for season in EVALUATION_SEASONS:
        train, evaluation = rolling_origin_split(frame, season)
        train_x = model_features(train, columns)
        evaluation_x = model_features(evaluation, columns)
        if spec.stabilized:
            train_x = stabilize_small_samples(train_x)
            evaluation_x = stabilize_small_samples(evaluation_x)
        model = spec.factory()
        model.fit(train_x, train["runs_scored"])
        prediction = model.predict(evaluation_x)
        metrics = evaluate_predictions(
            evaluation["runs_scored"].to_numpy(),
            prediction,
            model.distribution,
            model.dispersion,
        )
        by_season[str(season)] = metrics
        nll_values.append(metrics["count_nll"])
        nll_weights.append(metrics["rows"])
        prediction_rows.append(
            pd.DataFrame(
                {
                    "game_pk": evaluation["game_pk"].to_numpy(),
                    "season": season,
                    "runs_scored": evaluation["runs_scored"].to_numpy(),
                    "prediction": prediction,
                    "model": spec.name,
                }
            )
        )
    predictions = pd.concat(prediction_rows, ignore_index=True)
    combined = evaluate_predictions(
        predictions["runs_scored"].to_numpy(), predictions["prediction"].to_numpy()
    )
    combined["count_nll"] = float(np.average(nll_values, weights=nll_weights))
    combined["distribution"] = next(iter(by_season.values()))["distribution"]
    return {"combined": combined, "by_season": by_season}, predictions


def run_sprint4_evaluation(session: Any, output_dir: Path) -> dict[str, Any]:
    matchup = build_multiseason_modeling_dataset(session, "sprint4_v1")
    baseline = build_multiseason_modeling_dataset(session, "sprint3_5_v1")
    specs = multiseason_model_specs(MATCHUP_FEATURE_COLUMNS)
    results = {}
    prediction_frames = []
    for spec in specs:
        metrics, predictions = _run_model(matchup, MATCHUP_FEATURE_COLUMNS, spec)
        results[spec.name] = metrics
        prediction_frames.append(predictions)

    ablation = {}
    for model_name in ("poisson_stabilized", "gradient_boosting_stabilized"):
        base_spec = next(
            item
            for item in multiseason_model_specs(MULTISEASON_FEATURE_COLUMNS)
            if item.name == model_name
        )
        base_metrics, _ = _run_model(baseline, MULTISEASON_FEATURE_COLUMNS, base_spec)
        matchup_metrics = results[model_name]
        ablation[model_name] = {
            "sprint3_5_v1": base_metrics,
            "sprint4_v1": matchup_metrics,
            "combined_poisson_deviance_change": (
                matchup_metrics["combined"]["poisson_deviance"]
                - base_metrics["combined"]["poisson_deviance"]
            ),
        }
    selected = min(results, key=lambda name: results[name]["combined"]["poisson_deviance"])
    metadata = {
        "created_at": datetime.now(UTC).isoformat(),
        "feature_version": "sprint4_v1",
        "base_feature_version": "sprint3_5_v1",
        "rows": len(matchup),
        "games": int(matchup["game_pk"].nunique()),
        "protocol": "rolling-origin 2022-2025 development backtest",
        "evaluation_seasons": list(EVALUATION_SEASONS),
        "training_policy": "for each evaluation season, fit only prior seasons",
        "random_seed": RANDOM_SEED,
        "selected_development_model": selected,
        "model_metrics": results,
        "ablation": ablation,
        "prospective_reserve": "2026 live predictions or another future locked period",
        "dependencies": _dependencies(),
        "limitations": [
            "All 2021-2025 results are retrospective development evidence.",
            "The completed-game feed reconstructs actual lineups, not archived pregame forecasts.",
            "The full Sprint 4 feature bundle did not improve combined Poisson deviance.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, default=str) + "\n", encoding="utf-8"
    )
    pd.concat(prediction_frames, ignore_index=True).to_csv(
        output_dir / "predictions.csv", index=False
    )
    matchup.to_csv(output_dir / "modeling_dataset.csv", index=False)
    return metadata
