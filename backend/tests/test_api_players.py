"""Players in the log, player profiles, and the custodian's password reset links."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import AuditEvent, Character, PasswordReset, User
from tests.api_helpers import PASSWORD, Person, Troupe, new_character


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def troupe_log(troupe: Troupe) -> list[dict[str, Any]]:
    response = troupe.lead.client.get(f"/troupes/{troupe.id}/log")
    assert response.status_code == 200, response.text
    return response.json()


def member(troupe: Troupe, name: str = "Mr. Carbuncle") -> str:
    character_id = new_character(troupe, troupe.player, name)
    joined = troupe.player.client.post(
        f"/characters/{character_id}/troupes", json={"troupe_id": troupe.id}
    )
    assert joined.status_code == 201, joined.text
    return character_id


def profile(person: Person, user_id: str) -> dict[str, Any]:
    response = person.client.get(f"/players/{user_id}")
    assert response.status_code == 200, response.text
    return response.json()


def edit(person: Person, **changes: Any) -> Any:
    body = {"display_name": "player", "bio": None, "links": [], "discord_handle": None}
    return person.client.put("/profile", json={**body, **changes})


# --- the log ---------------------------------------------------------------------------------


def test_the_log_names_a_characters_player(troupe: Troupe) -> None:
    character_id = member(troupe)
    troupe.player.client.delete(f"/characters/{character_id}/troupes/{troupe.id}")

    messages = [e["message"] for e in troupe_log(troupe)]
    assert messages[:2] == [
        "Mr. Carbuncle (player) left the troupe.",
        "Mr. Carbuncle (player) started visiting the troupe.",
    ]
    entry = troupe_log(troupe)[0]
    assert (entry["player_id"], entry["player_name"]) == (troupe.player.id, "player")
    assert entry["actor_id"] == troupe.player.id


def test_a_player_named_as_the_actor_is_not_named_twice(troupe: Troupe) -> None:
    character_id = member(troupe)
    request = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    )
    troupe.lead.client.post(f"/approvals/{request.json()['id']}/approve", json={})

    assert [e["message"] for e in troupe_log(troupe)][:2] == [
        "lead accepted Mr. Carbuncle (player); this is its home.",
        "player asked to make this Mr. Carbuncle's home.",
    ]


def test_the_log_uses_the_players_name_as_it_is_now(troupe: Troupe) -> None:
    member(troupe)
    assert edit(troupe.player, display_name="Jane Doe").status_code == 200

    assert (
        troupe_log(troupe)[0]["message"] == "Mr. Carbuncle (Jane Doe) started visiting the troupe."
    )


def test_an_npc_has_no_player_in_the_log(troupe: Troupe) -> None:
    troupe.storyteller.client.post(f"/troupes/{troupe.id}/npcs", json={"name": "Prince Vasquez"})

    entry = troupe_log(troupe)[0]
    assert entry["message"] == "storyteller made an NPC, Prince Vasquez."
    assert entry["player_id"] is None


def test_the_roster_links_each_player(troupe: Troupe) -> None:
    member(troupe)
    roster = troupe.lead.client.get(f"/troupes/{troupe.id}/characters").json()

    assert [(r["player_name"], r["player_id"]) for r in roster] == [("player", troupe.player.id)]


# --- profiles --------------------------------------------------------------------------------


def test_anyone_signed_in_sees_a_profile_but_not_the_email(troupe: Troupe) -> None:
    edit(
        troupe.player,
        bio="Plays on Thursdays.",
        links=[{"label": "", "url": "https://www.example.org/me"}],
        discord_handle="@MrCarbuncle",
    )

    seen = profile(troupe.stranger, troupe.player.id)
    assert seen["display_name"] == "player"
    assert seen["bio"] == "Plays on Thursdays."
    assert seen["links"] == [{"label": "example.org", "url": "https://www.example.org/me"}]
    assert seen["discord_handle"] == "mrcarbuncle"
    assert seen["member_since"]
    assert seen["email"] is None
    assert profile(troupe.player, troupe.player.id)["email"] == troupe.player.email
    assert profile(troupe.custodian, troupe.player.id)["email"] == troupe.player.email
    assert troupe.stranger.client.get(f"/players/{uuid.uuid4()}").status_code == 404


def test_a_profile_lists_only_the_characters_the_viewer_may_see(troupe: Troupe) -> None:
    new_character(troupe, troupe.player, "Agnes")
    member(troupe)

    def names(person: Person) -> list[str]:
        return [c["name"] for c in profile(person, troupe.player.id)["characters"]]

    assert names(troupe.player) == ["Agnes", "Mr. Carbuncle"]
    assert names(troupe.custodian) == ["Agnes", "Mr. Carbuncle"]
    assert names(troupe.lead) == ["Mr. Carbuncle"]
    assert names(troupe.stranger) == []


@pytest.mark.parametrize(
    ("changes", "refusal"),
    [
        ({"links": [{"label": "x", "url": "javascript:alert(1)"}]}, "is not a web address"),
        (
            {"links": [{"label": "x", "url": f"https://a.example/{n}"} for n in range(7)]},
            "at most 6",
        ),
        ({"discord_handle": "no spaces please"}, "A Discord username"),
        ({"discord_handle": "two..stops"}, "A Discord username"),
        ({"bio": "x" * 2001}, "2000 characters"),
        ({"display_name": "   "}, "display name"),
    ],
)
def test_a_profile_refuses_what_it_cannot_show(
    troupe: Troupe, changes: dict[str, Any], refusal: str
) -> None:
    response = edit(troupe.player, **changes)

    assert response.status_code == 422
    assert refusal in response.json()["detail"]


def test_clearing_a_profile(troupe: Troupe) -> None:
    edit(troupe.player, bio="Hello", discord_handle="mrcarbuncle")
    cleared = edit(troupe.player, bio="  ", discord_handle="")

    assert (cleared.json()["bio"], cleared.json()["discord_handle"]) == (None, None)


def test_the_custodian_finds_people_by_name_or_email(troupe: Troupe) -> None:
    def found(q: str) -> list[str]:
        response = troupe.custodian.client.get("/players", params={"q": q})
        assert response.status_code == 200, response.text
        return [p["display_name"] for p in response.json()]

    assert found("teller") == ["storyteller"]
    assert found("") == sorted(found(""))
    assert found("player@example") == ["player"]
    assert troupe.lead.client.get("/players").status_code == 403


def test_the_custodian_filters_people_by_the_troupe_their_active_pc_is_home_in(
    troupe: Troupe,
) -> None:
    other = troupe.custodian.client.post(
        "/troupes", json={"name": "Brujah Rabble", "lead_handle": troupe.lead.handle}
    ).json()["id"]

    def found(**params: str) -> list[str]:
        response = troupe.custodian.client.get("/players", params=params)
        assert response.status_code == 200, response.text
        return [p["display_name"] for p in response.json()]

    def character(person: Person, name: str, **changes: Any) -> None:
        row = troupe.session.get_one(Character, uuid.UUID(new_character(troupe, person, name)))
        for field, value in changes.items():
            setattr(row, field, value)
        troupe.session.flush()

    here = uuid.UUID(troupe.id)
    character(troupe.player, "Home", home_troupe_id=here)
    character(troupe.lead, "Elsewhere", home_troupe_id=uuid.UUID(other))
    character(troupe.storyteller, "Retired", home_troupe_id=here, status="retired")
    character(troupe.assistant, "Building", building_troupe_id=here)
    visiting = new_character(troupe, troupe.narrator, "Visiting")
    troupe.narrator.client.post(f"/characters/{visiting}/troupes", json={"troupe_id": troupe.id})
    npc = troupe.session.get_one(Character, uuid.UUID(new_character(troupe, troupe.stranger)))
    npc.kind, npc.owner_troupe_id, npc.home_troupe_id = "npc", here, here
    npc.npc_kind, npc.npc_form = "vampire", "sheeted"
    troupe.session.flush()

    assert found(troupe_id=troupe.id) == ["player"]
    assert found(troupe_id=other) == ["lead"]
    assert found(troupe_id=troupe.id, q="play") == ["player"]
    assert found(troupe_id=troupe.id, q="lead") == []
    assert len(found()) == 7
    assert troupe.lead.client.get("/players", params={"troupe_id": troupe.id}).status_code == 403


# --- password resets -------------------------------------------------------------------------


def reset_link(troupe: Troupe, user_id: str) -> str:
    response = troupe.custodian.client.post(f"/players/{user_id}/password-reset")
    assert response.status_code == 201, response.text
    url: str = response.json()["url"]
    assert url.startswith("http://localhost:5173/reset-password/")
    return url.rsplit("/", 1)[1]


def sign_in(client: TestClient, email: str, password: str) -> int:
    return client.post("/auth/login", json={"login": email, "password": password}).status_code


def test_a_reset_link_sets_a_new_password_and_ends_other_sessions(
    troupe: Troupe, client_for: Callable[[], TestClient], session: Session
) -> None:
    token = reset_link(troupe, troupe.player.id)
    locked_out = client_for()

    assert locked_out.get(f"/auth/reset/{token}").json() == {
        "display_name": "player",
        "email": troupe.player.email,
    }
    reset = locked_out.post("/auth/reset", json={"token": token, "password": "a new password!"})
    assert reset.status_code == 200, reset.text
    assert locked_out.get("/auth/me").json()["id"] == troupe.player.id
    # The session they had elsewhere is over, and the old password no longer works.
    assert troupe.player.client.get("/auth/me").status_code == 401
    assert sign_in(client_for(), troupe.player.email, PASSWORD) == 401
    assert sign_in(client_for(), troupe.player.email, "a new password!") == 200
    # A link works once.
    again = client_for().post("/auth/reset", json={"token": token, "password": "another one!!"})
    assert again.status_code == 404
    # One transaction gives every event the same created_at; ids (UUID v7) keep their order.
    actions = list(
        session.scalars(
            select(AuditEvent.action)
            .where(AuditEvent.action.startswith("account."))
            .order_by(AuditEvent.id)
        )
    )
    assert actions == ["account.reset_link", "account.password_reset"]


def test_only_the_custodian_makes_reset_links(troupe: Troupe) -> None:
    response = troupe.lead.client.post(f"/players/{troupe.player.id}/password-reset")

    assert response.status_code == 403


def test_a_new_link_cancels_the_old_one(
    troupe: Troupe, client_for: Callable[[], TestClient]
) -> None:
    old = reset_link(troupe, troupe.player.id)
    reset_link(troupe, troupe.player.id)

    assert client_for().get(f"/auth/reset/{old}").status_code == 404


def test_a_link_expires_after_a_day(
    troupe: Troupe, client_for: Callable[[], TestClient], session: Session
) -> None:
    token = reset_link(troupe, troupe.player.id)
    session.scalars(select(PasswordReset)).one().expires_at = datetime.now(UTC) - timedelta(
        minutes=1
    )
    session.flush()

    response = client_for().post("/auth/reset", json={"token": token, "password": "too late now"})
    assert response.status_code == 404
    assert "Ask for a new one" in response.json()["detail"]


def test_a_reset_gives_a_discord_only_account_a_password(
    troupe: Troupe, client_for: Callable[[], TestClient], session: Session
) -> None:
    user = User(
        email="discord@example.com",
        display_name="Discord Only",
        handle="discord_only",
        password_hash=None,
    )
    session.add(user)
    session.flush()
    token = reset_link(troupe, str(user.id))

    reset = client_for().post("/auth/reset", json={"token": token, "password": "first password"})
    assert reset.status_code == 200, reset.text
    assert sign_in(client_for(), "discord@example.com", "first password") == 200


def test_a_new_password_is_long_enough(
    troupe: Troupe, client_for: Callable[[], TestClient]
) -> None:
    token = reset_link(troupe, troupe.player.id)

    assert (
        client_for().post("/auth/reset", json={"token": token, "password": "short"}).status_code
        == 422
    )
