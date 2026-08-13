from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SimulationResult:
    home_win_probability: float
    tie_probability: float
    mean_total: float
    most_likely_score: tuple[int, int]
    top_score_frequencies: tuple[tuple[int, int, float], ...]
    total_80_range: tuple[int, int]
    total_95_range: tuple[int, int]


def simulate_game(
    home_pmf: np.ndarray,
    away_pmf: np.ndarray,
    extra_home_win: float,
    simulations: int,
    seed: int,
) -> SimulationResult:
    rng = np.random.default_rng(seed)
    support = np.arange(len(home_pmf))
    home = rng.choice(support, simulations, p=home_pmf)
    away = rng.choice(support, simulations, p=away_pmf)
    tied = home == away
    extra_wins = rng.random(simulations) < extra_home_win
    wins = (home > away) | (tied & extra_wins)
    scores, counts = np.unique(np.column_stack([away, home]), axis=0, return_counts=True)
    mode = scores[np.argmax(counts)]
    order = np.argsort(counts)[-5:][::-1]
    totals = home + away
    return SimulationResult(
        float(wins.mean()),
        float(tied.mean()),
        float(totals.mean()),
        (int(mode[0]), int(mode[1])),
        tuple(
            (int(scores[index, 0]), int(scores[index, 1]), float(counts[index] / simulations))
            for index in order
        ),
        tuple(int(value) for value in np.quantile(totals, [0.10, 0.90])),
        tuple(int(value) for value in np.quantile(totals, [0.025, 0.975])),
    )
