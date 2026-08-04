from copy import deepcopy
from typing import Any

import pytest

from mlb_predictor.ingestion.parser import FeedValidationError, innings_to_outs, parse_game_feed


def test_parse_completed_regular_season_game(game_feed: dict[str, Any]) -> None:
    game = parse_game_feed(game_feed, 999001)
    assert game.home_team_runs == 4
    assert game.away_team_runs == 3
    assert len(game.starters) == 2
    assert len(game.lineups) == 18
    assert len(game.batting) == 18
    assert len(game.pitching) == 2
    assert game.pitching[0].outs_recorded == 17
    assert {entry.batting_order for entry in game.lineups} == set(range(1, 10))


def test_rejects_nonfinal_game(game_feed: dict[str, Any]) -> None:
    payload = deepcopy(game_feed)
    payload["gameData"]["status"]["abstractGameState"] = "Live"
    with pytest.raises(FeedValidationError, match="not final"):
        parse_game_feed(payload, 999001)


def test_baseball_innings_convert_to_outs() -> None:
    assert innings_to_outs("0.0") == 0
    assert innings_to_outs("7.1") == 22
    assert innings_to_outs("9.0") == 27
    with pytest.raises(FeedValidationError):
        innings_to_outs("3.3")


def test_rejects_incomplete_lineup(game_feed: dict[str, Any]) -> None:
    payload = deepcopy(game_feed)
    payload["liveData"]["boxscore"]["teams"]["away"]["battingOrder"].pop()
    with pytest.raises(FeedValidationError, match="expected 9"):
        parse_game_feed(payload, 999001)
