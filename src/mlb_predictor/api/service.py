"""Select and validate saved forecasts without generating predictions or outcomes."""

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from mlb_predictor.api.schemas import (
    GameContext,
    GameDetail,
    ObservedOutcome,
    Prediction,
    RunBin,
)
from mlb_predictor.db.models import LiveGameState, LivePredictionRecord, PredictionInputSnapshot
from mlb_predictor.live import (
    ACCEPTED_ARTIFACT_SHA256,
    CALIBRATION_VERSION,
    DISTRIBUTION_VERSION,
    FEATURE_VERSION,
    MODEL_VERSION,
)
from mlb_predictor.presentation import (
    describe_confidence,
    describe_run_ranges,
    explain_inputs,
    validate_evidence,
)


class StoredPredictionError(Exception):
    """A retained record cannot satisfy the public data contract."""


class StoredIntervals(BaseModel):
    model_config = ConfigDict(extra="forbid")
    p50: tuple[RunBin, RunBin] = Field(alias="50")
    p80: tuple[RunBin, RunBin] = Field(alias="80")
    p95: tuple[RunBin, RunBin] = Field(alias="95")


def utc(value: datetime | None) -> datetime | None:
    """Normalize the UTC storage contract (SQLite test fixtures strip tzinfo)."""
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def game_context(game: LiveGameState | None) -> GameContext | None:
    """Expose latest discovery without treating it as the prediction-time snapshot."""
    if game is None:
        return None
    fields = {name: getattr(game, name) for name in GameContext.model_fields}
    for name in ("scheduled_start_time_utc", "source_retrieved_at"):
        fields[name] = utc(fields[name])
    return GameContext.model_validate(fields)


def _forecast(record: LivePredictionRecord, side: str) -> dict[str, Any]:
    probabilities = json.loads(record.run_probabilities_json)
    intervals = json.loads(record.prediction_intervals_json)
    parsed = StoredIntervals.model_validate(intervals[side]).model_dump(by_alias=True)
    return {
        "expected_runs": getattr(record, f"expected_{side}_runs"),
        "run_distribution": {"probabilities": probabilities[side]},
        "intervals": {
            level: {"lower": bounds[0], "upper": bounds[1], "upper_is_censored": bounds[1] == 12}
            for level, bounds in parsed.items()
        },
    }


def serialize_prediction(
    record: LivePredictionRecord,
    game: LiveGameState | None,
    snapshot: PredictionInputSnapshot | None = None,
) -> Prediction:
    """Fail closed on malformed stored JSON, invalid probabilities, or partial outcomes."""
    try:
        if (
            record.feature_version != FEATURE_VERSION
            or record.calibration_version != CALIBRATION_VERSION
            or record.distribution_version != DISTRIBUTION_VERSION
        ):
            raise ValueError("retained version does not match the accepted contract")
        evidence = validate_evidence(record, snapshot, ACCEPTED_ARTIFACT_SHA256)
        provenance = {
            name: getattr(record, name)
            for name in (
                "prediction_timestamp",
                "scheduled_start_time_utc",
                "feature_cutoff_timestamp",
                "source_retrieved_at",
                "model_version",
                "feature_version",
                "calibration_version",
                "distribution_version",
                "code_version",
                "lineup_confirmation_state",
                "home_starter_id",
                "away_starter_id",
                "timing_classification",
                "prediction_kind",
            )
        }
        for name, value in provenance.items():
            if isinstance(value, datetime):
                provenance[name] = utc(value)
        provenance["minutes_before_scheduled_start"] = record.minutes_before_first_pitch
        outcome = None
        observed = [
            record.observed_home_runs,
            record.observed_away_runs,
            record.observed_home_win,
            record.observed_at,
        ]
        if any(value is not None for value in observed):
            outcome = ObservedOutcome(
                home_team_runs=record.observed_home_runs,
                away_team_runs=record.observed_away_runs,
                home_win=record.observed_home_win,
                observed_at=utc(record.observed_at),
                settlement_timestamp=utc(record.settlement_timestamp),
                completion_status=record.completion_status,
                actual_start_time_utc=utc(record.actual_start_time_utc),
                minutes_before_actual_start=record.minutes_before_actual_start,
            )
        scores = json.loads(record.most_likely_scores_json)
        labeled_scores = []
        for score in scores:
            # Validate numeric bins before constructing public labels.
            home = RunScore.model_validate(score)
            labeled_scores.append(
                {
                    "home_run_bucket": "12+" if home.home == 12 else str(home.home),
                    "away_run_bucket": "12+" if home.away == 12 else str(home.away),
                    "probability": home.probability,
                }
            )
        return Prediction(
            record_id=record.id,
            game_pk=record.game_pk,
            game_date=game.game_date if game else utc(record.scheduled_start_time_utc).date(),
            date_basis="mlb_official_date" if game else "scheduled_start_utc",
            latest_discovery=game_context(game),
            home=_forecast(record, "home"),
            away=_forecast(record, "away"),
            raw_home_win_probability=record.raw_home_win_probability,
            calibrated_home_win_probability=record.calibrated_home_win_probability,
            away_win_probability=record.away_win_probability,
            regulation_tie_probability=record.regulation_tie_probability,
            extra_inning_home_win_probability=record.extra_inning_adjustment,
            distribution_name=record.distribution_name,
            dispersion=json.loads(record.distribution_parameters_json)["dispersion"],
            most_likely_score_bins=labeled_scores,
            data_quality_warnings=json.loads(record.data_quality_warnings_json),
            provenance=provenance,
            observed_outcome=outcome,
            explanation=explain_inputs(evidence),
            confidence=describe_confidence(record, evidence),
            run_ranges=describe_run_ranges(record),
        )
    except (ValueError, TypeError, KeyError, AttributeError, ValidationError) as exc:
        raise StoredPredictionError from exc


class RunScore(BaseModel):
    model_config = ConfigDict(extra="forbid")
    home: RunBin
    away: RunBin
    probability: float


def _official_query() -> Any:
    return (
        select(LivePredictionRecord, LiveGameState, PredictionInputSnapshot)
        .outerjoin(LiveGameState, LiveGameState.game_pk == LivePredictionRecord.game_pk)
        .outerjoin(
            PredictionInputSnapshot,
            PredictionInputSnapshot.prediction_id == LivePredictionRecord.id,
        )
        .where(
            LivePredictionRecord.is_official.is_(True),
            LivePredictionRecord.model_version == MODEL_VERSION,
        )
    )


def list_predictions(session: Session, requested: date) -> list[Prediction]:
    """Use MLB official date when retained; otherwise disclose a UTC-start-date fallback."""
    start = datetime.combine(requested, datetime.min.time(), tzinfo=UTC)
    saved_date_bounds = [LivePredictionRecord.scheduled_start_time_utc >= start]
    if requested < date.max:
        saved_date_bounds.append(
            LivePredictionRecord.scheduled_start_time_utc < start + timedelta(days=1)
        )
    statement = (
        _official_query()
        .where(
            or_(
                LiveGameState.game_date == requested,
                and_(
                    LiveGameState.game_pk.is_(None),
                    *saved_date_bounds,
                ),
            )
        )
        .order_by(LivePredictionRecord.scheduled_start_time_utc, LivePredictionRecord.game_pk)
    )
    return [
        serialize_prediction(record, game, snapshot)
        for record, game, snapshot in session.execute(statement)
    ]


def get_game_detail(session: Session, game_pk: int) -> GameDetail | None:
    """A discovery without an official prediction remains visible as not recorded."""
    row = session.execute(_official_query().where(LivePredictionRecord.game_pk == game_pk)).first()
    game = row[1] if row else session.get(LiveGameState, game_pk)
    if row is None and game is None:
        return None
    try:
        return GameDetail(
            game_pk=game_pk,
            model_version=MODEL_VERSION,
            prediction_status="available" if row else "not_recorded",
            latest_discovery=game_context(game),
            official_prediction=serialize_prediction(row[0], game, row[2]) if row else None,
        )
    except ValidationError as exc:
        raise StoredPredictionError from exc
