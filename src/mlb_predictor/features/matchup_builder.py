from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from mlb_predictor.db.models import (
    Game,
    GameStartingLineup,
    GameStartingPitcher,
    PlayerGameBatting,
    PlayerGameHandedBatting,
    PlayerGamePitchGroup,
    PregameFeatureSnapshot,
)

BASE_VERSION = "sprint3_5_v1"
MATCHUP_VERSION = "sprint4_v1"
GROUPS = ("fastball", "breaking", "offspeed", "other")


def _counter() -> defaultdict[str, float]:
    return defaultdict(float)


def _rate(numerator: float, denominator: float, fallback: float) -> float:
    return numerator / denominator if denominator else fallback


def _shrunk(numerator: float, denominator: float, prior: float, strength: float) -> float:
    return (numerator + prior * strength) / (denominator + strength)


def _decay(states: dict[Any, defaultdict[str, float]], weight: float) -> None:
    for totals in states.values():
        for key in totals:
            totals[key] *= weight


def build_matchup_features(
    session: Session, feature_version: str = MATCHUP_VERSION
) -> list[PregameFeatureSnapshot]:
    """Extend accepted multi-season features with strictly prior-date matchup context."""
    if feature_version != MATCHUP_VERSION:
        raise ValueError(f"Sprint 4 feature version must be {MATCHUP_VERSION}")
    games = list(
        session.scalars(
            select(Game)
            .where(Game.season.in_(range(2021, 2026)))
            .order_by(Game.game_date, Game.game_pk)
        )
    )
    game_ids = [game.game_pk for game in games]
    base = {
        (row.game_pk, row.offense_team_id): row
        for row in session.scalars(
            select(PregameFeatureSnapshot).where(
                PregameFeatureSnapshot.feature_version == BASE_VERSION,
                PregameFeatureSnapshot.game_pk.in_(game_ids),
            )
        )
    }
    lineups: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    for row in session.scalars(
        select(GameStartingLineup)
        .where(GameStartingLineup.game_pk.in_(game_ids))
        .order_by(
            GameStartingLineup.game_pk, GameStartingLineup.team_id, GameStartingLineup.batting_order
        )
    ):
        lineups[(row.game_pk, row.team_id)].append((row.batting_order, row.player_id))
    starters = {
        (row.game_pk, row.team_id): (row.pitcher_id, row.throws or "R")
        for row in session.scalars(
            select(GameStartingPitcher).where(GameStartingPitcher.game_pk.in_(game_ids))
        )
    }
    games_by_date: dict[date, list[Game]] = defaultdict(list)
    for game in games:
        games_by_date[game.game_date].append(game)

    batting: dict[int, defaultdict[str, float]] = defaultdict(_counter)
    handed: dict[tuple[int, str], defaultdict[str, float]] = defaultdict(_counter)
    pitch_stats: dict[tuple[int, str, str], defaultdict[str, float]] = defaultdict(_counter)
    league_pitch: dict[str, defaultdict[str, float]] = defaultdict(_counter)
    slot_stats: dict[int, defaultdict[str, float]] = defaultdict(_counter)
    snapshots: list[PregameFeatureSnapshot] = []
    active_season: int | None = None
    created_at = datetime.now(UTC)
    new_columns = {
        "id",
        "lineup_weighted_on_base_rate",
        "lineup_weighted_strikeout_rate",
        "lineup_weighted_home_run_rate",
        "lineup_projected_plate_appearances",
        "lineup_vs_starter_hand_pa",
        "lineup_vs_starter_hand_on_base_rate",
        "lineup_vs_starter_hand_strikeout_rate",
        "lineup_vs_starter_hand_home_run_rate",
        "starter_pitch_group_prior_pitches",
        "starter_fastball_rate",
        "starter_breaking_rate",
        "starter_offspeed_rate",
        "starter_other_pitch_rate",
        "lineup_pitch_group_prior_pitches",
        "lineup_pitch_mix_whiff_rate",
        "lineup_pitch_mix_hit_in_play_rate",
        "matchup_fallback_count",
    }

    for game_date in sorted(games_by_date):
        season = games_by_date[game_date][0].season
        if active_season is not None and season != active_season:
            _decay(batting, 0.5)
            _decay(handed, 0.5)
            _decay(pitch_stats, 0.5)
            _decay(league_pitch, 0.5)
            _decay(slot_stats, 0.5)
        active_season = season
        for game in games_by_date[game_date]:
            for offense_id, opponent_id in (
                (game.away_team_id, game.home_team_id),
                (game.home_team_id, game.away_team_id),
            ):
                source = base[(game.game_pk, offense_id)]
                lineup = lineups[(game.game_pk, offense_id)]
                starter_id, starter_hand = starters[(game.game_pk, opponent_id)]
                slot_means = [
                    _rate(slot_stats[slot]["pa"], slot_stats[slot]["starts"], 4.25)
                    for slot, _ in lineup
                ]
                weight_total = sum(slot_means)
                weights = [value / weight_total for value in slot_means]
                projected_pa = sum(slot_means)
                weighted_obp = weighted_k = weighted_hr = 0.0
                hand_obp = hand_k = hand_hr = 0.0
                hand_pa = pitch_sample = fallback_count = 0
                player_pitch_rates: list[tuple[list[float], list[float]]] = []
                for weight, (_, player_id) in zip(weights, lineup, strict=True):
                    totals = batting[player_id]
                    pa = totals["pa"]
                    if not pa:
                        fallback_count += 1
                    obp = _shrunk(
                        totals["hits"] + totals["walks"], totals["ab"] + totals["walks"], 0.320, 100
                    )
                    strikeout = _shrunk(totals["strikeouts"], pa, 0.225, 100)
                    homer = _shrunk(totals["home_runs"], pa, 0.030, 100)
                    weighted_obp += weight * obp
                    weighted_k += weight * strikeout
                    weighted_hr += weight * homer
                    split = handed[(player_id, starter_hand)]
                    hand_pa += round(split["pa"])
                    hand_obp += weight * _shrunk(
                        split["hits"] + split["walks"], split["ab"] + split["walks"], obp, 50
                    )
                    hand_k += weight * _shrunk(split["strikeouts"], split["pa"], strikeout, 50)
                    hand_hr += weight * _shrunk(split["home_runs"], split["pa"], homer, 50)
                    batter_whiff: list[float] = []
                    batter_hit: list[float] = []
                    for group in GROUPS:
                        values = pitch_stats[(player_id, "batter", group)]
                        pitch_sample += round(values["pitches"])
                        league = league_pitch[group]
                        league_whiff = _rate(league["whiffs"], league["swings"], 0.22)
                        league_hit = _rate(league["hits"], league["in_play"], 0.30)
                        batter_whiff.append(
                            _shrunk(values["whiffs"], values["swings"], league_whiff, 100)
                        )
                        batter_hit.append(
                            _shrunk(values["hits"], values["in_play"], league_hit, 100)
                        )
                    player_pitch_rates.append((batter_whiff, batter_hit))

                starter_groups = [pitch_stats[(starter_id, "pitcher", group)] for group in GROUPS]
                starter_pitches = sum(item["pitches"] for item in starter_groups)
                if not starter_pitches:
                    fallback_count += 1
                league_total = sum(league_pitch[group]["pitches"] for group in GROUPS)
                mix = [
                    (
                        item["pitches"]
                        + 200 * _rate(league_pitch[group]["pitches"], league_total, 0.25)
                    )
                    / (starter_pitches + 200)
                    for group, item in zip(GROUPS, starter_groups, strict=True)
                ]
                mix_whiff = sum(
                    weight
                    * sum(
                        group_rate * mix_rate
                        for group_rate, mix_rate in zip(rate[0], mix, strict=True)
                    )
                    for weight, rate in zip(weights, player_pitch_rates, strict=True)
                )
                mix_hit = sum(
                    weight
                    * sum(
                        group_rate * mix_rate
                        for group_rate, mix_rate in zip(rate[1], mix, strict=True)
                    )
                    for weight, rate in zip(weights, player_pitch_rates, strict=True)
                )
                copied = {
                    column.name: getattr(source, column.name)
                    for column in PregameFeatureSnapshot.__table__.columns
                    if column.name not in new_columns
                }
                copied.update(feature_version=feature_version, created_at=created_at)
                snapshots.append(
                    PregameFeatureSnapshot(
                        **copied,
                        lineup_weighted_on_base_rate=weighted_obp,
                        lineup_weighted_strikeout_rate=weighted_k,
                        lineup_weighted_home_run_rate=weighted_hr,
                        lineup_projected_plate_appearances=projected_pa,
                        lineup_vs_starter_hand_pa=hand_pa,
                        lineup_vs_starter_hand_on_base_rate=hand_obp,
                        lineup_vs_starter_hand_strikeout_rate=hand_k,
                        lineup_vs_starter_hand_home_run_rate=hand_hr,
                        starter_pitch_group_prior_pitches=round(starter_pitches),
                        starter_fastball_rate=mix[0],
                        starter_breaking_rate=mix[1],
                        starter_offspeed_rate=mix[2],
                        starter_other_pitch_rate=mix[3],
                        lineup_pitch_group_prior_pitches=pitch_sample,
                        lineup_pitch_mix_whiff_rate=mix_whiff,
                        lineup_pitch_mix_hit_in_play_rate=mix_hit,
                        matchup_fallback_count=fallback_count,
                    )
                )

        date_ids = [game.game_pk for game in games_by_date[game_date]]
        batting_rows = list(
            session.scalars(
                select(PlayerGameBatting).where(PlayerGameBatting.game_pk.in_(date_ids))
            )
        )
        batting_map = {(row.game_pk, row.player_id): row for row in batting_rows}
        for game in games_by_date[game_date]:
            for team_id in (game.away_team_id, game.home_team_id):
                for slot, player_id in lineups[(game.game_pk, team_id)]:
                    row = batting_map.get((game.game_pk, player_id))
                    if row:
                        slot_stats[slot]["pa"] += row.plate_appearances
                        slot_stats[slot]["starts"] += 1
        for row in batting_rows:
            totals = batting[row.player_id]
            totals["pa"] += row.plate_appearances
            totals["ab"] += row.at_bats
            totals["hits"] += row.hits
            totals["walks"] += row.base_on_balls
            totals["strikeouts"] += row.strike_outs
            totals["home_runs"] += row.home_runs
        for row in session.scalars(
            select(PlayerGameHandedBatting).where(PlayerGameHandedBatting.game_pk.in_(date_ids))
        ):
            totals = handed[(row.batter_id, row.pitcher_hand)]
            totals["pa"] += row.plate_appearances
            totals["ab"] += row.at_bats
            totals["hits"] += row.hits
            totals["walks"] += row.walks
            totals["strikeouts"] += row.strikeouts
            totals["home_runs"] += row.home_runs
        for row in session.scalars(
            select(PlayerGamePitchGroup).where(PlayerGamePitchGroup.game_pk.in_(date_ids))
        ):
            totals = pitch_stats[(row.player_id, row.role, row.pitch_group)]
            totals["pitches"] += row.pitches
            totals["swings"] += row.swings
            totals["whiffs"] += row.whiffs
            totals["in_play"] += row.balls_in_play
            totals["hits"] += row.hits_on_contact
            if row.role == "batter":
                league = league_pitch[row.pitch_group]
                league["pitches"] += row.pitches
                league["swings"] += row.swings
                league["whiffs"] += row.whiffs
                league["in_play"] += row.balls_in_play
                league["hits"] += row.hits_on_contact

    session.execute(
        delete(PregameFeatureSnapshot).where(
            PregameFeatureSnapshot.feature_version == feature_version
        )
    )
    session.add_all(snapshots)
    session.flush()
    return snapshots
