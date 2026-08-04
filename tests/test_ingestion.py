from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mlb_predictor.db.models import (
    Game,
    GameStartingLineup,
    GameStartingPitcher,
    PlayerGameBatting,
    PlayerGamePitching,
)
from mlb_predictor.ingestion.service import ingest_game


class StubClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def get_game_feed(self, game_pk: int) -> dict[str, Any]:
        return self.payload


def test_ingestion_is_idempotent(session: Session, game_feed: dict[str, Any]) -> None:
    client = StubClient(game_feed)
    ingest_game(session, client, 999001)  # type: ignore[arg-type]
    ingest_game(session, client, 999001)  # type: ignore[arg-type]
    session.commit()

    assert session.scalar(select(func.count()).select_from(Game)) == 1
    assert session.scalar(select(func.count()).select_from(GameStartingPitcher)) == 2
    assert session.scalar(select(func.count()).select_from(GameStartingLineup)) == 18
    assert session.scalar(select(func.count()).select_from(PlayerGameBatting)) == 18
    assert session.scalar(select(func.count()).select_from(PlayerGamePitching)) == 2
