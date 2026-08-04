import gzip
import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any


class RawJsonCache:
    """Gzip-compressed, atomic raw JSON cache keyed by source path."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def get_or_fetch(
        self, relative_path: str, fetch: Callable[[], dict[str, Any]]
    ) -> dict[str, Any]:
        path = self.root / relative_path
        if path.exists():
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                payload = json.load(handle)
            if not isinstance(payload, dict):
                raise ValueError(f"Cached payload is not an object: {path}")
            return payload
        payload = fetch()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        with gzip.open(temporary, "wt", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"))
        temporary.replace(path)
        return payload

    def game_feed(
        self, season: int, game_pk: int, fetch: Callable[[], dict[str, Any]]
    ) -> dict[str, Any]:
        return self.get_or_fetch(f"{season}/games/{game_pk}.json.gz", fetch)

    def schedule(self, season: int, fetch: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        return self.get_or_fetch(f"{season}/schedule.json.gz", fetch)

    def build_manifest(self, season: int) -> dict[str, Any]:
        season_root = self.root / str(season)
        files = sorted(path for path in season_root.rglob("*.json.gz") if path.is_file())
        entries = []
        for path in files:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            entries.append(
                {
                    "path": path.relative_to(self.root).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": digest,
                }
            )
        return {
            "season": season,
            "algorithm": "sha256",
            "file_count": len(entries),
            "total_bytes": sum(item["bytes"] for item in entries),
            "files": entries,
        }
