"""Serving the built frontend: its files as they are, and index.html, with the
site's address filled in for link previews, for the app's own routes."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from horatio.app import serve_frontend
from horatio.config import get_settings


@pytest.fixture
def site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    (tmp_path / "index.html").write_text(
        '<meta property="og:image" content="__HORATIO_PUBLIC_URL__/preview.jpg" />'
    )
    (tmp_path / "favicon.ico").write_bytes(b"icon")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "PlayerPage-abc123.js").write_text("export {}")
    monkeypatch.setattr(get_settings(), "public_url", "https://horatio.example.org/")
    app = FastAPI()
    serve_frontend(tmp_path, app)
    return TestClient(app)


@pytest.mark.parametrize("path", ["/", "/characters/123", "/index.html"])
def test_index_names_the_site(site: TestClient, path: str) -> None:
    response = site.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'content="https://horatio.example.org/preview.jpg"' in response.text


def test_files_are_served_as_they_are(site: TestClient) -> None:
    assert site.get("/favicon.ico").content == b"icon"
    assert site.get("/api/nothing").status_code == 404


@pytest.mark.parametrize(
    "path", ["/assets/PlayerPage-old999.js", "/assets/nothing", "/missing.js", "/old.css"]
)
def test_a_missing_file_is_a_404_not_index_html(site: TestClient, path: str) -> None:
    assert site.get(path).status_code == 404


def test_the_apps_own_routes_fall_back_to_index_html(site: TestClient) -> None:
    assert site.get("/players/abc").status_code == 200
    assert site.get("/t/not-a-uuid").status_code == 200


def test_index_is_always_rechecked_and_built_files_are_kept(site: TestClient) -> None:
    for path in ["/", "/index.html", "/characters/123", "/t/not-a-uuid"]:
        assert site.get(path).headers["cache-control"] == "no-cache"
    built = site.get("/assets/PlayerPage-abc123.js")
    assert built.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert "cache-control" not in site.get("/favicon.ico").headers
