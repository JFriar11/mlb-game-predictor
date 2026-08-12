import math
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mlb_predictor.db.models import (
    PlayerGameHandedBatting,
    PlayerGamePitchGroup,
    PregameFeatureSnapshot,
)


@dataclass(frozen=True)
class MatchupAudit:
    aggregate_games: int
    handed_batting_rows: int
    pitch_group_rows: int
    feature_rows: int
    feature_games: int
    null_feature_rows: tuple[int, ...]
    invalid_rate_rows: tuple[int, ...]
    invalid_pitch_mix_rows: tuple[int, ...]

    @property
    def passed(self) -> bool:
        return (
            self.aggregate_games == 12148
            and self.feature_rows == 24296
            and self.feature_games == 12148
            and not self.null_feature_rows
            and not self.invalid_rate_rows
            and not self.invalid_pitch_mix_rows
        )

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "passed": self.passed}


def audit_matchups(session: Session) -> MatchupAudit:
    rows = list(
        session.scalars(
            select(PregameFeatureSnapshot).where(
                PregameFeatureSnapshot.feature_version == "sprint4_v1"
            )
        )
    )
    fields = (
        "lineup_weighted_on_base_rate",
        "lineup_weighted_strikeout_rate",
        "lineup_weighted_home_run_rate",
        "lineup_projected_plate_appearances",
        "lineup_vs_starter_hand_on_base_rate",
        "lineup_vs_starter_hand_strikeout_rate",
        "lineup_vs_starter_hand_home_run_rate",
        "starter_fastball_rate",
        "starter_breaking_rate",
        "starter_offspeed_rate",
        "starter_other_pitch_rate",
        "lineup_pitch_mix_whiff_rate",
        "lineup_pitch_mix_hit_in_play_rate",
    )
    nulls = tuple(row.id for row in rows if any(getattr(row, field) is None for field in fields))
    rate_fields = tuple(field for field in fields if field != "lineup_projected_plate_appearances")
    invalid_rates = tuple(
        row.id
        for row in rows
        if any(
            not math.isfinite(value := float(getattr(row, field))) or not 0 <= value <= 1
            for field in rate_fields
        )
        or not 20 <= float(row.lineup_projected_plate_appearances or 0) <= 60
    )
    invalid_mix = tuple(
        row.id
        for row in rows
        if not math.isclose(
            sum(
                float(value or 0)
                for value in (
                    row.starter_fastball_rate,
                    row.starter_breaking_rate,
                    row.starter_offspeed_rate,
                    row.starter_other_pitch_rate,
                )
            ),
            1.0,
            abs_tol=1e-9,
        )
    )
    aggregate_games = int(
        session.scalar(select(func.count(func.distinct(PlayerGameHandedBatting.game_pk)))) or 0
    )
    return MatchupAudit(
        aggregate_games=aggregate_games,
        handed_batting_rows=int(
            session.scalar(select(func.count()).select_from(PlayerGameHandedBatting)) or 0
        ),
        pitch_group_rows=int(
            session.scalar(select(func.count()).select_from(PlayerGamePitchGroup)) or 0
        ),
        feature_rows=len(rows),
        feature_games=len({row.game_pk for row in rows}),
        null_feature_rows=nulls,
        invalid_rate_rows=invalid_rates,
        invalid_pitch_mix_rows=invalid_mix,
    )
