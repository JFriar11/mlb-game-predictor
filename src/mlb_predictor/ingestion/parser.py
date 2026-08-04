from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

SOURCE = "MLB_STATS_API"


class FeedValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedPlayer:
    player_id: int
    full_name: str
    bat_side: str | None
    throws: str | None


@dataclass(frozen=True)
class ParsedLineupEntry:
    team_id: int
    player_id: int
    batting_order: int
    defensive_position: str | None
    bat_side: str | None
    is_home: bool


@dataclass(frozen=True)
class ParsedStarter:
    team_id: int
    pitcher_id: int
    throws: str | None
    is_home: bool


@dataclass(frozen=True)
class ParsedGame:
    game_pk: int
    game_date: date
    scheduled_start_time_utc: datetime
    actual_start_time_utc: datetime | None
    season: int
    game_type: str
    status: str
    home_team_id: int
    away_team_id: int
    venue_id: int
    home_team_runs: int
    away_team_runs: int
    innings_played: int
    doubleheader_code: str
    game_number: int
    teams: tuple[dict[str, Any], dict[str, Any]]
    venue_name: str
    players: tuple[ParsedPlayer, ...]
    starters: tuple[ParsedStarter, ...]
    lineups: tuple[ParsedLineupEntry, ...]


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def parse_game_feed(payload: dict[str, Any], expected_game_pk: int) -> ParsedGame:
    game_data = payload["gameData"]
    live_data = payload["liveData"]
    game_pk = int(game_data["game"]["pk"])
    if game_pk != expected_game_pk:
        raise FeedValidationError(f"Expected game {expected_game_pk}, received {game_pk}")
    status = str(game_data["status"]["abstractGameState"])
    if status != "Final":
        raise FeedValidationError(f"Game {game_pk} is not final: {status}")
    game_type = str(game_data["game"]["type"])
    if game_type != "R":
        raise FeedValidationError(f"Game {game_pk} is not regular season: {game_type}")

    teams_data = game_data["teams"]
    home_team = teams_data["home"]
    away_team = teams_data["away"]
    home_id, away_id = int(home_team["id"]), int(away_team["id"])
    linescore = live_data["linescore"]
    box_teams = live_data["boxscore"]["teams"]
    people = game_data.get("players", {})

    players: dict[int, ParsedPlayer] = {}
    starters: list[ParsedStarter] = []
    lineups: list[ParsedLineupEntry] = []
    for side, team_id in (("away", away_id), ("home", home_id)):
        box = box_teams[side]
        batting_order = [int(player_id) for player_id in box.get("battingOrder", [])]
        if len(batting_order) != 9:
            raise FeedValidationError(
                f"Game {game_pk} {side} lineup has {len(batting_order)} starters, expected 9"
            )
        pitcher_ids = [int(player_id) for player_id in box.get("pitchers", [])]
        if not pitcher_ids:
            raise FeedValidationError(f"Game {game_pk} {side} has no pitcher")
        starter_id = pitcher_ids[0]
        required_ids = set(batting_order) | {starter_id}
        for player_id in required_ids:
            person = people.get(f"ID{player_id}") or box.get("players", {}).get(
                f"ID{player_id}", {}
            ).get("person", {})
            if not person:
                raise FeedValidationError(f"Game {game_pk} cannot resolve player {player_id}")
            players[player_id] = ParsedPlayer(
                player_id=player_id,
                full_name=str(person.get("fullName") or person.get("fullName", player_id)),
                bat_side=(person.get("batSide") or {}).get("code"),
                throws=(person.get("pitchHand") or {}).get("code"),
            )
        starter_person = players[starter_id]
        starters.append(
            ParsedStarter(team_id, starter_id, starter_person.throws, is_home=side == "home")
        )
        for slot, player_id in enumerate(batting_order, start=1):
            box_player = box.get("players", {}).get(f"ID{player_id}", {})
            position = (box_player.get("position") or {}).get("abbreviation")
            lineups.append(
                ParsedLineupEntry(
                    team_id, player_id, slot, position, players[player_id].bat_side, side == "home"
                )
            )

    scheduled = _parse_datetime(game_data["datetime"]["dateTime"])
    if scheduled is None:
        raise FeedValidationError(f"Game {game_pk} has no scheduled time")
    return ParsedGame(
        game_pk=game_pk,
        game_date=date.fromisoformat(game_data["datetime"]["officialDate"]),
        scheduled_start_time_utc=scheduled,
        actual_start_time_utc=_parse_datetime(game_data["datetime"].get("firstPitch")),
        season=int(game_data["game"]["season"]),
        game_type=game_type,
        status=status,
        home_team_id=home_id,
        away_team_id=away_id,
        venue_id=int(game_data["venue"]["id"]),
        home_team_runs=int(linescore["teams"]["home"]["runs"]),
        away_team_runs=int(linescore["teams"]["away"]["runs"]),
        innings_played=len(linescore["innings"]),
        doubleheader_code=str(game_data["game"].get("doubleHeader", "N")),
        game_number=int(game_data["game"].get("gameNumber", 1)),
        teams=(away_team, home_team),
        venue_name=str(game_data["venue"]["name"]),
        players=tuple(players.values()),
        starters=tuple(starters),
        lineups=tuple(lineups),
    )
