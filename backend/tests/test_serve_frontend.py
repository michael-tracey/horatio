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
