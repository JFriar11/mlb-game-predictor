import argparse
import json
from pathlib import Path

from sqlalchemy import select

from mlb_predictor.config import get_settings
from mlb_predictor.db.models import Game
from mlb_predictor.db.session import create_db_engine, session_scope
from mlb_predictor.ingestion.client import MlbStatsClient
from mlb_predictor.ingestion.service import ingest_game
from mlb_predictor.logging import configure_logging
from mlb_predictor.reporting import reconstruct_game
from mlb_predictor.validation.games import validate_games

MANIFEST_PATH = Path(__file__).parents[2] / "config" / "sprint0_games.json"


def _load_sprint0_ids() -> list[int]:
    payload = json.loads(MANIFEST_PATH.read_text())
    ids = [int(item["game_pk"]) for item in payload["games"]]
    if len(ids) != 5 or len(set(ids)) != 5:
        raise ValueError("Sprint 0 manifest must contain exactly five unique game IDs")
    return ids


def _ingest_five() -> int:
    settings = get_settings()
    engine = create_db_engine()
    ids = _load_sprint0_ids()
    with MlbStatsClient(
        settings.api_base_url, settings.http_timeout_seconds, settings.http_max_attempts
    ) as client:
        for game_pk in ids:
            with session_scope(engine) as session:
                ingest_game(session, client, game_pk)
    print(f"Ingested exactly {len(ids)} games: {', '.join(map(str, ids))}")
    return 0


def _validate(expected_games: int) -> int:
    with session_scope(create_db_engine()) as session:
        result = validate_games(session, expected_games)
    print(f"Validation: {'PASS' if result.passed else 'FAIL'} ({result.game_count} games)")
    for failure in result.failures:
        print(f"- {failure}")
    return 0 if result.passed else 1


def _show_game(game_pk: int | None) -> int:
    with session_scope(create_db_engine()) as session:
        if game_pk is None:
            game_pk = session.scalar(
                select(Game.game_pk).order_by(Game.game_date, Game.game_pk).limit(1)
            )
        if game_pk is None:
            raise LookupError("No games are stored")
        print(reconstruct_game(session, game_pk))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="MLB predictor Sprint 0 tooling")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("ingest-five", help="ingest only the five-game Sprint 0 manifest")
    validate = subparsers.add_parser("validate", help="run Sprint 0 data-quality checks")
    validate.add_argument("--expected-games", type=int, default=5)
    show = subparsers.add_parser("show-game", help="print a reconstructed game")
    show.add_argument("game_pk", type=int, nargs="?")
    args = parser.parse_args()
    configure_logging(get_settings().log_level)
    if args.command == "ingest-five":
        return _ingest_five()
    if args.command == "validate":
        return _validate(args.expected_games)
    return _show_game(args.game_pk)
