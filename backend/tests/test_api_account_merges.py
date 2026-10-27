"""The custodian merges two accounts of the same person (#272)."""

import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.config import get_settings
from horatio.connectors import email
from horatio.models import AuditEvent, AuthIdentity, FormerHandle, User
from horatio.models import Troupe as TroupeRow
from tests.api_helpers import PASSWORD, Person, Troupe, new_character, sign_up
from tests.test_api_play import send, tap
from tests.test_api_renames import at_home, other_troupe, summaries, troupe_log, visit
from tests.test_email_connector import FakeSMTP


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def twin(client_for: Callable[[], TestClient]) -> Person:
    """The player's second account, signed up with another email: the one merged."""
    return sign_up(client_for, "twin")


@pytest.fixture
def mail(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeSMTP]:
    fake = FakeSMTP()
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "mail.example.org")
    monkeypatch.setattr(settings, "mail_from", "Horatio <horatio@example.org>")
    monkeypatch.setattr(email, "smtp_factory", fake)
    yield fake


def preview(person: Person, keep: Person, other: Person) -> Any:
    return person.client.get("/accounts/merge", params={"keep": keep.handle, "merge": other.handle})


def merge(person: Person, keep: Person, other: Person, reason: str = "Signed up twice") -> Any:
    return person.client.post(
        "/accounts/merge", json={"keep": keep.handle, "merge": other.handle, "reason": reason}
    )


def merged(troupe: Troupe, keep: Person, other: Person, reason: str = "Signed up twice") -> None:
    response = merge(troupe.custodian, keep, other, reason)
    assert response.status_code == 204, response.text


def account(troupe: Troupe, person: Person) -> User:
    user = troupe.session.get_one(User, uuid.UUID(person.id))
    troupe.session.refresh(user)
    return user


def vault(person: Person) -> list[str]:
    return [c["id"] for c in person.client.get("/characters").json()]


def staff(person: Person, troupe_id: str) -> dict[str, str]:
    """The troupe's staff, the lead's included, by handle."""
    found = person.client.get(f"/troupes/{troupe_id}/staff").json()
    return {s["handle"]: s["role"] for s in found}


def test_merging_moves_the_characters_and_staff_roles(troupe: Troupe, twin: Person) -> None:
    agnes = at_home(troupe, "Agnes Moreau", twin)
    elsewhere = other_troupe(troupe)
    visit(twin, agnes, elsewhere)
    tom = new_character(troupe, twin, "Old Tom")
    added = troupe.lead.client.put(
        f"/troupes/{troupe.id}/staff", json={"handle": twin.handle, "role": "narrator"}
    )
    assert added.status_code == 200, added.text

    merged(troupe, troupe.player, twin)

    assert set(vault(troupe.player)) >= {agnes, tom}
    assert staff(troupe.lead, troupe.id)[troupe.player.handle] == "narrator"
    assert twin.handle not in staff(troupe.lead, troupe.id)
    # Each character's log says it moved, as a character move does.
    log = [e["message"] for e in troupe.player.client.get(f"/characters/{agnes}/log").json()]
    assert log[0] == (
        f"The custodian, custodian, moved Agnes Moreau (player) from @{twin.handle} to"
        f" @{troupe.player.handle}: accounts merged (Signed up twice)"
    )


def test_the_merged_account_cannot_sign_in_and_its_handle_finds_the_other(
    troupe: Troupe, twin: Person
) -> None:
    merged(troupe, troupe.player, twin)

    # Signed out everywhere.
    assert twin.client.get("/auth/me").status_code == 401
    for login in (twin.email, twin.handle):
        signed_in = troupe.client_for().post(
            "/auth/login", json={"login": login, "password": PASSWORD}
        )
        assert signed_in.status_code == 401
    # Its handle finds the account it was merged into, for good.
    found = troupe.custodian.client.get("/handles", params={"q": twin.handle}).json()
    assert [p["handle"] for p in found["people"]] == [troupe.player.handle]
    held = troupe.session.scalars(
        select(FormerHandle).where(FormerHandle.handle == twin.handle)
    ).one()
    assert str(held.user_id) == troupe.player.id
    assert held.held_until.year == 9999
    response = troupe.lead.client.put(
        f"/troupes/{troupe.id}/staff", json={"handle": twin.handle, "role": "narrator"}
    )
    assert response.status_code == 200, response.text
    assert staff(troupe.lead, troupe.id)[troupe.player.handle] == "narrator"
    # Its profile is the other account's.
    profile = troupe.stranger.client.get(f"/players/{twin.id}").json()
    assert profile["id"] == troupe.player.id
    # It is listed and found nowhere.
    people = troupe.custodian.client.get("/players", params={"q": "twin"}).json()
    assert [p["id"] for p in people] == [troupe.player.id]
    everyone = troupe.custodian.client.get("/handles", params={"limit": 50}).json()
    assert twin.id not in [p["id"] for p in everyone["people"]]
    # No one else can take the handle.
    taken = troupe.stranger.client.put("/handle", json={"handle": twin.handle})
    assert taken.status_code == 409
    # The player can take it back as their own handle.
    account(troupe, troupe.player).handle_changed_at = None
    troupe.session.flush()
    back = troupe.player.client.put("/handle", json={"handle": twin.handle})
    assert back.status_code == 200, back.text


def test_its_email_is_kept_for_the_record_but_freed(
    troupe: Troupe, twin: Person, client_for: Callable[[], TestClient]
) -> None:
    merged(troupe, troupe.player, twin)

    assert account(troupe, twin).email == twin.email
    again = client_for().post(
        "/auth/signup",
        json={"email": twin.email, "password": PASSWORD, "display_name": "Someone new"},
    )
    assert again.status_code == 201, again.text


def test_history_keeps_the_merged_account_and_says_whom_it_was_merged_into(
    troupe: Troupe, twin: Person
) -> None:
    agnes = at_home(troupe, "Agnes Moreau", twin)

    merged(troupe, troupe.player, twin)

    entries = troupe.player.client.get(f"/characters/{agnes}/log").json()
    asked = next(e for e in entries if e["action"] == "approval.request")
    assert asked["actor_id"] == twin.id
    assert asked["actor_name"] == f"twin (merged into @{troupe.player.handle})"
    # And it follows the other account's handle when that changes.
    account(troupe, troupe.player).handle_changed_at = None
    troupe.session.flush()
    changed = troupe.player.client.put("/handle", json={"handle": "the_player"})
    assert changed.status_code == 200, changed.text
    assert account(troupe, twin).display_name == "twin (merged into @the_player)"


def test_a_clash_on_one_troupe_staff_keeps_the_higher_role(troupe: Troupe, twin: Person) -> None:
    # The player is a narrator there, the twin a storyteller.
    for person, role in ((troupe.player, "narrator"), (twin, "storyteller")):
        added = troupe.lead.client.put(
            f"/troupes/{troupe.id}/staff", json={"handle": person.handle, "role": role}
        )
        assert added.status_code == 200, added.text

    found = preview(troupe.custodian, troupe.player, twin).json()

    assert [(s["troupe"]["name"], s["role"], s["had"], s["keeps"]) for s in found["staff"]] == [
        ("Lords of the Night", "storyteller", "narrator", "storyteller")
    ]
    assert found["staff"][0]["summary"] == (
        f"its storyteller role (@{troupe.player.handle}, its narrator, is now its storyteller)"
    )
    merged(troupe, troupe.player, twin)
    roles = staff(troupe.lead, troupe.id)
    assert roles[troupe.player.handle] == "storyteller"
    assert twin.handle not in roles


def test_merging_a_lead_storyteller_makes_the_other_account_lead(
    troupe: Troupe, twin: Person
) -> None:
    # The lead's second account is the one that stays: a narrator of the troupe.
    added = troupe.lead.client.put(
        f"/troupes/{troupe.id}/staff", json={"handle": twin.handle, "role": "narrator"}
    )
    assert added.status_code == 200, added.text

    merged(troupe, twin, troupe.lead)

    row = troupe.session.get_one(TroupeRow, uuid.UUID(troupe.id))
    troupe.session.refresh(row)
    assert str(row.lead_user_id) == twin.id
    roles = staff(twin, troupe.id)
    assert roles[twin.handle] == "lead_storyteller"
    assert troupe.lead.handle not in roles


def test_sign_in_links_password_and_settings_move_where_the_other_has_none(
    troupe: Troupe, twin: Person
) -> None:
    keep = account(troupe, troupe.player)
    other = account(troupe, twin)
    # The player signed up with Google, and has no password; the twin has one, a
    # Discord link, notification settings and a bio.
    keep.password_hash = None
    troupe.session.add(AuthIdentity(user_id=keep.id, provider="google", subject="g-1"))
    troupe.session.add(AuthIdentity(user_id=other.id, provider="discord", subject="d-1"))
    other.preferences = {"email_downtime": True, "ratings": "pips"}
    other.bio = "Plays Toreador."
    keep.preferences = {"ratings": "numbers"}
    troupe.session.flush()

    found = preview(troupe.custodian, troupe.player, twin).json()
    assert found["sign_in"] == ["Discord", "password"]
    assert found["settings"] == ["notification settings", "bio"]
    merged(troupe, troupe.player, twin)

    keep = account(troupe, troupe.player)
    assert keep.preferences == {"ratings": "numbers", "email_downtime": True}
    assert keep.bio == "Plays Toreador."
    providers = troupe.session.scalars(
        select(AuthIdentity.provider).where(AuthIdentity.user_id == keep.id)
    ).all()
    assert sorted(providers) == ["discord", "google"]
    # The twin's password now signs in to the player's account.
    signed_in = troupe.client_for().post(
        "/auth/login", json={"login": troupe.player.handle, "password": PASSWORD}
    )
    assert signed_in.status_code == 200, signed_in.text
    assert signed_in.json()["id"] == troupe.player.id
    assert account(troupe, twin).password_hash is None


def test_it_is_logged_and_the_people_it_affects_are_told(
    troupe: Troupe, twin: Person, mail: FakeSMTP
) -> None:
    at_home(troupe, "Agnes Moreau", twin)
    elsewhere = other_troupe(troupe)

    merged(troupe, troupe.player, twin, "Signed up with Google and with email")

    line = (
        f"The custodian, custodian, merged @{twin.handle} into @{troupe.player.handle}, the"
        " same person, moving Agnes Moreau: Signed up with Google and with email"
    )
    assert line in troupe_log(troupe.lead, troupe.id)
    assert not any("merged" in m for m in troupe_log(troupe.stranger, elsewhere))
    record = troupe.session.scalars(
        select(AuditEvent).where(
            AuditEvent.action == "account.merged", AuditEvent.troupe_id.is_(None)
        )
    ).one()
    assert record.data["merged_id"] == twin.id
    assert record.data["kept_id"] == troupe.player.id
    assert record.data["merged_name"] == "twin"
    assert record.data["merged_email"] == twin.email
    assert len(record.data["characters"]) == 1
    assert record.data["handles"] == [twin.handle]
    # The person, in the bell and at both addresses, and the troupe's lead.
    assert summaries(troupe.player) == [
        f"The custodian merged your account @{twin.handle} into this one,"
        f" @{troupe.player.handle}: Signed up with Google and with email"
    ]
    assert summaries(troupe.lead) == [
        f"The custodian merged @{twin.handle} into @{troupe.player.handle}, the same person,"
        " moving Agnes Moreau: Signed up with Google and with email"
    ]
    assert summaries(troupe.stranger) == []
    assert sorted(m["To"].addresses[0].addr_spec for m in mail.sent) == sorted(
        [troupe.player.email, twin.email]
    )
    text = mail.sent[0].get_content()
    assert f"sign in as @{troupe.player.handle}" in text
    assert "Agnes Moreau" in text


def test_its_messages_move_to_the_bell_of_the_account_that_stays(
    troupe: Troupe, twin: Person
) -> None:
    agnes = at_home(troupe, "Agnes Moreau", twin)
    # The twin is told of a move, by way of a message to find later.
    moved = troupe.custodian.client.post(
        f"/characters/{agnes}/move", json={"handle": troupe.stranger.handle, "reason": "Test"}
    )
    assert moved.status_code == 204, moved.text
    assert len(summaries(twin)) == 1

    merged(troupe, troupe.player, twin)

    assert any(s.startswith("The custodian moved Agnes Moreau") for s in summaries(troupe.player))


def test_only_the_custodian_can_merge_accounts(troupe: Troupe, twin: Person) -> None:
    agnes = at_home(troupe, "Agnes Moreau", twin)

    for person in (troupe.lead, troupe.storyteller, troupe.player, twin, troupe.stranger):
        assert merge(person, troupe.player, twin).status_code == 403
        assert preview(person, troupe.player, twin).status_code == 403
    assert agnes in vault(twin)
    assert account(troupe, twin).merged_into_id is None


def test_a_merge_needs_a_reason_and_two_different_people(troupe: Troupe, twin: Person) -> None:
    response = merge(troupe.custodian, troupe.player, twin, " ")
    assert response.status_code == 422
    assert response.json()["detail"] == "Give a reason for the merge."
    response = merge(troupe.custodian, troupe.player, troupe.player)
    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Pick two different people: that is the same account twice."
    )
    response = troupe.custodian.client.post(
        "/accounts/merge", json={"keep": troupe.player.handle, "merge": "nobody", "reason": "x"}
    )
    assert response.status_code == 404


def test_the_custodian_account_cannot_be_merged_away(troupe: Troupe, twin: Person) -> None:
    response = merge(troupe.custodian, twin, troupe.custodian)

    assert response.status_code == 409
    assert response.json()["detail"] == (
        f"@{troupe.custodian.handle} is a custodian, so that account can't be closed."
        " Keep it instead."
    )


def test_a_game_under_way_refuses_the_merge(troupe: Troupe, twin: Person) -> None:
    agnes = at_home(troupe, "Agnes Moreau", twin)
    send(twin, agnes, tap("blood", -1))

    found = preview(troupe.custodian, troupe.player, twin).json()
    response = merge(troupe.custodian, troupe.player, twin)

    assert response.status_code == 409
    assert found["refusals"] == [
        "Agnes Moreau is in a game on the Play View. End it first with Reset for next game,"
        " so the game isn't split between two people."
    ]
    assert agnes in vault(twin)


def test_the_preview_lists_what_moves(troupe: Troupe, twin: Person) -> None:
    agnes = at_home(troupe, "Agnes Moreau", twin)
    elsewhere = other_troupe(troupe)
    visit(twin, agnes, elsewhere)

    found = preview(troupe.custodian, troupe.player, twin)

    assert found.status_code == 200, found.text
    body = found.json()
    assert body["keep"]["handle"] == troupe.player.handle
    assert body["merge"]["handle"] == twin.handle
    assert [(c["name"], [t["name"] for t in c["troupes"]]) for c in body["characters"]] == [
        ("Agnes Moreau", ["Lords of the Night", "Elsewhere"])
    ]
    assert body["handles"] == [twin.handle]
    assert body["refusals"] == []
