import gzip
import json
from pathlib import Path

from mlb_predictor.ingestion.cache import RawJsonCache
from mlb_predictor.ingestion.season import discover_completed_game_ids


def test_raw_cache_fetches_once(tmp_path: Path) -> None:
    calls = 0

    def fetch() -> dict[str, int]:
        nonlocal calls
        calls += 1
        return {"gamePk": 123}

    cache = RawJsonCache(tmp_path)
    assert cache.game_feed(2025, 123, fetch) == {"gamePk": 123}
    assert cache.game_feed(2025, 123, fetch) == {"gamePk": 123}
    assert calls == 1
    with gzip.open(tmp_path / "2025/games/123.json.gz", "rt") as handle:
        assert json.load(handle) == {"gamePk": 123}


def test_schedule_discovery_filters_and_deduplicates() -> None:
    schedule = {
        "dates": [
            {
                "games": [
                    {
                        "gamePk": 1,
                        "gameType": "R",
                        "season": "2025",
                        "status": {"abstractGameState": "Final"},
                    },
                    {
                        "gamePk": 2,
                        "gameType": "S",
                        "season": "2025",
                        "status": {"abstractGameState": "Final"},
                    },
                    {
                        "gamePk": 1,
                        "gameType": "R",
                        "season": "2025",
                        "status": {"abstractGameState": "Final"},
                    },
                ]
            }
        ]
    }
    assert discover_completed_game_ids(schedule, 2025) == [1]
