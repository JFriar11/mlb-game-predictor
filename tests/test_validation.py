from typing import Any

from sqlalchemy.orm import Session

from mlb_predictor.ingestion.service import ingest_game
from mlb_predictor.validation.games import validate_games


class StubClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def get_game_feed(self, game_pk: int) -> dict[str, Any]:
        return self.payload


def test_acceptance_validation(session: Session, game_feed: dict[str, Any]) -> None:
    ingest_game(session, StubClient(game_feed), 999001)  # type: ignore[arg-type]
    result = validate_games(session, expected_games=1)
    assert result.passed
    assert result.failures == ()


def test_validation_reports_wrong_game_count(session: Session) -> None:
    result = validate_games(session, expected_games=5)
    assert not result.passed
    assert "expected 5 unique games, found 0" in result.failures
