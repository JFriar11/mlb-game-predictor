from copy import deepcopy
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from mlb_predictor.db.models import PregameFeatureSnapshot
from mlb_predictor.features.builder import build_2025_features
from mlb_predictor.features.pitching_builder import build_pitching_features
from mlb_predictor.ingestion.service import ingest_game


class StubClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def get_game_feed(self, game_pk: int) -> dict[str, Any]:
        return self.payload


def test_features_use_only_strictly_prior_dates(
    session: Session, game_feed: dict[str, Any]
) -> None:
    ingest_game(session, StubClient(game_feed), 999001)
    next_feed = deepcopy(game_feed)
    next_feed["gameData"]["game"]["pk"] = 999002
    next_feed["gameData"]["datetime"] = {
        "dateTime": "2025-04-02T18:20:00Z",
        "officialDate": "2025-04-02",
        "firstPitch": "2025-04-02T18:22:00Z",
    }
    ingest_game(session, StubClient(next_feed), 999002)
    doubleheader_feed = deepcopy(next_feed)
    doubleheader_feed["gameData"]["game"]["pk"] = 999003
    doubleheader_feed["gameData"]["game"]["doubleHeader"] = "Y"
    doubleheader_feed["gameData"]["game"]["gameNumber"] = 2
    doubleheader_feed["gameData"]["datetime"]["dateTime"] = "2025-04-02T23:20:00Z"
    doubleheader_feed["gameData"]["datetime"]["firstPitch"] = "2025-04-02T23:22:00Z"
    ingest_game(session, StubClient(doubleheader_feed), 999003)

    snapshots = build_2025_features(session, "test_v1")
    session.commit()

    assert len(snapshots) == 6
    first = [item for item in snapshots if item.game_pk == 999001]
    second = [item for item in snapshots if item.game_pk == 999002]
    same_day_second_game = [item for item in snapshots if item.game_pk == 999003]
    assert all(item.team_prior_games == 0 for item in first)
    assert all(item.max_source_game_date is None for item in first)
    assert all(item.team_prior_games == 1 for item in second)
    assert all(item.team_prior_games == 1 for item in same_day_second_game)
    assert all(item.max_source_game_date == date(2025, 4, 1) for item in second)
    assert all(item.max_source_game_date < date(2025, 4, 2) for item in second)
    assert (
        session.scalar(
            select(PregameFeatureSnapshot).where(
                PregameFeatureSnapshot.game_pk == 999002,
                PregameFeatureSnapshot.is_home.is_(True),
            )
        )
        is not None
    )


def test_target_game_outcome_does_not_change_its_features(
    session: Session, game_feed: dict[str, Any]
) -> None:
    ingest_game(session, StubClient(game_feed), 999001)
    original = build_2025_features(session, "target_invariance_v1")
    original_values = {
        item.is_home: (
            item.team_runs_avg_10,
            item.lineup_on_base_rate,
            item.starter_era,
            item.bullpen_era_30d,
            item.fallback_count,
        )
        for item in original
    }
    game_feed["liveData"]["linescore"]["teams"]["home"]["runs"] = 19
    game_feed["liveData"]["linescore"]["teams"]["away"]["runs"] = 17
    ingest_game(session, StubClient(game_feed), 999001)
    rebuilt = build_2025_features(session, "target_invariance_v1")
    rebuilt_values = {
        item.is_home: (
            item.team_runs_avg_10,
            item.lineup_on_base_rate,
            item.starter_era,
            item.bullpen_era_30d,
            item.fallback_count,
        )
        for item in rebuilt
    }
    assert rebuilt_values == original_values


def test_pitching_features_exclude_target_outcome_and_same_day_games(
    session: Session, game_feed: dict[str, Any]
) -> None:
    ingest_game(session, StubClient(game_feed), 999001)
    second = deepcopy(game_feed)
    second["gameData"]["game"]["pk"] = 999002
    second["gameData"]["datetime"].update(
        {
            "dateTime": "2025-04-02T18:20:00Z",
            "officialDate": "2025-04-02",
            "firstPitch": "2025-04-02T18:22:00Z",
        }
    )
    ingest_game(session, StubClient(second), 999002)
    same_day = deepcopy(second)
    same_day["gameData"]["game"]["pk"] = 999003
    same_day["gameData"]["datetime"]["dateTime"] = "2025-04-02T23:20:00Z"
    ingest_game(session, StubClient(same_day), 999003)
    original = build_pitching_features(session, "pitching_test_v1")
    second_values = {
        row.team_id: (row.starter_prior_starts, row.starter_avg_outs, row.bullpen_workload_3d)
        for row in original
        if row.game_pk == 999002
    }
    same_day_values = {
        row.team_id: (row.starter_prior_starts, row.starter_avg_outs, row.bullpen_workload_3d)
        for row in original
        if row.game_pk == 999003
    }
    assert second_values == same_day_values

    game_feed["liveData"]["boxscore"]["teams"]["home"]["players"]["ID250"]["stats"]["pitching"][
        "numberOfPitches"
    ] = 140
    ingest_game(session, StubClient(game_feed), 999001)
    rebuilt = build_pitching_features(session, "pitching_test_v1")
    first_before = {
        row.team_id: (row.starter_avg_outs, row.starter_avg_pitches, row.fallback_count)
        for row in original
        if row.game_pk == 999001
    }
    first_after = {
        row.team_id: (row.starter_avg_outs, row.starter_avg_pitches, row.fallback_count)
        for row in rebuilt
        if row.game_pk == 999001
    }
    assert first_before == first_after
