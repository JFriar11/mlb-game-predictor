import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import Engine

from mlb_predictor.db.session import session_scope
from mlb_predictor.ingestion.cache import RawJsonCache
from mlb_predictor.ingestion.client import MlbStatsClient
from mlb_predictor.ingestion.service import ingest_game

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionException:
    game_pk: int
    error_type: str
    message: str


@dataclass(frozen=True)
class SeasonIngestionResult:
    discovered: int
    ingested: int
    exceptions: tuple[IngestionException, ...]


def discover_completed_game_ids(schedule: dict[str, Any], season: int) -> list[int]:
    ids = {
        int(game["gamePk"])
        for day in schedule.get("dates", [])
        for game in day.get("games", [])
        if game.get("gameType") == "R"
        and str(game.get("season")) == str(season)
        and (game.get("status") or {}).get("abstractGameState") == "Final"
    }
    return sorted(ids)


def ingest_season(
    engine: Engine,
    client: MlbStatsClient,
    cache: RawJsonCache,
    season: int,
    exception_path: Path,
) -> SeasonIngestionResult:
    if season != 2025:
        raise ValueError("Sprint 1 ingestion is restricted to season 2025")
    schedule = cache.schedule(season, lambda: client.get_regular_season_schedule(season))
    game_ids = discover_completed_game_ids(schedule, season)
    exceptions: list[IngestionException] = []
    ingested = 0
    for index, game_pk in enumerate(game_ids, start=1):
        try:
            payload = cache.game_feed(season, game_pk, lambda pk=game_pk: client.get_game_feed(pk))
            with session_scope(engine) as session:
                ingest_game(session, client, game_pk, payload=payload, strict_lineups=False)
            ingested += 1
        except Exception as error:
            LOGGER.exception("season game ingestion failed", extra={"game_pk": game_pk})
            exceptions.append(IngestionException(game_pk, type(error).__name__, str(error)))
        if index % 100 == 0 or index == len(game_ids):
            LOGGER.info(
                f"season ingestion progress {index}/{len(game_ids)}; "
                f"ingested={ingested}; exceptions={len(exceptions)}"
            )
    exception_path.parent.mkdir(parents=True, exist_ok=True)
    exception_path.write_text(
        json.dumps([asdict(item) for item in exceptions], indent=2) + "\n", encoding="utf-8"
    )
    return SeasonIngestionResult(len(game_ids), ingested, tuple(exceptions))
