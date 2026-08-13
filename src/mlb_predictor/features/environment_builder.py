import gzip
import json
import re
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from mlb_predictor.db.models import EnvironmentFeatureSnapshot, Game

FEATURE_VERSION = "sprint6_v1"
WIND_DIRECTIONS = {
    "Out To CF": (1.0, 0.0),
    "Out To LF": (0.7, -0.7),
    "Out To RF": (0.7, 0.7),
    "In From CF": (-1.0, 0.0),
    "In From LF": (-0.7, 0.7),
    "In From RF": (-0.7, -0.7),
    "L To R": (0.0, 1.0),
    "R To L": (0.0, -1.0),
}


def parse_wind(value: str | None) -> tuple[float, float, float]:
    if not value:
        return 0.0, 0.0, 0.0
    match = re.search(r"(\d+)\s*mph(?:,\s*(.*))?", value)
    if not match:
        return 0.0, 0.0, 0.0
    speed = float(match.group(1))
    outward, cross = WIND_DIRECTIONS.get(match.group(2) or "", (0.0, 0.0))
    return speed, speed * outward, speed * cross


def _feed(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def build_environment_features(
    session: Session, raw_root: Path, feature_version: str = FEATURE_VERSION
) -> list[EnvironmentFeatureSnapshot]:
    games = list(
        session.scalars(
            select(Game)
            .where(Game.season.between(2021, 2025))
            .order_by(Game.game_date, Game.game_pk)
        )
    )
    by_date: dict[date, list[Game]] = defaultdict(list)
    for game in games:
        by_date[game.game_date].append(game)
    venue_runs: dict[int, float] = defaultdict(float)
    venue_games: dict[int, int] = defaultdict(int)
    league_runs = 0.0
    league_games = 0
    snapshots = []
    max_source_date: date | None = None
    created_at = datetime.now(UTC)
    for game_date in sorted(by_date):
        league_per_team = league_runs / (2 * league_games) if league_games else 4.5
        for game in by_date[game_date]:
            payload = _feed(raw_root / str(game.season) / "games" / f"{game.game_pk}.json.gz")
            game_data = payload.get("gameData") or {}
            weather = game_data.get("weather") or {}
            venue = game_data.get("venue") or {}
            location = venue.get("location") or {}
            field = venue.get("fieldInfo") or {}
            fallback = 0
            prior_games = venue_games[game.venue_id]
            raw_factor = (
                venue_runs[game.venue_id] / (2 * prior_games) / league_per_team
                if prior_games and league_per_team
                else 1.0
            )
            if not prior_games:
                fallback += 1
            weight = prior_games / (prior_games + 50.0)
            park_factor = weight * raw_factor + (1 - weight)
            temperature = float(weather.get("temp", 70.0))
            if weather.get("temp") is None:
                fallback += 1
            wind_speed, wind_out, wind_cross = parse_wind(weather.get("wind"))
            if not weather.get("wind"):
                fallback += 1
            elevation = float(location.get("elevation", 0.0))
            if location.get("elevation") is None:
                fallback += 1
            roof_type = str(field.get("roofType") or "Unknown")
            if roof_type == "Unknown":
                fallback += 1
            condition = str(weather.get("condition") or "Unknown")
            snapshots.append(
                EnvironmentFeatureSnapshot(
                    game_pk=game.game_pk,
                    feature_version=feature_version,
                    as_of=game.scheduled_start_time_utc - timedelta(minutes=30),
                    max_source_game_date=max_source_date,
                    park_prior_games=prior_games,
                    park_factor=min(max(park_factor, 0.7), 1.3),
                    temperature_f=temperature,
                    wind_speed_mph=wind_speed,
                    wind_out_component=wind_out,
                    wind_cross_component=wind_cross,
                    elevation_ft=elevation,
                    roof_type=roof_type,
                    roof_closed_proxy=condition in {"Roof Closed", "Dome"},
                    day_game=game.day_night == "day",
                    artificial_turf="Artificial" in str(field.get("turfType") or ""),
                    weather_observed_proxy=bool(weather),
                    fallback_count=fallback,
                    created_at=created_at,
                )
            )
        # Park outcomes become visible only after all same-date snapshots are complete.
        for game in by_date[game_date]:
            total_runs = game.home_team_runs + game.away_team_runs
            venue_runs[game.venue_id] += total_runs
            venue_games[game.venue_id] += 1
            league_runs += total_runs
            league_games += 1
        max_source_date = game_date
    session.execute(
        delete(EnvironmentFeatureSnapshot).where(
            EnvironmentFeatureSnapshot.feature_version == feature_version
        )
    )
    session.add_all(snapshots)
    session.flush()
    return snapshots
