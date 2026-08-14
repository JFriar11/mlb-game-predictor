import copy
from datetime import UTC, datetime, timedelta

import numpy as np

from mlb_predictor.live import (
    DiscoveredGame,
    official_eligible,
    parse_discovered_games,
    prediction_kind,
    timing_classification,
)
from mlb_predictor.modeling.calibration import ProbabilityCalibrator


def _game(start: datetime, lineup_state: str = "confirmed") -> DiscoveredGame:
    return DiscoveredGame(
        1,
        start.date(),
        start,
        1,
        "H",
        2,
        "A",
        3,
        "V",
        4,
        5,
        "Scheduled",
        lineup_state,
        tuple(range(9)),
        tuple(range(9)),
        start - timedelta(hours=1),
    )


def test_timing_and_prospective_classification() -> None:
    now = datetime(2026, 8, 14, tzinfo=UTC)
    launch = now - timedelta(hours=1)
    assert timing_classification(now, now + timedelta(minutes=30))[1] == "target_window"
    assert official_eligible(_game(now + timedelta(minutes=30)), now)
    assert not official_eligible(_game(now + timedelta(minutes=30), "unavailable"), now)
    assert prediction_kind(now, now + timedelta(minutes=30), launch) == "prospective"
    assert prediction_kind(now, now - timedelta(minutes=1), launch) == "backfill"
    assert prediction_kind(now, now + timedelta(minutes=30), None) == "backfill"


def test_lineup_requires_two_complete_nines() -> None:
    schedule = {
        "dates": [
            {
                "date": "2026-08-13",
                "games": [
                    {
                        "gamePk": 1,
                        "gameDate": "2026-08-14T00:00:00Z",
                        "teams": {
                            "home": {"team": {"id": 1, "name": "H"}},
                            "away": {"team": {"id": 2, "name": "A"}},
                        },
                        "venue": {"id": 3, "name": "V"},
                        "status": {"detailedState": "Scheduled"},
                    }
                ],
            }
        ]
    }
    feed = {
        "liveData": {
            "boxscore": {
                "teams": {
                    "home": {"battingOrder": list(range(1, 10))},
                    "away": {"battingOrder": list(range(11, 20))},
                }
            }
        }
    }
    assert (
        parse_discovered_games(schedule, datetime.now(UTC), {1: feed})[0].lineup_state
        == "confirmed"
    )
    broken = copy.deepcopy(feed)
    broken["liveData"]["boxscore"]["teams"]["away"]["battingOrder"] = []
    assert (
        parse_discovered_games(schedule, datetime.now(UTC), {1: broken})[0].lineup_state
        == "unavailable"
    )


def test_frozen_calibrator_is_reproducible() -> None:
    probability = np.array([0.2, 0.4, 0.6, 0.8])
    target = np.array([0, 0, 1, 1])
    model = ProbabilityCalibrator("platt").fit(probability, target)
    assert np.array_equal(model.predict(probability), model.predict(probability))
