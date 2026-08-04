from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from mlb_predictor.db.models import Base


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


@pytest.fixture
def game_feed() -> dict[str, Any]:
    away_ids = list(range(101, 110))
    home_ids = list(range(201, 210))
    away_starter, home_starter = 150, 250
    all_ids = away_ids + home_ids + [away_starter, home_starter]
    people = {
        f"ID{player_id}": {
            "id": player_id,
            "fullName": f"Player {player_id}",
            "batSide": {"code": "R"},
            "pitchHand": {"code": "R"},
        }
        for player_id in all_ids
    }

    def box(ids: list[int], starter: int) -> dict[str, Any]:
        return {
            "battingOrder": ids,
            "pitchers": [starter],
            "players": {
                f"ID{player_id}": {
                    "person": people[f"ID{player_id}"],
                    "position": {"abbreviation": "CF"},
                }
                for player_id in [*ids, starter]
            },
        }

    return {
        "gameData": {
            "game": {
                "pk": 999001,
                "type": "R",
                "season": "2025",
                "doubleHeader": "N",
                "gameNumber": 1,
            },
            "status": {"abstractGameState": "Final"},
            "datetime": {
                "dateTime": "2025-04-01T18:20:00Z",
                "officialDate": "2025-04-01",
                "firstPitch": "2025-04-01T18:22:00Z",
            },
            "teams": {
                "away": {"id": 10, "name": "Away Club", "abbreviation": "AWY"},
                "home": {"id": 20, "name": "Home Club", "abbreviation": "HME"},
            },
            "venue": {"id": 30, "name": "Test Park"},
            "players": people,
        },
        "liveData": {
            "linescore": {
                "teams": {"away": {"runs": 3}, "home": {"runs": 4}},
                "innings": [{} for _ in range(9)],
            },
            "boxscore": {
                "teams": {
                    "away": box(away_ids, away_starter),
                    "home": box(home_ids, home_starter),
                }
            },
        },
        "metaData": {"timeStamp": datetime.now(UTC).strftime("%Y%m%d_%H%M%S")},
    }
