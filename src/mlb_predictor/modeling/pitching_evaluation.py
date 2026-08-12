import importlib.metadata
import json
import platform
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sqlalchemy import select

from mlb_predictor.db.models import Game, PitchingFeatureSnapshot, PlayerGamePitching
from mlb_predictor.modeling.dataset import (
    MULTISEASON_FEATURE_COLUMNS,
    build_multiseason_modeling_dataset,
)
from mlb_predictor.modeling.metrics import evaluate_predictions
from mlb_predictor.modeling.models import RANDOM_SEED, SklearnCountModel
from mlb_predictor.modeling.multiseason import EVALUATION_SEASONS
from mlb_predictor.modeling.stabilization import stabilize_small_samples

FEATURE_COLUMNS = [
    "starter_prior_starts",
    "starter_avg_outs",
    "starter_avg_pitches",
    "starter_pitches_per_out",
    "starter_days_rest",
    "team_prior_games",
    "manager_avg_starter_outs",
    "manager_avg_starter_pitches",
    "bullpen_prior_appearances",
    "bullpen_workload_1d",
    "bullpen_workload_3d",
    "available_reliever_count",
    "unavailable_reliever_count",
    "available_bullpen_era",
    "available_bullpen_strikeout_rate",
    "available_bullpen_walk_rate",
    "high_usage_available",
    "fallback_count",
]


def build_pitching_dataset(session: Any) -> pd.DataFrame:
    snapshots = session.execute(
        select(PitchingFeatureSnapshot, Game)
        .join(Game, PitchingFeatureSnapshot.game_pk == Game.game_pk)
        .where(PitchingFeatureSnapshot.feature_version == "sprint5_v1")
        .order_by(Game.game_date, Game.game_pk, PitchingFeatureSnapshot.team_id)
    ).all()
    outcomes = session.scalars(
        select(PlayerGamePitching).where(
            PlayerGamePitching.game_pk.in_([snapshot.game_pk for snapshot, _ in snapshots])
        )
    )
    starter_outcome: dict[tuple[int, int], PlayerGamePitching] = {}
    bullpen_outs: dict[tuple[int, int], int] = {}
    for row in outcomes:
        key = (row.game_pk, row.team_id)
        if row.is_starter:
            starter_outcome[key] = row
        else:
            bullpen_outs[key] = bullpen_outs.get(key, 0) + row.outs_recorded
    records = []
    for snapshot, game in snapshots:
        key = (snapshot.game_pk, snapshot.team_id)
        starter = starter_outcome.get(key)
        if starter is None:
            continue
        record = {
            "game_pk": game.game_pk,
            "game_date": game.game_date,
            "season": game.season,
            "team_id": snapshot.team_id,
            "starter_id": snapshot.starter_id,
            "scheduled_innings": game.scheduled_innings,
            "starter_outs": starter.outs_recorded,
            "starter_pitches": starter.pitches_thrown,
            "bullpen_outs": bullpen_outs.get(key, 0),
        }
        record.update({column: getattr(snapshot, column) for column in FEATURE_COLUMNS})
        records.append(record)
    frame = pd.DataFrame(records)
    if len(frame) != 24287 or frame["game_pk"].nunique() != 12148:
        raise ValueError("Sprint 5 pitching dataset cardinality is invalid")
    return frame


def _metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float | int]:
    residual = predicted - actual
    return {
        "rows": len(actual),
        "mae": float(np.mean(np.abs(residual))),
        "rmse": float(np.sqrt(np.mean(residual**2))),
        "mean_bias": float(np.mean(residual)),
        "minimum_prediction": float(np.min(predicted)),
        "maximum_prediction": float(np.max(predicted)),
    }


def _fit_gradient(train: pd.DataFrame, target: str) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        loss="squared_error",
        learning_rate=0.05,
        max_iter=200,
        max_leaf_nodes=15,
        min_samples_leaf=30,
        l2_regularization=1.0,
        random_state=RANDOM_SEED,
    ).fit(train[FEATURE_COLUMNS], train[target])


def _downstream_ablation(session: Any) -> dict[str, Any]:
    runs = build_multiseason_modeling_dataset(session, "sprint3_5_v1")
    state_columns = [f"pitching_{column}" for column in FEATURE_COLUMNS]
    state_rows = session.scalars(
        select(PitchingFeatureSnapshot).where(
            PitchingFeatureSnapshot.feature_version == "sprint5_v1"
        )
    )
    state = pd.DataFrame(
        [
            {
                "game_pk": row.game_pk,
                "team_id": row.team_id,
                **{column: getattr(row, column) for column in FEATURE_COLUMNS},
            }
            for row in state_rows
        ]
    ).rename(
        columns={
            "team_id": "opponent_team_id",
            **{column: f"pitching_{column}" for column in FEATURE_COLUMNS},
        }
    )
    frame = runs.merge(state, on=["game_pk", "opponent_team_id"], how="left", validate="1:1")
    if frame[state_columns].isna().any().any():
        raise ValueError("Missing Sprint 5 pitching state in downstream run dataset")
    result: dict[str, Any] = {}
    for label, columns in {
        "sprint3_5_v1": MULTISEASON_FEATURE_COLUMNS,
        "sprint3_5_plus_pitching_state": [*MULTISEASON_FEATURE_COLUMNS, *state_columns],
    }.items():
        actual_parts: list[np.ndarray] = []
        prediction_parts: list[np.ndarray] = []
        by_season: dict[str, Any] = {}
        for season in EVALUATION_SEASONS:
            train = frame.loc[frame["season"] < season]
            evaluation = frame.loc[frame["season"] == season]
            train_x = stabilize_small_samples(train[columns].copy())
            evaluation_x = stabilize_small_samples(evaluation[columns].copy())
            model = SklearnCountModel(
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
            ).fit(train_x, train["runs_scored"])
            predicted = model.predict(evaluation_x)
            actual = evaluation["runs_scored"].to_numpy()
            by_season[str(season)] = evaluate_predictions(actual, predicted)
            actual_parts.append(actual)
            prediction_parts.append(predicted)
        result[label] = {
            "combined": evaluate_predictions(
                np.concatenate(actual_parts), np.concatenate(prediction_parts)
            ),
            "by_season": by_season,
        }
    result["combined_poisson_deviance_change"] = (
        result["sprint3_5_plus_pitching_state"]["combined"]["poisson_deviance"]
        - result["sprint3_5_v1"]["combined"]["poisson_deviance"]
    )
    return result


def run_pitching_evaluation(session: Any, output_dir: Path) -> dict[str, Any]:
    frame = build_pitching_dataset(session)
    predictions: list[pd.DataFrame] = []
    by_season: dict[str, Any] = {}
    for season in EVALUATION_SEASONS:
        train = frame.loc[frame["season"] < season]
        evaluation = frame.loc[frame["season"] == season].copy()
        outs_model = _fit_gradient(train, "starter_outs")
        pitch_model = _fit_gradient(train, "starter_pitches")
        league_outs = np.full(len(evaluation), train["starter_outs"].mean())
        rolling_outs = evaluation["starter_avg_outs"].to_numpy()
        model_outs = np.clip(outs_model.predict(evaluation[FEATURE_COLUMNS]), 0, 27)
        league_pitches = np.full(len(evaluation), train["starter_pitches"].mean())
        rolling_pitches = evaluation["starter_avg_pitches"].to_numpy()
        model_pitches = np.clip(pitch_model.predict(evaluation[FEATURE_COLUMNS]), 0, 150)

        # Calibrate uncertainty and bullpen length to the winning simple component method.
        train_outs_prediction = train["starter_avg_outs"].to_numpy()
        residual = train["starter_outs"].to_numpy() - train_outs_prediction
        q10, q90 = np.quantile(residual, [0.10, 0.90])
        q025, q975 = np.quantile(residual, [0.025, 0.975])
        actual_outs = evaluation["starter_outs"].to_numpy()
        actual_bullpen = evaluation["bullpen_outs"].to_numpy()
        expected_bullpen = np.clip(evaluation["scheduled_innings"] * 3 - rolling_outs, 0, 27)
        by_season[str(season)] = {
            "starter_outs": {
                "league_mean": _metrics(actual_outs, league_outs),
                "pitcher_rolling": _metrics(actual_outs, rolling_outs),
                "gradient_boosting": _metrics(actual_outs, model_outs),
            },
            "starter_pitches": {
                "league_mean": _metrics(evaluation["starter_pitches"].to_numpy(), league_pitches),
                "pitcher_rolling": _metrics(
                    evaluation["starter_pitches"].to_numpy(), rolling_pitches
                ),
                "gradient_boosting": _metrics(
                    evaluation["starter_pitches"].to_numpy(), model_pitches
                ),
            },
            "expected_bullpen_outs": _metrics(actual_bullpen, expected_bullpen),
            "starter_outs_interval_coverage": {
                "80_percent": float(
                    np.mean(
                        (actual_outs >= rolling_outs + q10) & (actual_outs <= rolling_outs + q90)
                    )
                ),
                "95_percent": float(
                    np.mean(
                        (actual_outs >= rolling_outs + q025) & (actual_outs <= rolling_outs + q975)
                    )
                ),
            },
        }
        predictions.append(
            evaluation[
                [
                    "game_pk",
                    "game_date",
                    "season",
                    "team_id",
                    "starter_id",
                    "starter_outs",
                    "starter_pitches",
                    "bullpen_outs",
                ]
            ].assign(
                league_starter_outs=league_outs,
                rolling_starter_outs=rolling_outs,
                predicted_starter_outs=model_outs,
                league_starter_pitches=league_pitches,
                rolling_starter_pitches=rolling_pitches,
                predicted_starter_pitches=model_pitches,
                predicted_bullpen_outs=expected_bullpen,
            )
        )

    prediction_frame = pd.concat(predictions, ignore_index=True)
    combined = {
        "starter_outs_league_mean": _metrics(
            prediction_frame["starter_outs"].to_numpy(),
            prediction_frame["league_starter_outs"].to_numpy(),
        ),
        "starter_outs_pitcher_rolling": _metrics(
            prediction_frame["starter_outs"].to_numpy(),
            prediction_frame["rolling_starter_outs"].to_numpy(),
        ),
        "starter_outs_gradient_boosting": _metrics(
            prediction_frame["starter_outs"].to_numpy(),
            prediction_frame["predicted_starter_outs"].to_numpy(),
        ),
        "starter_pitches_league_mean": _metrics(
            prediction_frame["starter_pitches"].to_numpy(),
            prediction_frame["league_starter_pitches"].to_numpy(),
        ),
        "starter_pitches_pitcher_rolling": _metrics(
            prediction_frame["starter_pitches"].to_numpy(),
            prediction_frame["rolling_starter_pitches"].to_numpy(),
        ),
        "starter_pitches_gradient_boosting": _metrics(
            prediction_frame["starter_pitches"].to_numpy(),
            prediction_frame["predicted_starter_pitches"].to_numpy(),
        ),
        "expected_bullpen_outs": _metrics(
            prediction_frame["bullpen_outs"].to_numpy(),
            prediction_frame["predicted_bullpen_outs"].to_numpy(),
        ),
    }
    dependencies = {
        "python": platform.python_version(),
        **{
            package: importlib.metadata.version(package)
            for package in ("numpy", "pandas", "scikit-learn", "sqlalchemy")
        },
    }
    metadata = {
        "created_at": datetime.now(UTC).isoformat(),
        "feature_version": "sprint5_v1",
        "source_feature_reference": "sprint3_5_v1",
        "rows": len(frame),
        "games": int(frame["game_pk"].nunique()),
        "excluded_missing_starter_targets": 24296 - len(frame),
        "targets": ["starter_outs", "starter_pitches", "bullpen_outs"],
        "protocol": "rolling-origin; train prior seasons and evaluate 2022-2025",
        "evaluation_seasons": list(EVALUATION_SEASONS),
        "random_seed": RANDOM_SEED,
        "selected_component_method": "pitcher_rolling",
        "combined_metrics": combined,
        "by_season": by_season,
        "downstream_run_ablation": _downstream_ablation(session),
        "dependencies": dependencies,
        "prospective_reserve": "2026 live predictions or another future locked period",
        "limitations": [
            "Nine team-games lack a normalized starter target because the listed starter "
            "recorded zero outs and faced zero batters; feature rows remain auditable.",
            "Reliever roles are prior-usage proxies, not saves/holds or leverage-index labels.",
            "Bullpen availability is a workload proxy and does not include roster transactions.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, default=str) + "\n", encoding="utf-8"
    )
    frame.to_csv(output_dir / "pitching_dataset.csv", index=False)
    prediction_frame.to_csv(output_dir / "predictions.csv", index=False)
    return metadata
