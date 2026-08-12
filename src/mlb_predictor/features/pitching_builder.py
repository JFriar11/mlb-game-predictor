from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from mlb_predictor.db.models import (
    Game,
    GameStartingPitcher,
    PitchingFeatureSnapshot,
    PlayerGamePitching,
)

FEATURE_VERSION = "sprint5_v1"
SEASONS = (2021, 2022, 2023, 2024, 2025)


@dataclass
class PitchTotals:
    appearances: float = 0
    outs: float = 0
    pitches: float = 0
    batters_faced: float = 0
    earned_runs: float = 0
    strikeouts: float = 0
    walks: float = 0

    def add(self, row: PlayerGamePitching) -> None:
        self.appearances += 1
        self.outs += row.outs_recorded
        self.pitches += row.pitches_thrown
        self.batters_faced += row.batters_faced
        self.earned_runs += row.earned_runs
        self.strikeouts += row.strike_outs
        self.walks += row.base_on_balls

    def decay(self, factor: float) -> None:
        for name in self.__dataclass_fields__:
            setattr(self, name, getattr(self, name) * factor)


@dataclass(frozen=True)
class DatedPitching:
    game_date: date
    row: PlayerGamePitching


def _mean(numerator: float, denominator: float, fallback: float) -> float:
    return numerator / denominator if denominator else fallback


def build_pitching_features(
    session: Session, feature_version: str = FEATURE_VERSION
) -> list[PitchingFeatureSnapshot]:
    """Build defense-team snapshots using only games on strictly earlier dates."""
    games = list(
        session.scalars(
            select(Game).where(Game.season.in_(SEASONS)).order_by(Game.game_date, Game.game_pk)
        )
    )
    game_ids = [game.game_pk for game in games]
    starters = {
        (row.game_pk, row.team_id): row.pitcher_id
        for row in session.scalars(
            select(GameStartingPitcher).where(GameStartingPitcher.game_pk.in_(game_ids))
        )
    }
    pitching: dict[int, list[PlayerGamePitching]] = defaultdict(list)
    for row in session.scalars(
        select(PlayerGamePitching).where(PlayerGamePitching.game_pk.in_(game_ids))
    ):
        pitching[row.game_pk].append(row)
    by_date: dict[date, list[Game]] = defaultdict(list)
    for game in games:
        by_date[game.game_date].append(game)

    starter_history: dict[int, PitchTotals] = defaultdict(PitchTotals)
    team_starter_history: dict[int, PitchTotals] = defaultdict(PitchTotals)
    relief_history: dict[int, dict[int, PitchTotals]] = defaultdict(
        lambda: defaultdict(PitchTotals)
    )
    relief_recent: dict[int, dict[int, list[DatedPitching]]] = defaultdict(
        lambda: defaultdict(list)
    )
    starter_last_date: dict[int, date] = {}
    league_starters = PitchTotals()
    league_relief = PitchTotals()
    snapshots: list[PitchingFeatureSnapshot] = []
    max_source_date: date | None = None
    active_season: int | None = None
    created_at = datetime.now(UTC)

    for game_date in sorted(by_date):
        season = by_date[game_date][0].season
        if active_season is not None and season != active_season:
            for totals in starter_history.values():
                totals.decay(0.5)
            for totals in team_starter_history.values():
                totals.decay(0.5)
            for team in relief_history.values():
                for totals in team.values():
                    totals.decay(0.5)
            league_starters.decay(0.5)
            league_relief.decay(0.5)
            relief_recent = defaultdict(lambda: defaultdict(list))
            starter_last_date = {}
        active_season = season

        league_outs = _mean(league_starters.outs, league_starters.appearances, 15.0)
        league_pitches = _mean(league_starters.pitches, league_starters.appearances, 85.0)
        league_ppo = _mean(league_starters.pitches, league_starters.outs, 5.7)
        league_relief_era = _mean(league_relief.earned_runs * 27, league_relief.outs, 4.5)
        league_relief_k = _mean(league_relief.strikeouts, league_relief.batters_faced, 0.225)
        league_relief_bb = _mean(league_relief.walks, league_relief.batters_faced, 0.085)

        for game in by_date[game_date]:
            for team_id in (game.away_team_id, game.home_team_id):
                starter_id = starters[(game.game_pk, team_id)]
                starter = starter_history[starter_id]
                team_starters = team_starter_history[team_id]
                fallback = 0
                if not starter.appearances:
                    fallback += 1
                if not team_starters.appearances:
                    fallback += 1
                last_start = starter_last_date.get(starter_id)
                starter_rest = min((game_date - last_start).days, 30) if last_start else 7
                if last_start is None:
                    fallback += 1

                candidate_ids = set(relief_history[team_id])
                available: list[int] = []
                unavailable: list[int] = []
                workload_1d = 0
                workload_3d = 0
                for player_id in candidate_ids:
                    recent = relief_recent[team_id][player_id]
                    pitches_1d = sum(
                        item.row.pitches_thrown
                        for item in recent
                        if (game_date - item.game_date).days == 1
                    )
                    pitches_3d = sum(
                        item.row.pitches_thrown
                        for item in recent
                        if 0 < (game_date - item.game_date).days <= 3
                    )
                    workload_1d += pitches_1d
                    workload_3d += pitches_3d
                    (unavailable if pitches_1d >= 30 or pitches_3d >= 50 else available).append(
                        player_id
                    )
                mixture = PitchTotals()
                for player_id in available:
                    totals = relief_history[team_id][player_id]
                    for field in mixture.__dataclass_fields__:
                        setattr(mixture, field, getattr(mixture, field) + getattr(totals, field))
                if not available or not mixture.outs:
                    fallback += 1
                role_order = sorted(
                    candidate_ids,
                    key=lambda player_id: relief_history[team_id][player_id].appearances,
                    reverse=True,
                )[:3]
                high_usage_available = sum(player_id in available for player_id in role_order)

                snapshots.append(
                    PitchingFeatureSnapshot(
                        game_pk=game.game_pk,
                        team_id=team_id,
                        starter_id=starter_id,
                        feature_version=feature_version,
                        as_of=game.scheduled_start_time_utc - timedelta(minutes=30),
                        max_source_game_date=max_source_date,
                        starter_prior_starts=round(starter.appearances),
                        starter_avg_outs=_mean(starter.outs, starter.appearances, league_outs),
                        starter_avg_pitches=_mean(
                            starter.pitches, starter.appearances, league_pitches
                        ),
                        starter_pitches_per_out=min(
                            _mean(starter.pitches, starter.outs, league_ppo), 20.0
                        ),
                        starter_days_rest=starter_rest,
                        team_prior_games=round(team_starters.appearances),
                        manager_avg_starter_outs=_mean(
                            team_starters.outs, team_starters.appearances, league_outs
                        ),
                        manager_avg_starter_pitches=_mean(
                            team_starters.pitches, team_starters.appearances, league_pitches
                        ),
                        bullpen_prior_appearances=round(mixture.appearances),
                        bullpen_workload_1d=workload_1d,
                        bullpen_workload_3d=workload_3d,
                        available_reliever_count=len(available),
                        unavailable_reliever_count=len(unavailable),
                        available_bullpen_era=_mean(
                            mixture.earned_runs * 27, mixture.outs, league_relief_era
                        ),
                        available_bullpen_strikeout_rate=_mean(
                            mixture.strikeouts, mixture.batters_faced, league_relief_k
                        ),
                        available_bullpen_walk_rate=_mean(
                            mixture.walks, mixture.batters_faced, league_relief_bb
                        ),
                        high_usage_available=high_usage_available,
                        fallback_count=fallback,
                        created_at=created_at,
                    )
                )

        # A date is one state transition, so doubleheader games cannot see each other.
        for game in by_date[game_date]:
            for row in pitching[game.game_pk]:
                if row.is_starter:
                    starter_history[row.player_id].add(row)
                    team_starter_history[row.team_id].add(row)
                    league_starters.add(row)
                    starter_last_date[row.player_id] = game_date
                else:
                    relief_history[row.team_id][row.player_id].add(row)
                    relief_recent[row.team_id][row.player_id].append(DatedPitching(game_date, row))
                    league_relief.add(row)
        max_source_date = game_date

    session.execute(
        delete(PitchingFeatureSnapshot).where(
            PitchingFeatureSnapshot.feature_version == feature_version
        )
    )
    session.add_all(snapshots)
    session.flush()
    return snapshots
