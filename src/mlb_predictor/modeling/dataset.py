from typing import Final

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from mlb_predictor.db.models import Game, PregameFeatureSnapshot

FEATURE_VERSION: Final = "sprint2_v1"
MULTISEASON_FEATURE_VERSION: Final = "sprint3_5_v1"

FEATURE_COLUMNS: Final[list[str]] = [
    "is_home",
    "venue_id",
    "team_prior_games",
    "team_runs_avg_10",
    "team_runs_allowed_avg_10",
    "team_runs_avg_season",
    "lineup_prior_pa",
    "lineup_on_base_rate",
    "lineup_strikeout_rate",
    "lineup_home_run_rate",
    "starter_prior_starts",
    "starter_era",
    "starter_strikeout_rate",
    "starter_walk_rate",
    "starter_outs_per_start",
    "bullpen_prior_outs",
    "bullpen_era_30d",
    "bullpen_strikeout_rate_30d",
    "bullpen_walk_rate_30d",
    "bullpen_recent_outs",
    "days_rest",
    "fallback_count",
]

MULTISEASON_FEATURE_COLUMNS: Final[list[str]] = [
    *FEATURE_COLUMNS,
    "season",
    "universal_dh",
    "scheduled_innings",
    "history_decay",
    "prior_season_team_games",
    "prior_season_lineup_pa",
    "prior_season_starter_starts",
    "prior_season_bullpen_outs",
]


def build_modeling_dataset(
    session: Session, feature_version: str = FEATURE_VERSION
) -> pd.DataFrame:
    """Return the immutable stacked team-game dataset joined to its postgame target."""
    if feature_version != FEATURE_VERSION:
        raise ValueError(f"Sprint 3 requires immutable feature version {FEATURE_VERSION}")
    rows = session.execute(
        select(PregameFeatureSnapshot, Game)
        .join(Game, PregameFeatureSnapshot.game_pk == Game.game_pk)
        .where(PregameFeatureSnapshot.feature_version == feature_version)
        .order_by(
            Game.game_date,
            Game.scheduled_start_time_utc,
            Game.game_pk,
            PregameFeatureSnapshot.is_home,
        )
    ).all()
    records = []
    for snapshot, game in rows:
        record = {
            "game_pk": snapshot.game_pk,
            "game_date": game.game_date,
            "scheduled_start_time_utc": game.scheduled_start_time_utc,
            "offense_team_id": snapshot.offense_team_id,
            "opponent_team_id": snapshot.opponent_team_id,
            "feature_version": snapshot.feature_version,
            "runs_scored": game.home_team_runs if snapshot.is_home else game.away_team_runs,
        }
        record.update({column: getattr(snapshot, column) for column in FEATURE_COLUMNS})
        records.append(record)
    frame = pd.DataFrame.from_records(records)
    if len(frame) != 4860 or frame["game_pk"].nunique() != 2430:
        raise ValueError(
            f"Expected 4,860 rows across 2,430 games, got {len(frame)} rows and "
            f"{frame['game_pk'].nunique()} games"
        )
    return frame


def build_multiseason_modeling_dataset(
    session: Session, feature_version: str = MULTISEASON_FEATURE_VERSION
) -> pd.DataFrame:
    """Build a stacked 2021-2025 dataset for an explicit Sprint 3.5 feature version."""
    if not feature_version.startswith("sprint3_5_"):
        raise ValueError("Sprint 3.5 requires an explicit sprint3_5 feature version")
    rows = session.execute(
        select(PregameFeatureSnapshot, Game)
        .join(Game, PregameFeatureSnapshot.game_pk == Game.game_pk)
        .where(PregameFeatureSnapshot.feature_version == feature_version)
        .order_by(Game.game_date, Game.game_pk, PregameFeatureSnapshot.is_home)
    ).all()
    records = []
    for snapshot, game in rows:
        record = {
            "game_pk": snapshot.game_pk,
            "game_date": game.game_date,
            "scheduled_start_time_utc": game.scheduled_start_time_utc,
            "offense_team_id": snapshot.offense_team_id,
            "opponent_team_id": snapshot.opponent_team_id,
            "feature_version": snapshot.feature_version,
            "runs_scored": game.home_team_runs if snapshot.is_home else game.away_team_runs,
            "season": game.season,
            "universal_dh": game.season >= 2022,
            "scheduled_innings": game.scheduled_innings,
        }
        for column in FEATURE_COLUMNS:
            record[column] = getattr(snapshot, column)
        for column in MULTISEASON_FEATURE_COLUMNS:
            if column not in record:
                record[column] = getattr(snapshot, column)
        records.append(record)
    frame = pd.DataFrame.from_records(records)
    expected_games = 12148
    if len(frame) != expected_games * 2 or frame["game_pk"].nunique() != expected_games:
        raise ValueError(
            f"Expected {expected_games * 2} rows across {expected_games} games, got "
            f"{len(frame)} rows and {frame['game_pk'].nunique()} games"
        )
    return frame


def model_features(
    frame: pd.DataFrame, feature_columns: list[str] = FEATURE_COLUMNS
) -> pd.DataFrame:
    """Select model inputs, structurally excluding targets and row identifiers."""
    return frame.loc[:, feature_columns].copy()
