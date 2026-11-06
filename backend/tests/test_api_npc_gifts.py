"""Giving a sheeted NPC to a player (issue #481)."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import TroupeMembership
from tests.api_helpers import Person, Troupe, sign_up
from tests.test_api_npc_kinds import made
from tests.test_api_renames import character_log, summaries, troupe_log
from tests.test_api_retainers import MARTA, put, with_both


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def heir(client_for: Callable[[], TestClient]) -> Person:
    """The player an NPC is given to."""
    return sign_up(client_for, "heir")


def built(troupe: Troupe, name: str = "Lucien", **body: Any) -> str:
    """A sheeted vampire NPC with a few ratings set straight."""
    npc_id: str = made(troupe, name=name, **body)["id"]
    for category, trait, rating in (
        ("attributes", "Physical", 5),
        ("skills", "Brawl", 3),
        ("disciplines", "Celerity", 2),
    ):
        response = troupe.storyteller.client.put(
            f"/characters/{npc_id}/npc/ratings",
            json={"category": category, "name": trait, "rating": rating},
        )
        assert response.status_code == 200, response.text
    return npc_id


def ratings(person: Person, character_id: str) -> list[tuple[str, str, int | None, int]]:
    traits = person.client.get(f"/characters/{character_id}/sheet").json()["traits"]
    return [(t["category"], t["name"], t["rating"], t["free_rating"]) for t in traits]


def preview(person: Person, npc_id: str, handle: str | None = None) -> Any:
    params = {"handle": handle} if handle else {}
    return person.client.get(f"/characters/{npc_id}/give-to-player", params=params)


def give(person: Person, npc_id: str, handle: str, carried: int = 0, reason: str = "") -> Any:
    return person.client.post(
        f"/characters/{npc_id}/give-to-player",
        json={"handle": handle, "carried_xp": carried, "carried_reason": reason},
    )


def given(person: Person, npc_id: str, to: Person, carried: int = 0, reason: str = "") -> None:
    response = give(person, npc_id, to.handle, carried, reason)
    assert response.status_code == 204, response.text


def xp(person: Person, character_id: str) -> list[dict[str, Any]]:
    response = person.client.get(f"/characters/{character_id}/xp")
    assert response.status_code == 200, response.text
    return response.json()


def tally(troupe: Troupe, npc_id: str) -> int:
    total: int = troupe.storyteller.client.get(f"/characters/{npc_id}/npc/tally").json()["total"]
    return total


def test_it_becomes_the_players_character_at_home_and_accepted(
    troupe: Troupe, heir: Person
) -> None:
    npc = built(troupe)
    sheet_before = ratings(troupe.storyteller, npc)

    given(troupe.lead, npc, heir)

    character = heir.client.get(f"/characters/{npc}").json()
    assert character["kind"] == "pc"
    assert character["player_id"] == heir.id
    assert character["home_troupe_id"] == troupe.id
    assert (character["npc_kind"], character["npc_form"]) == (None, None)
    assert npc in [c["id"] for c in heir.client.get("/characters").json()]
    # Its sheet is as it was, and that is its accepted sheet.
    assert ratings(heir, npc) == sheet_before
    # Physical can't be lowered below it now, but by staff.
    sheet = heir.client.get(f"/characters/{npc}/sheet").json()["traits"]
    assert [t["min_rating"] for t in sheet if t["name"] == "Physical"] == [5]
    membership = troupe.session.scalars(
        select(TroupeMembership).where(TroupeMembership.character_id == uuid.UUID(npc))
    ).one()
    assert membership.approved_version_id is not None
    # It is no longer one of the troupe's NPCs, but one of its home characters.
    assert troupe.lead.client.get(f"/troupes/{troupe.id}/npcs").json() == []
    roster = troupe.lead.client.get(f"/troupes/{troupe.id}/characters").json()
    assert [r["player_handle"] for r in roster if r["character_id"] == npc] == [heir.handle]


def test_its_xp_balances_with_an_imported_award_for_what_the_sheet_cost(
    troupe: Troupe, heir: Person
) -> None:
    npc = built(troupe)
    cost = tally(troupe, npc)
    assert cost > 0

    given(troupe.lead, npc, heir)

    entries = xp(heir, npc)
    awards = [(e["reason"], e["amount"]) for e in entries if e["kind"] == "award"]
    assert awards == [("Imported: what Lucien's sheet cost at Lords of the Night's prices", cost)]
    purchases = [e for e in entries if e["kind"] == "purchase"]
    assert sum(e["amount"] for e in purchases) == -cost
    assert "Brawl 0 → 3, as an NPC" in [e["reason"] for e in purchases]
    # Nothing is left unspent.
    assert sum(e["amount"] for e in entries) == 0


def test_unspent_xp_carried_over_is_its_own_award(troupe: Troupe, heir: Person) -> None:
    npc = built(troupe)

    given(troupe.lead, npc, heir, 12, "Banked in our old spreadsheet")

    entries = xp(heir, npc)
    assert entries[-1]["kind"] == "award"
    assert (entries[-1]["reason"], entries[-1]["amount"]) == (
        "Unspent XP carried over: Banked in our old spreadsheet",
        12,
    )
    assert sum(e["amount"] for e in entries) == 12


def test_the_preview_says_what_it_costs_and_who_it_goes_to(troupe: Troupe, heir: Person) -> None:
    npc = built(troupe)

    body = preview(troupe.storyteller, npc, heir.handle).json()

    assert body["xp"] == tally(troupe, npc)
    assert body["to_player"]["handle"] == heir.handle
    assert body["troupe_name"] == "Lords of the Night"
    assert body["refusal"] is None
    assert preview(troupe.storyteller, npc).json()["to_player"] is None


def test_the_player_is_told_and_the_troupe_log_has_it(troupe: Troupe, heir: Person) -> None:
    npc = built(troupe)

    given(troupe.storyteller, npc, heir, 5, "From Yorick")

    assert summaries(heir) == [
        "Lucien is yours now: Lords of the Night gave it to you, at home there and accepted"
    ]
    line = (
        f"storyteller gave the NPC Lucien (heir) to @{heir.handle}, at home here and accepted,"
        f" with {tally_after(troupe, heir, npc)} XP for its sheet and 5 XP carried over"
        " (From Yorick)."
    )
    assert line in troupe_log(troupe.lead, troupe.id)
    assert line in character_log(heir, npc)


def tally_after(troupe: Troupe, heir: Person, npc: str) -> int:
    """The Imported award, read back once the NPC is given."""
    awards = [e for e in xp(heir, npc) if e["reason"].startswith("Imported")]
    amount: int = awards[0]["amount"]
    return amount


def test_a_retainer_linked_to_it_is_unlinked_with_a_note(troupe: Troupe, heir: Person) -> None:
    owner = with_both(troupe)
    npc = built(troupe, "Marta")
    listed = put(troupe.player, owner, [MARTA]).json()["retainers"][0]
    linked = put(troupe.storyteller, owner, [{**listed, "npc_id": npc}]).json()
    assert linked["retainers"][0]["npc_id"] == npc
    assert preview(troupe.lead, npc).json()["retainers"] == [
        {"character_name": "Agnes", "name": "Marta, the driver"}
    ]

    given(troupe.lead, npc, heir)

    after = troupe.storyteller.client.get(f"/characters/{owner}/retainers").json()
    assert after["retainers"][0]["npc_id"] is None
    assert (
        "Marta, the driver, one of Agnes (player)'s Retainers, is no longer linked to the NPC"
        f" Marta: lead gave it to @{heir.handle}."
    ) in troupe_log(troupe.lead, troupe.id)


def test_only_the_custodian_and_storytellers_give_one(troupe: Troupe, heir: Person) -> None:
    npc = built(troupe)

    for person in (troupe.assistant, troupe.narrator, troupe.player, troupe.stranger):
        assert give(person, npc, heir.handle).status_code in (403, 404), person.handle
        assert preview(person, npc).status_code in (403, 404), person.handle
    given(troupe.custodian, npc, heir)


def test_a_stock_npc_or_one_of_another_kind_is_refused(troupe: Troupe, heir: Person) -> None:
    stock = made(troupe, name="Bites", npc_kind="werewolf", npc_form="stock")["id"]
    mage = made(troupe, name="Sarah", npc_kind="mage")["id"]
    building = made(troupe, name="Unfinished", wizard=True)["id"]

    refused = give(troupe.lead, stock, heir.handle)
    assert refused.status_code == 409
    assert refused.json()["detail"] == (
        "Bites is a Stock NPC, with no full sheet to play. Make it a full sheet first."
    )
    assert preview(troupe.lead, stock).json()["refusal"] == refused.json()["detail"]
    assert "isn't a vampire or a ghoul" in give(troupe.lead, mage, heir.handle).json()["detail"]
    assert "still being built" in give(troupe.lead, building, heir.handle).json()["detail"]
    # Given once, it is a PC: there is nothing more to give.
    npc = built(troupe)
    given(troupe.lead, npc, heir)
    assert give(troupe.lead, npc, troupe.player.handle).status_code == 409


def test_carried_xp_must_be_sensible(troupe: Troupe, heir: Person) -> None:
    npc = built(troupe)

    assert give(troupe.lead, npc, heir.handle, -1).status_code == 422
    assert give(troupe.lead, npc, heir.handle, 10001).status_code == 422
