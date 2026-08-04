import math
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mlb_predictor.db.models import Game, PregameFeatureSnapshot


@dataclass(frozen=True)
class FeatureAudit:
    feature_version: str
    rows: int
    games: int
    games_without_two_rows: tuple[int, ...]
    as_of_violations: tuple[int, ...]
    source_date_violations: tuple[int, ...]
    nonfinite_rows: tuple[int, ...]
    opening_day_fallback_rows: int
    rows_with_no_fallbacks: int
    min_team_prior_games: int
    max_team_prior_games: int
    expected_rows: int

    @property
    def passed(self) -> bool:
        return (
            self.rows == self.expected_rows
            and not self.games_without_two_rows
            and not self.as_of_violations
            and not self.source_date_violations
            and not self.nonfinite_rows
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["passed"] = self.passed
        return payload


def audit_features(session: Session, feature_version: str = "sprint2_v1") -> FeatureAudit:
    snapshots = list(
        session.scalars(
            select(PregameFeatureSnapshot).where(
                PregameFeatureSnapshot.feature_version == feature_version
            )
        )
    )
    bad_counts = tuple(
        int(row.game_pk)
        for row in session.execute(
            select(PregameFeatureSnapshot.game_pk, func.count().label("count"))
            .where(PregameFeatureSnapshot.feature_version == feature_version)
            .group_by(PregameFeatureSnapshot.game_pk)
            .having(func.count() != 2)
            .order_by(PregameFeatureSnapshot.game_pk)
        )
    )
    game_map = {
        game.game_pk: game
        for game in session.scalars(
            select(Game).where(Game.game_pk.in_([snapshot.game_pk for snapshot in snapshots]))
        )
    }
    as_of_violations = tuple(
        snapshot.id
        for snapshot in snapshots
        if snapshot.as_of >= game_map[snapshot.game_pk].scheduled_start_time_utc
    )
    source_violations = tuple(
        snapshot.id
        for snapshot in snapshots
        if snapshot.max_source_game_date is not None
        and snapshot.max_source_game_date >= game_map[snapshot.game_pk].game_date
    )
    numeric_fields = (
        "team_runs_avg_10",
        "team_runs_allowed_avg_10",
        "team_runs_avg_season",
        "lineup_on_base_rate",
        "lineup_strikeout_rate",
        "lineup_home_run_rate",
        "starter_era",
        "starter_strikeout_rate",
        "starter_walk_rate",
        "starter_outs_per_start",
        "bullpen_era_30d",
        "bullpen_strikeout_rate_30d",
        "bullpen_walk_rate_30d",
    )
    nonfinite = tuple(
        snapshot.id
        for snapshot in snapshots
        if any(not math.isfinite(getattr(snapshot, field)) for field in numeric_fields)
    )
    prior_games = [snapshot.team_prior_games for snapshot in snapshots]
    expected_rows = len(game_map) * 2
    return FeatureAudit(
        feature_version=feature_version,
        rows=len(snapshots),
        games=len({snapshot.game_pk for snapshot in snapshots}),
        games_without_two_rows=bad_counts,
        as_of_violations=as_of_violations,
        source_date_violations=source_violations,
        nonfinite_rows=nonfinite,
        opening_day_fallback_rows=sum(snapshot.team_prior_games == 0 for snapshot in snapshots),
        rows_with_no_fallbacks=sum(snapshot.fallback_count == 0 for snapshot in snapshots),
        min_team_prior_games=min(prior_games, default=0),
        max_team_prior_games=max(prior_games, default=0),
        expected_rows=expected_rows,
    )
