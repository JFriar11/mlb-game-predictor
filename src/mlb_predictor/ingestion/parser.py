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
class ParsedBatting:
    team_id: int
    player_id: int
    is_home: bool
    plate_appearances: int
    at_bats: int
    runs: int
    hits: int
    doubles: int
    triples: int
    home_runs: int
    rbi: int
    base_on_balls: int
    strike_outs: int
    stolen_bases: int


@dataclass(frozen=True)
class ParsedPitching:
    team_id: int
    player_id: int
    is_home: bool
    is_starter: bool
    outs_recorded: int
    batters_faced: int
    pitches_thrown: int
    strikes: int
    hits_allowed: int
    runs_allowed: int
    earned_runs: int
    base_on_balls: int
    strike_outs: int
    home_runs_allowed: int


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
    batting: tuple[ParsedBatting, ...]
    pitching: tuple[ParsedPitching, ...]


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def innings_to_outs(value: str) -> int:
    """Convert MLB's baseball-decimal innings notation (5.2) into outs (17)."""
    whole, _, remainder = value.partition(".")
    partial = int(remainder or "0")
    if partial not in (0, 1, 2):
        raise FeedValidationError(f"Invalid inningsPitched value: {value}")
    return int(whole) * 3 + partial


def parse_game_feed(
    payload: dict[str, Any], expected_game_pk: int, *, strict_lineups: bool = True
) -> ParsedGame:
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
    batting: list[ParsedBatting] = []
    pitching: list[ParsedPitching] = []
    for side, team_id in (("away", away_id), ("home", home_id)):
        box = box_teams[side]
        batting_order = [int(player_id) for player_id in box.get("battingOrder", [])]
        if len(batting_order) != 9 and strict_lineups:
            raise FeedValidationError(
                f"Game {game_pk} {side} lineup has {len(batting_order)} starters, expected 9"
            )
        pitcher_ids = [int(player_id) for player_id in box.get("pitchers", [])]
        if not pitcher_ids:
            raise FeedValidationError(f"Game {game_pk} {side} has no pitcher")
        starter_id = pitcher_ids[0]
        box_players = box.get("players", {})
        statistical_ids = {
            int(key.removeprefix("ID"))
            for key, value in box_players.items()
            if (value.get("stats") or {}).get("batting")
            or (value.get("stats") or {}).get("pitching")
        }
        required_ids = set(batting_order) | {starter_id} | statistical_ids
        for player_id in required_ids:
            person = people.get(f"ID{player_id}") or box_players.get(f"ID{player_id}", {}).get(
                "person", {}
            )
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
            box_player = box_players.get(f"ID{player_id}", {})
            position = (box_player.get("position") or {}).get("abbreviation")
            lineups.append(
                ParsedLineupEntry(
                    team_id, player_id, slot, position, players[player_id].bat_side, side == "home"
                )
            )
        for player_id in sorted(statistical_ids):
            stats = box_players[f"ID{player_id}"].get("stats", {})
            batting_stats = stats.get("batting") or {}
            if batting_stats and (
                int(batting_stats.get("gamesPlayed", 0)) > 0
                or int(batting_stats.get("plateAppearances", 0)) > 0
                or int(batting_stats.get("runs", 0)) > 0
            ):
                batting.append(
                    ParsedBatting(
                        team_id=team_id,
                        player_id=player_id,
                        is_home=side == "home",
                        plate_appearances=int(batting_stats.get("plateAppearances", 0)),
                        at_bats=int(batting_stats.get("atBats", 0)),
                        runs=int(batting_stats.get("runs", 0)),
                        hits=int(batting_stats.get("hits", 0)),
                        doubles=int(batting_stats.get("doubles", 0)),
                        triples=int(batting_stats.get("triples", 0)),
                        home_runs=int(batting_stats.get("homeRuns", 0)),
                        rbi=int(batting_stats.get("rbi", 0)),
                        base_on_balls=int(batting_stats.get("baseOnBalls", 0)),
                        strike_outs=int(batting_stats.get("strikeOuts", 0)),
                        stolen_bases=int(batting_stats.get("stolenBases", 0)),
                    )
                )
            pitching_stats = stats.get("pitching") or {}
            if pitching_stats and (
                int(pitching_stats.get("battersFaced", 0)) > 0
                or str(pitching_stats.get("inningsPitched", "0.0")) != "0.0"
            ):
                pitching.append(
                    ParsedPitching(
                        team_id=team_id,
                        player_id=player_id,
                        is_home=side == "home",
                        is_starter=player_id == starter_id,
                        outs_recorded=innings_to_outs(
                            str(pitching_stats.get("inningsPitched", "0.0"))
                        ),
                        batters_faced=int(pitching_stats.get("battersFaced", 0)),
                        pitches_thrown=int(pitching_stats.get("numberOfPitches", 0)),
                        strikes=int(pitching_stats.get("strikes", 0)),
                        hits_allowed=int(pitching_stats.get("hits", 0)),
                        runs_allowed=int(pitching_stats.get("runs", 0)),
                        earned_runs=int(pitching_stats.get("earnedRuns", 0)),
                        base_on_balls=int(pitching_stats.get("baseOnBalls", 0)),
                        strike_outs=int(pitching_stats.get("strikeOuts", 0)),
                        home_runs_allowed=int(pitching_stats.get("homeRuns", 0)),
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
        batting=tuple(batting),
        pitching=tuple(pitching),
    )
