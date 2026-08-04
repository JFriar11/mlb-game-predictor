import logging
from datetime import UTC, datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

from mlb_predictor.db.models import (
    Game,
    GameStartingLineup,
    GameStartingPitcher,
    Player,
    Team,
    Venue,
)
from mlb_predictor.ingestion.client import MlbStatsClient
from mlb_predictor.ingestion.parser import SOURCE, ParsedGame, parse_game_feed

LOGGER = logging.getLogger(__name__)


def ingest_game(session: Session, client: MlbStatsClient, game_pk: int) -> ParsedGame:
    """Fetch and atomically replace one game's normalized representation."""
    retrieved_at = datetime.now(UTC)
    parsed = parse_game_feed(client.get_game_feed(game_pk), game_pk)
    for team_data in parsed.teams:
        session.merge(
            Team(
                team_id=int(team_data["id"]),
                name=str(team_data["name"]),
                abbreviation=team_data.get("abbreviation"),
                source=SOURCE,
                retrieved_at=retrieved_at,
            )
        )
    session.merge(
        Venue(
            venue_id=parsed.venue_id,
            name=parsed.venue_name,
            source=SOURCE,
            retrieved_at=retrieved_at,
        )
    )
    for player in parsed.players:
        session.merge(
            Player(
                player_id=player.player_id,
                full_name=player.full_name,
                bat_side=player.bat_side,
                throws=player.throws,
                source=SOURCE,
                retrieved_at=retrieved_at,
            )
        )
    session.flush()
    session.merge(
        Game(
            game_pk=parsed.game_pk,
            game_date=parsed.game_date,
            scheduled_start_time_utc=parsed.scheduled_start_time_utc,
            actual_start_time_utc=parsed.actual_start_time_utc,
            season=parsed.season,
            game_type=parsed.game_type,
            status=parsed.status,
            home_team_id=parsed.home_team_id,
            away_team_id=parsed.away_team_id,
            venue_id=parsed.venue_id,
            home_team_runs=parsed.home_team_runs,
            away_team_runs=parsed.away_team_runs,
            innings_played=parsed.innings_played,
            doubleheader_code=parsed.doubleheader_code,
            game_number=parsed.game_number,
            source=SOURCE,
            retrieved_at=retrieved_at,
        )
    )
    session.flush()
    session.execute(delete(GameStartingLineup).where(GameStartingLineup.game_pk == game_pk))
    session.execute(delete(GameStartingPitcher).where(GameStartingPitcher.game_pk == game_pk))
    session.add_all(
        GameStartingPitcher(
            game_pk=game_pk,
            team_id=item.team_id,
            pitcher_id=item.pitcher_id,
            throws=item.throws,
            is_home=item.is_home,
            source=SOURCE,
            retrieved_at=retrieved_at,
        )
        for item in parsed.starters
    )
    session.add_all(
        GameStartingLineup(
            game_pk=game_pk,
            team_id=item.team_id,
            player_id=item.player_id,
            batting_order=item.batting_order,
            defensive_position=item.defensive_position,
            bat_side=item.bat_side,
            is_home=item.is_home,
            source=SOURCE,
            retrieved_at=retrieved_at,
        )
        for item in parsed.lineups
    )
    session.flush()
    LOGGER.info("ingested game", extra={"game_pk": game_pk})
    return parsed
