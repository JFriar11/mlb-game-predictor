from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import PoissonRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from mlb_predictor.modeling.dataset import FEATURE_COLUMNS

RANDOM_SEED = 20250318


class CountModel(Protocol):
    distribution: str
    dispersion: float | None

    def fit(self, features: pd.DataFrame, target: pd.Series) -> "CountModel": ...

    def predict(self, features: pd.DataFrame) -> np.ndarray: ...


class LeagueAverageModel:
    distribution = "poisson"
    dispersion: float | None = None

    def fit(self, features: pd.DataFrame, target: pd.Series) -> "LeagueAverageModel":
        del features
        self.mean_ = float(target.mean())
        return self

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        return np.full(len(features), self.mean_, dtype=float)


class TeamRollingAverageModel:
    distribution = "poisson"
    dispersion: float | None = None

    def fit(self, features: pd.DataFrame, target: pd.Series) -> "TeamRollingAverageModel":
        del features, target
        return self

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        return features["team_runs_avg_10"].to_numpy(dtype=float).clip(min=1e-6)


def _preprocessor(feature_columns: list[str] = FEATURE_COLUMNS) -> ColumnTransformer:
    numeric = [column for column in feature_columns if column != "venue_id"]
    return ColumnTransformer(
        [
            ("numeric", StandardScaler(), numeric),
            (
                "venue",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                ["venue_id"],
            ),
        ],
        sparse_threshold=0,
    )


class SklearnCountModel:
    distribution = "poisson"
    dispersion: float | None = None

    def __init__(self, estimator: object, feature_columns: list[str] = FEATURE_COLUMNS) -> None:
        self.pipeline = Pipeline(
            [("preprocess", _preprocessor(feature_columns)), ("model", estimator)]
        )

    def fit(self, features: pd.DataFrame, target: pd.Series) -> "SklearnCountModel":
        self.pipeline.fit(features, target)
        return self

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        return np.asarray(self.pipeline.predict(features), dtype=float).clip(min=1e-6)


class NegativeBinomialModel:
    distribution = "negative_binomial"

    def __init__(self, feature_columns: list[str] = FEATURE_COLUMNS) -> None:
        self.preprocessor = _preprocessor(feature_columns)
        self.dispersion: float | None = None

    def fit(self, features: pd.DataFrame, target: pd.Series) -> "NegativeBinomialModel":
        matrix = self.preprocessor.fit_transform(features)
        design = sm.add_constant(matrix, has_constant="add")
        values = target.to_numpy(dtype=float)
        poisson = sm.GLM(values, design, family=sm.families.Poisson()).fit(maxiter=200)
        mean = np.asarray(poisson.predict(design)).clip(min=1e-6)
        numerator = np.sum((values - mean) ** 2 - mean)
        denominator = np.sum(mean**2)
        self.dispersion = float(np.clip(numerator / denominator, 1e-4, 2.0))
        self.result = sm.GLM(
            values,
            design,
            family=sm.families.NegativeBinomial(alpha=self.dispersion),
        ).fit_regularized(alpha=0.01, L1_wt=0.0, maxiter=500)
        return self

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        matrix = self.preprocessor.transform(features)
        design = sm.add_constant(matrix, has_constant="add")
        return np.asarray(self.result.predict(design), dtype=float).clip(min=1e-6)


@dataclass(frozen=True)
class ModelSpec:
    name: str
    factory: Callable[[], CountModel]
    stabilized: bool
    nonnegative_method: str


MODEL_SPECS = (
    ModelSpec("league_average", LeagueAverageModel, False, "positive training-target mean"),
    ModelSpec("team_rolling_average", TeamRollingAverageModel, False, "positive rolling mean"),
    ModelSpec(
        "poisson_raw",
        lambda: SklearnCountModel(PoissonRegressor(alpha=0.01, max_iter=1000)),
        False,
        "Poisson log link",
    ),
    ModelSpec(
        "poisson_stabilized",
        lambda: SklearnCountModel(PoissonRegressor(alpha=0.01, max_iter=1000)),
        True,
        "Poisson log link",
    ),
    ModelSpec(
        "negative_binomial_stabilized",
        NegativeBinomialModel,
        True,
        "negative-binomial log link",
    ),
    ModelSpec(
        "gradient_boosting_stabilized",
        lambda: SklearnCountModel(
            HistGradientBoostingRegressor(
                loss="poisson",
                learning_rate=0.05,
                max_iter=200,
                max_leaf_nodes=15,
                min_samples_leaf=30,
                l2_regularization=1.0,
                random_state=RANDOM_SEED,
            )
        ),
        True,
        "Poisson loss with log link",
    ),
)


def multiseason_model_specs(feature_columns: list[str]) -> tuple[ModelSpec, ...]:
    """Return the required Sprint 3.5 comparisons for one explicit feature treatment."""
    return (
        ModelSpec("league_average", LeagueAverageModel, False, "positive training-target mean"),
        ModelSpec("team_rolling_average", TeamRollingAverageModel, False, "positive rolling mean"),
        ModelSpec(
            "poisson_stabilized",
            lambda: SklearnCountModel(PoissonRegressor(alpha=0.01, max_iter=1000), feature_columns),
            True,
            "Poisson log link",
        ),
        ModelSpec(
            "negative_binomial_stabilized",
            lambda: NegativeBinomialModel(feature_columns),
            True,
            "negative-binomial log link",
        ),
        ModelSpec(
            "gradient_boosting_stabilized",
            lambda: SklearnCountModel(
                HistGradientBoostingRegressor(
                    loss="poisson",
                    learning_rate=0.05,
                    max_iter=200,
                    max_leaf_nodes=15,
                    min_samples_leaf=30,
                    l2_regularization=1.0,
                    random_state=RANDOM_SEED,
                ),
                feature_columns,
            ),
            True,
            "Poisson loss with log link",
        ),
    )
