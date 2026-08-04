import argparse
import json
from pathlib import Path

from sqlalchemy import func, select

from mlb_predictor.config import get_settings
from mlb_predictor.db.models import Game
from mlb_predictor.db.session import create_db_engine, session_scope
from mlb_predictor.features.builder import build_2025_features, build_multiseason_features
from mlb_predictor.ingestion.cache import RawJsonCache
from mlb_predictor.ingestion.client import MlbStatsClient
from mlb_predictor.ingestion.season import ingest_season
from mlb_predictor.ingestion.service import ingest_game
from mlb_predictor.logging import configure_logging
from mlb_predictor.modeling.evaluation import run_sprint3_evaluation
from mlb_predictor.modeling.multiseason import run_multiseason_evaluation
from mlb_predictor.reporting import reconstruct_game
from mlb_predictor.validation.features import audit_features
from mlb_predictor.validation.games import validate_games
from mlb_predictor.validation.season import audit_season

MANIFEST_PATH = Path(__file__).parents[2] / "config" / "sprint0_games.json"
PROJECT_ROOT = Path(__file__).parents[2]


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


def _ingest_season(season: int) -> int:
    settings = get_settings()
    engine = create_db_engine()
    cache = RawJsonCache(PROJECT_ROOT / "data" / "raw" / "mlb_stats_api")
    exception_path = PROJECT_ROOT / "data" / "interim" / f"{season}_ingestion_exceptions.json"
    with MlbStatsClient(
        settings.api_base_url, settings.http_timeout_seconds, settings.http_max_attempts
    ) as client:
        result = ingest_season(engine, client, cache, season, exception_path)
    print(
        f"Season {season}: discovered={result.discovered}, ingested={result.ingested}, "
        f"exceptions={len(result.exceptions)}"
    )
    print(f"Exception report: {exception_path}")
    return 0 if not result.exceptions else 1


def _audit_season(season: int, output: Path | None) -> int:
    with session_scope(create_db_engine()) as session:
        audit = audit_season(session, season)
        payload = audit.to_dict()
    exception_path = PROJECT_ROOT / "data" / "interim" / f"{season}_ingestion_exceptions.json"
    exceptions = json.loads(exception_path.read_text()) if exception_path.exists() else []
    payload["exceptions"] = exceptions
    payload["exception_count"] = len(exceptions)
    payload["passed"] = payload["passed"] and not exceptions
    rendered = json.dumps(payload, indent=2, default=str)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
        print(f"Audit report: {output}")
    print(rendered)
    return 0 if audit.passed else 1


def _freeze_raw(season: int, output: Path | None) -> int:
    cache = RawJsonCache(PROJECT_ROOT / "data" / "raw" / "mlb_stats_api")
    manifest = cache.build_manifest(season)
    output = output or PROJECT_ROOT / "data" / "interim" / f"{season}_raw_manifest.json"
    with session_scope(create_db_engine()) as session:
        expected_files = (
            int(
                session.scalar(select(func.count()).select_from(Game).where(Game.season == season))
                or 0
            )
            + 1
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        f"Raw manifest: files={manifest['file_count']}, bytes={manifest['total_bytes']}, "
        f"output={output}"
    )
    # A cache may intentionally retain non-played schedule entries fetched before their
    # cancellation status was classified; manifests hash all source objects, including them.
    return 0 if manifest["file_count"] >= expected_files else 1


def _build_features(season: int, feature_version: str) -> int:
    if season != 2025:
        raise ValueError("Sprint 2 feature construction is restricted to season 2025")
    with session_scope(create_db_engine()) as session:
        snapshots = build_2025_features(session, feature_version)
    print(f"Built {len(snapshots)} feature rows for {season}, version={feature_version}")
    return 0


def _build_multiseason_features(feature_version: str) -> int:
    if feature_version == "sprint2_v1":
        raise ValueError("The immutable Sprint 2 feature version cannot be rebuilt here")
    variants = {
        "sprint3_5_v1": {"offseason_decay": 0.5, "carry_prior_history": True},
        "sprint3_5_nodecay_v1": {"offseason_decay": None, "carry_prior_history": True},
        "sprint3_5_coldstart_v1": {
            "offseason_decay": None,
            "carry_prior_history": False,
        },
    }
    if feature_version not in variants:
        raise ValueError(f"Unsupported multi-season feature version: {feature_version}")
    with session_scope(create_db_engine()) as session:
        snapshots = build_multiseason_features(
            session, feature_version, **variants[feature_version]
        )
    print(f"Built {len(snapshots)} multi-season feature rows, version={feature_version}")
    return 0


def _audit_features(feature_version: str, output: Path | None) -> int:
    with session_scope(create_db_engine()) as session:
        audit = audit_features(session, feature_version)
        payload = audit.to_dict()
    rendered = json.dumps(payload, indent=2, default=str)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
        print(f"Feature audit: {output}")
    print(rendered)
    return 0 if audit.passed else 1


def _evaluate_baselines(output_dir: Path) -> int:
    with session_scope(create_db_engine()) as session:
        metadata = run_sprint3_evaluation(session, output_dir)
    print(f"Selected on development folds: {metadata['selected_model']}")
    print(f"Artifacts: {output_dir}")
    print(json.dumps(metadata["final_test_metrics"], indent=2))
    return 0


def _evaluate_multiseason(output_dir: Path) -> int:
    with session_scope(create_db_engine()) as session:
        metadata = run_multiseason_evaluation(session, output_dir)
    print(f"Selected development model: {metadata['selected_development_model']}")
    print(f"Artifacts: {output_dir}")
    print(json.dumps(metadata["model_metrics"], indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="MLB predictor data tooling")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("ingest-five", help="ingest only the five-game Sprint 0 manifest")
    validate = subparsers.add_parser("validate", help="run Sprint 0 data-quality checks")
    validate.add_argument("--expected-games", type=int, default=5)
    show = subparsers.add_parser("show-game", help="print a reconstructed game")
    show.add_argument("game_pk", type=int, nargs="?")
    season_ingest = subparsers.add_parser(
        "ingest-season", help="ingest one regular season (2021-2025)"
    )
    season_ingest.add_argument("--season", type=int, required=True, choices=range(2021, 2026))
    season_audit = subparsers.add_parser("audit-season", help="audit the normalized season")
    season_audit.add_argument("--season", type=int, required=True, choices=range(2021, 2026))
    season_audit.add_argument("--output", type=Path)
    raw_freeze = subparsers.add_parser("freeze-raw", help="checksum one season's raw layer")
    raw_freeze.add_argument("--season", type=int, required=True, choices=range(2021, 2026))
    raw_freeze.add_argument("--output", type=Path)
    feature_build = subparsers.add_parser(
        "build-features", help="build leakage-controlled 2025 pregame snapshots"
    )
    feature_build.add_argument("--season", type=int, default=2025, choices=[2025])
    feature_build.add_argument("--version", default="sprint2_v1")
    multiseason_build = subparsers.add_parser(
        "build-multiseason-features", help="build leakage-safe 2021-2025 snapshots"
    )
    multiseason_build.add_argument("--version", default="sprint3_5_v1")
    feature_audit = subparsers.add_parser(
        "audit-features", help="audit feature coverage and as-of cutoffs"
    )
    feature_audit.add_argument("--version", default="sprint2_v1")
    feature_audit.add_argument("--output", type=Path)
    baseline_evaluation = subparsers.add_parser(
        "evaluate-baselines", help="run Sprint 3 chronological baseline evaluation"
    )
    baseline_evaluation.add_argument(
        "--output-dir", type=Path, default=Path("data/processed/sprint3")
    )
    multiseason_evaluation = subparsers.add_parser(
        "evaluate-multiseason", help="run Sprint 3.5 rolling-origin evaluation"
    )
    multiseason_evaluation.add_argument(
        "--output-dir", type=Path, default=Path("data/processed/sprint3_5")
    )
    args = parser.parse_args()
    configure_logging(get_settings().log_level)
    if args.command == "ingest-five":
        return _ingest_five()
    if args.command == "validate":
        return _validate(args.expected_games)
    if args.command == "ingest-season":
        return _ingest_season(args.season)
    if args.command == "audit-season":
        return _audit_season(args.season, args.output)
    if args.command == "freeze-raw":
        return _freeze_raw(args.season, args.output)
    if args.command == "build-features":
        return _build_features(args.season, args.version)
    if args.command == "build-multiseason-features":
        return _build_multiseason_features(args.version)
    if args.command == "audit-features":
        return _audit_features(args.version, args.output)
    if args.command == "evaluate-baselines":
        return _evaluate_baselines(args.output_dir)
    if args.command == "evaluate-multiseason":
        return _evaluate_multiseason(args.output_dir)
    return _show_game(args.game_pk)
