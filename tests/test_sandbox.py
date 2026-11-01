"""Scientific/input boundaries and no-write behavior of optional local inference."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from mlb_predictor.api.app import create_app
from mlb_predictor.api.sandbox import SandboxRequest, catalog, retained_lineup, run_sandbox
from mlb_predictor.config import Settings
from mlb_predictor.db.models import Base, Game, Player, Team, Venue


def inputs() -> dict:
    return dict(
        as_of="2026-08-14T00:00:00Z",
        home_team_id=20,
        away_team_id=10,
        venue_id=30,
        home_starter_id=250,
        away_starter_id=150,
        home_lineup=list(range(201, 210)),
        away_lineup=list(range(101, 110)),
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"home_lineup": list(range(201, 209))},
        {"home_lineup": [201] * 9},
        {"away_lineup": list(range(201, 210))},
        {"home_team_id": 10},
        {"home_starter_id": 150},
        {"home_starter_id": 101},
        {"away_starter_id": 201},
        {"as_of": "2025-12-31T23:59:59Z"},
        {"as_of": "2099-01-01T00:00:00Z"},
        {"as_of": "2026-08-14T00:00:00"},
        {"venue_id": -1},
        {"home_lineup": ["201", *range(202, 210)]},
    ],
)
def test_invalid_matchups_are_rejected(changes: dict) -> None:
    with pytest.raises(ValidationError):
        SandboxRequest.model_validate(inputs() | changes)


def test_two_way_player_and_utc_cutoff() -> None:
    request = SandboxRequest.model_validate(
        inputs() | {"home_starter_id": 201, "as_of": "2026-08-14T01:00:00+02:00"}
    )
    assert request.as_of == datetime(2026, 8, 13, 23, tzinfo=UTC)


def seed_people(session: Session) -> None:
    common = dict(source="test", retrieved_at=datetime(2026, 1, 1, tzinfo=UTC))
    session.add_all([Team(team_id=i, name=str(i), **common) for i in (10, 20)])
    session.add(Venue(venue_id=30, name="Test Park", **common))
    session.add_all(
        [
            Player(player_id=i, full_name=f"Player {i}", **common)
            for i in [*range(101, 110), *range(201, 210), 150, 250]
        ]
    )
    session.commit()


def test_ephemeral_inference_and_no_dml(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    seed_people(session)
    statements = []
    event.listen(
        session.bind,
        "before_cursor_execute",
        lambda conn, cursor, stmt, params, ctx, many: statements.append(stmt),
    )
    monkeypatch.setattr("mlb_predictor.api.sandbox.verify_accepted_artifact", lambda path: None)
    monkeypatch.setattr(
        "mlb_predictor.api.sandbox.predict_from_features",
        lambda away, home, artifact: {
            "expected_home_runs": 4.5,
            "expected_away_runs": 4.0,
            "dispersion": 0.2,
            "home_pmf": [1 / 13] * 13,
            "away_pmf": [1 / 13] * 13,
            "calibrated_home_win_probability": 0.54,
            "most_likely_scores": [{"home": 12, "away": 3, "probability": 0.02}],
        },
    )
    result = run_sandbox(session, SandboxRequest.model_validate(inputs()), Path("unused"))
    assert not result.saved and not result.is_official and result.kind == "hypothetical"
    assert result.away_win_probability == pytest.approx(0.46)
    assert result.most_likely_score_bins[0].home_run_bucket == "12+"
    assert result.home.run_ranges["95"].upper >= result.home.run_ranges["80"].upper
    assert result.explanation.home_lineup == inputs()["home_lineup"]
    assert result.confidence.input_quality.status == "limited"
    assert any("stale" in x for x in result.warnings)
    assert all(
        not x.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for x in statements
    )
    assert not session.new and not session.dirty
    assert session.scalar(select(func.count()).select_from(Game)) == 0


def test_missing_people_fail_before_loading_artifact(session: Session) -> None:
    with pytest.raises(ValueError, match="known teams"):
        run_sandbox(session, SandboxRequest.model_validate(inputs()), Path("missing"))


def test_catalog_and_seed_exclude_target_date(session: Session) -> None:
    from mlb_predictor.db.models import GameStartingLineup, GameStartingPitcher

    seed_people(session)
    common = dict(source="test", retrieved_at=datetime(2026, 8, 14, tzinfo=UTC))
    for game_id, day in ((1, 12), (2, 14)):
        session.add(
            Game(
                game_pk=game_id,
                game_date=datetime(2026, 8, day).date(),
                scheduled_start_time_utc=datetime(2026, 8, day, tzinfo=UTC),
                season=2026,
                game_type="R",
                status="Final",
                home_team_id=20,
                away_team_id=10,
                venue_id=30,
                home_team_runs=5,
                away_team_runs=3,
                innings_played=9,
                **common,
            )
        )
        session.add(
            GameStartingPitcher(game_pk=game_id, team_id=20, pitcher_id=250, is_home=True, **common)
        )
        session.add_all(
            [
                GameStartingLineup(
                    game_pk=game_id,
                    team_id=20,
                    player_id=200 + i,
                    batting_order=i,
                    is_home=True,
                    **common,
                )
                for i in range(1, 10)
            ]
        )
    session.commit()
    session.add(Venue(venue_id=-1, name="Historical sentinel", **common))
    session.commit()
    info = catalog(session)
    assert all(v.id > 0 for v in info.venues)
    assert info.latest_history_date.isoformat() == "2026-08-14"
    assert info.default_as_of.day == 15
    value = retained_lineup(session, 20, datetime(2026, 8, 14, 12, tzinfo=UTC))
    assert value.game_date.isoformat() == "2026-08-12"
    assert value.lineup == list(range(201, 210))
    assert retained_lineup(session, 20, datetime(2026, 8, 12, tzinfo=UTC)) is None


def test_api_opt_in_artifact_fail_closed_and_input_errors(tmp_path: Path) -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    try:
        for enabled in (False, True):
            settings = Settings(
                _env_file=None, sandbox_enabled=enabled, artifact_path=tmp_path / "missing"
            )
            with TestClient(create_app(settings, engine)) as client:
                assert client.get("/api/v1/sandbox/catalog").status_code == (
                    200 if enabled else 404
                )
                result = client.post("/api/v1/sandbox/predict", json=inputs())
                assert result.status_code == (503 if enabled else 404)
                if enabled:
                    assert result.json()["error"]["code"] == "artifact_unavailable"
                    assert (
                        client.post(
                            "/api/v1/sandbox/predict", json=inputs() | {"home_team_id": 10}
                        ).status_code
                        == 422
                    )
                    assert (
                        client.get(
                            "/api/v1/sandbox/lineup",
                            params={"team_id": 20, "as_of": "2026-08-14T00:00:00"},
                        ).status_code
                        == 422
                    )
                    assert (
                        client.get(
                            "/api/v1/sandbox/lineup",
                            params={"team_id": 20, "as_of": "2026-08-14T00:00:00Z"},
                        ).status_code
                        == 404
                    )
    finally:
        engine.dispose()
