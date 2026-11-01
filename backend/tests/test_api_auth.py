"""Signing up, in and out."""

from collections.abc import Callable

import bcrypt
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.auth.resets import issue_reset
from horatio.models import AuditEvent, User
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


# --- changing your password --------------------------------------------------------------------

NEW_PASSWORD = "a much longer passphrase"


def sign_in_status(client_for: Callable[[], TestClient], login: str, password: str) -> int:
    return client_for().post("/auth/login", json={"login": login, "password": password}).status_code


def test_changing_your_password_needs_the_current_one(
    client_for: Callable[[], TestClient], session: Session
) -> None:
    person = sign_up(client_for, "agnes")

    response = person.client.post(
        "/auth/password", json={"current": "not my password", "password": NEW_PASSWORD}
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "That's not your current password."
    assert sign_in_status(client_for, person.email, PASSWORD) == 200
    assert sign_in_status(client_for, person.email, NEW_PASSWORD) == 401


def test_a_new_password_follows_the_sign_up_rules(client_for: Callable[[], TestClient]) -> None:
    person = sign_up(client_for, "agnes")

    short = person.client.post("/auth/password", json={"current": PASSWORD, "password": "short"})
    same = person.client.post("/auth/password", json={"current": PASSWORD, "password": PASSWORD})

    assert short.status_code == 422
    assert same.status_code == 422
    assert sign_in_status(client_for, person.email, PASSWORD) == 200


def test_a_changed_password_signs_in_and_the_old_one_does_not(
    client_for: Callable[[], TestClient], session: Session
) -> None:
    person = sign_up(client_for, "agnes")
    elsewhere = client_for()
    assert elsewhere.post(
        "/auth/login", json={"login": person.email, "password": PASSWORD}
    ).is_success

    response = person.client.post(
        "/auth/password", json={"current": PASSWORD, "password": NEW_PASSWORD}
    )

    assert response.status_code == 204
    assert sign_in_status(client_for, person.email, NEW_PASSWORD) == 200
    assert sign_in_status(client_for, person.email, PASSWORD) == 401
    # Hashed as at sign-up.
    user = session.scalars(select(User).where(User.email == person.email)).one()
    assert user.password_hash is not None and user.password_hash.startswith("$argon2id$")
    # Still signed in here, but signed out everywhere else.
    assert person.client.get("/auth/me").status_code == 200
    assert elsewhere.get("/auth/me").status_code == 401
    # And it is in the log of account events.
    logged = session.scalars(
        select(AuditEvent).where(AuditEvent.action == "account.password_changed")
    ).one()
    assert logged.actor_id == user.id


def test_changing_your_password_cancels_a_reset_link(
    client_for: Callable[[], TestClient], session: Session
) -> None:
    person = sign_up(client_for, "agnes")
    user = session.scalars(select(User).where(User.email == person.email)).one()
    token, _ = issue_reset(session, user, user)

    person.client.post("/auth/password", json={"current": PASSWORD, "password": NEW_PASSWORD})

    assert client_for().get(f"/auth/reset/{token}").status_code == 404


def test_signed_out_no_password_can_be_changed(client_for: Callable[[], TestClient]) -> None:
    response = client_for().post(
        "/auth/password", json={"current": PASSWORD, "password": NEW_PASSWORD}
    )

    assert response.status_code == 401
