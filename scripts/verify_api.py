"""Real HTTP smoke check against the harness's synthetic PostgreSQL fixture."""

import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

BASE_URL = "http://127.0.0.1:8000"


def fetch(path: str, expected: int = 200, method: str = "GET") -> dict:
    """Read a local HTTP response and verify its status, including expected errors."""
    try:
        response = urlopen(Request(BASE_URL + path, method=method), timeout=2)
    except HTTPError as exc:
        response = exc
    with response:
        assert response.status == expected, (path, response.status)
        return json.load(response)


def main() -> None:
    """Exercise the running ASGI server; no forecast generation or writes."""
    for _ in range(30):
        try:
            assert fetch("/health/live")["status"] == "alive"
            break
        except (URLError, TimeoutError):
            time.sleep(1)
    else:
        raise RuntimeError("API did not become live within 30 attempts")
    assert fetch("/health/ready")["status"] == "ready"
    assert fetch("/api/v1/model")["artifact_status"] == "verified"
    predictions = fetch("/api/v1/predictions?date=2026-08-14")
    assert predictions["count"] == 1  # the fixture also has two diagnostic records
    detail = fetch("/api/v1/games/999002")
    assert detail["official_prediction"] == predictions["predictions"][0]
    assert detail["official_prediction"]["observed_outcome"]["home_team_runs"] == 5
    assert detail["official_prediction"]["explanation"]["status"] == "available"
    assert len(detail["official_prediction"]["explanation"]["factors"]) == 8
    assert detail["official_prediction"]["confidence"]["calibration"]["evaluated_games"] == 5928
    assert detail["official_prediction"]["run_ranges"]["home"]["95"]["upper"] >= 0
    assert fetch("/api/v1/predictions?date=2026-08-15")["count"] == 0
    assert fetch("/api/v1/predictions", 422)["error"]["code"] == "invalid_request"
    assert fetch("/api/v1/games/99999999", 404)["error"]["code"] == "game_not_found"
    fetch("/api/v1/games/999002", 405, "POST")
    spec = fetch("/openapi.json")
    assert len(spec["paths"]) == 5
    assert all(set(operations) == {"get"} for operations in spec["paths"].values())
    if os.environ.get("MLB_WEB_DIRECTORY"):
        with urlopen(BASE_URL + "/", timeout=2) as response:
            html = response.read().decode()
            assert "MLB Game Predictor" in html
            assert "script-src 'self'" in response.headers["Content-Security-Policy"]
            assert response.headers["X-Content-Type-Options"] == "nosniff"
        import re

        asset = re.search(r'<script[^>]+src="([^"]+)"', html).group(1)
        assert urlparse(asset).netloc == "" and asset.startswith("/assets/")
        with urlopen(BASE_URL + asset, timeout=2) as response:
            assert response.status == 200
        fetch("/api/v1/unknown", 404)
        fetch("/.env", 404)
    print(json.dumps({"status": "PASS", "http_routes": len(spec["paths"])}))


if __name__ == "__main__":
    main()
