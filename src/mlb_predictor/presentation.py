"""Deterministic baseball input summaries and qualified forecast uncertainty."""

import json
from datetime import UTC, datetime
from math import isfinite
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from scipy.stats import nbinom, poisson

from mlb_predictor.db.models import LivePredictionRecord, PredictionInputSnapshot
from mlb_predictor.explanations import SNAPSHOT_SOURCE, SNAPSHOT_VERSION, FeatureEvidence

Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
Count = Annotated[int, Field(ge=0)]


class PresentationContract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class KeyFactor(PresentationContract):
    offense_side: Literal["home", "away"]
    feature: str
    label: str
    raw_value: float
    model_value: float
    unit: str
    sample_size: Count | None
    sample_unit: str | None
    note: str


class Explanation(PresentationContract):
    status: Literal["available", "not_retained"]
    method: Literal["pregame_input_summary_v1"] = "pregame_input_summary_v1"
    as_of: datetime | None
    snapshot_version: str | None
    home_lineup: list[int] | None
    away_lineup: list[int] | None
    home_team_id: int | None
    away_team_id: int | None
    factors: list[KeyFactor]
    note: str


class InputQuality(PresentationContract):
    status: Literal["unknown", "limited", "no_recorded_limitations"]
    fallback_counts: dict[Literal["home", "away"], Count] | None
    recorded_warnings: list[str]
    note: str


class CalibrationEvidence(PresentationContract):
    scope: Literal["retrospective_development"] = "retrospective_development"
    evaluation_seasons: list[int] = Field(default_factory=lambda: [2022, 2023, 2024, 2025])
    evaluated_games: Literal[5928] = 5928
    brier_score: float = 0.24485
    log_loss: float = 0.68266
    expected_calibration_error: float = 0.01717
    local_reliability: Literal["not_estimated"] = "not_estimated"
    source_report: str = "docs/SPRINT8_FINAL_RETROSPECTIVE_AUDIT.md"
    note: str = (
        "Rounded aggregate chronological development results, not a game-specific reliability "
        "estimate or prospective validation. Only four evaluated home probabilities exceeded 0.8."
    )


class Confidence(PresentationContract):
    favorite: Literal["home", "away", "even"]
    favorite_win_probability: Probability
    probability_margin_over_even: Annotated[float, Field(ge=0, le=0.5)]
    input_quality: InputQuality
    calibration: CalibrationEvidence = Field(default_factory=CalibrationEvidence)
    note: str = (
        "Win probability describes the outcome forecast, not confidence that the model is correct. "
        "Input quality and calibration evidence are reported separately; "
        "no composite score is used."
    )


class CountRange(PresentationContract):
    lower: Count
    upper: Count
    nominal_mass: Probability
    model_mass: Probability


class RunRanges(PresentationContract):
    method: Literal["saved_count_distribution_equal_tailed_v1"] = (
        "saved_count_distribution_equal_tailed_v1"
    )
    home: dict[Literal["80", "95"], CountRange]
    away: dict[Literal["80", "95"], CountRange]
    note: str = (
        "Uncensored marginal count quantiles from the saved means/dispersion. Nominal and model "
        "mass are not measured real-world coverage. Saved 12+ bin intervals remain separate."
    )


def count_range(mean: float, dispersion: float, level: float) -> CountRange:
    """Equal-tailed quantiles using the same NB mean/dispersion parameterization."""
    if not all(isfinite(x) for x in (mean, dispersion, level)):
        raise ValueError("nonfinite count parameters")
    if mean < 0 or dispersion < 0 or not 0 < level < 1:
        raise ValueError("invalid count parameters")
    if dispersion == 0:
        distribution = poisson(mean)
    else:
        size = 1 / dispersion
        probability = size / (size + mean)
        if not isfinite(size) or not 0 < probability <= 1:
            raise ValueError("invalid NB shape")
        distribution = nbinom(size, probability)
    tail = (1 - level) / 2
    low, high = distribution.ppf([tail, 1 - tail])
    if not isfinite(low) or not isfinite(high) or low < 0 or high < low:
        raise ValueError("invalid count quantiles")
    mass = float(distribution.cdf(high) - distribution.cdf(low - 1))
    return CountRange(
        lower=int(low), upper=int(high), nominal_mass=level, model_mass=min(1, max(0, mass))
    )


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def validate_evidence(
    record: LivePredictionRecord,
    snapshot: PredictionInputSnapshot | None,
    expected_artifact_sha256: str,
) -> FeatureEvidence | None:
    """Bind evidence to its original record, never to mutable latest discovery."""
    if snapshot is None:
        return None
    evidence = FeatureEvidence.model_validate_json(snapshot.payload_json)
    if (
        snapshot.prediction_id != record.id
        or evidence.game_pk != record.game_pk
        or snapshot.snapshot_version != SNAPSHOT_VERSION
        or snapshot.source != SNAPSHOT_SOURCE
        or _utc(snapshot.as_of) != evidence.as_of
        or evidence.as_of != _utc(record.feature_cutoff_timestamp)
        or evidence.as_of > _utc(record.prediction_timestamp)
        or evidence.artifact_sha256 != expected_artifact_sha256
        or evidence.home_starter_id != record.home_starter_id
        or evidence.away_starter_id != record.away_starter_id
    ):
        raise ValueError("input snapshot provenance mismatch")
    return evidence


def explain_inputs(evidence: FeatureEvidence | None) -> Explanation:
    """Summarize four baseball input groups per offense in a fixed, unranked order."""
    if evidence is None:
        return Explanation(
            status="not_retained",
            as_of=None,
            snapshot_version=None,
            home_lineup=None,
            away_lineup=None,
            home_team_id=None,
            away_team_id=None,
            factors=[],
            note="Prediction-time inputs were not retained. "
            "No historical explanation is reconstructed.",
        )
    definitions = [
        (
            "lineup_on_base_rate",
            "Lineup on-base proxy",
            "rate",
            "lineup_prior_pa",
            "plate appearances",
            "(Hits + walks) / (at-bats + walks) across retained prior MLB history; "
            "not official OBP. "
            "Excludes hit-by-pitch and sacrifice flies. Empty history uses a prior.",
        ),
        (
            "starter_era",
            "Opposing starter ERA",
            "earned runs per nine innings",
            "starter_prior_starts",
            "starts",
            "Opposing starting pitcher's retained prior MLB starts. Empty history uses a prior; "
            "the mean model receives the stabilized value, not an assumed current-game outcome.",
        ),
        (
            "bullpen_era_30d",
            "Opposing bullpen ERA",
            "earned runs per nine innings",
            "bullpen_prior_outs",
            "outs",
            "Opposing team's reliever results from earlier dates within 30 days. "
            "This is team history, "
            "not a confirmed available-reliever projection. Empty history uses a prior.",
        ),
        (
            "team_runs_avg_10",
            "Recent team scoring",
            "runs per game",
            None,
            None,
            "Average over up to ten retained team games. Early-season or empty-history fallbacks "
            "can use earlier history or a league prior; the exact window count was not retained.",
        ),
    ]
    factors = []
    for side in ("home", "away"):
        for feature, label, unit, sample_column, sample_unit, note in definitions:
            factors.append(
                KeyFactor(
                    offense_side=side,
                    feature=feature,
                    label=label,
                    raw_value=evidence.raw[side][feature],
                    model_value=evidence.stabilized[side][feature],
                    unit=unit,
                    sample_size=int(evidence.raw[side][sample_column]) if sample_column else None,
                    sample_unit=sample_unit,
                    note=note,
                )
            )
    return Explanation(
        status="available",
        as_of=evidence.as_of,
        snapshot_version=evidence.snapshot_version,
        home_lineup=evidence.home_lineup,
        away_lineup=evidence.away_lineup,
        home_team_id=evidence.home_team_id,
        away_team_id=evidence.away_team_id,
        factors=factors,
        note="Recorded pregame inputs in a fixed order. These are not ranked contributions, "
        "causal effects, or estimates of runs added; raw and stabilized model values are shown.",
    )


def describe_confidence(
    record: LivePredictionRecord, evidence: FeatureEvidence | None
) -> Confidence:
    """Separate probability, recorded input limitations, and retrospective calibration."""
    warnings = json.loads(record.data_quality_warnings_json)
    counts = (
        {side: int(evidence.raw[side]["fallback_count"]) for side in ("home", "away")}
        if evidence
        else None
    )
    status = (
        "unknown"
        if counts is None
        else ("limited" if warnings or any(counts.values()) else "no_recorded_limitations")
    )
    home = record.calibrated_home_win_probability
    return Confidence(
        favorite="home" if home > 0.5 else ("away" if home < 0.5 else "even"),
        favorite_win_probability=max(home, 1 - home),
        probability_margin_over_even=abs(home - 0.5),
        input_quality=InputQuality(
            status=status,
            fallback_counts=counts,
            recorded_warnings=warnings,
            note="Missing evidence is unknown quality. Fallbacks or recorded warnings flag limited "
            "inputs. No recorded limitations does not certify complete or current data.",
        ),
    )


def describe_run_ranges(record: LivePredictionRecord) -> RunRanges:
    """Derive marginal count ranges without changing the saved censored-bin forecast."""
    dispersion = json.loads(record.distribution_parameters_json)["dispersion"]
    return RunRanges(
        **{
            side: {
                str(int(level * 100)): count_range(
                    getattr(record, f"expected_{side}_runs"), dispersion, level
                )
                for level in (0.8, 0.95)
            }
            for side in ("home", "away")
        }
    )
