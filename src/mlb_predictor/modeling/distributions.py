from dataclasses import dataclass

import numpy as np
from scipy.stats import nbinom, poisson

MAX_RUNS = 12
SUPPORT = np.arange(MAX_RUNS + 1)


def poisson_pmf(mean: np.ndarray) -> np.ndarray:
    values = poisson.pmf(SUPPORT[None, :], np.asarray(mean)[:, None])
    values[:, -1] = 1 - values[:, :-1].sum(axis=1)
    return values


def negative_binomial_pmf(mean: np.ndarray, dispersion: float) -> np.ndarray:
    size = 1.0 / dispersion
    probability = size / (size + np.asarray(mean))
    values = nbinom.pmf(SUPPORT[None, :], size, probability[:, None])
    values[:, -1] = 1 - values[:, :-1].sum(axis=1)
    return values


def estimate_dispersion(actual: np.ndarray, mean: np.ndarray) -> float:
    numerator = np.sum((actual - mean) ** 2 - mean)
    denominator = np.sum(mean**2)
    return float(np.clip(numerator / denominator, 1e-4, 2.0))


@dataclass
class DirectBucketDistribution:
    edges: np.ndarray
    probabilities: np.ndarray

    @classmethod
    def fit(
        cls, mean: np.ndarray, actual: np.ndarray, buckets: int = 8
    ) -> "DirectBucketDistribution":
        edges = np.unique(np.quantile(mean, np.linspace(0, 1, buckets + 1)))
        index = np.clip(np.digitize(mean, edges[1:-1]), 0, len(edges) - 2)
        probabilities = np.zeros((len(edges) - 1, MAX_RUNS + 1))
        league = np.bincount(np.minimum(actual, MAX_RUNS), minlength=MAX_RUNS + 1) + 1
        for bucket in range(len(probabilities)):
            counts = np.bincount(
                np.minimum(actual[index == bucket], MAX_RUNS), minlength=MAX_RUNS + 1
            )
            probabilities[bucket] = (counts + league / league.sum() * 25) / (counts.sum() + 25)
        return cls(edges, probabilities)

    def predict(self, mean: np.ndarray) -> np.ndarray:
        index = np.clip(np.digitize(mean, self.edges[1:-1]), 0, len(self.probabilities) - 1)
        return self.probabilities[index]


def distribution_scores(actual: np.ndarray, pmf: np.ndarray) -> dict[str, float | int]:
    observed = np.minimum(actual.astype(int), MAX_RUNS)
    probability = pmf[np.arange(len(observed)), observed].clip(1e-12)
    cdf = np.cumsum(pmf, axis=1)
    observed_cdf = SUPPORT[None, :] >= observed[:, None]
    predicted_mean = pmf @ SUPPORT
    predicted_variance = ((SUPPORT[None, :] - predicted_mean[:, None]) ** 2 * pmf).sum(axis=1)
    output: dict[str, float | int] = {
        "rows": len(actual),
        "count_nll": float(-np.log(probability).mean()),
        "ranked_probability_score": float(np.mean(np.sum((cdf - observed_cdf) ** 2, axis=1))),
        "empirical_mean": float(actual.mean()),
        "predicted_mean": float(predicted_mean.mean()),
        "empirical_variance": float(actual.var()),
        "predicted_variance": float(predicted_variance.mean()),
    }
    for level in (0.50, 0.80, 0.95):
        lower_q = (1 - level) / 2
        upper_q = 1 - lower_q
        lower = np.argmax(cdf >= lower_q, axis=1)
        upper = np.argmax(cdf >= upper_q, axis=1)
        output[f"coverage_{int(level * 100)}"] = float(
            np.mean((observed >= lower) & (observed <= upper))
        )
        output[f"width_{int(level * 100)}"] = float(np.mean(upper - lower))
    return output


def analytic_home_win(
    home: np.ndarray, away: np.ndarray, extra_home_win: float
) -> tuple[float, float]:
    strict = float(np.tril(np.outer(home, away), k=-1).sum())
    tie = float(np.sum(home * away))
    return strict + tie * extra_home_win, tie
