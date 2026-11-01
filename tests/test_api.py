import hashlib
import json
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event, inspect, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from mlb_predictor.api.app import create_app
from mlb_predictor.api.schemas import Prediction
from mlb_predictor.config import Settings
from mlb_predictor.db.models import (
    Base,
    LiveGameState,
    LivePredictionRecord,
    PredictionInputSnapshot,
)
from mlb_predictor.live import (
    ACCEPTED_ARTIFACT_SHA256,
    CALIBRATION_VERSION,
    DISTRIBUTION_VERSION,
    FEATURE_VERSION,
    MODEL_VERSION,
    DiscoveredGame,
    persist_discovery,
    save_prediction,
    settle_prediction,
)

NOW = datetime(2026, 8, 14, tzinfo=UTC)


@pytest.fixture
def api_engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, artifact_path=tmp_path / "missing.joblib")


@pytest.fixture
def client(api_engine: Engine, settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings, api_engine)) as test_client:
        yield test_client


def fixture_game() -> DiscoveredGame:
    return DiscoveredGame(
        1,
        date(2026, 8, 13),
        NOW + timedelta(minutes=30),
        20,
        "Home",
        10,
        "Away",
        30,
        "Park",
        250,
        150,
        "Pre-Game",
        "confirmed",
        tuple(range(201, 210)),
        tuple(range(101, 110)),
        NOW - timedelta(seconds=1),
    )


def save_api_fixture(
    api_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    feature_pair: tuple[dict[str, Any], dict[str, Any]] | None = None,
) -> int:
    monkeypatch.setattr("mlb_predictor.live.verify_accepted_artifact", lambda path: None)
    if feature_pair is not None:
        monkeypatch.setattr(
            "mlb_predictor.live.artifact_hash", lambda path: ACCEPTED_ARTIFACT_SHA256
        )
    game = fixture_game()
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
        "most_likely_scores": [{"home": 12, "away": 3, "probability": 0.02}],
    }
    with Session(api_engine) as session, session.begin():
        persist_discovery(session, game)
        row = save_prediction(
            session,
            game,
            result,
            NOW,
            official=True,
            warnings=["cold_start"],
            cutoff=NOW,
            launch=NOW - timedelta(hours=1),
            artifact_path=Path("synthetic"),
            feature_pair=feature_pair,
        )
        identifier = row.id
    return identifier


@pytest.fixture
def saved(api_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> int:
    return save_api_fixture(api_engine, monkeypatch)


@pytest.fixture
def saved_with_inputs(api_engine: Engine, monkeypatch: pytest.MonkeyPatch, feature_pair) -> int:
    return save_api_fixture(api_engine, monkeypatch, feature_pair)


def test_empty_dates_and_input_errors(client: TestClient) -> None:
    response = client.get("/api/v1/predictions?date=2026-11-01")
    assert response.status_code == 200
    assert response.json()["predictions"] == []
    assert response.json()["count"] == 0
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/api/v1/predictions?date=9999-12-31").json()["count"] == 0
    for path in (
        "/api/v1/predictions",
        "/api/v1/predictions?date=bad-date",
        "/api/v1/predictions?date=20260813",
        "/api/v1/predictions?date=2026-02-30",
        "/api/v1/predictions?date=2026-08-13T00:00:00Z",
        "/api/v1/games/0",
        "/api/v1/games/2147483648",
        "/api/v1/games/not-an-id",
    ):
        assert client.get(path).status_code == 422
    assert client.get("/api/v1/games/999").status_code == 404


def test_legacy_predictions_never_invent_explanations(client: TestClient, saved: int) -> None:
    prediction = client.get("/api/v1/games/1").json()["official_prediction"]
    assert prediction["explanation"]["status"] == "not_retained"
    assert prediction["explanation"]["factors"] == []
    assert prediction["confidence"]["input_quality"]["status"] == "unknown"
    assert prediction["run_ranges"]["home"]["95"]["upper"] >= 0


def test_retained_inputs_survive_discovery_settlement_and_reruns(
    client: TestClient,
    saved_with_inputs: int,
    api_engine: Engine,
    feature_pair,
) -> None:
    original = client.get("/api/v1/games/1").json()["official_prediction"]
    assert original["explanation"]["status"] == "available"
    assert original["explanation"]["home_lineup"] == list(range(201, 210))
    assert original["explanation"]["factors"][0]["model_value"] == pytest.approx(0.36)
    with Session(api_engine) as session, session.begin():
        payload = session.get(PredictionInputSnapshot, saved_with_inputs).payload_json
        feature_pair[1]["lineup_on_base_rate"] = 0.1
        repeat = save_prediction(
            session,
            fixture_game(),
            {},
            NOW + timedelta(minutes=1),
            official=True,
            warnings=[],
            cutoff=NOW + timedelta(minutes=1),
            launch=NOW - timedelta(hours=1),
            artifact_path=Path("synthetic"),
            feature_pair=feature_pair,
        )
        assert repeat.id == saved_with_inputs
        persist_discovery(
            session, replace(fixture_game(), home_lineup=tuple(range(301, 310)), status="Final")
        )
        repeat.prediction_timestamp = repeat.prediction_timestamp.replace(tzinfo=UTC)
        settle_prediction(repeat, 15, 3, "Final", NOW + timedelta(hours=4))
        assert session.get(PredictionInputSnapshot, saved_with_inputs).payload_json == payload
    current = client.get("/api/v1/games/1").json()["official_prediction"]
    for name in ("explanation", "confidence", "run_ranges", "provenance", "home", "away"):
        assert current[name] == original[name]


@pytest.mark.parametrize("field", ["payload_json", "as_of", "source", "snapshot_version"])
def test_corrupt_input_evidence_fails_closed(
    client: TestClient,
    saved_with_inputs: int,
    api_engine: Engine,
    field: str,
) -> None:
    with Session(api_engine) as session, session.begin():
        snapshot = session.get(PredictionInputSnapshot, saved_with_inputs)
        setattr(snapshot, field, NOW + timedelta(days=1) if field == "as_of" else "invalid")
    response = client.get("/api/v1/games/1")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "invalid_stored_prediction"


@pytest.mark.parametrize(
    "field,value",
    [
        ("artifact_sha256", "0" * 64),
        ("game_pk", 999),
        ("home_starter_id", 999),
    ],
)
def test_input_snapshot_must_match_forecast_provenance(
    client: TestClient,
    saved_with_inputs: int,
    api_engine: Engine,
    field: str,
    value: Any,
) -> None:
    with Session(api_engine) as session, session.begin():
        snapshot = session.get(PredictionInputSnapshot, saved_with_inputs)
        payload = json.loads(snapshot.payload_json)
        payload[field] = value
        snapshot.payload_json = json.dumps(payload)
    response = client.get("/api/v1/games/1")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "invalid_stored_prediction"


def test_invalid_inputs_do_not_partially_persist(
    api_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    feature_pair,
) -> None:
    feature_pair[1]["lineup_on_base_rate"] = float("nan")
    with pytest.raises(ValueError):
        save_api_fixture(api_engine, monkeypatch, feature_pair)
    with Session(api_engine) as session:
        assert session.scalar(select(LivePredictionRecord.id)) is None
        assert session.scalar(select(PredictionInputSnapshot.prediction_id)) is None


def test_forecast_provenance_censoring_and_official_date(
    client: TestClient,
    saved: int,
    api_engine: Engine,
) -> None:
    response = client.get("/api/v1/predictions?date=2026-08-13")
    assert response.status_code == 200
    forecast = response.json()["predictions"][0]
    Prediction.model_validate(forecast)
    assert forecast["record_id"] == saved
    assert forecast["game_date"] == "2026-08-13"
    assert forecast["date_basis"] == "mlb_official_date"
    assert forecast["home"]["expected_runs"] == 4.5
    assert forecast["home"]["run_distribution"]["labels"][-1] == "12+"
    assert forecast["home"]["intervals"]["95"]["upper_is_censored"] is True
    assert forecast["most_likely_score_bins"][0]["home_run_bucket"] == "12+"
    assert forecast["provenance"]["model_version"] == MODEL_VERSION
    assert forecast["provenance"]["feature_version"] == FEATURE_VERSION
    assert forecast["provenance"]["calibration_version"] == CALIBRATION_VERSION
    assert forecast["provenance"]["distribution_version"] == DISTRIBUTION_VERSION
    assert forecast["provenance"]["prediction_timestamp"] == "2026-08-14T00:00:00Z"
    assert forecast["data_quality_warnings"] == ["cold_start"]
    assert forecast["observed_outcome"] is None
    assert client.get("/api/v1/predictions?date=2026-08-14").json()["count"] == 0
    # Latest discovery is mutable context, not a replacement for frozen schedule/provenance.
    with Session(api_engine) as session, session.begin():
        state = session.get(LiveGameState, 1)
        state.scheduled_start_time_utc = NOW + timedelta(hours=1)
        state.status = "Delayed Start"
    detail = client.get("/api/v1/games/1").json()
    assert detail["prediction_status"] == "available"
    assert detail["latest_discovery"]["status"] == "Delayed Start"
    assert (
        detail["official_prediction"]["provenance"]["scheduled_start_time_utc"]
        == "2026-08-14T00:30:00Z"
    )


def test_excludes_diagnostics_and_other_models(
    client: TestClient,
    saved: int,
    api_engine: Engine,
) -> None:
    with Session(api_engine) as session, session.begin():
        row = session.get(LivePredictionRecord, saved)
        fields = {c.name: getattr(row, c.name) for c in row.__table__.columns if c.name != "id"}
        session.add(LivePredictionRecord(**{**fields, "model_version": "unaccepted_model"}))
        session.add(LivePredictionRecord(**{**fields, "game_pk": 2, "is_official": None}))
        state = session.get(LiveGameState, 1)
        discovery = {c.name: getattr(state, c.name) for c in state.__table__.columns}
        session.add(LiveGameState(**{**discovery, "game_pk": 2, "lineup_state": "unavailable"}))
    assert client.get("/api/v1/predictions?date=2026-08-13").json()["count"] == 1
    detail = client.get("/api/v1/games/2").json()
    assert detail["prediction_status"] == "not_recorded"
    assert detail["official_prediction"] is None
    assert detail["latest_discovery"]["lineup_state"] == "unavailable"


def test_orphaned_ledger_records_use_disclosed_utc_date(
    client: TestClient,
    saved: int,
    api_engine: Engine,
) -> None:
    with Session(api_engine) as session, session.begin():
        session.delete(session.get(LiveGameState, 1))
    response = client.get("/api/v1/predictions?date=2026-08-14")
    forecast = response.json()["predictions"][0]
    assert forecast["date_basis"] == "scheduled_start_utc"
    assert forecast["latest_discovery"] is None
    assert client.get("/api/v1/games/1").json()["official_prediction"]["record_id"] == saved


def test_settlement_is_separate_from_retained_forecast(
    client: TestClient,
    saved: int,
    api_engine: Engine,
) -> None:
    before = client.get("/api/v1/games/1").json()["official_prediction"]
    with Session(api_engine) as session, session.begin():
        row = session.get(LivePredictionRecord, saved)
        # SQLite strips tzinfo; the production PostgreSQL timestamp remains aware.
        row.prediction_timestamp = row.prediction_timestamp.replace(tzinfo=UTC)
        settle_prediction(
            row,
            5,
            3,
            "Final",
            NOW + timedelta(hours=4),
            NOW + timedelta(minutes=32),
        )
    after = client.get("/api/v1/games/1").json()["official_prediction"]
    assert after["observed_outcome"]["home_team_runs"] == 5
    assert after["observed_outcome"]["minutes_before_actual_start"] == 32
    before.pop("observed_outcome")
    after.pop("observed_outcome")
    assert after == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_probabilities_json", "not-json"),
        ("run_probabilities_json", '{"home":[1],"away":[1]}'),
        ("run_probabilities_json", json.dumps({"home": [0] * 13, "away": [1 / 13] * 13})),
        (
            "run_probabilities_json",
            json.dumps({"home": [float("nan")] + [0] * 12, "away": [1 / 13] * 13}),
        ),
        (
            "prediction_intervals_json",
            json.dumps(
                {side: {"50": [5, 2], "80": [1, 9], "95": [0, 12]} for side in ("home", "away")}
            ),
        ),
        ("most_likely_scores_json", '[{"home":13,"away":0,"probability":0.1}]'),
        ("away_win_probability", 0.99),
        ("observed_home_runs", 2),
        ("feature_cutoff_timestamp", NOW + timedelta(seconds=1)),
        ("calibration_version", "unaccepted_calibration"),
    ],
)
def test_invalid_stored_data_fails_closed(
    client: TestClient,
    saved: int,
    api_engine: Engine,
    field: str,
    value: Any,
) -> None:
    with Session(api_engine) as session, session.begin():
        setattr(session.get(LivePredictionRecord, saved), field, value)
    for path in ("/api/v1/games/1", "/api/v1/predictions?date=2026-08-13"):
        response = client.get(path)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "invalid_stored_prediction"
        assert "Traceback" not in response.text


def test_missing_and_mismatched_artifacts_do_not_block_saved_data(
    client: TestClient,
    saved: int,
    settings: Settings,
) -> None:
    assert client.get("/health/live").json() == {"status": "alive"}
    ready = client.get("/health/ready")
    assert ready.status_code == 503
    assert ready.json() == {"status": "not_ready", "database": "ready", "artifact": "missing"}
    settings.artifact_path.write_bytes(b"untrusted-artifact")
    assert client.get("/health/ready").json()["artifact"] == "checksum_mismatch"
    assert client.get("/api/v1/model").json()["artifact_status"] == "checksum_mismatch"
    assert client.get("/api/v1/games/1").status_code == 200
    settings.artifact_path.unlink()
    settings.artifact_path.mkdir()
    assert client.get("/health/ready").json()["artifact"] == "unreadable"
    assert client.get("/api/v1/games/1").status_code == 200


def test_ready_with_verified_artifact(
    client: TestClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blob = b"test artifact checksum; never unpickled"
    settings.artifact_path.write_bytes(blob)
    monkeypatch.setattr(
        "mlb_predictor.api.app.ACCEPTED_ARTIFACT_SHA256", hashlib.sha256(blob).hexdigest()
    )
    assert client.get("/health/ready").json() == {
        "status": "ready",
        "database": "ready",
        "artifact": "verified",
    }


def test_database_failure_is_safe_and_liveness_independent(
    client: TestClient,
    api_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fail(*args: Any, **kwargs: Any) -> None:
        raise OperationalError("private-sql", {}, RuntimeError("private-password"))

    monkeypatch.setattr(api_engine, "connect", fail)
    assert client.get("/health/live").status_code == 200
    assert client.get("/api/v1/model").status_code == 200
    assert client.get("/health/ready").json()["database"] == "unavailable"
    response = client.get("/api/v1/predictions?date=2026-08-13")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"
    assert "private-password" not in response.text + caplog.text
    assert "private-sql" not in response.text + caplog.text


def test_no_schema_creation_or_migration_on_startup(settings: Settings) -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    with TestClient(create_app(settings, engine)) as test_client:
        assert test_client.get("/health/live").status_code == 200
        assert test_client.get("/health/ready").json()["database"] == "unavailable"
        assert inspect(engine).get_table_names() == []
    engine.dispose()


def test_all_http_routes_are_read_only(
    client: TestClient,
    saved: int,
    api_engine: Engine,
) -> None:
    statements = []

    def collect(connection, cursor, statement, parameters, context, executemany) -> None:
        statements.append(statement.strip().split()[0].upper())

    event.listen(api_engine, "before_cursor_execute", collect)
    with Session(api_engine) as session:
        before = [
            dict(r) for r in session.execute(select(LivePredictionRecord.__table__)).mappings()
        ]
    for path in (
        "/health/live",
        "/health/ready",
        "/api/v1/model",
        "/api/v1/games/1",
        "/api/v1/predictions?date=2026-08-13",
        "/openapi.json",
    ):
        client.get(path)
    assert client.post("/api/v1/games/1").status_code == 405
    with Session(api_engine) as session:
        after = [
            dict(r) for r in session.execute(select(LivePredictionRecord.__table__)).mappings()
        ]
    assert before == after
    assert set(statements) == {"SELECT"}
    spec = client.get("/openapi.json").json()
    assert len(spec["paths"]) == 5
    assert all(set(operations) == {"get"} for operations in spec["paths"].values())
