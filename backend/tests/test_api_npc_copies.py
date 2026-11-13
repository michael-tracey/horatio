"""Storytellers copy a retired player character as an NPC (horatio.npc_copies, #764)."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, finish
from tests.test_api_boons import Ledger, row
from tests.test_api_leaving import retire
from tests.test_api_renames import character_log, renamed, summaries, troupe_log
from tests.test_api_sect_status import choose, make_home


@pytest.fixture
def ledger(client_for: Callable[[], TestClient], session: Session) -> Ledger:
    return Ledger(Troupe(client_for, session))


def built(troupe: Troupe, name: str = "Viktor") -> str:
    """A Brujah of the Anarchs with a few traits bought and a sire named, at home in
    the troupe."""
    player = troupe.player
    response = player.client.post("/characters", json={"splat": "vampire", "name": name})
    assert response.status_code == 201, response.text
    character_id: str = response.json()["id"]
    choose(player, character_id, "clan", "Brujah")
    choose(player, character_id, "sect", "Anarch")
    finish(troupe, character_id)
    for category, trait, rating in (
        ("attributes", "Physical", 4),
        ("skills", "Brawl", 3),
        ("disciplines", "Celerity", 2),
    ):
        bought = player.client.put(
            f"/characters/{character_id}/traits",
            json={"category": category, "name": trait, "rating": rating},
        )
        assert bought.status_code == 200, bought.text
    sired = player.client.put(
        f"/characters/{character_id}/sire", json={"name": "Salvador", "clan": "Brujah"}
    )
    assert sired.status_code == 200, sired.text
    make_home(troupe, player, character_id)
    return character_id


def copy(person: Person, character_id: str) -> Any:
    return person.client.post(f"/characters/{character_id}/npc-copy")


def copied(person: Person, character_id: str) -> dict[str, Any]:
    response = copy(person, character_id)
    assert response.status_code == 201, response.text
    return response.json()


def sheet(person: Person, character_id: str) -> set[tuple[str, str, str, int | None]]:
    response = person.client.get(f"/characters/{character_id}/sheet")
    assert response.status_code == 200, response.text
    return {(t["category"], t["name"], t["detail"], t["rating"]) for t in response.json()["traits"]}


def character(person: Person, character_id: str) -> dict[str, Any]:
    response = person.client.get(f"/characters/{character_id}")
    assert response.status_code == 200, response.text
    return response.json()


def sire(person: Person, character_id: str) -> tuple[str, str]:
    found = person.client.get(f"/characters/{character_id}/sire").json()
    return found["name"], found["clan"]


def test_a_retired_character_is_copied_as_an_npc_and_the_original_stays_with_its_player(
    ledger: Ledger,
) -> None:
    troupe = ledger.troupe
    viktor = built(troupe)
    before = sheet(troupe.player, viktor)
    retire(troupe.player, viktor, reason="off_field", note="Gone over to the Sabbat.", listed=False)
    shown_before = summaries(troupe.player)

    made = copied(troupe.storyteller, viktor)

    assert made["left_out"] == []
    npc = made["character"]
    assert npc["name"] == "[NPC] Viktor"
    assert (npc["kind"], npc["npc_form"], npc["status"]) == ("npc", "sheeted", "active")
    assert npc["owner_troupe_id"] == troupe.id
    # The same sheet: clan, sect, attributes, skills and disciplines.
    assert sheet(troupe.storyteller, npc["id"]) == before
    assert {("clan", "Brujah"), ("sect", "Anarch")} <= {(c, n) for c, n, _, _ in before}
    assert sire(troupe.storyteller, npc["id"]) == ("Salvador", "Brujah")
    # The original is as it was, retired, the player's.
    original = character(troupe.player, viktor)
    assert (original["name"], original["status"], original["kind"]) == (
        "Viktor",
        "retired",
        "pc",
    )
    assert original["player_id"] == troupe.player.id
    assert sheet(troupe.player, viktor) == before
    # Staff see where it came from, in the NPC's log, the original's and the troupe's.
    made_line = (
        f"storyteller made the NPC [NPC] Viktor, a copy of @{troupe.player.handle}'s retired"
        " character Viktor as it stood; parts left out: 0."
    )
    assert made_line in character_log(troupe.storyteller, npc["id"])
    assert made_line in troupe_log(troupe.lead, troupe.id)
    copy_line = "storyteller made the NPC [NPC] Viktor from a copy of Viktor"
    assert any(m.startswith(copy_line) for m in character_log(troupe.storyteller, viktor))
    # Its player isn't told: no notice, and nothing in their own view of its log.
    assert summaries(troupe.player) == shown_before
    assert not any("NPC" in m for m in character_log(troupe.player, viktor))


def test_its_boons_and_whos_who_listing_stay_with_the_original(ledger: Ledger) -> None:
    troupe = ledger.troupe
    made = ledger.register(row(ledger.agnes, ledger.bram, kind="major"))
    assert made.status_code == 201, made.text
    retire(troupe.player, ledger.agnes, reason="final_death", listed=True)

    npc = copied(troupe.lead, ledger.agnes)["character"]

    parties = {
        party["character_id"]
        for boon in ledger.ledger(view="all")["boons"]
        for party in (boon["debtor"], boon["creditor"])
    }
    assert ledger.agnes in parties
    assert npc["id"] not in parties
    npcs = troupe.lead.client.get(f"/troupes/{troupe.id}/npcs").json()
    assert [n["on_whos_who"] for n in npcs if n["id"] == npc["id"]] == [False]


@pytest.mark.parametrize("reason", ["final_death", "off_field", "inactive", None])
def test_any_retired_character_can_be_copied_however_it_left(
    ledger: Ledger, reason: str | None
) -> None:
    troupe = ledger.troupe
    if reason is None:
        # Retired with no reason, as characters were before reasons were kept.
        response = troupe.player.client.post(f"/characters/{ledger.agnes}/retire")
        assert response.status_code == 200, response.text
    else:
        retire(troupe.player, ledger.agnes, reason=reason, listed=False)

    assert copied(troupe.storyteller, ledger.agnes)["character"]["name"] == "[NPC] Agnes"


def test_an_active_character_is_refused(ledger: Ledger) -> None:
    troupe = ledger.troupe

    refused = copy(troupe.storyteller, ledger.agnes)

    assert refused.status_code == 409
    assert refused.json()["detail"] == (
        "Agnes is still active: only a retired character can be made an NPC."
    )


def test_only_the_home_troupes_running_staff_copy_it(ledger: Ledger) -> None:
    troupe = ledger.troupe
    retire(troupe.player, ledger.agnes, reason="off_field", listed=False)

    assert copy(troupe.player, ledger.agnes).status_code == 403
    assert copy(troupe.narrator, ledger.agnes).status_code == 404
    assert copy(troupe.stranger, ledger.agnes).status_code == 404
    assert copy(troupe.assistant, ledger.agnes).status_code == 201


def test_an_npc_isnt_copied_and_a_second_copy_is_refused(ledger: Ledger) -> None:
    troupe = ledger.troupe
    assert copy(troupe.storyteller, ledger.vidal).status_code == 409
    retire(troupe.player, ledger.agnes, reason="off_field", listed=False)
    copied(troupe.storyteller, ledger.agnes)

    again = copy(troupe.storyteller, ledger.agnes)

    assert again.status_code == 409
    assert again.json()["detail"] == "The troupe already has an NPC named [NPC] Agnes."


def test_a_change_to_either_leaves_the_other_alone(ledger: Ledger) -> None:
    troupe = ledger.troupe
    viktor = built(troupe)
    retire(troupe.player, viktor, reason="off_field", listed=False)
    npc = copied(troupe.storyteller, viktor)["character"]["id"]
    before = sheet(troupe.player, viktor)

    raised = troupe.storyteller.client.put(
        f"/characters/{npc}/npc/ratings",
        json={"category": "disciplines", "name": "Potence", "rating": 3},
    )
    assert raised.status_code == 200, raised.text
    renamed(troupe.custodian, viktor, "Viktor B.")

    assert sheet(troupe.player, viktor) == before
    assert ("disciplines", "Potence", "", 3) in sheet(troupe.storyteller, npc)
    assert character(troupe.storyteller, npc)["name"] == "[NPC] Viktor"
