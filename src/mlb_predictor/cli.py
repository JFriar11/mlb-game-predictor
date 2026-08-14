import argparse
import json
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import func, select

from mlb_predictor.config import get_settings
from mlb_predictor.db.models import Game, LivePredictionRecord
from mlb_predictor.db.session import create_db_engine, session_scope
from mlb_predictor.features.builder import build_2025_features, build_multiseason_features
from mlb_predictor.features.environment_builder import build_environment_features
from mlb_predictor.features.matchup_builder import build_matchup_features
from mlb_predictor.features.pitching_builder import build_pitching_features
from mlb_predictor.ingestion.cache import RawJsonCache
from mlb_predictor.ingestion.client import MlbStatsClient
from mlb_predictor.ingestion.matchups import rebuild_matchup_aggregates
from mlb_predictor.ingestion.season import ingest_season
from mlb_predictor.ingestion.service import ingest_game
from mlb_predictor.live import (
    DiscoveredGame,
    establish_launch_timestamp,
    evaluate_prospective_ledger,
    freeze_accepted_artifact,
    get_launch_timestamp,
    official_eligible,
    parse_discovered_games,
    persist_discovery,
    predict_from_features,
    save_prediction,
    settle_prediction,
    timing_classification,
)
from mlb_predictor.live_features import build_live_feature_pair
from mlb_predictor.logging import configure_logging
from mlb_predictor.modeling.calibration_evaluation import run_calibration_evaluation
from mlb_predictor.modeling.distribution_evaluation import run_distribution_evaluation
from mlb_predictor.modeling.environment_evaluation import run_environment_evaluation
from mlb_predictor.modeling.evaluation import run_sprint3_evaluation
from mlb_predictor.modeling.matchup_evaluation import run_sprint4_evaluation
from mlb_predictor.modeling.multiseason import run_multiseason_evaluation
from mlb_predictor.modeling.pitching_ablation import run_pitching_ablation
from mlb_predictor.modeling.pitching_evaluation import run_pitching_evaluation
from mlb_predictor.reporting import reconstruct_game
from mlb_predictor.validation.environment import audit_environment_features
from mlb_predictor.validation.features import audit_features
from mlb_predictor.validation.games import validate_games
from mlb_predictor.validation.matchups import audit_matchups
from mlb_predictor.validation.pitching import audit_pitching_features
from mlb_predictor.validation.season import audit_season

MANIFEST_PATH = Path(__file__).parents[2] / "config" / "sprint0_games.json"
PROJECT_ROOT = Path(__file__).parents[2]
ACCEPTED_ARTIFACT = PROJECT_ROOT / "data" / "processed" / "accepted_model_v1.joblib"


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


def _build_matchup_aggregates() -> int:
    raw_root = PROJECT_ROOT / "data" / "raw" / "mlb_stats_api"
    with session_scope(create_db_engine()) as session:
        result = rebuild_matchup_aggregates(session, raw_root, tuple(range(2021, 2026)))
    print(json.dumps(result, indent=2))
    return 0


def _build_matchup_features() -> int:
    with session_scope(create_db_engine()) as session:
        snapshots = build_matchup_features(session)
    print(f"Built {len(snapshots)} Sprint 4 feature rows, version=sprint4_v1")
    return 0


def _evaluate_matchups(output_dir: Path) -> int:
    with session_scope(create_db_engine()) as session:
        metadata = run_sprint4_evaluation(session, output_dir)
    print(f"Selected development model: {metadata['selected_development_model']}")
    print(json.dumps(metadata["ablation"], indent=2))
    return 0


def _audit_matchups(output: Path | None) -> int:
    with session_scope(create_db_engine()) as session:
        payload = audit_matchups(session).to_dict()
    rendered = json.dumps(payload, indent=2)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if payload["passed"] else 1


def _build_pitching_features() -> int:
    with session_scope(create_db_engine()) as session:
        snapshots = build_pitching_features(session)
    print(f"Built {len(snapshots)} Sprint 5 pitching rows, version=sprint5_v1")
    return 0


def _audit_pitching_features(output: Path | None) -> int:
    with session_scope(create_db_engine()) as session:
        payload = audit_pitching_features(session).to_dict()
    rendered = json.dumps(payload, indent=2)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if payload["passed"] else 1


def _evaluate_pitching(output_dir: Path) -> int:
    with session_scope(create_db_engine()) as session:
        metadata = run_pitching_evaluation(session, output_dir)
    print(json.dumps(metadata["combined_metrics"], indent=2))
    return 0


def _evaluate_pitching_ablation(output_dir: Path) -> int:
    with session_scope(create_db_engine()) as session:
        metadata = run_pitching_ablation(session, output_dir)
    summary = {
        label: {
            "poisson_deviance": result["combined"]["poisson_deviance"],
            "change": result["poisson_deviance_change"],
        }
        for label, result in metadata["results"].items()
    }
    print(json.dumps(summary, indent=2))
    return 0


def _build_environment_features() -> int:
    raw_root = PROJECT_ROOT / "data" / "raw" / "mlb_stats_api"
    with session_scope(create_db_engine()) as session:
        snapshots = build_environment_features(session, raw_root)
    print(f"Built {len(snapshots)} Sprint 6 environment rows, version=sprint6_v1")
    return 0


def _audit_environment_features(output: Path | None) -> int:
    with session_scope(create_db_engine()) as session:
        payload = audit_environment_features(session).to_dict()
    rendered = json.dumps(payload, indent=2)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if payload["passed"] else 1


def _evaluate_environment(output_dir: Path) -> int:
    with session_scope(create_db_engine()) as session:
        metadata = run_environment_evaluation(session, output_dir)
    print(
        json.dumps(
            {
                label: {
                    "poisson_deviance": result["combined"]["poisson_deviance"],
                    "change": result["poisson_deviance_change"],
                }
                for label, result in metadata["results"].items()
            },
            indent=2,
        )
    )
    return 0


def _evaluate_distributions(output_dir: Path) -> int:
    with session_scope(create_db_engine()) as session:
        metadata = run_distribution_evaluation(session, output_dir)
    print(json.dumps(metadata["combined_distribution_metrics"], indent=2))
    print(json.dumps(metadata["win_probability_metrics"], indent=2))
    return 0


def _evaluate_calibration(output_dir: Path) -> int:
    with session_scope(create_db_engine()) as session:
        metadata = run_calibration_evaluation(
            session, PROJECT_ROOT / "data" / "processed" / "sprint7", output_dir
        )
    print(f"Selected calibration: {metadata['selected_calibration']}")
    print(
        json.dumps(
            {name: value["combined"] for name, value in metadata["results"].items()}, indent=2
        )
    )
    return 0


def _discover(
    client: MlbStatsClient, requested: date, *, feeds: bool = True
) -> list[DiscoveredGame]:
    retrieved = datetime.now(UTC)
    schedule = client.get_schedule_for_date(requested)
    raw = parse_discovered_games(schedule, retrieved)
    feed_map = {g.game_pk: client.get_game_feed(g.game_pk) for g in raw} if feeds else {}
    return parse_discovered_games(schedule, retrieved, feed_map)


def _predict_date(requested: date, dry_run: bool, game_pk: int | None = None) -> int:
    settings, now = get_settings(), datetime.now(UTC)
    if not ACCEPTED_ARTIFACT.exists():
        raise FileNotFoundError(
            "Freeze accepted artifact first: mlb-predictor freeze-accepted-model"
        )
    with MlbStatsClient(
        settings.api_base_url, settings.http_timeout_seconds, settings.http_max_attempts
    ) as client:
        games = _discover(client, requested)
    if game_pk is not None:
        games = [g for g in games if g.game_pk == game_pk]
    with session_scope(create_db_engine()) as session:
        launch = get_launch_timestamp(session)
        for game in games:
            persist_discovery(session, game)
            ready = official_eligible(game, now)
            minutes, _ = timing_classification(now, game.scheduled_start_time_utc)
            print(
                f"{game.game_pk} {game.away_team_name} at {game.home_team_name} | "
                f"{game.scheduled_start_time_utc.isoformat()} | {game.status} | "
                f"starters={game.away_starter_id or 'TBD'}/{game.home_starter_id or 'TBD'} | "
                f"lineup={game.lineup_state} | minutes={minutes:.1f} | eligible={ready}"
            )
            if game.lineup_state != "confirmed":
                continue
            away, home, warnings = build_live_feature_pair(
                session,
                game_pk=game.game_pk,
                home_team_id=game.home_team_id,
                away_team_id=game.away_team_id,
                venue_id=game.venue_id or 0,
                home_starter_id=game.home_starter_id or 0,
                away_starter_id=game.away_starter_id or 0,
                home_lineup=game.home_lineup,
                away_lineup=game.away_lineup,
                as_of=now,
            )
            if not game.home_starter_id or not game.away_starter_id:
                warnings.append("missing_probable_starter")
            result = predict_from_features(away, home, ACCEPTED_ARTIFACT)
            print(
                f"  Away {result['expected_away_runs']:.2f}, "
                f"Home {result['expected_home_runs']:.2f}; "
                f"home {result['calibrated_home_win_probability']:.1%}; "
                f"tie {result['regulation_tie_probability']:.1%}"
            )
            if not dry_run:
                save_prediction(
                    session,
                    game,
                    result,
                    now,
                    official=ready,
                    warnings=warnings + ([] if ready else ["diagnostic_not_official"]),
                    cutoff=now,
                    launch=launch,
                )
    return 0


def _freeze_accepted() -> int:
    with session_scope(create_db_engine()) as session:
        result = freeze_accepted_artifact(
            session,
            ACCEPTED_ARTIFACT,
            PROJECT_ROOT / "data/processed/sprint7",
            PROJECT_ROOT / "data/processed/sprint8",
        )
    print(json.dumps(result, indent=2))
    return 0


def _settle(game_date: date) -> int:
    settings, now = get_settings(), datetime.now(UTC)
    with MlbStatsClient(
        settings.api_base_url, settings.http_timeout_seconds, settings.http_max_attempts
    ) as client:
        games = _discover(client, game_date, feeds=False)
        feeds = {g.game_pk: client.get_game_feed(g.game_pk) for g in games if "Final" in g.status}
    count = 0
    with session_scope(create_db_engine()) as session:
        for game in games:
            row = session.scalar(
                select(LivePredictionRecord).where(
                    LivePredictionRecord.game_pk == game.game_pk,
                    LivePredictionRecord.is_official.is_(True),
                )
            )
            feed = feeds.get(game.game_pk)
            if not row or not feed:
                continue
            linescore = feed.get("liveData", {}).get("linescore", {}).get("teams", {})
            settle_prediction(
                row,
                int(linescore["home"]["runs"]),
                int(linescore["away"]["runs"]),
                game.status,
                now,
            )
            count += 1
    print(f"Settled {count} official predictions")
    return 0


def _inspect_prediction(game_pk: int) -> int:
    with session_scope(create_db_engine()) as session:
        rows = list(
            session.scalars(
                select(LivePredictionRecord)
                .where(LivePredictionRecord.game_pk == game_pk)
                .order_by(LivePredictionRecord.prediction_timestamp)
            )
        )
        for row in rows:
            print(
                json.dumps(
                    {c.name: getattr(row, c.name) for c in row.__table__.columns},
                    default=str,
                    indent=2,
                )
            )
    return 0


def _evaluate_live() -> int:
    with session_scope(create_db_engine()) as session:
        print(json.dumps(evaluate_prospective_ledger(session), indent=2))
    return 0


def _launch() -> int:
    now = datetime.now(UTC)
    with session_scope(create_db_engine()) as session:
        timestamp = establish_launch_timestamp(session, now)
    print(f"Prospective launch timestamp: {timestamp.isoformat()}")
    return 0


def _daily_live(requested: date, dry_run: bool) -> int:
    result = _ingest_season(2026)
    if result:
        return result
    return _predict_date(requested, dry_run)


def _settle_live(requested: date) -> int:
    result = _settle(requested)
    if result:
        return result
    return _evaluate_live()


def main() -> int:
    parser = argparse.ArgumentParser(description="MLB predictor data tooling")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("ingest-five", help="ingest only the five-game Sprint 0 manifest")
    validate = subparsers.add_parser("validate", help="run Sprint 0 data-quality checks")
    validate.add_argument("--expected-games", type=int, default=5)
    show = subparsers.add_parser("show-game", help="print a reconstructed game")
    show.add_argument("game_pk", type=int, nargs="?")
    season_ingest = subparsers.add_parser(
        "ingest-season", help="ingest regular-season history (2021-2026)"
    )
    season_ingest.add_argument("--season", type=int, required=True, choices=range(2021, 2027))
    season_audit = subparsers.add_parser("audit-season", help="audit the normalized season")
    season_audit.add_argument("--season", type=int, required=True, choices=range(2021, 2027))
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
    subparsers.add_parser(
        "build-matchup-aggregates", help="replay cached feeds into Sprint 4 aggregates"
    )
    subparsers.add_parser(
        "build-matchup-features", help="build leakage-safe Sprint 4 matchup features"
    )
    matchup_evaluation = subparsers.add_parser(
        "evaluate-matchups", help="run Sprint 4 rolling-origin ablation"
    )
    matchup_evaluation.add_argument(
        "--output-dir", type=Path, default=Path("data/processed/sprint4")
    )
    matchup_audit = subparsers.add_parser("audit-matchups", help="audit Sprint 4 aggregates")
    matchup_audit.add_argument("--output", type=Path)
    subparsers.add_parser(
        "build-pitching-features", help="build leakage-safe Sprint 5 pitching state"
    )
    pitching_audit = subparsers.add_parser(
        "audit-pitching-features", help="audit Sprint 5 pitching state"
    )
    pitching_audit.add_argument("--output", type=Path)
    pitching_evaluation = subparsers.add_parser(
        "evaluate-pitching", help="run Sprint 5 rolling-origin component evaluation"
    )
    pitching_evaluation.add_argument(
        "--output-dir", type=Path, default=Path("data/processed/sprint5")
    )
    pitching_ablation = subparsers.add_parser(
        "evaluate-pitching-ablation", help="run the fixed Sprint 5.5 downstream ablation"
    )
    pitching_ablation.add_argument(
        "--output-dir", type=Path, default=Path("data/processed/sprint5_5")
    )
    subparsers.add_parser(
        "build-environment-features", help="build Sprint 6 cached-feed environment state"
    )
    environment_audit = subparsers.add_parser(
        "audit-environment-features", help="audit Sprint 6 environment state"
    )
    environment_audit.add_argument("--output", type=Path)
    environment_evaluation = subparsers.add_parser(
        "evaluate-environment", help="run Sprint 6 raw and modular environment evaluation"
    )
    environment_evaluation.add_argument(
        "--output-dir", type=Path, default=Path("data/processed/sprint6")
    )
    distribution_evaluation = subparsers.add_parser(
        "evaluate-distributions", help="run Sprint 7 distribution and simulation audit"
    )
    distribution_evaluation.add_argument(
        "--output-dir", type=Path, default=Path("data/processed/sprint7")
    )
    calibration_evaluation = subparsers.add_parser(
        "evaluate-calibration", help="run Sprint 8 nested chronological calibration audit"
    )
    calibration_evaluation.add_argument(
        "--output-dir", type=Path, default=Path("data/processed/sprint8")
    )
    subparsers.add_parser(
        "freeze-accepted-model", help="materialize the frozen accepted model artifact"
    )
    predict_date = subparsers.add_parser("predict-date", help="discover and predict eligible games")
    predict_date.add_argument("--date", type=date.fromisoformat, required=True)
    predict_date.add_argument("--dry-run", action="store_true")
    predict_date.add_argument("--game-pk", type=int)
    settle = subparsers.add_parser(
        "settle-date", help="attach final outcomes without changing forecasts"
    )
    settle.add_argument("--date", type=date.fromisoformat, required=True)
    inspect = subparsers.add_parser("inspect-prediction", help="show retained prediction snapshots")
    inspect.add_argument("game_pk", type=int)
    subparsers.add_parser("evaluate-live", help="score genuine settled prospective rows")
    subparsers.add_parser("launch-prospective", help="establish the immutable launch boundary")
    daily = subparsers.add_parser("daily-live", help="refresh state and check today's games")
    daily.add_argument("--date", type=date.fromisoformat, default=date.today())
    daily.add_argument("--dry-run", action="store_true")
    settle_live = subparsers.add_parser("settle-live", help="settle a date and update ledger")
    settle_live.add_argument("--date", type=date.fromisoformat, default=date.today())
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
    if args.command == "build-matchup-aggregates":
        return _build_matchup_aggregates()
    if args.command == "build-matchup-features":
        return _build_matchup_features()
    if args.command == "evaluate-matchups":
        return _evaluate_matchups(args.output_dir)
    if args.command == "audit-matchups":
        return _audit_matchups(args.output)
    if args.command == "build-pitching-features":
        return _build_pitching_features()
    if args.command == "audit-pitching-features":
        return _audit_pitching_features(args.output)
    if args.command == "evaluate-pitching":
        return _evaluate_pitching(args.output_dir)
    if args.command == "evaluate-pitching-ablation":
        return _evaluate_pitching_ablation(args.output_dir)
    if args.command == "build-environment-features":
        return _build_environment_features()
    if args.command == "audit-environment-features":
        return _audit_environment_features(args.output)
    if args.command == "evaluate-environment":
        return _evaluate_environment(args.output_dir)
    if args.command == "evaluate-distributions":
        return _evaluate_distributions(args.output_dir)
    if args.command == "evaluate-calibration":
        return _evaluate_calibration(args.output_dir)
    if args.command == "freeze-accepted-model":
        return _freeze_accepted()
    if args.command == "predict-date":
        return _predict_date(args.date, args.dry_run, args.game_pk)
    if args.command == "settle-date":
        return _settle(args.date)
    if args.command == "inspect-prediction":
        return _inspect_prediction(args.game_pk)
    if args.command == "evaluate-live":
        return _evaluate_live()
    if args.command == "launch-prospective":
        return _launch()
    if args.command == "daily-live":
        return _daily_live(args.date, args.dry_run)
    if args.command == "settle-live":
        return _settle_live(args.date)
    return _show_game(args.game_pk)
