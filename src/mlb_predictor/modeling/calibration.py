import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression


def _logit(probability: np.ndarray) -> np.ndarray:
    values = np.clip(probability, 1e-6, 1 - 1e-6)
    return np.log(values / (1 - values))


class ProbabilityCalibrator:
    def __init__(self, method: str) -> None:
        self.method = method

    def fit(self, probability: np.ndarray, target: np.ndarray) -> "ProbabilityCalibrator":
        if self.method == "none":
            return self
        if self.method == "platt":
            self.model = LogisticRegression(C=1e6).fit(_logit(probability)[:, None], target)
        elif self.method == "isotonic":
            self.model = IsotonicRegression(out_of_bounds="clip").fit(probability, target)
        elif self.method == "beta":
            values = np.clip(probability, 1e-6, 1 - 1e-6)
            features = np.column_stack([np.log(values), np.log1p(-values)])
            self.model = LogisticRegression(C=1e6).fit(features, target)
        else:
            raise ValueError(f"Unknown calibration method: {self.method}")
        return self

    def predict(self, probability: np.ndarray) -> np.ndarray:
        if self.method == "none":
            return probability
        if self.method == "platt":
            return self.model.predict_proba(_logit(probability)[:, None])[:, 1]
        if self.method == "isotonic":
            return self.model.predict(probability)
        values = np.clip(probability, 1e-6, 1 - 1e-6)
        return self.model.predict_proba(np.column_stack([np.log(values), np.log1p(-values)]))[:, 1]
