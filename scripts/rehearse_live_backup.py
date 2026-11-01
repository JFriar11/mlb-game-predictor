"""Copy local live-state data from a consistent read-only snapshot into a disposable DB.

Never clears/restores into the source database; never generates predictions.
Private data-only archive and non-secret acceptance manifest stay under ignored data/.
"""

import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from mlb_predictor.db import models
from mlb_predictor.live import verify_accepted_artifact
from mlb_predictor.live_features import build_live_feature_pair

ROOT = Path(__file__).resolve().parents[1]
LIVE_MODELS = (
    models.Team,
    models.Player,
    models.Venue,
    models.Game,
    models.GameStartingPitcher,
    models.GameStartingLineup,
    models.PlayerGameBatting,
    models.PlayerGamePitching,
    models.LiveGameState,
    models.LivePredictionRecord,
    models.OperationalState,
    models.WatcherEvent,
    models.PredictionInputSnapshot,
)
POSTGRES_IMAGE = (
    "postgres:16-alpine@sha256:57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777"
)


def run(*args: str, **kwargs: Any) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=ROOT, check=True, **kwargs)


def table_counts(session: Session) -> dict[str, int]:
    return {
        model.__tablename__: session.scalar(select(func.count()).select_from(model))
        for model in LIVE_MODELS
    }


def ledger_hash(session: Session) -> str:
    payload = {}
    for model in (
        models.LivePredictionRecord,
        models.PredictionInputSnapshot,
        models.OperationalState,
    ):
        payload[model.__tablename__] = sorted(
            json.dumps(dict(row), sort_keys=True, default=str)
            for row in session.execute(select(model.__table__)).mappings()
        )
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def choose_probe(session: Session) -> dict[str, Any]:
    reference = session.scalar(
        select(models.Game)
        .order_by(models.Game.game_date.desc(), models.Game.game_pk.desc())
        .limit(1)
    )
    if reference is None:
        raise RuntimeError("No source history exists for a meaningful feature-copy check")
    lineups = list(
        session.scalars(
            select(models.GameStartingLineup)
            .where(models.GameStartingLineup.game_pk == reference.game_pk)
            .order_by(models.GameStartingLineup.batting_order)
        )
    )
    starters = list(
        session.scalars(
            select(models.GameStartingPitcher).where(
                models.GameStartingPitcher.game_pk == reference.game_pk
            )
        )
    )
    cutoff_date = reference.game_date + timedelta(days=1)
    return {
        "home_team_id": reference.home_team_id,
        "away_team_id": reference.away_team_id,
        "venue_id": reference.venue_id,
        "home_starter_id": next(row.pitcher_id for row in starters if row.is_home),
        "away_starter_id": next(row.pitcher_id for row in starters if not row.is_home),
        "home_lineup": tuple(row.player_id for row in lineups if row.is_home),
        "away_lineup": tuple(row.player_id for row in lineups if not row.is_home),
        "as_of": datetime(cutoff_date.year, cutoff_date.month, cutoff_date.day, 12, tzinfo=UTC),
    }


def probe_features(session: Session, probe: dict[str, Any]) -> str:
    if len(probe["home_lineup"]) != 9 or len(probe["away_lineup"]) != 9:
        raise RuntimeError("Reference lineup is incomplete")
    # Synthetic next-date probe only, not a forecast/backfill for the reference game.
    pair = build_live_feature_pair(session, game_pk=0, **probe)
    return hashlib.sha256(json.dumps(pair, sort_keys=True, allow_nan=False).encode()).hexdigest()


def main() -> None:
    source_container = run(
        "docker", "compose", "ps", "-q", "postgres", capture_output=True, text=True
    ).stdout.strip()
    if not source_container or "\n" in source_container:
        raise RuntimeError("Start exactly the supported Compose postgres service first")
    port = (
        run("docker", "compose", "port", "postgres", "5432", capture_output=True, text=True)
        .stdout.strip()
        .rsplit(":", 1)[1]
    )
    source_url = f"postgresql+psycopg://mlb:mlb@127.0.0.1:{port}/mlb_predictor"
    source_engine = create_engine(source_url, isolation_level="REPEATABLE READ")
    target_name = "mlb-recovery-" + uuid.uuid4().hex[:10]
    created = False
    target_engine = None
    output = (
        ROOT
        / "data/processed/release"
        / ("recovery-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    )
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    try:
        with source_engine.connect() as connection, connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            if revision != "0014":
                raise RuntimeError(
                    "Expected accepted local schema 0014; no source migration is attempted"
                )
            exported = connection.execute(text("SELECT pg_export_snapshot()")).scalar_one()
            with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                counts = table_counts(session)
                ledger = ledger_hash(session)
                probe = choose_probe(session)
                expected_features = probe_features(session, probe)
            archive = output / "live-state.dump"
            with archive.open("xb") as stream:
                os.chmod(archive, 0o600)
                run(
                    "docker",
                    "exec",
                    source_container,
                    "pg_dump",
                    "-U",
                    "mlb",
                    "-d",
                    "mlb_predictor",
                    "--format=custom",
                    "--data-only",
                    "--no-owner",
                    "--no-acl",
                    f"--snapshot={exported}",
                    *[f"--table=public.{model.__tablename__}" for model in LIVE_MODELS],
                    stdout=stream,
                )
        # The source snapshot is now released; all remaining writes target a new container.
        run(
            "docker",
            "run",
            "-d",
            "--name",
            target_name,
            "--label",
            "mlb-purpose=acceptance",
            "-e",
            "POSTGRES_USER=mlb_acceptance",
            "-e",
            "POSTGRES_PASSWORD=acceptance_only",
            "-e",
            "POSTGRES_DB=mlb_restored",
            "-p",
            "127.0.0.1::5432",
            POSTGRES_IMAGE,
            capture_output=True,
        )
        created = True
        for _ in range(60):
            result = subprocess.run(
                [
                    "docker",
                    "exec",
                    target_name,
                    "pg_isready",
                    "-U",
                    "mlb_acceptance",
                    "-d",
                    "mlb_restored",
                ],
                capture_output=True,
                check=False,
            )
            if result.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Disposable restore database did not become ready")
        target_port = (
            run("docker", "port", target_name, "5432", capture_output=True, text=True)
            .stdout.strip()
            .rsplit(":", 1)[1]
        )
        target_url = f"postgresql+psycopg://mlb_acceptance:acceptance_only@127.0.0.1:{target_port}/mlb_restored"
        env = {**os.environ, "MLB_DATABASE_URL": target_url}
        run(sys.executable, "-m", "alembic", "upgrade", "head", env=env)
        with archive.open("rb") as stream:
            run(
                "docker",
                "exec",
                "-i",
                target_name,
                "pg_restore",
                "-U",
                "mlb_acceptance",
                "-d",
                "mlb_restored",
                "--exit-on-error",
                "--no-owner",
                "--no-acl",
                stdin=stream,
            )
        target_engine = create_engine(target_url)
        with Session(target_engine) as session:
            assert table_counts(session) == counts, "Restored live-table counts differ"
            assert ledger_hash(session) == ledger, "Prediction/launch/evidence contents differ"
            assert probe_features(session, probe) == expected_features, (
                "As-of feature values differ"
            )
            for model in (
                models.PregameFeatureSnapshot,
                models.PitchingFeatureSnapshot,
                models.EnvironmentFeatureSnapshot,
            ):
                assert session.scalar(select(func.count()).select_from(model)) == 0
        run(sys.executable, "-m", "alembic", "check", env=env)
        artifact = ROOT / "data/processed/accepted_model_v1.joblib"
        verify_accepted_artifact(artifact)
        manifest = {
            "status": "PASS",
            "source": "local_compose_read_only_snapshot",
            "schema": revision,
            "created_at": datetime.now(UTC).isoformat(),
            "table_counts": counts,
            "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "archive_bytes": archive.stat().st_size,
            "ledger_sha256": ledger,
            "feature_probe_sha256": expected_features,
            "feature_probe": {**probe, "as_of": probe["as_of"].isoformat()},
            "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            "elapsed_seconds": round(time.monotonic() - started, 1),
            "note": "Synthetic next-date feature-copy check, "
            "not a prediction or prospective evaluation.",
        }
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(json.dumps(manifest, indent=2))
        print(f"Private backup retained at {output.relative_to(ROOT)}")
    finally:
        source_engine.dispose()
        if target_engine is not None:
            target_engine.dispose()
        if created:
            run("docker", "rm", "--force", "--volumes", target_name, stdout=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
