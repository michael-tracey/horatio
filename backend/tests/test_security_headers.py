"""Every answer forbids other sites to frame Horatio (issue #1061), errors included."""

from collections.abc import Callable

from fastapi.testclient import TestClient
from httpx2 import Response


def assert_unframeable(response: Response) -> None:
    assert response.headers["content-security-policy"] == "frame-ancestors 'none'"
    assert response.headers["x-frame-options"] == "DENY"


def test_answers_and_errors_forbid_framing(client_for: Callable[[], TestClient]) -> None:
    client = client_for()

    ok = client.get("/health")
    missing = client.get("/no-such-thing")
    signed_out = client.get("/auth/me")

    assert (ok.status_code, missing.status_code, signed_out.status_code) == (200, 404, 401)
    for response in (ok, missing, signed_out):
        assert_unframeable(response)


def test_the_csrf_refusal_forbids_framing(client_for: Callable[[], TestClient]) -> None:
    client = client_for()
    del client.headers["X-Horatio"]

    refused = client.post("/auth/logout")

    assert refused.status_code == 403
    assert_unframeable(refused)
