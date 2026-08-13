from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from mlb_predictor.db.models import EnvironmentFeatureSnapshot, Game


@dataclass(frozen=True)
class EnvironmentAudit:
    rows: int
    games: int
    invalid_source_dates: int
    invalid_values: int
    weather_proxy_rows: int
    passed: bool

    def to_dict(self) -> dict[str, int | bool]:
        return asdict(self)


def audit_environment_features(session: Session) -> EnvironmentAudit:
    rows = list(
        session.scalars(
            select(EnvironmentFeatureSnapshot).where(
                EnvironmentFeatureSnapshot.feature_version == "sprint6_v1"
            )
        )
    )
    dates = dict(session.execute(select(Game.game_pk, Game.game_date)).all())
    invalid_source = sum(
        row.max_source_game_date is not None and row.max_source_game_date >= dates[row.game_pk]
        for row in rows
    )
    invalid = sum(
        not (0.7 <= row.park_factor <= 1.3)
        or not (-50 <= row.temperature_f <= 140)
        or not (0 <= row.wind_speed_mph <= 100)
        or not (-100 <= row.wind_out_component <= 100)
        or not (-100 <= row.wind_cross_component <= 100)
        for row in rows
    )
    games = len({row.game_pk for row in rows})
    proxy_rows = sum(row.weather_observed_proxy for row in rows)
    return EnvironmentAudit(
        len(rows),
        games,
        invalid_source,
        invalid,
        proxy_rows,
        len(rows) == 12148 and games == 12148 and invalid_source == 0 and invalid == 0,
    )
