"""Each person's settings (issue #100): defaults, changes, and what is kept."""

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import User
from tests.api_helpers import sign_up


def test_settings_start_at_their_defaults(client_for: Callable[[], TestClient]) -> None:
    person = sign_up(client_for, "settler")
    shown = person.client.get("/auth/me").json()["preferences"]
    assert shown["ratings"] == "numbers"
    assert shown["quick_notes"] is True
    assert shown["time_zone"] is None
    assert person.client.get("/preferences").json() == shown


def test_changing_a_setting_keeps_the_rest(
    client_for: Callable[[], TestClient], session: Session
) -> None:
    person = sign_up(client_for, "settler")
    changed = person.client.patch(
        "/preferences", json={"ratings": "pips", "time_zone": "America/New_York"}
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["ratings"] == "pips"
    assert changed.json()["paper"] == "letter"
    assert person.client.get("/auth/me").json()["preferences"]["time_zone"] == "America/New_York"

    # Only what differs from the default is kept on the account.
    person.client.patch("/preferences", json={"ratings": "numbers"})
    user = session.scalars(select(User).where(User.email == person.email)).one()
    session.refresh(user)
    assert user.preferences == {"time_zone": "America/New_York"}


def test_unknown_settings_and_values_are_refused(client_for: Callable[[], TestClient]) -> None:
    person = sign_up(client_for, "settler")
    for body, says in (
        ({"colour": "pink"}, "No such setting: colour."),
        ({"time_zone": "Mars/Olympus"}, "Mars/Olympus is not a time zone Horatio knows."),
    ):
        refused = person.client.patch("/preferences", json=body)
        assert refused.status_code == 422
        assert refused.json()["detail"] == says
    assert person.client.patch("/preferences", json={"ratings": "stars"}).status_code == 422


def test_a_stored_value_no_longer_allowed_falls_back(
    client_for: Callable[[], TestClient], session: Session
) -> None:
    person = sign_up(client_for, "settler")
    user = session.scalars(select(User).where(User.email == person.email)).one()
    user.preferences = {"ratings": "stars", "paper": "a4", "retired_setting": 1}
    session.flush()
    shown = person.client.get("/preferences").json()
    assert (shown["ratings"], shown["paper"]) == ("numbers", "a4")


def test_settings_need_a_sign_in(client_for: Callable[[], TestClient]) -> None:
    assert client_for().get("/preferences").status_code == 401
