from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from mlb_predictor.api.app import create_app
from mlb_predictor.config import Settings
from mlb_predictor.live import code_version


def test_static_release_preserves_api_routes_and_secrets_boundary(tmp_path: Path) -> None:
    root = tmp_path / "web"
    root.mkdir()
    (root / "index.html").write_text('<html lang="en"><title>Approved dashboard</title></html>')
    (root / "assets").mkdir()
    (root / "assets/app.js").write_text("console.log('dashboard')")
    (tmp_path / ".env").write_text("PRIVATE_CREDENTIAL=not-public")
    settings = Settings(_env_file=None, web_directory=root, artifact_path=tmp_path / "missing")
    engine = create_engine("sqlite://")
    try:
        with TestClient(create_app(settings, engine)) as client:
            page = client.get("/?demo=1&date=2026-08-14")
            assert page.status_code == 200 and "Approved dashboard" in page.text
            assert page.headers["x-content-type-options"] == "nosniff"
            assert "script-src 'self'" in page.headers["content-security-policy"]
            assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
            assert client.get("/assets/app.js").status_code == 200
            assert client.get("/health/live").json() == {"status": "alive"}
            assert client.get("/api/v1/model").status_code == 200
            assert client.get("/api/v1/unknown").status_code == 404
            assert client.get("/docs").status_code == 404
            assert client.get("/redoc").status_code == 404
            assert client.get("/.env").status_code == 404
            assert client.get("/%2e%2e/.env").status_code == 404
            assert len(client.get("/openapi.json").json()["paths"]) == 5
    finally:
        engine.dispose()


def test_release_requires_a_real_dashboard_build(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="built dashboard"):
        create_app(Settings(_env_file=None, web_directory=tmp_path))


def test_explicit_release_revision_is_used_without_git(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLB_CODE_VERSION", "abc123+dirty")
    assert code_version() == "abc123+dirty"
    monkeypatch.setenv("MLB_CODE_VERSION", "invalid revision")
    with pytest.raises(ValueError):
        code_version()
