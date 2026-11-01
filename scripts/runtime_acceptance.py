"""Exercise migrations, persistence, recovery, and an optional built runtime image.

Creates and removes only its own disposable PostgreSQL container. No project
volumes, existing database URLs, external MLB services, or real predictions are used.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import MetaData, create_engine, select, text

ROOT = Path(__file__).resolve().parents[1]
POSTGRES_IMAGE = (
    "postgres:16-alpine@sha256:57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777"
)


def run(*args: str, **kwargs: Any) -> subprocess.CompletedProcess:
    """Run an argument vector without invoking a shell."""
    return subprocess.run(args, check=True, cwd=ROOT, **kwargs)


def snapshot(url: str) -> dict[str, Any]:
    """Hash all table rows and sequence state for a full logical restore comparison."""
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            metadata = MetaData()
            metadata.reflect(connection)
            tables = {}
            for table in metadata.sorted_tables:
                rows = [dict(row) for row in connection.execute(select(table)).mappings()]
                serialized = sorted(json.dumps(r, sort_keys=True, default=str) for r in rows)
                tables[table.name] = {
                    "rows": len(rows),
                    "sha256": hashlib.sha256("\n".join(serialized).encode()).hexdigest(),
                }
            sequences = [
                dict(row)
                for row in connection.execute(
                    text(
                        "SELECT sequencename, last_value FROM pg_sequences "
                        "WHERE schemaname = 'public' ORDER BY sequencename"
                    )
                ).mappings()
            ]
            return {"tables": tables, "sequences": sequences}
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", help="also smoke-test an already-built runtime image")
    parser.add_argument(
        "--artifact", type=Path, default=ROOT / "data/processed/accepted_model_v1.joblib"
    )
    args = parser.parse_args()
    if args.image and not args.artifact.is_file():
        parser.error("--image requires the trusted frozen --artifact; no refitting is performed")
    name = "mlb-acceptance-" + uuid.uuid4().hex[:12]
    created = False
    api_created = False
    api_name = name + "-api"
    started = time.monotonic()
    try:
        run(
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--label",
            "mlb-purpose=acceptance",
            "-e",
            "POSTGRES_USER=mlb_acceptance",
            "-e",
            "POSTGRES_PASSWORD=acceptance_only",
            "-e",
            "POSTGRES_DB=mlb_acceptance",
            "-p",
            "127.0.0.1::5432",
            POSTGRES_IMAGE,
            capture_output=True,
        )
        created = True
        for _ in range(60):
            ready = subprocess.run(
                [
                    "docker",
                    "exec",
                    name,
                    "pg_isready",
                    "-U",
                    "mlb_acceptance",
                    "-d",
                    "mlb_acceptance",
                ],
                capture_output=True,
                check=False,
            )
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("disposable PostgreSQL did not become ready within 60 seconds")
        port = (
            run("docker", "port", name, "5432", capture_output=True, text=True)
            .stdout.strip()
            .rsplit(":", 1)[1]
        )
        url = f"postgresql+psycopg://mlb_acceptance:acceptance_only@127.0.0.1:{port}/mlb_acceptance"
        env = {**os.environ, "MLB_DATABASE_URL": url, "MLB_ACCEPTANCE_DATABASE_URL": url}
        # The fixture insists on an empty migrated database; rerunning this command
        # always creates a new container rather than clearing an existing database.
        run(sys.executable, "-m", "alembic", "upgrade", "head", env=env)
        run(sys.executable, "-m", "alembic", "upgrade", "head", env=env)
        run(sys.executable, "-m", "alembic", "check", env=env)
        run(sys.executable, "-m", "pytest", "tests/integration", "-q", env=env)
        before = snapshot(url)
        dump = run(
            "docker",
            "exec",
            name,
            "pg_dump",
            "-U",
            "mlb_acceptance",
            "-d",
            "mlb_acceptance",
            "--format=custom",
            "--no-owner",
            "--no-acl",
            capture_output=True,
        ).stdout
        run("docker", "exec", name, "createdb", "-U", "mlb_acceptance", "mlb_restored")
        run(
            "docker",
            "exec",
            "-i",
            name,
            "pg_restore",
            "-U",
            "mlb_acceptance",
            "-d",
            "mlb_restored",
            "--exit-on-error",
            "--no-owner",
            "--no-acl",
            input=dump,
        )
        restored_url = url.rsplit("/", 1)[0] + "/mlb_restored"
        assert snapshot(restored_url) == before, "restored tables or sequences differ"
        run(sys.executable, "-m", "alembic", "check", env={**env, "MLB_DATABASE_URL": restored_url})
        if args.image:
            runtime_url = (
                "postgresql+psycopg://mlb_acceptance:acceptance_only@127.0.0.1:5432/mlb_acceptance"
            )
            base = [
                "docker",
                "run",
                "--rm",
                "--network",
                f"container:{name}",
                "-e",
                f"MLB_DATABASE_URL={runtime_url}",
                "-v",
                f"{args.artifact.resolve()}:/app/data/processed/accepted_model_v1.joblib:ro",
            ]
            run(
                *base,
                "--entrypoint",
                "mlb-predictor",
                args.image,
                "--help",
                stdout=subprocess.DEVNULL,
            )
            run(*base, "--entrypoint", "python", args.image, "-m", "pip", "check")
            run(*base, "--entrypoint", "alembic", args.image, "check")
            output = run(
                *base,
                "--entrypoint",
                "python",
                args.image,
                "scripts/verify_runtime.py",
                capture_output=True,
                text=True,
            )
            smoke = json.loads(output.stdout)
            assert smoke["status"] == "PASS"
            host_output = run(
                sys.executable,
                "scripts/verify_runtime.py",
                env={
                    **env,
                    "MLB_ARTIFACT_PATH": str(args.artifact.resolve()),
                },
                capture_output=True,
                text=True,
            )
            host_smoke = json.loads(host_output.stdout)
            # Floating point kernels can differ by platform; require close numerical
            # agreement for every nested prediction value, not byte-identical floats.
            import numpy as np

            def compare(left: Any, right: Any) -> None:
                if isinstance(left, dict):
                    assert left.keys() == right.keys()
                    for key in left:
                        compare(left[key], right[key])
                elif isinstance(left, list):
                    assert len(left) == len(right)
                    for a, b in zip(left, right, strict=True):
                        compare(a, b)
                else:
                    assert np.isclose(left, right, rtol=1e-9, atol=1e-12), (left, right)

            compare(smoke["synthetic_inference"], host_smoke["synthetic_inference"])
            run(
                "docker",
                "run",
                "--detach",
                "--name",
                api_name,
                "--label",
                "mlb-purpose=acceptance",
                "--network",
                f"container:{name}",
                "-e",
                f"MLB_DATABASE_URL={runtime_url}",
                "-v",
                f"{args.artifact.resolve()}:/app/data/processed/accepted_model_v1.joblib:ro",
                "--entrypoint",
                "mlb-predictor-api",
                args.image,
                capture_output=True,
            )
            api_created = True
            run("docker", "exec", api_name, "python", "scripts/verify_api.py")
            assert snapshot(url) == before, "runtime smoke unexpectedly wrote database state"
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "migrations_and_persistence": "PASS",
                    "backup_restore": "PASS",
                    "table_count": len(before["tables"]),
                    "runtime_image": args.image or "not_checked",
                    "http_api": "PASS" if args.image else "not_checked",
                    "elapsed_seconds": round(time.monotonic() - started, 1),
                },
                indent=2,
            )
        )
    finally:
        if api_created:
            run("docker", "rm", "--force", "--volumes", api_name, stdout=subprocess.DEVNULL)
        if created:
            run("docker", "rm", "--force", "--volumes", name, stdout=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
