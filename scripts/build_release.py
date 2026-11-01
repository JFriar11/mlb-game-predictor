"""Build a local private release image and save a non-secret review manifest."""

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from mlb_predictor.live import (
    ACCEPTED_ARTIFACT_SHA256,
    MODEL_VERSION,
    code_version,
    verify_accepted_artifact,
)

ROOT = Path(__file__).resolve().parents[1]


def source_hash() -> str:
    """Fingerprint only declared build inputs, excluding secrets and generated data."""
    selected = [
        ROOT / name
        for name in (
            "Dockerfile",
            ".dockerignore",
            "pyproject.toml",
            "README.md",
            "alembic.ini",
            "frontend/package.json",
            "frontend/package-lock.json",
            "frontend/index.html",
            "frontend/tsconfig.json",
            "frontend/vite.config.ts",
            "scripts/verify_runtime.py",
            "scripts/verify_api.py",
        )
    ]
    for directory in ("src", "migrations", "config", "requirements", "frontend/src"):
        selected.extend(
            path
            for path in (ROOT / directory).rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix not in {".pyc", ".pyo"}
        )
    digest = hashlib.sha256()
    for path in sorted(set(selected)):
        digest.update(str(path.relative_to(ROOT)).encode() + b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="mlb-predictor:release-local")
    parser.add_argument(
        "--artifact", type=Path, default=ROOT / "data/processed/accepted_model_v1.joblib"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "data/processed/release/manifest.json"
    )
    args = parser.parse_args()
    verify_accepted_artifact(args.artifact)
    revision = code_version()
    source = source_hash()
    subprocess.run(
        [
            "docker",
            "build",
            "--target",
            "release",
            "--build-arg",
            f"SOURCE_REVISION={revision}",
            "--secret",
            f"id=accepted_model,src={args.artifact.resolve()}",
            "-t",
            args.image,
            ".",
        ],
        cwd=ROOT,
        check=True,
    )
    if source_hash() != source:
        raise RuntimeError("Build inputs changed during release preparation; rebuild before review")
    image_id = subprocess.run(
        ["docker", "image", "inspect", args.image, "--format", "{{.Id}}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    payload = {
        "created_at": datetime.now(UTC).isoformat(),
        "image": args.image,
        "local_image_id": image_id,
        "source_revision": revision,
        "source_tree_sha256": source,
        "model_version": MODEL_VERSION,
        "artifact_sha256": ACCEPTED_ARTIFACT_SHA256,
        "publication_status": "local_only_not_pushed",
        "registry_digest": None,
        "note": "A local Docker image ID is not a registry manifest digest. "
        "Capture the latter only after approved publication.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
