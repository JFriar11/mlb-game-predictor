from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from mlb_predictor.db.models import Game, PlayerGameBatting, PlayerGamePitching
from mlb_predictor.features.builder import (
    DEFAULT_HOME_RUN_RATE,
    DEFAULT_ON_BASE_RATE,
    DEFAULT_OUTS_PER_START,
    DEFAULT_RUNS,
    DEFAULT_STRIKEOUT_RATE,
)
from mlb_predictor.modeling.dataset import MULTISEASON_FEATURE_COLUMNS


def _rate(numerator: float, denominator: float, fallback: float) -> float:
    return numerator / denominator if denominator else fallback


def build_live_feature_pair(
    session: Session,
    *,
    game_pk: int,
    home_team_id: int,
    away_team_id: int,
    venue_id: int,
    home_starter_id: int,
    away_starter_id: int,
    home_lineup: tuple[int, ...],
    away_lineup: tuple[int, ...],
    as_of: datetime,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Build accepted features from completed records strictly before ``as_of``.

    The live path uses completion timestamps when present; when the normalized source has
    only scheduled timestamps, it conservatively requires a prior calendar date. This is
    stricter than necessary for some doubleheaders and cannot leak a target-game outcome.
    """
    del game_pk
    games = list(
        session.scalars(
            select(Game)
            .where(Game.scheduled_start_time_utc < as_of)
            .order_by(Game.game_date, Game.game_pk)
        )
    )
    games = [g for g in games if g.season <= as_of.year and g.game_date < as_of.date()]
    game_ids = [g.game_pk for g in games]
    batting = (
        list(
            session.scalars(
                select(PlayerGameBatting).where(PlayerGameBatting.game_pk.in_(game_ids))
            )
        )
        if game_ids
        else []
    )
    pitching = (
        list(
            session.scalars(
                select(PlayerGamePitching).where(PlayerGamePitching.game_pk.in_(game_ids))
            )
        )
        if game_ids
        else []
    )
    by_game = {g.game_pk: g for g in games}
    team_games: dict[int, list[tuple[Game, int, int]]] = defaultdict(list)
    for g in games:
        team_games[g.home_team_id].append((g, g.home_team_runs, g.away_team_runs))
        team_games[g.away_team_id].append((g, g.away_team_runs, g.home_team_runs))
    batter_rows: dict[int, list[PlayerGameBatting]] = defaultdict(list)
    starter_rows: dict[int, list[PlayerGamePitching]] = defaultdict(list)
    reliever_rows: dict[int, list[PlayerGamePitching]] = defaultdict(list)
    for row in batting:
        batter_rows[row.player_id].append(row)
    for row in pitching:
        (starter_rows if row.is_starter else reliever_rows)[
            row.player_id if row.is_starter else row.team_id
        ].append(row)
    league_runs = (
        sum(g.home_team_runs + g.away_team_runs for g in games) / max(2 * len(games), 1)
        if games
        else DEFAULT_RUNS
    )
    warnings: list[str] = []

    def side(
        offense: int, defense: int, lineup: tuple[int, ...], starter: int, is_home: bool
    ) -> dict[str, Any]:
        history = team_games[offense]
        current = [x for x in history if x[0].season == as_of.year]
        source = current or history
        recent = source[-10:]
        fallback = int(not source)
        runs10 = sum(x[1] for x in recent) / len(recent) if recent else league_runs
        allow10 = sum(x[2] for x in recent) / len(recent) if recent else league_runs
        season_avg = sum(x[1] for x in current) / len(current) if current else runs10
        selected_batting = [r for player in lineup for r in batter_rows[player]]
        pa = sum(r.plate_appearances for r in selected_batting)
        ab = sum(r.at_bats for r in selected_batting)
        hits = sum(r.hits for r in selected_batting)
        walks = sum(r.base_on_balls for r in selected_batting)
        strikeouts = sum(r.strike_outs for r in selected_batting)
        homers = sum(r.home_runs for r in selected_batting)
        fallback += sum(not batter_rows[player] for player in lineup)
        starts = starter_rows[starter]
        outs = sum(r.outs_recorded for r in starts)
        bf = sum(r.batters_faced for r in starts)
        er = sum(r.earned_runs for r in starts)
        sk = sum(r.strike_outs for r in starts)
        bb = sum(r.base_on_balls for r in starts)
        fallback += int(not starts)
        bullpen = [
            r
            for r in reliever_rows[defense]
            if 0 < (as_of.date() - by_game[r.game_pk].game_date).days <= 30
        ]
        bo = sum(r.outs_recorded for r in bullpen)
        bbf = sum(r.batters_faced for r in bullpen)
        fallback += int(not bullpen)
        recent_outs = sum(
            r.outs_recorded
            for r in bullpen
            if (as_of.date() - by_game[r.game_pk].game_date).days <= 3
        )
        previous = max((x[0].game_date for x in history), default=None)
        days_rest = min(max((as_of.date() - previous).days - 1, 0), 7) if previous else 7
        fallback += int(previous is None)
        prior_season = [x for x in history if x[0].season == as_of.year - 1]
        result = {
            "is_home": is_home,
            "venue_id": venue_id,
            "team_prior_games": len(current),
            "team_runs_avg_10": runs10,
            "team_runs_allowed_avg_10": allow10,
            "team_runs_avg_season": season_avg,
            "lineup_prior_pa": pa,
            "lineup_on_base_rate": _rate(hits + walks, ab + walks, DEFAULT_ON_BASE_RATE),
            "lineup_strikeout_rate": _rate(strikeouts, pa, DEFAULT_STRIKEOUT_RATE),
            "lineup_home_run_rate": _rate(homers, pa, DEFAULT_HOME_RUN_RATE),
            "starter_prior_starts": len(starts),
            "starter_era": _rate(er * 27, outs, DEFAULT_RUNS),
            "starter_strikeout_rate": _rate(sk, bf, DEFAULT_STRIKEOUT_RATE),
            "starter_walk_rate": _rate(bb, bf, 0.085),
            "starter_outs_per_start": _rate(outs, len(starts), DEFAULT_OUTS_PER_START),
            "bullpen_prior_outs": bo,
            "bullpen_era_30d": _rate(sum(r.earned_runs for r in bullpen) * 27, bo, DEFAULT_RUNS),
            "bullpen_strikeout_rate_30d": _rate(
                sum(r.strike_outs for r in bullpen), bbf, DEFAULT_STRIKEOUT_RATE
            ),
            "bullpen_walk_rate_30d": _rate(sum(r.base_on_balls for r in bullpen), bbf, 0.085),
            "bullpen_recent_outs": recent_outs,
            "days_rest": days_rest,
            "fallback_count": fallback,
            "season": as_of.year,
            "universal_dh": True,
            "scheduled_innings": 9,
            "history_decay": 0.5,
            "prior_season_team_games": len(prior_season),
            "prior_season_lineup_pa": sum(
                r.plate_appearances
                for r in selected_batting
                if by_game[r.game_pk].season == as_of.year - 1
            ),
            "prior_season_starter_starts": sum(
                by_game[r.game_pk].season == as_of.year - 1 for r in starts
            ),
            "prior_season_bullpen_outs": sum(
                r.outs_recorded
                for r in reliever_rows[defense]
                if by_game[r.game_pk].season == as_of.year - 1
            ),
        }
        return {key: result[key] for key in MULTISEASON_FEATURE_COLUMNS}

    if not any(g.season == as_of.year for g in games):
        warnings.append("no_current_season_history")
    away = side(away_team_id, home_team_id, away_lineup, home_starter_id, False)
    home = side(home_team_id, away_team_id, home_lineup, away_starter_id, True)
    return away, home, warnings
