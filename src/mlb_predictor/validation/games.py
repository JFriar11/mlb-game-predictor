from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mlb_predictor.db.models import Game, GameStartingLineup, GameStartingPitcher


@dataclass(frozen=True)
class ValidationResult:
    game_count: int
    failures: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.failures


def validate_games(session: Session, expected_games: int = 5) -> ValidationResult:
    """Validate database-level and cross-row Sprint 0 acceptance rules."""
    games = list(session.scalars(select(Game).order_by(Game.game_pk)))
    failures: list[str] = []
    if len(games) != expected_games:
        failures.append(f"expected {expected_games} unique games, found {len(games)}")
    if len({game.game_pk for game in games}) != len(games):
        failures.append("duplicate game_pk values")
    for game in games:
        if game.home_team_id == game.away_team_id:
            failures.append(f"game {game.game_pk}: home and away team are identical")
        if game.home_team_runs < 0 or game.away_team_runs < 0:
            failures.append(f"game {game.game_pk}: negative score")
        starter_counts = dict(
            session.execute(
                select(GameStartingPitcher.is_home, func.count())
                .where(GameStartingPitcher.game_pk == game.game_pk)
                .group_by(GameStartingPitcher.is_home)
            ).all()
        )
        if starter_counts != {False: 1, True: 1}:
            failures.append(f"game {game.game_pk}: starter counts {starter_counts}")
        for is_home in (False, True):
            slots = list(
                session.scalars(
                    select(GameStartingLineup.batting_order)
                    .where(
                        GameStartingLineup.game_pk == game.game_pk,
                        GameStartingLineup.is_home == is_home,
                    )
                    .order_by(GameStartingLineup.batting_order)
                )
            )
            if slots != list(range(1, 10)):
                side = "home" if is_home else "away"
                failures.append(f"game {game.game_pk}: {side} batting slots {slots}")
    return ValidationResult(len(games), tuple(failures))
