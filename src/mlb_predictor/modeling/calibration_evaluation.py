import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss

from mlb_predictor.modeling.calibration import ProbabilityCalibrator, _logit
from mlb_predictor.modeling.dataset import build_multiseason_modeling_dataset

METHODS = ("none", "platt", "isotonic", "beta")


def _table(target: np.ndarray, probability: np.ndarray) -> list[dict[str, Any]]:
    frame = pd.DataFrame({"target": target, "probability": probability})
    frame["bucket"] = pd.cut(probability, np.linspace(0, 1, 11), include_lowest=True)
    return [
        {
            "bucket": str(bucket),
            "rows": len(group),
            "predicted": float(group.probability.mean()),
            "observed": float(group.target.mean()),
        }
        for bucket, group in frame.groupby("bucket", observed=True)
    ]


def _metrics(target: np.ndarray, probability: np.ndarray) -> dict[str, Any]:
    probability = np.clip(probability, 1e-9, 1 - 1e-9)
    table = _table(target, probability)
    ece = sum(item["rows"] * abs(item["predicted"] - item["observed"]) for item in table) / len(
        target
    )
    slope = LogisticRegression(C=1e6).fit(_logit(probability)[:, None], target)
    return {
        "rows": len(target),
        "brier_score": float(brier_score_loss(target, probability)),
        "log_loss": float(log_loss(target, probability)),
        "calibration_intercept": float(slope.intercept_[0]),
        "calibration_slope": float(slope.coef_[0, 0]),
        "expected_calibration_error": float(ece),
        "predicted_win_rate": float(probability.mean()),
        "observed_win_rate": float(target.mean()),
        "probability_stddev": float(probability.std()),
        "probability_min": float(probability.min()),
        "probability_max": float(probability.max()),
        "calibration_table": table,
    }


def run_calibration_evaluation(session: Any, sprint7_dir: Path, output_dir: Path) -> dict[str, Any]:
    probabilities = pd.read_csv(sprint7_dir / "game_probabilities.csv")
    stacked = build_multiseason_modeling_dataset(session, "sprint3_5_v1")
    game_context = stacked.pivot(
        index="game_pk",
        columns="is_home",
        values=["game_date", "fallback_count", "starter_prior_starts"],
    ).reset_index()
    game_context.columns = [
        "game_pk",
        "away_game_date",
        "home_game_date",
        "away_fallback",
        "home_fallback",
        "away_starts",
        "home_starts",
    ]
    frame = probabilities.merge(game_context, on="game_pk", validate="1:1")
    frame["game_date"] = pd.to_datetime(frame.home_game_date)
    frame["fallback_usage"] = np.where(frame.home_fallback + frame.away_fallback > 0, "any", "none")
    frame["uncertainty"] = np.where(
        frame.regulation_tie_probability >= frame.regulation_tie_probability.median(), "high", "low"
    )
    frame["favorite_side"] = np.where(
        frame.home_win_probability >= 0.5, "home_favorite", "home_underdog"
    )
    frame["probability_range"] = pd.cut(
        frame.home_win_probability,
        [0, 0.4, 0.5, 0.6, 1],
        labels=["<0.4", "0.4-0.5", "0.5-0.6", "0.6+"],
    ).astype(str)
    all_predictions = []
    boundaries = {}
    for season, group in frame.groupby("season"):
        dates = sorted(group.game_date.dt.date.unique())
        boundary = dates[max(1, int(len(dates) * 0.4)) - 1]
        calibration = group.loc[group.game_date.dt.date <= boundary]
        evaluation = group.loc[group.game_date.dt.date > boundary].copy()
        evaluation_start = evaluation.game_date.min()
        evaluation["season_phase"] = np.where(
            (evaluation.game_date - evaluation_start).dt.days < 30,
            "first_30_evaluation_days",
            "later_evaluation_days",
        )
        boundaries[str(season)] = {
            "calibration_end": str(boundary),
            "calibration_rows": len(calibration),
            "evaluation_rows": len(evaluation),
        }
        for method in METHODS:
            calibrated = (
                ProbabilityCalibrator(method)
                .fit(calibration.home_win_probability.to_numpy(), calibration.home_win.to_numpy())
                .predict(evaluation.home_win_probability.to_numpy())
            )
            all_predictions.append(
                evaluation.assign(method=method, calibrated_probability=calibrated)
            )
    prediction_frame = pd.concat(all_predictions, ignore_index=True)
    results = {}
    for method, group in prediction_frame.groupby("method"):
        results[method] = {
            "combined": _metrics(
                group.home_win.to_numpy(), group.calibrated_probability.to_numpy()
            ),
            "by_season": {
                str(season): _metrics(
                    part.home_win.to_numpy(), part.calibrated_probability.to_numpy()
                )
                for season, part in group.groupby("season")
            },
            "slices": {
                column: {
                    str(value): _metrics(
                        part.home_win.to_numpy(), part.calibrated_probability.to_numpy()
                    )
                    for value, part in group.groupby(column)
                }
                for column in (
                    "favorite_side",
                    "fallback_usage",
                    "season_phase",
                    "uncertainty",
                    "probability_range",
                )
            },
        }
    selected = min(METHODS, key=lambda name: results[name]["combined"]["log_loss"])
    metadata = {
        "created_at": datetime.now(UTC).isoformat(),
        "protocol": (
            "prior seasons mean/distribution; first 40% dates calibrate; remaining dates evaluate"
        ),
        "boundaries": boundaries,
        "results": results,
        "selected_calibration": selected,
        "selection_rule": (
            "combined log loss, require no material Brier degradation and season stability"
        ),
        "extreme_bucket_warning": (
            "Buckets below 0.2 or above 0.8 remain too sparse for standalone selection."
        ),
        "prospective_reserve": "2026; no 2026 outcomes used",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, default=str) + "\n", encoding="utf-8"
    )
    prediction_frame.to_csv(output_dir / "calibrated_predictions.csv", index=False)
    return metadata
