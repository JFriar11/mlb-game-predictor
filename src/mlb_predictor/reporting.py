from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from mlb_predictor.db.models import (
    Game,
    GameStartingLineup,
    GameStartingPitcher,
    Player,
    Team,
    Venue,
)


def reconstruct_game(session: Session, game_pk: int) -> str:
    home = aliased(Team)
    away = aliased(Team)
    row = session.execute(
        select(Game, home, away, Venue)
        .join(home, Game.home_team_id == home.team_id)
        .join(away, Game.away_team_id == away.team_id)
        .join(Venue, Game.venue_id == Venue.venue_id)
        .where(Game.game_pk == game_pk)
    ).one_or_none()
    if row is None:
        raise LookupError(f"Game {game_pk} is not stored")
    game, home_team, away_team, venue = row
    lines = [
        f"{game.game_date}: {away_team.name} {game.away_team_runs} at "
        f"{home_team.name} {game.home_team_runs}",
        f"Venue: {venue.name} | Innings: {game.innings_played} | MLB game_pk: {game.game_pk}",
    ]
    for is_home, team in ((False, away_team), (True, home_team)):
        starter = session.execute(
            select(Player)
            .join(GameStartingPitcher, GameStartingPitcher.pitcher_id == Player.player_id)
            .where(GameStartingPitcher.game_pk == game_pk, GameStartingPitcher.is_home == is_home)
        ).scalar_one()
        lineup = session.execute(
            select(GameStartingLineup, Player)
            .join(Player, GameStartingLineup.player_id == Player.player_id)
            .where(GameStartingLineup.game_pk == game_pk, GameStartingLineup.is_home == is_home)
            .order_by(GameStartingLineup.batting_order)
        ).all()
        lines.append(f"{team.name} starter: {starter.full_name}")
        lines.append(
            "  Lineup: "
            + "; ".join(
                f"{entry.batting_order}. {player.full_name} ({entry.defensive_position or '?'})"
                for entry, player in lineup
            )
        )
    return "\n".join(lines)
