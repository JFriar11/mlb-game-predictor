import logging
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import delete
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
from mlb_predictor.ingestion.parser import SOURCE, ParsedGame, parse_game_feed

LOGGER = logging.getLogger(__name__)


class GameFeedClient(Protocol):
    def get_game_feed(self, game_pk: int) -> dict[str, Any]: ...


def ingest_game(
    session: Session,
    client: GameFeedClient,
    game_pk: int,
    *,
    payload: dict[str, Any] | None = None,
    strict_lineups: bool = True,
) -> ParsedGame:
    """Fetch and atomically replace one game's normalized representation."""
    retrieved_at = datetime.now(UTC)
    parsed = parse_game_feed(
        payload if payload is not None else client.get_game_feed(game_pk),
        game_pk,
        strict_lineups=strict_lineups,
    )
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
    session.execute(delete(PlayerGameBatting).where(PlayerGameBatting.game_pk == game_pk))
    session.execute(delete(PlayerGamePitching).where(PlayerGamePitching.game_pk == game_pk))
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
    session.add_all(
        PlayerGameBatting(
            game_pk=game_pk,
            team_id=item.team_id,
            player_id=item.player_id,
            is_home=item.is_home,
            plate_appearances=item.plate_appearances,
            at_bats=item.at_bats,
            runs=item.runs,
            hits=item.hits,
            doubles=item.doubles,
            triples=item.triples,
            home_runs=item.home_runs,
            rbi=item.rbi,
            base_on_balls=item.base_on_balls,
            strike_outs=item.strike_outs,
            stolen_bases=item.stolen_bases,
            source=SOURCE,
            retrieved_at=retrieved_at,
        )
        for item in parsed.batting
    )
    session.add_all(
        PlayerGamePitching(
            game_pk=game_pk,
            team_id=item.team_id,
            player_id=item.player_id,
            is_home=item.is_home,
            is_starter=item.is_starter,
            outs_recorded=item.outs_recorded,
            batters_faced=item.batters_faced,
            pitches_thrown=item.pitches_thrown,
            strikes=item.strikes,
            hits_allowed=item.hits_allowed,
            runs_allowed=item.runs_allowed,
            earned_runs=item.earned_runs,
            base_on_balls=item.base_on_balls,
            strike_outs=item.strike_outs,
            home_runs_allowed=item.home_runs_allowed,
            source=SOURCE,
            retrieved_at=retrieved_at,
        )
        for item in parsed.pitching
    )
    session.flush()
    LOGGER.info("ingested game", extra={"game_pk": game_pk})
    return parsed
