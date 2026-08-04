from typing import Any

import numpy as np
from scipy.special import gammaln
from sklearn.metrics import mean_absolute_error, mean_poisson_deviance, mean_squared_error


def poisson_nll(target: np.ndarray, prediction: np.ndarray) -> float:
    mean = np.asarray(prediction, dtype=float).clip(min=1e-9)
    values = np.asarray(target, dtype=float)
    return float(np.mean(mean - values * np.log(mean) + gammaln(values + 1)))


def negative_binomial_nll(target: np.ndarray, prediction: np.ndarray, dispersion: float) -> float:
    values = np.asarray(target, dtype=float)
    mean = np.asarray(prediction, dtype=float).clip(min=1e-9)
    size = 1.0 / dispersion
    probability = size / (size + mean)
    log_probability = (
        gammaln(values + size)
        - gammaln(size)
        - gammaln(values + 1)
        + size * np.log(probability)
        + values * np.log1p(-probability)
    )
    return float(-np.mean(log_probability))


def evaluate_predictions(
    target: np.ndarray,
    prediction: np.ndarray,
    distribution: str = "poisson",
    dispersion: float | None = None,
) -> dict[str, Any]:
    values = np.asarray(target, dtype=float)
    mean = np.asarray(prediction, dtype=float).clip(min=1e-9)
    if distribution == "negative_binomial":
        if dispersion is None:
            raise ValueError("Negative-binomial scoring requires dispersion")
        count_nll = negative_binomial_nll(values, mean, dispersion)
    else:
        count_nll = poisson_nll(values, mean)
    return {
        "rows": len(values),
        "mae": float(mean_absolute_error(values, mean)),
        "rmse": float(mean_squared_error(values, mean) ** 0.5),
        "mean_bias": float(np.mean(mean - values)),
        "poisson_deviance": float(mean_poisson_deviance(values, mean)),
        "count_nll": count_nll,
        "distribution": distribution,
        "dispersion": dispersion,
        "minimum_prediction": float(mean.min()),
        "maximum_prediction": float(mean.max()),
    }
