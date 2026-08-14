from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss, mean_poisson_deviance
from sqlalchemy import select
from sqlalchemy.orm import Session

from mlb_predictor.db.models import Game, LiveGameState, LivePredictionRecord, OperationalState
from mlb_predictor.modeling.calibration import ProbabilityCalibrator
from mlb_predictor.modeling.dataset import MULTISEASON_FEATURE_COLUMNS
from mlb_predictor.modeling.distributions import (
    analytic_home_win,
    estimate_dispersion,
    negative_binomial_pmf,
)
from mlb_predictor.modeling.models import multiseason_model_specs
from mlb_predictor.modeling.multiseason import _fit_predict
from mlb_predictor.modeling.stabilization import stabilize_small_samples

MODEL_VERSION = "accepted_v1_2026_prospective"
FEATURE_VERSION = "sprint3_5_v1"
CALIBRATION_VERSION = "platt_v1"
DISTRIBUTION_VERSION = "negative_binomial_global_v1"
LAUNCH_KEY = "prospective_launch_timestamp"
TARGET_MINUTES = 30.0
ACCEPTED_ARTIFACT_SHA256 = "2d2f6bdd557bb9f4fa981fd88358774617fc246810f2efb2e4c79917ba9df945"


@dataclass(frozen=True)
class DiscoveredGame:
    game_pk: int
    game_date: date
    scheduled_start_time_utc: datetime
    home_team_id: int
    home_team_name: str
    away_team_id: int
    away_team_name: str
    venue_id: int | None
    venue_name: str | None
    home_starter_id: int | None
    away_starter_id: int | None
    status: str
    lineup_state: str
    home_lineup: tuple[int, ...]
    away_lineup: tuple[int, ...]
    retrieved_at: datetime


def _person_id(value: Any) -> int | None:
    return int(value["id"]) if isinstance(value, dict) and value.get("id") else None


def _lineup(feed: dict[str, Any], side: str) -> tuple[int, ...]:
    box = feed.get("liveData", {}).get("boxscore", {}).get("teams", {}).get(side, {})
    order = box.get("battingOrder") or []
    return tuple(int(value) for value in order[:9]) if len(order) >= 9 else ()


def parse_discovered_games(
    schedule: dict[str, Any], retrieved_at: datetime, feeds: dict[int, dict[str, Any]] | None = None
) -> list[DiscoveredGame]:
    output = []
    feeds = feeds or {}
    for day in schedule.get("dates", []):
        for item in day.get("games", []):
            game_pk = int(item["gamePk"])
            feed = feeds.get(game_pk, {})
            home_lineup, away_lineup = _lineup(feed, "home"), _lineup(feed, "away")
            lineup_state = (
                "confirmed" if len(home_lineup) == len(away_lineup) == 9 else "unavailable"
            )
            teams, venue = item["teams"], item.get("venue") or {}
            output.append(
                DiscoveredGame(
                    game_pk=game_pk,
                    game_date=date.fromisoformat(day["date"]),
                    scheduled_start_time_utc=datetime.fromisoformat(
                        item["gameDate"].replace("Z", "+00:00")
                    ),
                    home_team_id=int(teams["home"]["team"]["id"]),
                    home_team_name=teams["home"]["team"]["name"],
                    away_team_id=int(teams["away"]["team"]["id"]),
                    away_team_name=teams["away"]["team"]["name"],
                    venue_id=int(venue["id"]) if venue.get("id") else None,
                    venue_name=venue.get("name"),
                    home_starter_id=_person_id(teams["home"].get("probablePitcher")),
                    away_starter_id=_person_id(teams["away"].get("probablePitcher")),
                    status=(item.get("status") or {}).get("detailedState", "Unknown"),
                    lineup_state=lineup_state,
                    home_lineup=home_lineup,
                    away_lineup=away_lineup,
                    retrieved_at=retrieved_at,
                )
            )
    return output


def persist_discovery(session: Session, game: DiscoveredGame) -> LiveGameState:
    row = session.get(LiveGameState, game.game_pk) or LiveGameState(game_pk=game.game_pk)
    for key, value in asdict(game).items():
        if key == "retrieved_at":
            key = "source_retrieved_at"
        if key in {"home_lineup", "away_lineup"}:
            key += "_json"
            value = json.dumps(value)
        setattr(row, key, value)
    row.source = "MLB Stats API"
    session.add(row)
    return row


def timing_classification(now: datetime, start: datetime) -> tuple[float, str]:
    minutes = (start - now).total_seconds() / 60
    if minutes <= 0:
        label = "backfill_retrospective"
    elif 20 <= minutes <= 40:
        label = "primary_prospective"
    elif minutes > 40:
        label = "early_diagnostic"
    else:
        label = "late_prospective"
    return minutes, label


def get_launch_timestamp(session: Session) -> datetime | None:
    row = session.get(OperationalState, LAUNCH_KEY)
    return datetime.fromisoformat(row.value) if row else None


def establish_launch_timestamp(session: Session, now: datetime) -> datetime:
    existing = get_launch_timestamp(session)
    if existing is not None:
        return existing
    session.add(OperationalState(key=LAUNCH_KEY, value=now.isoformat(), created_at=now))
    session.flush()
    return now


def prediction_kind(now: datetime, start: datetime, launch: datetime | None) -> str:
    qualifies = launch is not None and now >= launch and start > launch and now < start
    return "prospective" if qualifies else "backfill"


def official_eligible(game: DiscoveredGame, now: datetime) -> bool:
    minutes, timing = timing_classification(now, game.scheduled_start_time_utc)
    return (
        game.lineup_state == "confirmed"
        and game.home_starter_id is not None
        and game.away_starter_id is not None
        and timing in {"primary_prospective", "late_prospective"}
        and minutes > 0
    )


def code_version() -> str:
    try:
        value = subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], check=True, capture_output=True, text=True
        ).stdout
        return value + ("+dirty" if dirty else "")
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def artifact_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_accepted_artifact(path: Path) -> None:
    observed = artifact_hash(path)
    if observed != ACCEPTED_ARTIFACT_SHA256:
        raise RuntimeError(
            f"accepted model checksum mismatch: expected {ACCEPTED_ARTIFACT_SHA256}, "
            f"observed {observed}; official prediction refused"
        )


def freeze_accepted_artifact(
    session: Session, output: Path, sprint7: Path, sprint8: Path
) -> dict[str, Any]:
    """Materialize accepted_v1 parameters once, without consulting any 2026 outcome."""
    from mlb_predictor.modeling.dataset import build_multiseason_modeling_dataset

    frame = build_multiseason_modeling_dataset(session, FEATURE_VERSION)
    if int(frame.season.max()) != 2025:
        raise ValueError(
            "Accepted artifact freeze requires exactly retrospective data through 2025"
        )
    spec = next(
        s
        for s in multiseason_model_specs(MULTISEASON_FEATURE_COLUMNS)
        if s.name == "gradient_boosting_stabilized"
    )
    model, fitted = _fit_predict(frame, frame, spec, MULTISEASON_FEATURE_COLUMNS)
    dispersion = estimate_dispersion(frame.runs_scored.to_numpy(), fitted)
    games = list(session.scalars(select(Game).where(Game.season.between(2021, 2025))))
    extras = [g for g in games if g.innings_played > g.scheduled_innings]
    extra_home = sum(g.home_team_runs > g.away_team_runs for g in extras) / len(extras)
    calibration = pd.read_csv(sprint8 / "calibrated_predictions.csv")
    calibration = calibration.loc[calibration.method == "platt"]
    calibrator = ProbabilityCalibrator("platt").fit(
        calibration.home_win_probability.to_numpy(), calibration.home_win.to_numpy()
    )
    payload = {
        "mean_model": model,
        "dispersion": dispersion,
        "extra_home_win": extra_home,
        "calibrator": calibrator,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(payload, output)
    metadata = {
        "model_version": MODEL_VERSION,
        "training_end_season": 2025,
        "rows": len(frame),
        "dispersion": dispersion,
        "extra_home_win": extra_home,
        "platt_intercept": float(calibrator.model.intercept_[0]),
        "platt_coefficient": float(calibrator.model.coef_[0, 0]),
        "artifact_sha256": artifact_hash(output),
        "sprint7_sha256": artifact_hash(sprint7 / "metadata.json"),
        "sprint8_sha256": artifact_hash(sprint8 / "metadata.json"),
    }
    output.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata


def _interval(pmf: np.ndarray, level: float) -> list[int]:
    cdf = np.cumsum(pmf)
    tail = (1 - level) / 2
    return [int(np.argmax(cdf >= tail)), int(np.argmax(cdf >= 1 - tail))]


def predict_from_features(
    away_features: dict[str, Any], home_features: dict[str, Any], artifact_path: Path
) -> dict[str, Any]:
    artifact = joblib.load(artifact_path)
    frame = pd.DataFrame([away_features, home_features], columns=MULTISEASON_FEATURE_COLUMNS)
    means = artifact["mean_model"].predict(stabilize_small_samples(frame))
    pmfs = negative_binomial_pmf(means, artifact["dispersion"])
    raw, tie = analytic_home_win(pmfs[1], pmfs[0], artifact["extra_home_win"])
    calibrated = float(artifact["calibrator"].predict(np.array([raw]))[0])
    scores = np.outer(pmfs[0], pmfs[1])
    top = np.argsort(scores.ravel())[::-1][:5]
    return {
        "expected_away_runs": float(means[0]),
        "expected_home_runs": float(means[1]),
        "dispersion": float(artifact["dispersion"]),
        "away_pmf": pmfs[0].tolist(),
        "home_pmf": pmfs[1].tolist(),
        "intervals": {
            side: {str(int(level * 100)): _interval(pmf, level) for level in (0.5, 0.8, 0.95)}
            for side, pmf in (("away", pmfs[0]), ("home", pmfs[1]))
        },
        "raw_home_win_probability": raw,
        "calibrated_home_win_probability": calibrated,
        "away_win_probability": 1 - calibrated,
        "regulation_tie_probability": tie,
        "extra_home_win_probability": float(artifact["extra_home_win"]),
        "most_likely_scores": [
            {"away": int(i // 13), "home": int(i % 13), "probability": float(scores.ravel()[i])}
            for i in top
        ],
    }


def save_prediction(
    session: Session,
    game: DiscoveredGame,
    result: dict[str, Any],
    now: datetime,
    *,
    official: bool,
    warnings: list[str],
    cutoff: datetime,
    launch: datetime | None,
    artifact_path: Path,
) -> LivePredictionRecord:
    if official:
        verify_accepted_artifact(artifact_path)
        existing = session.scalar(
            select(LivePredictionRecord).where(
                LivePredictionRecord.game_pk == game.game_pk,
                LivePredictionRecord.model_version == MODEL_VERSION,
                LivePredictionRecord.is_official.is_(True),
            )
        )
        if existing:
            return existing
    minutes, timing = timing_classification(now, game.scheduled_start_time_utc)
    row = LivePredictionRecord(
        game_pk=game.game_pk,
        prediction_timestamp=now,
        scheduled_start_time_utc=game.scheduled_start_time_utc,
        lineup_confirmation_state="prediction_generated" if official else game.lineup_state,
        home_starter_id=game.home_starter_id,
        away_starter_id=game.away_starter_id,
        feature_version=FEATURE_VERSION,
        model_version=MODEL_VERSION,
        expected_home_runs=result["expected_home_runs"],
        expected_away_runs=result["expected_away_runs"],
        distribution_name="negative_binomial",
        distribution_parameters_json=json.dumps({"dispersion": result["dispersion"]}),
        raw_home_win_probability=result["raw_home_win_probability"],
        calibrated_home_win_probability=result["calibrated_home_win_probability"],
        prediction_intervals_json=json.dumps(result["intervals"]),
        extra_inning_adjustment=result["extra_home_win_probability"],
        data_quality_warnings_json=json.dumps(warnings),
        minutes_before_first_pitch=minutes,
        timing_classification=timing,
        prediction_kind=prediction_kind(now, game.scheduled_start_time_utc, launch),
        is_official=True if official else None,
        source_retrieved_at=game.retrieved_at,
        feature_cutoff_timestamp=cutoff,
        calibration_version=CALIBRATION_VERSION,
        distribution_version=DISTRIBUTION_VERSION,
        code_version=code_version(),
        run_probabilities_json=json.dumps({"away": result["away_pmf"], "home": result["home_pmf"]}),
        most_likely_scores_json=json.dumps(result["most_likely_scores"]),
        away_win_probability=result["away_win_probability"],
        regulation_tie_probability=result["regulation_tie_probability"],
    )
    session.add(row)
    session.flush()
    return row


def settle_prediction(
    row: LivePredictionRecord,
    home_runs: int,
    away_runs: int,
    status: str,
    now: datetime,
    actual_start: datetime | None = None,
) -> None:
    row.observed_home_runs, row.observed_away_runs = home_runs, away_runs
    row.observed_home_win = home_runs > away_runs
    row.observed_at = row.settlement_timestamp = now
    row.completion_status = status
    row.actual_start_time_utc = actual_start
    row.minutes_before_actual_start = (
        (actual_start - row.prediction_timestamp).total_seconds() / 60 if actual_start else None
    )


def prospective_rows(session: Session) -> list[LivePredictionRecord]:
    return list(
        session.scalars(
            select(LivePredictionRecord).where(
                LivePredictionRecord.is_official.is_(True),
                LivePredictionRecord.prediction_kind == "prospective",
            )
        )
    )


def evaluate_prospective_ledger(session: Session) -> dict[str, Any]:
    rows = prospective_rows(session)
    if not rows:
        return {
            "total_eligible_predictions": 0,
            "primary_prospective_count": 0,
            "late_prospective_count": 0,
            "settled_count": 0,
            "unsettled_count": 0,
            "status": "awaiting_genuine_live_predictions",
        }
    settled = [row for row in rows if row.observed_at is not None]
    summary: dict[str, Any] = {
        "total_eligible_predictions": len(rows),
        "primary_prospective_count": sum(
            r.timing_classification == "primary_prospective" for r in rows
        ),
        "late_prospective_count": sum(r.timing_classification == "late_prospective" for r in rows),
        "settled_count": len(settled),
        "unsettled_count": len(rows) - len(settled),
    }
    if not settled:
        return summary
    rows = settled
    actual = np.array([[r.observed_away_runs, r.observed_home_runs] for r in rows], dtype=int)
    means = np.array([[r.expected_away_runs, r.expected_home_runs] for r in rows])
    probability = np.array([r.calibrated_home_win_probability for r in rows])
    wins = np.array([r.observed_home_win for r in rows], dtype=int)
    error = means - actual
    result: dict[str, Any] = {
        **summary,
        "mae": float(np.abs(error).mean()),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "poisson_deviance": float(mean_poisson_deviance(actual.ravel(), means.ravel())),
        "brier_score": float(brier_score_loss(wins, probability)),
        "log_loss": float(log_loss(wins, probability, labels=[0, 1])),
    }
    nll: list[float] = []
    rps: list[float] = []
    covered: dict[int, list[bool]] = {50: [], 80: [], 95: []}
    for row, scores in zip(rows, actual, strict=True):
        pmfs = json.loads(row.run_probabilities_json)
        intervals = json.loads(row.prediction_intervals_json)
        for side, observed in zip(("away", "home"), scores, strict=True):
            pmf = np.asarray(pmfs[side])
            bucket = min(int(observed), len(pmf) - 1)
            nll.append(float(-np.log(max(pmf[bucket], 1e-12))))
            observed_cdf = np.arange(len(pmf)) >= bucket
            rps.append(float(np.sum((np.cumsum(pmf) - observed_cdf) ** 2)))
            for level in covered:
                low, high = intervals[side][str(level)]
                covered[level].append(low <= observed <= high)
    result.update(
        {
            "nb_nll": float(np.mean(nll)),
            "rps": float(np.mean(rps)),
            "interval_coverage": {str(k): float(np.mean(v)) for k, v in covered.items()},
            "calibration_buckets": calibration_buckets(rows),
        }
    )
    result["by_timing_class"] = {
        timing: evaluate_settled_subset([r for r in rows if r.timing_classification == timing])
        for timing in ("primary_prospective", "late_prospective")
    }
    return result


def calibration_buckets(rows: list[LivePredictionRecord]) -> list[dict[str, Any]]:
    output = []
    for low in np.arange(0, 1, 0.1):
        selected = [r for r in rows if low <= r.calibrated_home_win_probability < low + 0.1]
        if selected:
            output.append(
                {
                    "range": f"{low:.1f}-{low + 0.1:.1f}",
                    "count": len(selected),
                    "predicted": float(
                        np.mean([r.calibrated_home_win_probability for r in selected])
                    ),
                    "observed": float(np.mean([r.observed_home_win for r in selected])),
                }
            )
    return output


def evaluate_settled_subset(rows: list[LivePredictionRecord]) -> dict[str, Any]:
    if not rows:
        return {"settled_count": 0}
    actual = np.array([[r.observed_away_runs, r.observed_home_runs] for r in rows], dtype=int)
    means = np.array([[r.expected_away_runs, r.expected_home_runs] for r in rows])
    probability = np.array([r.calibrated_home_win_probability for r in rows])
    wins = np.array([r.observed_home_win for r in rows], dtype=int)
    return {
        "settled_count": len(rows),
        "mae": float(np.abs(means - actual).mean()),
        "rmse": float(np.sqrt(np.mean((means - actual) ** 2))),
        "brier_score": float(brier_score_loss(wins, probability)),
        "log_loss": float(log_loss(wins, probability, labels=[0, 1])),
    }
