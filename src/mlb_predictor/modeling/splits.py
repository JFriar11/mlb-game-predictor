from dataclasses import dataclass
from datetime import date

import pandas as pd


@dataclass(frozen=True)
class ChronologicalFold:
    name: str
    train_start: date
    train_end: date
    evaluation_start: date
    evaluation_end: date
    is_final_test: bool = False


DEVELOPMENT_FOLDS = (
    ChronologicalFold(
        "validate_june", date(2025, 3, 18), date(2025, 5, 31), date(2025, 6, 1), date(2025, 6, 30)
    ),
    ChronologicalFold(
        "validate_july", date(2025, 3, 18), date(2025, 6, 30), date(2025, 7, 1), date(2025, 7, 31)
    ),
    ChronologicalFold(
        "validate_august", date(2025, 3, 18), date(2025, 7, 31), date(2025, 8, 1), date(2025, 8, 31)
    ),
)

FINAL_TEST_FOLD = ChronologicalFold(
    "test_september",
    date(2025, 3, 18),
    date(2025, 8, 31),
    date(2025, 9, 1),
    date(2025, 9, 28),
    is_final_test=True,
)


def split_frame(frame: pd.DataFrame, fold: ChronologicalFold) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.to_datetime(frame["game_date"]).dt.date
    train = frame.loc[(dates >= fold.train_start) & (dates <= fold.train_end)].copy()
    evaluation = frame.loc[(dates >= fold.evaluation_start) & (dates <= fold.evaluation_end)].copy()
    if train.empty or evaluation.empty:
        raise ValueError(f"Fold {fold.name} contains an empty partition")
    if max(train["game_date"]) >= min(evaluation["game_date"]):
        raise ValueError(f"Fold {fold.name} is not strictly chronological")
    if set(train.index) & set(evaluation.index):
        raise ValueError(f"Fold {fold.name} partitions overlap")
    return train, evaluation
