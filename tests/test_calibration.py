import numpy as np

from mlb_predictor.modeling.calibration import ProbabilityCalibrator


def test_calibrators_return_reproducible_probabilities() -> None:
    probability = np.linspace(0.1, 0.9, 100)
    target = (np.arange(100) % 3 != 0).astype(int)
    evaluation = np.array([0.2, 0.5, 0.8])
    for method in ("none", "platt", "isotonic", "beta"):
        first = ProbabilityCalibrator(method).fit(probability, target).predict(evaluation)
        second = ProbabilityCalibrator(method).fit(probability, target).predict(evaluation)
        np.testing.assert_allclose(first, second)
        assert np.all((first >= 0) & (first <= 1))
