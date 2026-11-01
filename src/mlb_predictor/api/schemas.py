"""Validated public contracts; censored run bins never imply exact scores."""

from datetime import date
from re import fullmatch
from typing import Annotated, Any, Literal, Self

from pydantic import AwareDatetime, BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from mlb_predictor.presentation import Confidence, Explanation, RunRanges

Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
NonnegativeFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]
RunBin = Annotated[int, Field(ge=0, le=12, strict=True)]
RunLabel = Annotated[str, Field(pattern=r"^(?:[0-9]|1[01]|12\+)$")]
ArtifactStatus = Literal["verified", "missing", "checksum_mismatch", "unreadable"]


def require_iso_date(value: Any) -> Any:
    """Reject timestamp/numeric coercions for the public YYYY-MM-DD date parameter."""
    if not isinstance(value, str) or not fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("date must use YYYY-MM-DD")
    return value


ISODate = Annotated[date, BeforeValidator(require_iso_date)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ErrorDetail(Contract):
    code: str
    message: str


class ErrorResponse(Contract):
    error: ErrorDetail


class RunDistribution(Contract):
    probabilities: Annotated[list[Probability], Field(min_length=13, max_length=13)]
    labels: list[RunLabel] = Field(default_factory=lambda: [*map(str, range(12)), "12+"])
    terminal_bucket_lower_bound: Literal[12] = 12
    terminal_bucket_is_censored: Literal[True] = True

    @model_validator(mode="after")
    def normalized(self) -> Self:
        if abs(sum(self.probabilities) - 1) > 1e-6:
            raise ValueError("run probabilities must sum to one")
        return self


class RunInterval(Contract):
    lower: RunBin
    upper: RunBin
    upper_is_censored: bool

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.lower > self.upper or self.upper_is_censored != (self.upper == 12):
            raise ValueError("invalid censored run interval")
        return self


class IntervalSet(Contract):
    p50: RunInterval = Field(alias="50")
    p80: RunInterval = Field(alias="80")
    p95: RunInterval = Field(alias="95")


class TeamForecast(Contract):
    expected_runs: NonnegativeFloat
    run_distribution: RunDistribution
    intervals: IntervalSet


class ScoreBin(Contract):
    home_run_bucket: RunLabel
    away_run_bucket: RunLabel
    probability: Probability


class Provenance(Contract):
    prediction_timestamp: AwareDatetime
    scheduled_start_time_utc: AwareDatetime
    feature_cutoff_timestamp: AwareDatetime
    source_retrieved_at: AwareDatetime
    model_version: str
    feature_version: str
    calibration_version: str
    distribution_version: str
    code_version: str
    lineup_confirmation_state: str
    home_starter_id: int | None
    away_starter_id: int | None
    timing_classification: str
    prediction_kind: str
    minutes_before_scheduled_start: Annotated[float, Field(allow_inf_nan=False)]
    is_official: Literal[True] = True

    @model_validator(mode="after")
    def cutoff_is_pregame_input(self) -> Self:
        if self.feature_cutoff_timestamp > self.prediction_timestamp:
            raise ValueError("feature cutoff follows prediction timestamp")
        return self


class ObservedOutcome(Contract):
    home_team_runs: Annotated[int, Field(ge=0)]
    away_team_runs: Annotated[int, Field(ge=0)]
    home_win: bool
    observed_at: AwareDatetime
    settlement_timestamp: AwareDatetime | None
    completion_status: str | None
    actual_start_time_utc: AwareDatetime | None
    minutes_before_actual_start: float | None

    @model_validator(mode="after")
    def winner_matches_runs(self) -> Self:
        if self.home_win != (self.home_team_runs > self.away_team_runs):
            raise ValueError("observed winner contradicts score")
        return self


class GameContext(Contract):
    """Latest discovery, explicitly separate from immutable prediction provenance."""

    game_date: date
    scheduled_start_time_utc: AwareDatetime
    home_team_id: int
    home_team_name: str
    away_team_id: int
    away_team_name: str
    venue_id: int | None
    venue_name: str | None
    status: str
    lineup_state: str
    source: str
    source_retrieved_at: AwareDatetime


class Prediction(Contract):
    record_id: int
    game_pk: int
    game_date: date
    date_basis: Literal["mlb_official_date", "scheduled_start_utc"]
    latest_discovery: GameContext | None
    home: TeamForecast
    away: TeamForecast
    raw_home_win_probability: Probability
    calibrated_home_win_probability: Probability
    away_win_probability: Probability
    regulation_tie_probability: Probability
    extra_inning_home_win_probability: Probability
    distribution_name: Literal["negative_binomial"]
    dispersion: NonnegativeFloat
    most_likely_score_bins: list[ScoreBin]
    data_quality_warnings: list[str]
    provenance: Provenance
    observed_outcome: ObservedOutcome | None
    explanation: Explanation
    confidence: Confidence
    run_ranges: RunRanges

    @model_validator(mode="after")
    def complementary_wins(self) -> Self:
        if abs(self.calibrated_home_win_probability + self.away_win_probability - 1) > 1e-6:
            raise ValueError("calibrated win probabilities must sum to one")
        return self


class PredictionList(Contract):
    date: date
    model_version: str
    generated_at: AwareDatetime
    count: int
    predictions: list[Prediction]


class GameDetail(Contract):
    game_pk: int
    model_version: str
    prediction_status: Literal["available", "not_recorded"]
    latest_discovery: GameContext | None
    official_prediction: Prediction | None


class ModelMetadata(Contract):
    model_version: str
    feature_version: str
    calibration_version: str
    distribution_version: str
    mean_model: str
    distribution: str
    calibration: str
    training_start_season: int
    training_end_season: int
    retrospective_evidence_only: bool
    artifact_sha256_expected: str
    artifact_status: ArtifactStatus
    known_limitations: list[str]


class Liveness(Contract):
    status: Literal["alive"] = "alive"


class Readiness(Contract):
    status: Literal["ready", "not_ready"]
    database: Literal["ready", "unavailable"]
    artifact: ArtifactStatus
