from dataclasses import asdict, dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mlb_predictor.db.models import Game, PitchingFeatureSnapshot


@dataclass(frozen=True)
class PitchingAudit:
    rows: int
    games: int
    invalid_source_dates: int
    invalid_starter_values: int
    invalid_bullpen_values: int
    passed: bool

    def to_dict(self) -> dict[str, int | bool]:
        return asdict(self)


def audit_pitching_features(session: Session) -> PitchingAudit:
    rows = list(
        session.scalars(
            select(PitchingFeatureSnapshot).where(
                PitchingFeatureSnapshot.feature_version == "sprint5_v1"
            )
        )
    )
    dates = dict(session.execute(select(Game.game_pk, Game.game_date)).all())
    invalid_source = sum(
        row.max_source_game_date is not None and row.max_source_game_date >= dates[row.game_pk]
        for row in rows
    )
    invalid_starter = sum(
        not (0 <= row.starter_avg_outs <= 27)
        or not (0 <= row.starter_avg_pitches <= 150)
        or not (0 <= row.starter_pitches_per_out <= 20)
        for row in rows
    )
    invalid_bullpen = sum(
        row.available_bullpen_era < 0
        or not (0 <= row.available_bullpen_strikeout_rate <= 1)
        or not (0 <= row.available_bullpen_walk_rate <= 1)
        for row in rows
    )
    games = int(
        session.scalar(
            select(func.count(func.distinct(PitchingFeatureSnapshot.game_pk))).where(
                PitchingFeatureSnapshot.feature_version == "sprint5_v1"
            )
        )
        or 0
    )
    passed = (
        len(rows) == 24296
        and games == 12148
        and invalid_source == 0
        and invalid_starter == 0
        and invalid_bullpen == 0
    )
    return PitchingAudit(len(rows), games, invalid_source, invalid_starter, invalid_bullpen, passed)
