import importlib.metadata
import json
import platform
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import brier_score_loss, log_loss
from sqlalchemy import select

from mlb_predictor.db.models import Game
from mlb_predictor.modeling.dataset import (
    MULTISEASON_FEATURE_COLUMNS,
    build_multiseason_modeling_dataset,
)
from mlb_predictor.modeling.distributions import (
    DirectBucketDistribution,
    analytic_home_win,
    distribution_scores,
    estimate_dispersion,
    negative_binomial_pmf,
    poisson_pmf,
)
from mlb_predictor.modeling.metrics import evaluate_predictions
from mlb_predictor.modeling.models import RANDOM_SEED, SklearnCountModel
from mlb_predictor.modeling.multiseason import EVALUATION_SEASONS, rolling_origin_split
from mlb_predictor.modeling.stabilization import stabilize_small_samples
from mlb_predictor.simulation import simulate_game


def _mean_model() -> SklearnCountModel:
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
        MULTISEASON_FEATURE_COLUMNS,
    )


def _calibration(actual: np.ndarray, pmf: np.ndarray) -> list[dict[str, float | int]]:
    output = []
    for threshold in (0, 1, 2, 3, 4, 5, 6, 8):
        predicted = pmf[:, : threshold + 1].sum(axis=1)
        output.append(
            {
                "runs_at_most": threshold,
                "predicted": float(predicted.mean()),
                "observed": float(np.mean(actual <= threshold)),
            }
        )
    return output


def _win_calibration(actual: np.ndarray, probability: np.ndarray) -> list[dict[str, Any]]:
    buckets = pd.cut(probability, np.linspace(0, 1, 11), include_lowest=True)
    frame = pd.DataFrame({"actual": actual, "probability": probability, "bucket": buckets})
    return [
        {
            "bucket": str(bucket),
            "rows": len(group),
            "predicted": float(group.probability.mean()),
            "observed": float(group.actual.mean()),
        }
        for bucket, group in frame.groupby("bucket", observed=True)
    ]


def run_distribution_evaluation(session: Any, output_dir: Path) -> dict[str, Any]:
    frame = build_multiseason_modeling_dataset(session, "sprint3_5_v1")
    distribution_rows = []
    game_rows = []
    seasonal = {}
    dispersions = {}
    dependence = {}
    examples = []
    stability = {}
    game_history = pd.DataFrame(
        session.execute(
            select(
                Game.game_pk,
                Game.season,
                Game.home_team_runs,
                Game.away_team_runs,
                Game.innings_played,
                Game.scheduled_innings,
            ).where(Game.season.between(2021, 2025))
        ).all(),
        columns=[
            "game_pk",
            "season",
            "home_runs",
            "away_runs",
            "innings_played",
            "scheduled_innings",
        ],
    )
    for season in EVALUATION_SEASONS:
        train, evaluation = rolling_origin_split(frame, season)
        model = _mean_model().fit(
            stabilize_small_samples(train[MULTISEASON_FEATURE_COLUMNS]), train.runs_scored
        )
        train_mean = model.predict(stabilize_small_samples(train[MULTISEASON_FEATURE_COLUMNS]))
        evaluation_mean = model.predict(
            stabilize_small_samples(evaluation[MULTISEASON_FEATURE_COLUMNS])
        )
        global_dispersion = estimate_dispersion(train.runs_scored.to_numpy(), train_mean)
        recent_train = train.loc[train.season == train.season.max()]
        recent_model_mean = model.predict(
            stabilize_small_samples(recent_train[MULTISEASON_FEATURE_COLUMNS])
        )
        recent_dispersion = estimate_dispersion(
            recent_train.runs_scored.to_numpy(), recent_model_mean
        )
        direct = DirectBucketDistribution.fit(train_mean, train.runs_scored.to_numpy())
        methods = {
            "poisson": poisson_pmf(evaluation_mean),
            "negative_binomial_global": negative_binomial_pmf(evaluation_mean, global_dispersion),
            "negative_binomial_recent_season": negative_binomial_pmf(
                evaluation_mean, recent_dispersion
            ),
            "direct_0_12_plus": direct.predict(evaluation_mean),
        }
        seasonal[str(season)] = {}
        dispersions[str(season)] = {
            "global_training": global_dispersion,
            "recent_training_season": recent_dispersion,
        }
        for name, pmf in methods.items():
            seasonal[str(season)][name] = {
                **distribution_scores(evaluation.runs_scored.to_numpy(), pmf),
                "calibration": _calibration(evaluation.runs_scored.to_numpy(), pmf),
            }
            for index, row in enumerate(evaluation.itertuples()):
                distribution_rows.append(
                    {
                        "game_pk": row.game_pk,
                        "season": season,
                        "is_home": row.is_home,
                        "runs_scored": row.runs_scored,
                        "predicted_mean": evaluation_mean[index],
                        "method": name,
                        "pmf": pmf[index],
                    }
                )

        # Global fold-only NB is selected before evaluation; do not choose using fold scores.
        selected_method = "negative_binomial_global"
        selected_pmf = methods[selected_method]
        paired = evaluation[["game_pk", "is_home", "runs_scored"]].copy()
        paired["predicted_mean"] = evaluation_mean
        home = paired.loc[paired.is_home].set_index("game_pk")
        away = paired.loc[~paired.is_home].set_index("game_pk")
        dependence[str(season)] = {
            "raw_run_correlation": float(home.runs_scored.corr(away.runs_scored)),
            "residual_correlation": float(
                (home.runs_scored - home.predicted_mean).corr(
                    away.runs_scored - away.predicted_mean
                )
            ),
        }
        prior_extras = game_history.loc[
            (game_history.season < season)
            & (game_history.innings_played > game_history.scheduled_innings)
        ]
        extra_home_win = float(np.mean(prior_extras.home_runs > prior_extras.away_runs))
        eval_order = evaluation.reset_index(drop=True)
        home_indices = eval_order.index[eval_order.is_home].to_numpy()
        away_indices = eval_order.index[~eval_order.is_home].to_numpy()
        home_by_game = dict(zip(eval_order.loc[home_indices, "game_pk"], home_indices, strict=True))
        away_by_game = dict(zip(eval_order.loc[away_indices, "game_pk"], away_indices, strict=True))
        for game_pk in sorted(home_by_game):
            hi, ai = home_by_game[game_pk], away_by_game[game_pk]
            analytic, tie = analytic_home_win(selected_pmf[hi], selected_pmf[ai], extra_home_win)
            actual_home_win = int(
                eval_order.loc[hi, "runs_scored"] > eval_order.loc[ai, "runs_scored"]
            )
            game_rows.append(
                {
                    "game_pk": game_pk,
                    "season": season,
                    "home_win": actual_home_win,
                    "home_win_probability": analytic,
                    "regulation_tie_probability": tie,
                    "extra_home_win_probability": extra_home_win,
                }
            )
        if season == 2025:
            for game_pk in sorted(home_by_game)[:3]:
                hi, ai = home_by_game[game_pk], away_by_game[game_pk]
                analytic, tie = analytic_home_win(
                    selected_pmf[hi], selected_pmf[ai], extra_home_win
                )
                samples = {
                    str(n): simulate_game(
                        selected_pmf[hi], selected_pmf[ai], extra_home_win, n, RANDOM_SEED + game_pk
                    ).home_win_probability
                    for n in (1000, 10000, 100000)
                }
                stability[str(game_pk)] = {
                    "analytic": analytic,
                    "simulations": samples,
                    "absolute_error": {
                        key: abs(value - analytic) for key, value in samples.items()
                    },
                }
                sim = simulate_game(
                    selected_pmf[hi],
                    selected_pmf[ai],
                    extra_home_win,
                    100000,
                    RANDOM_SEED + game_pk,
                )
                home_cdf, away_cdf = np.cumsum(selected_pmf[hi]), np.cumsum(selected_pmf[ai])
                examples.append(
                    {
                        "game_pk": game_pk,
                        "distribution": selected_method,
                        "expected_away_runs": float(evaluation_mean[ai]),
                        "expected_home_runs": float(evaluation_mean[hi]),
                        "away_80_range": [
                            int(np.argmax(away_cdf >= 0.1)),
                            int(np.argmax(away_cdf >= 0.9)),
                        ],
                        "home_80_range": [
                            int(np.argmax(home_cdf >= 0.1)),
                            int(np.argmax(home_cdf >= 0.9)),
                        ],
                        "away_95_range": [
                            int(np.argmax(away_cdf >= 0.025)),
                            int(np.argmax(away_cdf >= 0.975)),
                        ],
                        "home_95_range": [
                            int(np.argmax(home_cdf >= 0.025)),
                            int(np.argmax(home_cdf >= 0.975)),
                        ],
                        "home_win_probability": analytic,
                        "away_win_probability": 1 - analytic,
                        "regulation_tie_probability": tie,
                        "extra_home_win_probability": extra_home_win,
                        "most_likely_score_away_home": [
                            "12+" if value == 12 else value for value in sim.most_likely_score
                        ],
                        "top_score_frequencies": [
                            {
                                "away": "12+" if away == 12 else away,
                                "home": "12+" if home == 12 else home,
                                "probability": probability,
                            }
                            for away, home, probability in sim.top_score_frequencies
                        ],
                        "expected_total_runs": sim.mean_total,
                        "total_80_range": sim.total_80_range,
                        "total_95_range": sim.total_95_range,
                    }
                )

    combined = {}
    for method in (
        "poisson",
        "negative_binomial_global",
        "negative_binomial_recent_season",
        "direct_0_12_plus",
    ):
        rows = [row for row in distribution_rows if row["method"] == method]
        combined[method] = distribution_scores(
            np.array([row["runs_scored"] for row in rows]), np.stack([row["pmf"] for row in rows])
        )
    game_frame = pd.DataFrame(game_rows)
    wins = game_frame.home_win.to_numpy()
    probabilities = game_frame.home_win_probability.to_numpy().clip(1e-9, 1 - 1e-9)
    win_metrics = {
        "brier_score": float(brier_score_loss(wins, probabilities)),
        "log_loss": float(log_loss(wins, probabilities)),
        "calibration": _win_calibration(wins, probabilities),
        "by_season": {
            str(season): {
                "brier_score": float(brier_score_loss(group.home_win, group.home_win_probability)),
                "log_loss": float(log_loss(group.home_win, group.home_win_probability)),
            }
            for season, group in game_frame.groupby("season")
        },
        "home_view": {
            "brier_score": float(brier_score_loss(wins, probabilities)),
            "log_loss": float(log_loss(wins, probabilities)),
        },
        "away_view": {
            "brier_score": float(brier_score_loss(1 - wins, 1 - probabilities)),
            "log_loss": float(log_loss(1 - wins, 1 - probabilities)),
        },
    }
    means = np.array(
        [row["predicted_mean"] for row in distribution_rows if row["method"] == "poisson"]
    )
    actual = np.array(
        [row["runs_scored"] for row in distribution_rows if row["method"] == "poisson"]
    )
    overdispersion = {
        "overall": {
            "mean": float(actual.mean()),
            "variance": float(actual.var()),
            "variance_to_mean": float(actual.var() / actual.mean()),
        },
        "by_prediction_bucket": [],
    }
    for bucket, group in pd.DataFrame(
        {"actual": actual, "mean": means, "bucket": pd.cut(means, [0, 3, 4, 5, 6, np.inf])}
    ).groupby("bucket", observed=True):
        overdispersion["by_prediction_bucket"].append(
            {
                "bucket": str(bucket),
                "rows": len(group),
                "mean": float(group.actual.mean()),
                "variance": float(group.actual.var()),
                "variance_to_mean": float(group.actual.var() / group.actual.mean()),
            }
        )
    metadata = {
        "created_at": datetime.now(UTC).isoformat(),
        "feature_version": "sprint3_5_v1",
        "model": "accepted gradient_boosting_stabilized",
        "selected_distribution": "negative_binomial_global",
        "selection_reason": (
            "fold-only dispersion, seasonally robust NLL/RPS improvement over Poisson"
        ),
        "random_seed": RANDOM_SEED,
        "seasonal_distribution_metrics": seasonal,
        "combined_distribution_metrics": combined,
        "dispersion_estimates": dispersions,
        "overdispersion": overdispersion,
        "point_forecast_metrics": evaluate_predictions(actual, means),
        "dependence": dependence,
        "win_probability_metrics": win_metrics,
        "simulation_stability": stability,
        "examples": examples,
        "dependencies": {
            "python": platform.python_version(),
            **{
                package: importlib.metadata.version(package)
                for package in ("numpy", "pandas", "scipy", "scikit-learn")
            },
        },
        "limitations": [
            "12+ is one terminal run bucket.",
            "Extra innings use a training-only historical home-win approximation.",
            "Team run distributions remain conditionally independent in regulation simulation.",
            "All 2021-2025 evidence is retrospective development evidence.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, default=str) + "\n", encoding="utf-8"
    )
    game_frame.to_csv(output_dir / "game_probabilities.csv", index=False)
    return metadata
