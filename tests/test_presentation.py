import copy
from datetime import UTC, datetime

import numpy as np
import pytest
from pydantic import ValidationError
from scipy.stats import nbinom

from mlb_predictor.db.models import LivePredictionRecord
from mlb_predictor.explanations import capture_feature_evidence
from mlb_predictor.live import ACCEPTED_ARTIFACT_SHA256
from mlb_predictor.presentation import count_range, describe_confidence, explain_inputs

NOW = datetime(2026, 8, 14, tzinfo=UTC)


def evidence_for(pair):
    return capture_feature_evidence(
        *pair,
        as_of=NOW,
        game_pk=999002,
        artifact_sha256=ACCEPTED_ARTIFACT_SHA256,
        home_lineup=tuple(range(201, 210)),
        away_lineup=tuple(range(101, 110)),
        home_team_id=20,
        away_team_id=10,
        home_starter_id=250,
        away_starter_id=150,
    )


def test_explanations_show_inputs_and_opposing_pitching_roles(feature_pair) -> None:
    evidence = evidence_for(feature_pair)
    result = explain_inputs(evidence)
    assert result.status == "available" and len(result.factors) == 8
    lineup, starter, bullpen, scoring = result.factors[:4]
    assert lineup.raw_value == 0.4
    assert lineup.model_value == pytest.approx(0.36)
    assert lineup.sample_size == 200
    assert "not official OBP" in lineup.note
    assert starter.offense_side == "home" and starter.label == "Opposing starter ERA"
    assert starter.raw_value == 8.0 and starter.sample_size == 1
    assert starter.model_value < starter.raw_value
    assert bullpen.sample_unit == "outs" and scoring.sample_size is None
    assert "not ranked contributions" in result.note
    assert explain_inputs(None).factors == []
    assert explain_inputs(None).status == "not_retained"


@pytest.mark.parametrize(
    "invalid", ["future_target", "missing_feature", "nan", "bad_rate", "bad_count", "side"]
)
def test_evidence_rejects_invalid_or_nonaccepted_inputs(feature_pair, invalid: str) -> None:
    pair = copy.deepcopy(feature_pair)
    if invalid == "future_target":
        pair[1]["home_team_runs"] = 9
    elif invalid == "missing_feature":
        del pair[1]["season"]
    elif invalid == "nan":
        pair[1]["team_runs_avg_10"] = float("nan")
    elif invalid == "bad_rate":
        pair[1]["lineup_on_base_rate"] = 1.1
    elif invalid == "bad_count":
        pair[1]["fallback_count"] = -1
    else:
        pair[1]["is_home"] = False
    with pytest.raises((ValueError, KeyError, ValidationError)):
        evidence_for(pair)


def test_capture_is_a_copy_and_keeps_the_explicit_cutoff(feature_pair) -> None:
    evidence = evidence_for(feature_pair)
    original = evidence.model_dump_json()
    feature_pair[1]["lineup_on_base_rate"] = 0.99
    assert evidence.model_dump_json() == original
    assert evidence.as_of == NOW
    assert "home_team_runs" not in evidence.raw["home"]


@pytest.mark.parametrize("mean,dispersion", [(4.5, 0.23), (20, 0.5), (0, 0.2), (4, 0)])
def test_uncensored_ranges_have_the_requested_model_mass(mean: float, dispersion: float) -> None:
    ranges = [count_range(mean, dispersion, level) for level in (0.8, 0.95)]
    assert ranges[0].lower >= ranges[1].lower
    assert ranges[0].upper <= ranges[1].upper
    for result in ranges:
        assert 0 <= result.lower <= result.upper
        assert result.model_mass >= result.nominal_mass - 1e-12
    if mean == 20:
        assert ranges[1].upper > 12
    if mean == 0:
        assert ranges[1].lower == ranges[1].upper == 0


def test_run_ranges_match_enumerated_nb_cdf() -> None:
    mean, dispersion = 18.0, 0.3
    pmf = nbinom.pmf(np.arange(300), 1 / dispersion, 1 / (1 + mean * dispersion))
    cumulative = np.cumsum(pmf)
    result = count_range(mean, dispersion, 0.95)
    assert result.lower == np.searchsorted(cumulative, 0.025)
    assert result.upper == np.searchsorted(cumulative, 0.975)
    assert result.model_mass == pytest.approx(sum(pmf[result.lower : result.upper + 1]))


@pytest.mark.parametrize(
    "mean,dispersion,level", [(float("nan"), 0.2, 0.8), (4, -1, 0.8), (4, 0.2, 1)]
)
def test_ranges_reject_invalid_parameters(mean: float, dispersion: float, level: float) -> None:
    with pytest.raises(ValueError):
        count_range(mean, dispersion, level)


def test_probability_is_separate_from_quality_and_calibration(feature_pair) -> None:
    row = LivePredictionRecord(
        calibrated_home_win_probability=0.95, data_quality_warnings_json="[]"
    )
    unknown = describe_confidence(row, None)
    assert unknown.favorite_win_probability == 0.95
    assert unknown.input_quality.status == "unknown"
    assert unknown.calibration.scope == "retrospective_development"
    assert unknown.calibration.local_reliability == "not_estimated"
    assert unknown.calibration.evaluated_games == 5928
    limited = describe_confidence(row, evidence_for(feature_pair))
    assert limited.input_quality.status == "limited"
    for side in feature_pair:
        side["fallback_count"] = 0
    clean = describe_confidence(row, evidence_for(feature_pair))
    assert clean.input_quality.status == "no_recorded_limitations"
    row.data_quality_warnings_json = '["no_current_season_history"]'
    assert describe_confidence(row, evidence_for(feature_pair)).input_quality.status == "limited"
    row.calibrated_home_win_probability = 0.5
    assert describe_confidence(row, None).favorite == "even"
    row.calibrated_home_win_probability = 0.4
    assert describe_confidence(row, None).favorite == "away"
