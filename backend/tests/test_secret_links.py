"""Links with a secret in them stay out of the logs and the Referer (issue #1060).

Every route whose path holds a token or a code, in the API and in the frontend's
pages, is logged with REDACTED in its place, by the app (horatio.secret_links) and
by nginx (deploy/nginx-horatio.conf.j2) alike.
"""

import logging
import re
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.routing import iter_route_contexts
from fastapi.testclient import TestClient

from horatio.app import app
from horatio.secret_links import REDACTED, RedactSecrets, redact

ROOT = Path(__file__).resolve().parents[2]
NGINX = ROOT / "deploy" / "nginx-horatio.conf.j2"
FRONTEND_ROUTES = ROOT / "frontend" / "src" / "App.tsx"

SECRET = "s3cr3t-T0ken_abc"
SECRET_PARAM = re.compile(r"\w*token\w*|code")
PATH_PARAM = re.compile(r"{(\w+)(?::\w+)?}")


def nginx_map(variable: str) -> Callable[[str], str]:
    """The map in nginx's config that sets `variable`, as a function."""
    block = re.search(rf"map \$\S+ \${variable} \{{\n(.*?)\n\}}", NGINX.read_text(), re.S)
    assert block, f"no map for ${variable} in {NGINX.name}"
    default = re.search(r'^\s*default "?([^";]*)"?;', block.group(1), re.M)
    assert default
    rules = [
        (re.compile(pattern), re.sub(r"\$(\d)", r"\\\1", value))
        for pattern, value in re.findall(r'^\s*"~(.*)" "?([^";]*)"?;$', block.group(1), re.M)
    ]
    assert rules

    def mapped(value: str) -> str:
        for pattern, logged in rules:
            found = pattern.match(value)
            if found:
                return found.expand(logged)
        return value if default.group(1) == "$request_uri" else default.group(1)

    return mapped


nginx_uri = nginx_map("horatio_logged_uri")
nginx_referer = nginx_map("horatio_logged_referer")


def api_secret_paths() -> list[str]:
    paths = set()
    for route in iter_route_contexts(app.routes):
        path = route.path or ""
        if any(SECRET_PARAM.fullmatch(name) for name in PATH_PARAM.findall(path)):
            paths.add(
                PATH_PARAM.sub(
                    lambda m: SECRET if SECRET_PARAM.fullmatch(m.group(1)) else "x", path
                )
            )
    return sorted(paths)


def page_secret_paths() -> list[str]:
    paths = set()
    for path in re.findall(r'path="([^"]+)"', FRONTEND_ROUTES.read_text()):
        params = re.findall(r":(\w+)", path)
        if any(SECRET_PARAM.fullmatch(name) for name in params):
            paths.add(
                re.sub(
                    r":(\w+)\??",
                    lambda m: SECRET if SECRET_PARAM.fullmatch(m.group(1)) else "x",
                    path,
                )
            )
    return sorted(paths)


def test_the_routes_with_secrets_are_found() -> None:
    # If these change, check the lists still find every link with a secret.
    assert api_secret_paths() == [
        f"/api/auth/email-change/{SECRET}",
        f"/api/auth/reset/{SECRET}",
        f"/api/calendar/{SECRET}.ics",
        f"/api/checkin/{SECRET}",
        f"/api/claims/{SECRET}",
        f"/api/claims/{SECRET}/pictures/x/x",
        f"/api/unsubscribe/{SECRET}",
    ]
    assert page_secret_paths() == [
        f"/check-in/{SECRET}",
        f"/claim/{SECRET}",
        f"/confirm-email/{SECRET}",
        f"/reset-password/{SECRET}",
        f"/unsubscribe/{SECRET}",
    ]


@pytest.mark.parametrize(
    "target",
    [
        *api_secret_paths(),
        *page_secret_paths(),
        *[f"{path}?from=email" for path in page_secret_paths()],
        f"/api/discord/callback?code={SECRET}&state=x.{SECRET}",
    ],
)
def test_secrets_are_redacted_by_the_app_and_nginx_alike(target: str) -> None:
    logged = redact(target)
    assert SECRET not in logged
    assert REDACTED in logged
    assert nginx_uri(target) == logged


def test_the_rest_of_a_path_is_kept() -> None:
    assert redact(f"/api/claims/{SECRET}/pictures/abc/face.webp") == (
        f"/api/claims/{REDACTED}/pictures/abc/face.webp"
    )
    assert redact(f"/api/calendar/{SECRET}.ics") == f"/api/calendar/{REDACTED}.ics"


@pytest.mark.parametrize(
    "target",
    ["/api/calendar/links", "/claims", "/characters/abc?tab=sheet", "/api/auth/me", "/check-in"],
)
def test_other_paths_are_logged_as_they_are(target: str) -> None:
    assert redact(target) == target
    assert nginx_uri(target) == target


def test_nginx_logs_only_a_referers_origin() -> None:
    assert nginx_referer(f"https://horatio.example.org/claim/{SECRET}?x=1") == (
        "https://horatio.example.org"
    )
    assert nginx_referer("") == "-"


def test_uvicorns_access_log_is_redacted() -> None:
    access = logging.getLogger("uvicorn.access")
    assert any(isinstance(f, RedactSecrets) for f in access.filters)
    # uvicorn's own call: client, method, path and query, HTTP version, status.
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:5000", "GET", f"/api/claims/{SECRET}", "1.1", 200),
        None,
    )
    assert access.filter(record)
    assert record.getMessage() == f'127.0.0.1:5000 - "GET /api/claims/{REDACTED} HTTP/1.1" 200'


def test_no_answer_sends_a_referer(client_for: Callable[[], TestClient]) -> None:
    client = client_for()
    del client.headers["X-Horatio"]
    for response in (
        client.get("/health"),
        client.get(f"/claims/{SECRET}"),
        client.post("/auth/logout"),
    ):
        assert response.headers["referrer-policy"] == "no-referrer"
