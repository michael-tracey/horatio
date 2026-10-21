"""Handles (issue #103): what people find and see each other by, instead of
their email."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from horatio.handles import from_name
from horatio.models import FormerHandle, User
from tests.api_helpers import PASSWORD, Person, Troupe, new_character, sign_up


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def signed_up(client_for: Callable[[], TestClient], **body: Any) -> Any:
    return client_for().post(
        "/auth/signup",
        json={"email": "agnes@example.com", "password": PASSWORD, "display_name": "Agnes"} | body,
    )


def user(session: Session, person: Person) -> User:
    found = session.scalars(select(User).where(User.email == person.email)).one()
    session.refresh(found)
    return found


def a_month_passes(session: Session, person: Person) -> None:
    found = user(session, person)
    assert found.handle_changed_at is not None
    found.handle_changed_at -= timedelta(days=31)
    session.flush()


# Choosing one


def test_a_handle_chosen_at_sign_up(client_for: Callable[[], TestClient]) -> None:
    response = signed_up(client_for, handle="@Night_Owl-7")
    assert response.status_code == 201, response.text
    assert response.json()["handle"] == "Night_Owl-7"
    assert response.json()["next_handle_change"] is None


def test_without_one_a_handle_is_made_from_the_name(
    client_for: Callable[[], TestClient],
) -> None:
    first = signed_up(client_for, display_name="Agnès Fairweather").json()
    second = signed_up(
        client_for, email="other@example.com", display_name="agnes fairweather", handle=" "
    ).json()
    short = signed_up(client_for, email="al@example.com", display_name="Al").json()
    assert (first["handle"], second["handle"], short["handle"]) == (
        "agnes_fairweather",
        "agnes_fairweather2",
        "player",
    )


def test_what_a_name_makes() -> None:
    assert from_name("Mary-Jane O'Neil") == "mary-jane_o_neil"
    assert from_name("  ¡Ñandú!  ") == "nandu"
    assert from_name("李") == "player"
    assert from_name("x" * 40) == "x" * 30


@pytest.mark.parametrize(
    "handle", ["ab", "a" * 31, "night owl", "agnes@home", "agnès", "a.b.c", "<script>"]
)
def test_a_handle_is_3_to_30_letters_numbers_underscores_and_hyphens(
    client_for: Callable[[], TestClient], handle: str
) -> None:
    response = signed_up(client_for, handle=handle)
    assert response.status_code == 422
    assert response.json()["detail"] == (
        "A handle is 3 to 30 letters, numbers, underscores and hyphens."
    )


def test_handles_are_unique_regardless_of_case(client_for: Callable[[], TestClient]) -> None:
    assert signed_up(client_for, handle="NightOwl").status_code == 201
    taken = signed_up(client_for, email="other@example.com", handle="nightowl")
    assert taken.status_code == 409
    assert taken.json()["detail"] == "Someone already has the handle nightowl."


# Changing one


def test_changing_a_handle_once_in_30_days(
    client_for: Callable[[], TestClient], session: Session
) -> None:
    person = sign_up(client_for, "agnes")
    changed = person.client.put("/handle", json={"handle": "Fairweather"})
    assert changed.status_code == 200, changed.text
    assert changed.json()["handle"] == "Fairweather"
    next_change = datetime.fromisoformat(changed.json()["next_handle_change"])
    assert timedelta(days=29) < next_change - datetime.now(UTC) <= timedelta(days=30)

    again = person.client.put("/handle", json={"handle": "Someone_Else"})
    assert again.status_code == 409
    assert again.json()["detail"] == (
        f"You can change your handle again on {next_change.day} {next_change:%B %Y}."
    )
    # Only its case is no change, and allowed.
    assert person.client.put("/handle", json={"handle": "fairWeather"}).status_code == 200
    assert person.client.get("/auth/me").json()["handle"] == "fairWeather"

    a_month_passes(session, person)
    assert person.client.get("/auth/me").json()["next_handle_change"] is None
    assert person.client.put("/handle", json={"handle": "Someone_Else"}).status_code == 200


def test_a_change_is_to_a_free_handle_of_the_right_form(troupe: Troupe) -> None:
    taken = troupe.player.client.put("/handle", json={"handle": "LEAD"})
    assert taken.status_code == 409
    assert taken.json()["detail"] == "Someone already has the handle LEAD."
    assert troupe.player.client.put("/handle", json={"handle": "no"}).status_code == 422
    # Neither started the 30 days.
    assert troupe.player.client.get("/auth/me").json()["next_handle_change"] is None


def test_an_old_handle_is_held_for_its_owner(troupe: Troupe, session: Session) -> None:
    assert troupe.player.client.put("/handle", json={"handle": "agnes"}).status_code == 200

    # No one else can take it…
    taken = troupe.stranger.client.put("/handle", json={"handle": "Player"})
    assert taken.status_code == 409
    signing_up = signed_up(troupe.client_for, email="new@example.com", handle="player")
    assert signing_up.status_code == 409
    # …finding people by it still finds them…
    added = troupe.lead.client.put(
        f"/troupes/{troupe.id}/staff", json={"handle": "player", "role": "narrator"}
    )
    assert added.status_code == 200, added.text
    assert added.json()["handle"] == "agnes"
    # …and they can take it back.
    a_month_passes(session, troupe.player)
    assert troupe.player.client.put("/handle", json={"handle": "player"}).status_code == 200
    held = session.scalars(
        select(FormerHandle.handle).where(FormerHandle.user_id == troupe.player.id)
    )
    assert list(held) == ["agnes"]


def test_an_old_handle_is_free_after_90_days(troupe: Troupe, session: Session) -> None:
    assert troupe.player.client.put("/handle", json={"handle": "agnes"}).status_code == 200
    former = session.scalars(select(FormerHandle)).one()
    former.held_until = datetime.now(UTC) - timedelta(days=1)
    session.flush()

    assert troupe.stranger.client.put("/handle", json={"handle": "player"}).status_code == 200
    staff = troupe.lead.client.put(
        f"/troupes/{troupe.id}/staff", json={"handle": "player", "role": "narrator"}
    )
    assert staff.json()["user_id"] == troupe.stranger.id


def test_changing_a_handle_needs_a_sign_in(client_for: Callable[[], TestClient]) -> None:
    assert client_for().put("/handle", json={"handle": "anyone"}).status_code == 401


# Signing in


def test_signing_in_with_the_handle_or_the_email(client_for: Callable[[], TestClient]) -> None:
    assert signed_up(client_for, handle="NightOwl").status_code == 201
    for login in ("nightowl", "@NightOwl", "  NIGHTOWL ", "Agnes@Example.com"):
        client = client_for()
        response = client.post("/auth/login", json={"login": login, "password": PASSWORD})
        assert response.status_code == 200, login
        assert client.get("/auth/me").json()["handle"] == "NightOwl"


def test_a_wrong_handle_reads_like_a_wrong_password(client_for: Callable[[], TestClient]) -> None:
    assert signed_up(client_for, handle="NightOwl").status_code == 201
    no_one = client_for().post("/auth/login", json={"login": "dayowl", "password": PASSWORD})
    wrong = client_for().post("/auth/login", json={"login": "nightowl", "password": "not it"})
    assert no_one.status_code == wrong.status_code == 401
    assert no_one.json() == wrong.json() == {"detail": "Wrong email, handle or password."}


def test_an_old_handle_does_not_sign_in(
    client_for: Callable[[], TestClient],
) -> None:
    person = sign_up(client_for, "agnes")
    assert person.client.put("/handle", json={"handle": "fairweather"}).status_code == 200
    old = client_for().post("/auth/login", json={"login": "agnes", "password": PASSWORD})
    assert old.status_code == 401


# Shown in place of the email


def test_others_see_the_handle_never_the_email(troupe: Troupe) -> None:
    def profile(viewer: Person) -> dict[str, Any]:
        return viewer.client.get(f"/players/{troupe.player.id}").json()

    assert profile(troupe.stranger)["handle"] == "player"
    assert profile(troupe.stranger)["email"] is None
    assert profile(troupe.lead)["email"] is None
    assert profile(troupe.player)["email"] == troupe.player.email
    assert profile(troupe.custodian)["email"] == troupe.player.email


def test_lists_of_people_show_handles_not_emails(troupe: Troupe) -> None:
    new_character(troupe, troupe.player)
    character = troupe.player.client.get("/characters").json()[0]
    joined = troupe.player.client.post(
        f"/characters/{character['id']}/troupes", json={"troupe_id": troupe.id}
    )
    assert joined.status_code in (200, 201), joined.text
    troupe.stranger.client.post("/troupe-requests", json={"name": "Nights of Boston"})

    staff = troupe.storyteller.client.get(f"/troupes/{troupe.id}/staff").json()
    roster = troupe.storyteller.client.get(f"/troupes/{troupe.id}/characters").json()
    requests = troupe.custodian.client.get("/troupe-requests").json()
    found = troupe.player.client.get("/handles", params={"q": "s"}).json()

    assert {m["handle"] for m in staff} == {"lead", "storyteller", "assistant", "narrator"}
    assert [e["player_handle"] for e in roster] == ["player"]
    assert [r["requester_handle"] for r in requests] == ["stranger"]
    assert {p["handle"] for p in found} == {"storyteller", "stranger", "assistant", "custodian"}
    for listed in (staff, roster, requests, found):
        assert all("@example.com" not in str(row) for row in listed)


def test_the_custodian_finds_people_by_handle_and_sees_their_email(troupe: Troupe) -> None:
    assert troupe.player.client.put("/handle", json={"handle": "NightOwl"}).status_code == 200
    found = troupe.custodian.client.get("/players", params={"q": "@nightow"}).json()
    assert [(p["handle"], p["email"]) for p in found] == [("NightOwl", troupe.player.email)]
    by_email = troupe.custodian.client.get("/players", params={"q": "player@"}).json()
    assert [p["handle"] for p in by_email] == ["NightOwl"]


# Used instead of the email


def test_staff_and_leads_are_named_by_handle(troupe: Troupe) -> None:
    newcomer = sign_up(troupe.client_for, "newcomer")
    added = troupe.lead.client.put(
        f"/troupes/{troupe.id}/staff", json={"handle": "@NewComer", "role": "narrator"}
    )
    assert added.status_code == 200, added.text
    assert added.json()["user_id"] == newcomer.id

    by_email = troupe.lead.client.put(
        f"/troupes/{troupe.id}/staff", json={"handle": newcomer.email, "role": "narrator"}
    )
    assert by_email.status_code == 404
    assert by_email.json()["detail"] == "Nobody has the handle newcomer@example.com."

    made = troupe.custodian.client.post(
        "/troupes", json={"name": "Second City", "lead_handle": "newcomer"}
    )
    assert made.status_code == 201, made.text
    assert made.json()["lead_user_id"] == newcomer.id
    appointed = troupe.custodian.client.put(
        f"/troupes/{troupe.id}/lead", json={"handle": "NEWCOMER"}
    )
    assert appointed.json()["lead_user_id"] == newcomer.id
    unknown = troupe.custodian.client.post(
        "/troupes", json={"name": "Nowhere", "lead_handle": "nobody"}
    )
    assert unknown.status_code == 404


def test_finding_people_as_you_type(troupe: Troupe) -> None:
    sign_up(troupe.client_for, "Storm_Crow")
    sign_up(troupe.client_for, "stormy")

    def find(q: str) -> list[str]:
        response = troupe.narrator.client.get("/handles", params={"q": q})
        assert response.status_code == 200
        return [p["handle"] for p in response.json()]

    # Handles starting with it first, then names with it in them.
    assert find("STOR") == ["storm_crow", "stormy", "storyteller"]
    assert find("@storm_") == ["storm_crow"]
    # "_" is a character, not a wildcard.
    assert find("st_") == []
    assert find("teller") == ["storyteller"]
    assert find("  ") == []
    assert set(troupe.narrator.client.get("/handles", params={"q": "s"}).json()[0]) == {
        "id",
        "handle",
        "display_name",
    }


def test_finding_people_needs_a_sign_in(client_for: Callable[[], TestClient]) -> None:
    assert client_for().get("/handles", params={"q": "a"}).status_code == 401


# Existing accounts


def test_the_migration_gives_existing_accounts_handles(
    engine: Engine, alembic_config: Config
) -> None:
    command.downgrade(alembic_config, "0038")
    try:
        with engine.begin() as connection:
            for n, name in enumerate(["Agnes", "agnes", "Lord Ruthven", "Al", "Bo"]):
                connection.execute(
                    text(
                        "insert into users (email, display_name, created_at) "
                        "values (:email, :name, now() + make_interval(secs => :n))"
                    ),
                    {"email": f"migrated-{n}@example.com", "name": name, "n": n},
                )
        command.upgrade(alembic_config, "head")
        with engine.begin() as connection:
            handles = connection.scalars(
                text("select handle from users where email like 'migrated-%' order by created_at")
            )
            assert list(handles) == ["agnes", "agnes2", "lord_ruthven", "player", "player2"]
    finally:
        command.upgrade(alembic_config, "head")
        with engine.begin() as connection:
            connection.execute(text("delete from users where email like 'migrated-%'"))
