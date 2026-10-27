"""The custodian moves a character from one player to another (#271)."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import AuditEvent, Character
from tests.api_helpers import Person, Troupe, new_character, sign_up
from tests.test_api_play import send, tap
from tests.test_api_renames import (
    at_home,
    character_log,
    other_troupe,
    summaries,
    troupe_log,
    visit,
)


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def heir(client_for: Callable[[], TestClient]) -> Person:
    """The player a character is moved to."""
    return sign_up(client_for, "heir")


def preview(person: Person, character_id: str, handle: str) -> Any:
    return person.client.get(f"/characters/{character_id}/move", params={"handle": handle})


def move(person: Person, character_id: str, handle: str, reason: str = "Signed up twice") -> Any:
    return person.client.post(
        f"/characters/{character_id}/move", json={"handle": handle, "reason": reason}
    )


def moved(troupe: Troupe, character_id: str, to: Person, reason: str = "Signed up twice") -> None:
    response = move(troupe.custodian, character_id, to.handle, reason)
    assert response.status_code == 204, response.text


def entries(person: Person, character_id: str) -> list[tuple[str, str | None]]:
    log = person.client.get(f"/characters/{character_id}/log").json()
    return [(e["action"], e["actor_id"]) for e in log]


def vault(person: Person) -> list[str]:
    return [c["id"] for c in person.client.get("/characters").json()]


def test_the_new_player_has_the_character_with_its_sheet_xp_and_history(
    troupe: Troupe, heir: Person
) -> None:
    agnes = at_home(troupe)
    sheet_before = troupe.player.client.get(f"/characters/{agnes}/sheet").json()
    xp_before = troupe.player.client.get(f"/characters/{agnes}/xp").json()
    log_before = entries(troupe.player, agnes)

    moved(troupe, agnes, heir)

    assert agnes in vault(heir)
    assert agnes not in vault(troupe.player)
    assert heir.client.get(f"/characters/{agnes}").json()["player_id"] == heir.id
    assert heir.client.get(f"/characters/{agnes}/sheet").json() == sheet_before
    assert heir.client.get(f"/characters/{agnes}/xp").json() == xp_before
    log = character_log(heir, agnes)
    assert log[0] == (
        f"The custodian, custodian, moved Agnes Moreau (heir) from @{troupe.player.handle}"
        f" to @{heir.handle}: Signed up twice"
    )
    # Its history comes with it as it was, each entry by whoever did it then.
    assert entries(heir, agnes)[1:] == log_before
    # The home troupe stays its home, and still has it.
    character = heir.client.get(f"/characters/{agnes}").json()
    assert character["home_troupe_id"] == troupe.id
    roster = troupe.lead.client.get(f"/troupes/{troupe.id}/characters").json()
    assert [r["player_handle"] for r in roster if r["character_id"] == agnes] == [heir.handle]


def test_the_old_player_can_no_longer_open_it(troupe: Troupe, heir: Person) -> None:
    agnes = at_home(troupe)

    moved(troupe, agnes, heir)

    assert troupe.player.client.get(f"/characters/{agnes}").status_code == 404
    assert troupe.player.client.get(f"/characters/{agnes}/sheet").status_code == 404
    renamed = troupe.player.client.patch(f"/characters/{agnes}", json={"name": "Agnes Duval"})
    assert renamed.status_code == 404


def test_both_players_and_the_lead_storyteller_are_told(troupe: Troupe, heir: Person) -> None:
    agnes = at_home(troupe)

    moved(troupe, agnes, heir, "Handed on with the troupe's blessing")

    old = troupe.player.handle
    assert summaries(troupe.player) == [
        f"The custodian moved Agnes Moreau to @{heir.handle}: Handed on with the troupe's blessing"
    ]
    assert summaries(heir) == [
        f"The custodian moved Agnes Moreau to you from @{old}: Handed on with the troupe's blessing"
    ]
    assert summaries(troupe.lead) == [
        f"The custodian moved Agnes Moreau from @{old} to @{heir.handle}:"
        " Handed on with the troupe's blessing"
    ]
    assert summaries(troupe.storyteller) == []
    assert summaries(troupe.custodian) == []


def test_it_is_logged_in_each_of_its_troupes_and_once_on_the_character(
    troupe: Troupe, heir: Person
) -> None:
    agnes = at_home(troupe)
    elsewhere = other_troupe(troupe)
    visit(troupe.player, agnes, elsewhere)

    moved(troupe, agnes, heir)

    line = (
        f"The custodian, custodian, moved Agnes Moreau (heir) from @{troupe.player.handle}"
        f" to @{heir.handle}: Signed up twice"
    )
    assert troupe_log(troupe.lead, troupe.id)[0] == line
    assert troupe_log(troupe.stranger, elsewhere)[0] == line
    assert character_log(heir, agnes).count(line) == 1
    events = troupe.session.scalars(
        select(AuditEvent).where(AuditEvent.action == "character.moved")
    ).all()
    assert {str(e.troupe_id) for e in events} == {troupe.id, elsewhere}
    assert events[0].data["from_player_id"] == troupe.player.id
    assert events[0].data["to_player_id"] == heir.id
    assert events[0].data["reason"] == "Signed up twice"


def test_history_keeps_the_old_player_as_who_did_it(troupe: Troupe, heir: Person) -> None:
    agnes = at_home(troupe)

    moved(troupe, agnes, heir)

    entries = heir.client.get(f"/characters/{agnes}/log").json()
    asked = next(e for e in entries if e["action"] == "approval.request")
    assert asked["actor_id"] == troupe.player.id


def test_only_the_custodian_can_move_a_character(troupe: Troupe, heir: Person) -> None:
    agnes = at_home(troupe)

    for person in (troupe.lead, troupe.storyteller, troupe.player, heir, troupe.stranger):
        assert move(person, agnes, heir.handle).status_code == 403
        assert preview(person, agnes, heir.handle).status_code == 403
    character = troupe.session.get_one(Character, uuid.UUID(agnes))
    troupe.session.refresh(character)
    assert str(character.player_id) == troupe.player.id


def test_a_move_needs_a_reason_and_someone_to_move_it_to(troupe: Troupe, heir: Person) -> None:
    agnes = at_home(troupe)

    response = move(troupe.custodian, agnes, heir.handle, "  ")
    assert response.status_code == 422
    assert response.json()["detail"] == "Give a reason for the move."
    response = move(troupe.custodian, agnes, "nobody_here")
    assert response.status_code == 404
    assert move(troupe.custodian, str(uuid.uuid4()), heir.handle).status_code == 404
    response = move(troupe.custodian, agnes, troupe.player.handle)
    assert response.status_code == 409
    assert response.json()["detail"] == f"Agnes Moreau already belongs to @{troupe.player.handle}."


def test_a_move_during_a_game_under_way_is_refused(troupe: Troupe, heir: Person) -> None:
    agnes = at_home(troupe)
    # Opening the Play View starts a game, but with no taps it is not under way.
    assert troupe.player.client.get(f"/characters/{agnes}/play").status_code == 200
    assert preview(troupe.custodian, agnes, heir.handle).json()["refusal"] is None
    send(troupe.player, agnes, tap("blood", -1))

    response = move(troupe.custodian, agnes, heir.handle)

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Agnes Moreau is in a game on the Play View. End it first with Reset for next game,"
        " so the game isn't split between two people."
    )
    assert (
        preview(troupe.custodian, agnes, heir.handle).json()["refusal"]
        == (response.json()["detail"])
    )
    reset = troupe.lead.client.post(f"/troupes/{troupe.id}/play/reset")
    assert reset.status_code == 200, reset.text
    moved(troupe, agnes, heir)


def test_an_npc_cannot_be_moved(troupe: Troupe, heir: Person) -> None:
    made = troupe.storyteller.client.post(f"/troupes/{troupe.id}/npcs", json={"name": "Lucien"})
    assert made.status_code == 201, made.text

    response = move(troupe.custodian, made.json()["id"], heir.handle)

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Lucien is an NPC: it belongs to its troupe, not a player, so it can't be moved."
    )


def test_a_retired_character_in_no_troupe_moves_too(troupe: Troupe, heir: Person) -> None:
    character_id = new_character(troupe, troupe.player, "Old Tom")
    retired = troupe.player.client.post(f"/characters/{character_id}/retire")
    assert retired.status_code == 200, retired.text

    moved(troupe, character_id, heir)

    assert character_id in vault(heir)
    events = troupe.session.scalars(
        select(AuditEvent).where(AuditEvent.action == "character.moved")
    ).all()
    assert [e.troupe_id for e in events] == [None]
    assert summaries(heir) == [
        f"The custodian moved Old Tom to you from @{troupe.player.handle}: Signed up twice"
    ]


def test_moving_back_undoes_a_move(troupe: Troupe, heir: Person) -> None:
    agnes = at_home(troupe)

    moved(troupe, agnes, heir)
    moved(troupe, agnes, troupe.player, "Moved to the wrong account")

    assert agnes in vault(troupe.player)
    assert agnes not in vault(heir)
    log = character_log(troupe.player, agnes)
    assert log[0].endswith(
        f"from @{heir.handle} to @{troupe.player.handle}: Moved to the wrong account"
    )
    assert log[1].endswith(f"from @{troupe.player.handle} to @{heir.handle}: Signed up twice")


def test_the_preview_says_what_will_happen(troupe: Troupe, heir: Person) -> None:
    agnes = at_home(troupe)
    elsewhere = other_troupe(troupe)
    visit(troupe.player, agnes, elsewhere)
    # A request the old player made, still waiting.
    asked = troupe.player.client.post(
        f"/characters/{agnes}/home-troupe", json={"troupe_id": elsewhere}
    )
    assert asked.status_code == 201, asked.text

    found = preview(troupe.custodian, agnes, troupe.storyteller.handle)

    assert found.status_code == 200, found.text
    body = found.json()
    assert body["character_name"] == "Agnes Moreau"
    assert body["retired"] is False
    assert body["from_player"]["handle"] == troupe.player.handle
    assert body["to_player"]["handle"] == troupe.storyteller.handle
    assert body["home_troupe"] == {"id": troupe.id, "name": "Lords of the Night"}
    assert body["visiting"] == [{"id": elsewhere, "name": "Elsewhere"}]
    assert [(r["summary"], r["troupe"]["name"]) for r in body["open_requests"]] == [
        ("Agnes Moreau asks to move Elsewhere its home", "Elsewhere")
    ]
    # The new player is a storyteller of its home troupe: said, but not refused.
    assert body["staff_roles"] == [
        {"troupe": {"id": troupe.id, "name": "Lords of the Night"}, "role": "storyteller"}
    ]
    assert body["refusal"] is None


def test_open_requests_stay_open_and_the_new_player_can_withdraw_them(
    troupe: Troupe, heir: Person
) -> None:
    agnes = at_home(troupe)
    elsewhere = other_troupe(troupe)
    asked = troupe.player.client.post(
        f"/characters/{agnes}/home-troupe", json={"troupe_id": elsewhere}
    )
    assert asked.status_code == 201, asked.text

    moved(troupe, agnes, heir)

    assert troupe.player.client.delete(f"/characters/{agnes}/home-troupe").status_code == 404
    withdrawn = heir.client.delete(f"/characters/{agnes}/home-troupe")
    assert withdrawn.status_code == 204, withdrawn.text
