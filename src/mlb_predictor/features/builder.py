from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from mlb_predictor.db.models import (
    Game,
    GameStartingLineup,
    GameStartingPitcher,
    PlayerGameBatting,
    PlayerGamePitching,
    PregameFeatureSnapshot,
)

DEFAULT_RUNS = 4.5
DEFAULT_ON_BASE_RATE = 0.320
DEFAULT_STRIKEOUT_RATE = 0.225
DEFAULT_HOME_RUN_RATE = 0.030
DEFAULT_OUTS_PER_START = 15.0


@dataclass
class BattingTotals:
    pa: int = 0
    ab: int = 0
    hits: int = 0
    walks: int = 0
    strikeouts: int = 0
    home_runs: int = 0

    def add(self, row: PlayerGameBatting) -> None:
        self.pa += row.plate_appearances
        self.ab += row.at_bats
        self.hits += row.hits
        self.walks += row.base_on_balls
        self.strikeouts += row.strike_outs
        self.home_runs += row.home_runs


@dataclass
class PitchingTotals:
    appearances: int = 0
    outs: int = 0
    batters_faced: int = 0
    earned_runs: int = 0
    walks: int = 0
    strikeouts: int = 0

    def add(self, row: PlayerGamePitching) -> None:
        self.appearances += 1
        self.outs += row.outs_recorded
        self.batters_faced += row.batters_faced
        self.earned_runs += row.earned_runs
        self.walks += row.base_on_balls
        self.strikeouts += row.strike_outs


@dataclass(frozen=True)
class TeamOutcome:
    game_date: date
    runs: int
    runs_allowed: int


@dataclass(frozen=True)
class ReliefAppearance:
    game_date: date
    team_id: int
    row: PlayerGamePitching


def _rate(numerator: int, denominator: int, fallback: float) -> float:
    return numerator / denominator if denominator > 0 else fallback


def _pitching_rates(totals: PitchingTotals, era_fallback: float) -> tuple[float, float, float]:
    era = totals.earned_runs * 27 / totals.outs if totals.outs else era_fallback
    strikeout_rate = _rate(totals.strikeouts, totals.batters_faced, DEFAULT_STRIKEOUT_RATE)
    walk_rate = _rate(totals.walks, totals.batters_faced, 0.085)
    return era, strikeout_rate, walk_rate


def build_2025_features(
    session: Session, feature_version: str = "sprint2_v1"
) -> list[PregameFeatureSnapshot]:
    """Build two rows per game using only games from strictly earlier calendar dates."""
    games = list(
        session.scalars(
            select(Game).where(Game.season == 2025).order_by(Game.game_date, Game.game_pk)
        )
    )
    game_ids = [game.game_pk for game in games]
    lineups: dict[tuple[int, int], list[int]] = defaultdict(list)
    for row in session.scalars(
        select(GameStartingLineup)
        .where(GameStartingLineup.game_pk.in_(game_ids))
        .order_by(
            GameStartingLineup.game_pk, GameStartingLineup.team_id, GameStartingLineup.batting_order
        )
    ):
        lineups[(row.game_pk, row.team_id)].append(row.player_id)
    starters = {
        (row.game_pk, row.team_id): row.pitcher_id
        for row in session.scalars(
            select(GameStartingPitcher).where(GameStartingPitcher.game_pk.in_(game_ids))
        )
    }
    batting_by_game: dict[int, list[PlayerGameBatting]] = defaultdict(list)
    for row in session.scalars(
        select(PlayerGameBatting).where(PlayerGameBatting.game_pk.in_(game_ids))
    ):
        batting_by_game[row.game_pk].append(row)
    pitching_by_game: dict[int, list[PlayerGamePitching]] = defaultdict(list)
    for row in session.scalars(
        select(PlayerGamePitching).where(PlayerGamePitching.game_pk.in_(game_ids))
    ):
        pitching_by_game[row.game_pk].append(row)

    games_by_date: dict[date, list[Game]] = defaultdict(list)
    for game in games:
        games_by_date[game.game_date].append(game)

    team_history: dict[int, list[TeamOutcome]] = defaultdict(list)
    batter_history: dict[int, BattingTotals] = defaultdict(BattingTotals)
    starter_history: dict[int, PitchingTotals] = defaultdict(PitchingTotals)
    relief_history: list[ReliefAppearance] = []
    last_game_date: dict[int, date] = {}
    league_batting = BattingTotals()
    league_starters = PitchingTotals()
    snapshots: list[PregameFeatureSnapshot] = []
    max_source_date: date | None = None
    created_at = datetime.now(UTC)

    for game_date in sorted(games_by_date):
        prior_team_outcomes = [item for values in team_history.values() for item in values]
        league_runs = (
            sum(item.runs for item in prior_team_outcomes) / len(prior_team_outcomes)
            if prior_team_outcomes
            else DEFAULT_RUNS
        )
        league_on_base = _rate(
            league_batting.hits + league_batting.walks,
            league_batting.ab + league_batting.walks,
            DEFAULT_ON_BASE_RATE,
        )
        league_strikeout = _rate(
            league_batting.strikeouts, league_batting.pa, DEFAULT_STRIKEOUT_RATE
        )
        league_home_run = _rate(league_batting.home_runs, league_batting.pa, DEFAULT_HOME_RUN_RATE)
        league_starter_era, league_starter_k, league_starter_bb = _pitching_rates(
            league_starters, DEFAULT_RUNS
        )
        league_starter_outs = _rate(
            league_starters.outs, league_starters.appearances, DEFAULT_OUTS_PER_START
        )

        for game in games_by_date[game_date]:
            as_of = game.scheduled_start_time_utc - timedelta(minutes=30)
            for is_home, offense_id, opponent_id in (
                (False, game.away_team_id, game.home_team_id),
                (True, game.home_team_id, game.away_team_id),
            ):
                fallback_count = 0
                history = team_history[offense_id]
                if history:
                    recent = history[-10:]
                    runs_10 = sum(item.runs for item in recent) / len(recent)
                    allowed_10 = sum(item.runs_allowed for item in recent) / len(recent)
                    runs_season = sum(item.runs for item in history) / len(history)
                else:
                    runs_10 = allowed_10 = runs_season = league_runs
                    fallback_count += 1

                lineup_ids = lineups[(game.game_pk, offense_id)]
                on_base_rates: list[float] = []
                strikeout_rates: list[float] = []
                home_run_rates: list[float] = []
                lineup_pa = 0
                for player_id in lineup_ids:
                    totals = batter_history[player_id]
                    lineup_pa += totals.pa
                    if totals.pa == 0:
                        fallback_count += 1
                    on_base_rates.append(
                        _rate(
                            totals.hits + totals.walks,
                            totals.ab + totals.walks,
                            league_on_base,
                        )
                    )
                    strikeout_rates.append(_rate(totals.strikeouts, totals.pa, league_strikeout))
                    home_run_rates.append(_rate(totals.home_runs, totals.pa, league_home_run))

                opponent_starter_id = starters[(game.game_pk, opponent_id)]
                starter_totals = starter_history[opponent_starter_id]
                if starter_totals.appearances == 0:
                    fallback_count += 1
                starter_era, starter_k, starter_bb = _pitching_rates(
                    starter_totals, league_starter_era
                )
                if starter_totals.batters_faced == 0:
                    starter_k, starter_bb = league_starter_k, league_starter_bb
                starter_outs = _rate(
                    starter_totals.outs,
                    starter_totals.appearances,
                    league_starter_outs,
                )

                opponent_relief = [
                    item
                    for item in relief_history
                    if item.team_id == opponent_id and 0 < (game_date - item.game_date).days <= 30
                ]
                league_relief = [
                    item for item in relief_history if 0 < (game_date - item.game_date).days <= 30
                ]
                bullpen = PitchingTotals()
                for item in opponent_relief:
                    bullpen.add(item.row)
                league_bullpen = PitchingTotals()
                for item in league_relief:
                    league_bullpen.add(item.row)
                league_bullpen_era, league_bullpen_k, league_bullpen_bb = _pitching_rates(
                    league_bullpen, DEFAULT_RUNS
                )
                if bullpen.outs == 0:
                    fallback_count += 1
                bullpen_era, bullpen_k, bullpen_bb = _pitching_rates(bullpen, league_bullpen_era)
                if bullpen.batters_faced == 0:
                    bullpen_k, bullpen_bb = league_bullpen_k, league_bullpen_bb
                recent_outs = sum(
                    item.row.outs_recorded
                    for item in opponent_relief
                    if (game_date - item.game_date).days <= 3
                )

                previous_date = last_game_date.get(offense_id)
                if previous_date is None:
                    days_rest = 7
                    fallback_count += 1
                else:
                    days_rest = min(max((game_date - previous_date).days - 1, 0), 7)

                snapshots.append(
                    PregameFeatureSnapshot(
                        game_pk=game.game_pk,
                        offense_team_id=offense_id,
                        opponent_team_id=opponent_id,
                        starter_id=opponent_starter_id,
                        venue_id=game.venue_id,
                        is_home=is_home,
                        as_of=as_of,
                        feature_version=feature_version,
                        max_source_game_date=max_source_date,
                        team_prior_games=len(history),
                        team_runs_avg_10=runs_10,
                        team_runs_allowed_avg_10=allowed_10,
                        team_runs_avg_season=runs_season,
                        lineup_prior_pa=lineup_pa,
                        lineup_on_base_rate=sum(on_base_rates) / len(on_base_rates),
                        lineup_strikeout_rate=sum(strikeout_rates) / len(strikeout_rates),
                        lineup_home_run_rate=sum(home_run_rates) / len(home_run_rates),
                        starter_prior_starts=starter_totals.appearances,
                        starter_era=starter_era,
                        starter_strikeout_rate=starter_k,
                        starter_walk_rate=starter_bb,
                        starter_outs_per_start=starter_outs,
                        bullpen_prior_outs=bullpen.outs,
                        bullpen_era_30d=bullpen_era,
                        bullpen_strikeout_rate_30d=bullpen_k,
                        bullpen_walk_rate_30d=bullpen_bb,
                        bullpen_recent_outs=recent_outs,
                        days_rest=days_rest,
                        fallback_count=fallback_count,
                        created_at=created_at,
                    )
                )

        # Same-day games update state together only after every snapshot for the date exists.
        for game in games_by_date[game_date]:
            team_history[game.home_team_id].append(
                TeamOutcome(game_date, game.home_team_runs, game.away_team_runs)
            )
            team_history[game.away_team_id].append(
                TeamOutcome(game_date, game.away_team_runs, game.home_team_runs)
            )
            last_game_date[game.home_team_id] = game_date
            last_game_date[game.away_team_id] = game_date
            for row in batting_by_game[game.game_pk]:
                batter_history[row.player_id].add(row)
                league_batting.add(row)
            for row in pitching_by_game[game.game_pk]:
                if row.is_starter:
                    starter_history[row.player_id].add(row)
                    league_starters.add(row)
                else:
                    relief_history.append(ReliefAppearance(game_date, row.team_id, row))
        max_source_date = game_date

    session.execute(
        delete(PregameFeatureSnapshot).where(
            PregameFeatureSnapshot.feature_version == feature_version,
            PregameFeatureSnapshot.game_pk.in_(game_ids),
        )
    )
    session.add_all(snapshots)
    session.flush()
    return snapshots
