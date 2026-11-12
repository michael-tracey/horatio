"""A troupe's sire lines (horatio.sire_lines): who gives a character's sire, a loop
refused, what staff see and what players see, and the troupe's choice to show them."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.models import Character
from tests.api_helpers import Troupe, sign_up
from tests.test_api_sect_status import member, npc


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def give(client: TestClient, childe: str, **body: Any) -> Any:
    return client.put(f"/characters/{childe}/sire", json=body)


def lines(client: TestClient, troupe: Troupe) -> Any:
    return client.get(f"/troupes/{troupe.id}/sire-lines")


def tree(client: TestClient, troupe: Troupe) -> dict[str, Any]:
    response = lines(client, troupe)
    assert response.status_code == 200, response.text
    found = response.json()
    by_key = {n["key"]: n for n in found["nodes"]}
    return {
        n["name"]: (by_key[n["sire_key"]]["name"] if n["sire_key"] else None)
        for n in found["nodes"]
    }


def show_to_players(troupe: Troupe, shown: bool) -> None:
    changed = troupe.lead.client.patch(f"/troupes/{troupe.id}", json={"sire_lines_players": shown})
    assert changed.status_code == 200, changed.text
    assert changed.json()["sire_lines_players"] is shown


def test_the_player_and_staff_give_a_sire_and_a_loop_is_refused(troupe: Troupe) -> None:
    elsa = member(troupe, "Elsa")
    anna = member(troupe, "Anna")
    # Its player, from the troupe's Who's Who.
    choices = troupe.player.client.get(f"/characters/{anna}/sire/choices")
    assert choices.status_code == 200, choices.text
    assert [c["name"] for c in choices.json()] == ["Elsa"]
    given = give(troupe.player.client, anna, character_id=elsa)
    assert given.status_code == 200, given.text
    assert given.json()["name"] == "Elsa" and given.json()["can_change"]
    # Elsa can't then be Anna's childe.
    loop = give(troupe.player.client, elsa, character_id=anna)
    assert loop.status_code == 422
    assert "descend from" in loop.json()["detail"]
    # Nor her own sire.
    assert give(troupe.player.client, elsa, character_id=elsa).status_code == 404
    # The home troupe's storytellers can give it too; a stranger can't.
    named = give(troupe.storyteller.client, elsa, name="Old Marcus", clan="Tremere")
    assert named.status_code == 200, named.text
    assert named.json() == {
        "character_id": None,
        "name": "Old Marcus",
        "clan": "Tremere",
        "secret": False,
        "can_change": True,
    }
    assert give(troupe.stranger.client, elsa, name="X").status_code == 404
    # A narrator doesn't see the sheet at all.
    assert give(troupe.narrator.client, elsa, name="X").status_code == 404
    # A clan without a name says nothing.
    assert give(troupe.player.client, elsa, clan="Tremere").status_code == 422
    # The log says so.
    log = troupe.storyteller.client.get(f"/characters/{elsa}/log")
    assert log.status_code == 200, log.text
    assert any("sire: Old Marcus (Tremere)." in e["message"] for e in log.json())


def told(person: Any) -> list[str]:
    return [i["summary"] for i in person.client.get("/notifications").json()["items"]]


def test_staff_are_told_when_the_player_changes_the_sire(troupe: Troupe) -> None:
    """#747: the player's change tells the home troupe's storytellers and assistant
    storytellers what the sire was and is now; staff's own change tells no one."""
    elsa = member(troupe, "Elsa")
    anna = member(troupe, "Anna")
    assert give(troupe.player.client, anna, character_id=elsa).status_code == 200
    said = "Anna's player changed the sire: now Elsa, was no sire."
    for staff in (troupe.lead, troupe.storyteller, troupe.assistant):
        assert said in told(staff)
    # Not the player who made it, nor a narrator.
    assert said not in told(troupe.player)
    assert said not in told(troupe.narrator)
    # Kept secret from players: staff are still told the name.
    secret = give(troupe.player.client, anna, name="Old Marcus", clan="Tremere", secret=True)
    assert secret.status_code == 200, secret.text
    assert (
        "Anna's player changed the sire: now Old Marcus (Tremere), kept from players, was Elsa."
        in told(troupe.storyteller)
    )
    # Clearing it tells them too.
    assert give(troupe.player.client, anna).status_code == 200
    assert (
        "Anna's player changed the sire: now no sire, was Old Marcus (Tremere), kept from players."
        in told(troupe.storyteller)
    )
    # The same sire again changes nothing, and tells no one.
    before = len(told(troupe.storyteller))
    assert give(troupe.player.client, anna).status_code == 200
    assert len(told(troupe.storyteller)) == before
    # Staff's own change tells no one.
    lead_before = told(troupe.lead)
    assert give(troupe.storyteller.client, anna, character_id=elsa).status_code == 200
    assert give(troupe.storyteller.client, anna).status_code == 200
    assert told(troupe.lead) == lead_before


def test_staff_see_every_line_and_players_only_what_the_whos_who_shows(
    troupe: Troupe, client_for: Callable[[], TestClient]
) -> None:
    elsa = member(troupe, "Elsa")
    anna = member(troupe, "Anna")
    berit = member(troupe, "Berit")
    hidden = npc(troupe, "Hidden Elder", "Camarilla")
    assert give(troupe.player.client, anna, character_id=elsa).status_code == 200
    assert give(troupe.storyteller.client, elsa, character_id=hidden).status_code == 200
    assert (
        give(
            troupe.player.client, berit, name="Old Marcus", clan="Tremere", secret=True
        ).status_code
        == 200
    )

    found = tree(troupe.storyteller.client, troupe)
    assert found["Anna"] == "Elsa"
    assert found["Elsa"] == "Hidden Elder"
    assert found["Berit"] == "Old Marcus"
    assert lines(troupe.assistant.client, troupe).status_code == 200

    # Players see nothing until the troupe shows them.
    assert lines(troupe.player.client, troupe).status_code == 403
    assert lines(troupe.stranger.client, troupe).status_code == 404
    show_to_players(troupe, True)
    seen = tree(troupe.player.client, troupe)
    assert seen["Anna"] == "Elsa"
    # An NPC not on the Who's Who is never named, nor a sire kept secret.
    assert "Hidden Elder" not in seen and seen["Elsa"] is None
    assert "Old Marcus" not in seen and seen["Berit"] is None
    # Another troupe's player still can't.
    other = sign_up(client_for, "outsider")
    assert lines(other.client, troupe).status_code == 404
    # A secret sire is kept from a player reading another's character, if they can.
    assert troupe.player.client.get(f"/characters/{berit}/sire").json()["name"] == "Old Marcus"


def test_deleting_a_sire_keeps_it_by_name(troupe: Troupe, session: Session) -> None:
    elder = npc(troupe, "Old Elsa", "Camarilla")
    anna = member(troupe, "Anna")
    assert give(troupe.storyteller.client, anna, character_id=elder).status_code == 200
    assert troupe.lead.client.delete(f"/characters/{elder}").status_code == 204
    session.expire_all()
    childe = session.get_one(Character, uuid.UUID(anna))
    assert childe.sire_id is None
    assert childe.sire_name == "Old Elsa"
    found = tree(troupe.storyteller.client, troupe)
    assert found["Anna"] == "Old Elsa"
