"""Opt-in persistence acceptance; run only with scripts/runtime_acceptance.py.

Synthetic records are committed for the harness's dump/restore comparison.
"""

import json
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from mlb_predictor.api.app import create_app, read_transaction
from mlb_predictor.config import Settings
from mlb_predictor.db.models import Game, LivePredictionRecord, PredictionInputSnapshot
from mlb_predictor.ingestion.service import ingest_game
from mlb_predictor.live import (
    ACCEPTED_ARTIFACT_SHA256,
    DiscoveredGame,
    establish_launch_timestamp,
    persist_discovery,
    save_prediction,
    settle_prediction,
)
from mlb_predictor.live_features import build_live_feature_pair

pytestmark = pytest.mark.postgres


class OfflineClient:
    def get_game_feed(self, game_pk: int) -> dict[str, Any]:
        raise AssertionError("acceptance must use the supplied offline fixture")


def test_postgres_prediction_and_ingestion_contract(
    game_feed: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    raw_url = os.environ.get("MLB_ACCEPTANCE_DATABASE_URL")
    if not raw_url:
        pytest.skip("run scripts/runtime_acceptance.py for isolated PostgreSQL acceptance")
    url = make_url(raw_url)
    if url.get_backend_name() != "postgresql" or url.database != "mlb_acceptance":
        pytest.fail("acceptance requires the harness's dedicated mlb_acceptance database")
    engine = create_engine(url)
    now = datetime(2026, 8, 14, tzinfo=UTC)
    game = DiscoveredGame(
        999002,
        now.date(),
        now + timedelta(minutes=30),
        20,
        "H",
        10,
        "A",
        30,
        "V",
        250,
        150,
        "Scheduled",
        "confirmed",
        tuple(range(201, 210)),
        tuple(range(101, 110)),
        now,
    )
    # Persistence acceptance needs no model binary; real artifact inference is a
    # separate, checksum-enforced container check in the harness.
    monkeypatch.setattr("mlb_predictor.live.verify_accepted_artifact", lambda path: None)
    monkeypatch.setattr("mlb_predictor.live.artifact_hash", lambda path: ACCEPTED_ARTIFACT_SHA256)
    result = {
        "expected_home_runs": 4.5,
        "expected_away_runs": 4.0,
        "dispersion": 0.2,
        "raw_home_win_probability": 0.55,
        "calibrated_home_win_probability": 0.54,
        "away_win_probability": 0.46,
        "extra_home_win_probability": 0.5,
        "regulation_tie_probability": 0.1,
        "intervals": {s: {"50": [2, 6], "80": [1, 9], "95": [0, 12]} for s in ("home", "away")},
        "home_pmf": [1 / 13] * 13,
        "away_pmf": [1 / 13] * 13,
        "most_likely_scores": [{"home": 4, "away": 3, "probability": 0.02}],
    }
    observed_columns = {
        "observed_home_runs",
        "observed_away_runs",
        "observed_home_win",
        "observed_at",
        "settlement_timestamp",
        "completion_status",
        "actual_start_time_utc",
        "minutes_before_actual_start",
    }
    try:
        with Session(engine) as session, session.begin():
            assert session.scalar(select(func.count()).select_from(LivePredictionRecord)) == 0
            ingest_game(session, OfflineClient(), 999001, payload=game_feed)
            ingest_game(session, OfflineClient(), 999001, payload=game_feed)
            assert session.scalar(select(func.count()).select_from(Game)) == 1
            persist_discovery(session, game)
            persist_discovery(session, replace(game, status="Pre-Game"))
            launch = establish_launch_timestamp(session, now - timedelta(hours=1))
            assert establish_launch_timestamp(session, now) == launch
            away_inputs, home_inputs, _ = build_live_feature_pair(
                session,
                game_pk=game.game_pk,
                home_team_id=20,
                away_team_id=10,
                venue_id=30,
                home_starter_id=250,
                away_starter_id=150,
                home_lineup=game.home_lineup,
                away_lineup=game.away_lineup,
                as_of=now,
            )

            def save(
                at: datetime, official: bool, values: dict[str, Any] = result
            ) -> LivePredictionRecord:
                return save_prediction(
                    session,
                    game,
                    values,
                    at,
                    official=official,
                    warnings=[],
                    cutoff=at,
                    launch=launch,
                    artifact_path=Path("unused-synthetic-artifact"),
                    feature_pair=(away_inputs, home_inputs),
                )

            official = save(now, True)
            original_id = official.id
            input_payload = session.get(PredictionInputSnapshot, original_id).payload_json
            assert (
                save(now + timedelta(minutes=1), True, {**result, "expected_home_runs": 8}).id
                == original_id
            )
            assert official.expected_home_runs == 4.5
            assert session.get(PredictionInputSnapshot, original_id).payload_json == input_payload
            save(now + timedelta(seconds=1), False)
            save(now + timedelta(seconds=2), False)
            session.flush()
            assert session.scalar(select(func.count()).select_from(LivePredictionRecord)) == 3
            assert session.scalar(select(func.count()).select_from(PredictionInputSnapshot)) == 3
            forecast = {
                c.name: getattr(official, c.name)
                for c in official.__table__.columns
                if c.name not in observed_columns
            }
            for _ in range(2):
                settle_prediction(
                    official,
                    5,
                    3,
                    "Final",
                    now + timedelta(hours=4),
                    game.scheduled_start_time_utc + timedelta(minutes=2),
                )
                session.flush()
                assert forecast == {name: getattr(official, name) for name in forecast}
                assert (
                    session.get(PredictionInputSnapshot, original_id).payload_json == input_payload
                )
            assert official.minutes_before_actual_start == 32
            assert official.prediction_kind == "prospective"
            assert json.loads(official.prediction_intervals_json) == result["intervals"]
        # Bypass application idempotency in an independent transaction: PostgreSQL
        # itself must reject a second official record while allowing diagnostics.
        with Session(engine) as session:
            original = session.get(LivePredictionRecord, original_id)
            duplicate = {
                c.name: getattr(original, c.name)
                for c in original.__table__.columns
                if c.name != "id"
            }
            duplicate["prediction_timestamp"] = now + timedelta(seconds=3)
            session.add(LivePredictionRecord(**duplicate))
            with pytest.raises(IntegrityError, match="uq_live_official_prediction"):
                session.commit()
            session.rollback()
        configuration = Settings(
            _env_file=None, database_url=raw_url, artifact_path=tmp_path / "missing.joblib"
        )
        with TestClient(create_app(configuration, engine)) as client:
            response = client.get("/api/v1/predictions?date=2026-08-14")
            assert response.status_code == 200
            assert response.json()["count"] == 1  # excludes the two diagnostics
            detail = client.get("/api/v1/games/999002").json()["official_prediction"]
            assert detail["observed_outcome"]["home_team_runs"] == 5
            assert detail["provenance"]["prediction_timestamp"] == "2026-08-14T00:00:00Z"
            assert detail["explanation"]["status"] == "available"
            assert len(detail["explanation"]["factors"]) == 8
            assert detail["confidence"]["input_quality"]["fallback_counts"] is not None
            assert detail["run_ranges"]["home"]["95"]["upper"] >= 0
            assert client.get("/health/ready").json()["database"] == "ready"
        with pytest.raises(DBAPIError) as rejected, read_transaction(engine) as session:
            session.execute(
                text(
                    "INSERT INTO operational_state (key,value,created_at) "
                    "VALUES ('should_not_exist','test',now())"
                )
            )
        assert rejected.value.orig.sqlstate == "25006"  # read_only_sql_transaction
    finally:
        engine.dispose()
