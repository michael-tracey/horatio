"""Signing up, in and out."""

from collections.abc import Callable

import bcrypt
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import User
from tests.api_helpers import PASSWORD, sign_up


def test_signing_up_signs_you_in(client_for: Callable[[], TestClient]) -> None:
    person = sign_up(client_for, "agnes")

    me = person.client.get("/auth/me")

    assert me.status_code == 200
    assert me.json()["email"] == "agnes@example.com"
    assert me.json()["is_custodian"] is False


def test_the_session_cookie_is_http_only(client_for: Callable[[], TestClient]) -> None:
    response = client_for().post(
        "/auth/signup",
        json={"email": "a@example.com", "password": PASSWORD, "display_name": "A"},
    )

    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "path=/;" in cookie or cookie.endswith("path=/")


def test_one_account_per_email_regardless_of_case(client_for: Callable[[], TestClient]) -> None:
    sign_up(client_for, "agnes")

    response = client_for().post(
        "/auth/signup",
        json={"email": "AGNES@example.com", "password": PASSWORD, "display_name": "Again"},
    )

    assert response.status_code == 409


def test_short_passwords_are_refused(client_for: Callable[[], TestClient]) -> None:
    response = client_for().post(
        "/auth/signup",
        json={"email": "a@example.com", "password": "short", "display_name": "A"},
    )

    assert response.status_code == 422


def test_signing_in(client_for: Callable[[], TestClient]) -> None:
    sign_up(client_for, "agnes")
    client = client_for()

    response = client.post("/auth/login", json={"login": "Agnes@example.com", "password": PASSWORD})

    assert response.status_code == 200
    assert client.get("/auth/me").status_code == 200


def test_a_wrong_password_and_an_unknown_email_look_the_same(
    client_for: Callable[[], TestClient],
) -> None:
    sign_up(client_for, "agnes")

    wrong_password = client_for().post(
        "/auth/login", json={"login": "agnes@example.com", "password": "not my password"}
    )
    no_account = client_for().post(
        "/auth/login", json={"login": "nobody@example.com", "password": PASSWORD}
    )

    assert wrong_password.status_code == no_account.status_code == 401
    assert wrong_password.json() == no_account.json()


def test_signing_out_ends_the_session(client_for: Callable[[], TestClient]) -> None:
    person = sign_up(client_for, "agnes")
    cookie = person.client.cookies.get("horatio_session")

    assert person.client.post("/auth/logout").status_code == 204

    # Even someone who kept a copy of the old cookie is signed out.
    replay = client_for()
    replay.cookies.set("horatio_session", cookie or "")
    assert replay.get("/auth/me").status_code == 401


def test_yorick_passwords_still_work_and_are_upgraded(
    client_for: Callable[[], TestClient], session: Session
) -> None:
    # Parse stored bcryptjs hashes, which start "$2a$".
    legacy_hash = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt(prefix=b"2a")).decode()
    session.add(
        User(email="old@example.com", display_name="Old", handle="old", password_hash=legacy_hash)
    )
    session.flush()

    response = client_for().post(
        "/auth/login", json={"login": "old@example.com", "password": PASSWORD}
    )

    assert response.status_code == 200
    user = session.scalars(select(User).where(User.email == "old@example.com")).one()
    assert user.password_hash is not None
    assert user.password_hash.startswith("$argon2id$")


def test_changes_need_the_csrf_header(client_for: Callable[[], TestClient]) -> None:
    client = client_for()
    del client.headers["X-Horatio"]

    response = client.post(
        "/auth/signup",
        json={"email": "a@example.com", "password": PASSWORD, "display_name": "A"},
    )

    assert response.status_code == 403
    assert client.get("/health").status_code == 200


def test_signed_out_requests_are_refused(client_for: Callable[[], TestClient]) -> None:
    assert client_for().get("/characters").status_code == 401
