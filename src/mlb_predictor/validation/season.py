from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from mlb_predictor.db.models import (
    Game,
    GameStartingLineup,
    GameStartingPitcher,
    Player,
    PlayerGameBatting,
    PlayerGamePitching,
    Team,
    Venue,
)


@dataclass(frozen=True)
class SeasonAudit:
    season: int
    games: int
    first_game_date: date | None
    last_game_date: date | None
    teams: int
    venues: int
    players: int
    starters: int
    lineup_entries: int
    batting_rows: int
    pitching_rows: int
    games_with_batting: int
    games_with_pitching: int
    min_games_per_team: int
    max_games_per_team: int
    batting_run_discrepancies: int
    pitching_run_discrepancies: int
    incomplete_starter_games: tuple[int, ...]
    incomplete_lineup_sides: tuple[dict[str, Any], ...]

    @property
    def passed(self) -> bool:
        return (
            self.games == 2430
            and self.teams == 30
            and self.starters == self.games * 2
            and self.lineup_entries == self.games * 18
            and not self.incomplete_starter_games
            and not self.incomplete_lineup_sides
            and self.games_with_batting == self.games
            and self.games_with_pitching == self.games
            and self.min_games_per_team == 162
            and self.max_games_per_team == 162
            and self.batting_run_discrepancies == 0
            and self.pitching_run_discrepancies == 0
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["passed"] = self.passed
        return payload


def audit_season(session: Session, season: int = 2025) -> SeasonAudit:
    game_filter = Game.season == season
    games, first_date, last_date = session.execute(
        select(func.count(), func.min(Game.game_date), func.max(Game.game_date)).where(game_filter)
    ).one()
    game_ids = select(Game.game_pk).where(game_filter)
    incomplete_starters = tuple(
        int(row.game_pk)
        for row in session.execute(
            select(Game.game_pk, func.count(GameStartingPitcher.id).label("count"))
            .outerjoin(GameStartingPitcher, Game.game_pk == GameStartingPitcher.game_pk)
            .where(game_filter)
            .group_by(Game.game_pk)
            .having(func.count(GameStartingPitcher.id) != 2)
            .order_by(Game.game_pk)
        )
    )
    incomplete_lineups = tuple(
        {
            "game_pk": int(row.game_pk),
            "is_home": bool(row.is_home),
            "entries": int(row.count),
        }
        for row in session.execute(
            select(
                GameStartingLineup.game_pk,
                GameStartingLineup.is_home,
                func.count(GameStartingLineup.id).label("count"),
            )
            .where(GameStartingLineup.game_pk.in_(game_ids))
            .group_by(GameStartingLineup.game_pk, GameStartingLineup.is_home)
            .having(func.count(GameStartingLineup.id) != 9)
            .order_by(GameStartingLineup.game_pk, GameStartingLineup.is_home)
        )
    )
    season_games = list(
        session.execute(
            select(
                Game.game_pk,
                Game.home_team_id,
                Game.away_team_id,
                Game.home_team_runs,
                Game.away_team_runs,
            ).where(game_filter)
        )
    )
    team_games: Counter[int] = Counter()
    for game in season_games:
        team_games[game.home_team_id] += 1
        team_games[game.away_team_id] += 1
    batting_runs = {
        (int(row.game_pk), bool(row.is_home)): int(row.runs)
        for row in session.execute(
            select(
                PlayerGameBatting.game_pk,
                PlayerGameBatting.is_home,
                func.sum(PlayerGameBatting.runs).label("runs"),
            )
            .where(PlayerGameBatting.game_pk.in_(game_ids))
            .group_by(PlayerGameBatting.game_pk, PlayerGameBatting.is_home)
        )
    }
    pitching_runs = {
        (int(row.game_pk), bool(row.is_home)): int(row.runs)
        for row in session.execute(
            select(
                PlayerGamePitching.game_pk,
                PlayerGamePitching.is_home,
                func.sum(PlayerGamePitching.runs_allowed).label("runs"),
            )
            .where(PlayerGamePitching.game_pk.in_(game_ids))
            .group_by(PlayerGamePitching.game_pk, PlayerGamePitching.is_home)
        )
    }
    batting_discrepancies = sum(
        batting_runs.get((game.game_pk, True)) != game.home_team_runs
        or batting_runs.get((game.game_pk, False)) != game.away_team_runs
        for game in season_games
    )
    pitching_discrepancies = sum(
        pitching_runs.get((game.game_pk, True)) != game.away_team_runs
        or pitching_runs.get((game.game_pk, False)) != game.home_team_runs
        for game in season_games
    )
    return SeasonAudit(
        season=season,
        games=int(games),
        first_game_date=first_date,
        last_game_date=last_date,
        teams=int(session.scalar(select(func.count()).select_from(Team)) or 0),
        venues=int(session.scalar(select(func.count()).select_from(Venue)) or 0),
        players=int(session.scalar(select(func.count()).select_from(Player)) or 0),
        starters=int(
            session.scalar(
                select(func.count())
                .select_from(GameStartingPitcher)
                .where(GameStartingPitcher.game_pk.in_(game_ids))
            )
            or 0
        ),
        lineup_entries=int(
            session.scalar(
                select(func.count())
                .select_from(GameStartingLineup)
                .where(GameStartingLineup.game_pk.in_(game_ids))
            )
            or 0
        ),
        batting_rows=int(
            session.scalar(
                select(func.count())
                .select_from(PlayerGameBatting)
                .where(PlayerGameBatting.game_pk.in_(game_ids))
            )
            or 0
        ),
        pitching_rows=int(
            session.scalar(
                select(func.count())
                .select_from(PlayerGamePitching)
                .where(PlayerGamePitching.game_pk.in_(game_ids))
            )
            or 0
        ),
        games_with_batting=int(
            session.scalar(
                select(func.count(distinct(PlayerGameBatting.game_pk))).where(
                    PlayerGameBatting.game_pk.in_(game_ids)
                )
            )
            or 0
        ),
        games_with_pitching=int(
            session.scalar(
                select(func.count(distinct(PlayerGamePitching.game_pk))).where(
                    PlayerGamePitching.game_pk.in_(game_ids)
                )
            )
            or 0
        ),
        min_games_per_team=min(team_games.values(), default=0),
        max_games_per_team=max(team_games.values(), default=0),
        batting_run_discrepancies=batting_discrepancies,
        pitching_run_discrepancies=pitching_discrepancies,
        incomplete_starter_games=incomplete_starters,
        incomplete_lineup_sides=incomplete_lineups,
    )
