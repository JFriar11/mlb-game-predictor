import numpy as np

from mlb_predictor.modeling.distributions import (
    analytic_home_win,
    negative_binomial_pmf,
    poisson_pmf,
)
from mlb_predictor.simulation import simulate_game


def test_distribution_probabilities_sum_to_one() -> None:
    means = np.array([2.5, 4.5, 8.0])
    np.testing.assert_allclose(poisson_pmf(means).sum(axis=1), 1.0)
    np.testing.assert_allclose(negative_binomial_pmf(means, 0.15).sum(axis=1), 1.0)


def test_simulation_matches_analytic_home_win_probability() -> None:
    home = poisson_pmf(np.array([4.7]))[0]
    away = poisson_pmf(np.array([4.2]))[0]
    analytic, tie = analytic_home_win(home, away, 0.55)
    simulation = simulate_game(home, away, 0.55, 200_000, 20250318)
    assert abs(simulation.home_win_probability - analytic) < 0.005
    assert abs(simulation.tie_probability - tie) < 0.005


def test_simulation_is_reproducible() -> None:
    pmf = poisson_pmf(np.array([4.5]))[0]
    assert simulate_game(pmf, pmf, 0.55, 10_000, 7) == simulate_game(pmf, pmf, 0.55, 10_000, 7)
