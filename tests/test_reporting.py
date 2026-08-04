from typing import Any

from sqlalchemy.orm import Session

from mlb_predictor.ingestion.service import ingest_game
from mlb_predictor.reporting import reconstruct_game


class StubClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def get_game_feed(self, game_pk: int) -> dict[str, Any]:
        return self.payload


def test_human_readable_reconstruction(session: Session, game_feed: dict[str, Any]) -> None:
    ingest_game(session, StubClient(game_feed), 999001)  # type: ignore[arg-type]
    report = reconstruct_game(session, 999001)
    assert "Away Club 3 at Home Club 4" in report
    assert "Venue: Test Park" in report
    assert report.count("Lineup:") == 2
