"""Blood bonds Horatio knows without anyone recording them (#663): a childe's to their
sire from the Embrace (MET: VTM p. 295), a ghoul's full bond to their domitor (p. 296),
and a vampire's ghoul Retainers' to them; added while the troupe's Blood bonds setting
isn't off, and for what came before, filled in when its running staff choose."""

import uuid
from collections.abc import Callable
from datetime import UTC
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.models import Character
from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_embrace import MALKAVIAN, NIGHT, embrace, vivian
from tests.test_api_generation_until_accepted import make_home
from tests.test_api_ghouls import bind, typed
from tests.test_api_npc_kinds import made
from tests.test_api_retainers import BOCEPHUS, give_retainers, make_npc, put
from tests.test_api_sect_status import member

pytestmark = pytest.mark.usefixtures("ghoul_rules")

# The night the helper Embraces on.
EMBRACED = NIGHT


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def track(troupe: Troupe, setting: str = "staff") -> None:
    set_to = troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/blood-bonds", json={"setting": setting}
    )
    assert set_to.status_code == 200, set_to.text


def bonds(troupe: Troupe) -> list[dict[str, Any]]:
    listed = troupe.storyteller.client.get(f"/troupes/{troupe.id}/bonds")
    assert listed.status_code == 200, listed.text
    return listed.json()["bonds"]


def between(troupe: Troupe, thrall: str, regnant: str) -> list[dict[str, Any]]:
    return [
        b for b in bonds(troupe) if (b["thrall"]["name"], b["regnant"]["name"]) == (thrall, regnant)
    ]


def known(troupe: Troupe, by: Person | None = None) -> Any:
    return (by or troupe.storyteller).client.get(f"/troupes/{troupe.id}/bonds/known")


def embraced(troupe: Troupe, ghoul: str) -> None:
    made_vampire = embrace(troupe.lead, ghoul)
    assert made_vampire.status_code == 200, made_vampire.text


def test_an_embrace_gives_the_childe_a_one_drink_bond_to_their_sire(troupe: Troupe) -> None:
    ghoul = vivian(troupe)
    track(troupe)

    embraced(troupe, ghoul)

    [bond] = between(troupe, "Vivian", MALKAVIAN["name"])
    assert (bond["level"], bond["status"], bond["known_to_regnant"]) == (1, "active", False)
    assert bond["regnant"]["character_id"] is None
    [entry] = bond["entries"]
    assert (entry["kind"], entry["night"]) == ("entered", EMBRACED)
    assert "p. 295" in entry["note"]
    # The childe's player sees it, as their own.
    card = troupe.player.client.get(f"/characters/{ghoul}/bonds").json()
    assert [b["name"] for b in card["bound_to"]] == [MALKAVIAN["name"]]


def test_nothing_is_added_while_bonds_are_off_until_staff_fill_it_in(troupe: Troupe) -> None:
    ghoul = vivian(troupe)
    embraced(troupe, ghoul)
    track(troupe)
    assert bonds(troupe) == []

    # Only the troupe's running staff see what Horatio can fill in.
    assert known(troupe, troupe.player).status_code in (403, 404)
    found = known(troupe)
    assert found.status_code == 200, found.text
    [item] = found.json()
    assert (item["why"], item["level"], item["night"]) == ("embrace", 1, EMBRACED)
    assert (item["thrall"]["name"], item["regnant"]["name"]) == ("Vivian", MALKAVIAN["name"])

    refused = troupe.player.client.post(f"/troupes/{troupe.id}/bonds/known")
    assert refused.status_code in (403, 404)
    filled = troupe.storyteller.client.post(f"/troupes/{troupe.id}/bonds/known")
    assert filled.status_code == 200, filled.text
    [added] = filled.json()["added"]
    assert (added["thrall"]["name"], added["level"]) == ("Vivian", 1)
    assert known(troupe).json() == []
    # Filled in once: running it again adds nothing.
    again = troupe.storyteller.client.post(f"/troupes/{troupe.id}/bonds/known")
    assert again.json()["added"] == []
    assert len(bonds(troupe)) == 1


def test_switched_off_the_troupe_has_nothing_to_fill_in(troupe: Troupe) -> None:
    assert known(troupe).status_code == 404


def test_a_ghoul_is_fully_bound_to_its_domitor_and_a_change_moves_it(troupe: Troupe) -> None:
    track(troupe)
    igor = made(troupe, name="Igor", npc_kind="ghoul")["id"]

    first = bind(troupe.storyteller, igor, typed("Lady Vasquez", "Toreador"))
    assert first.status_code == 200, first.text
    [bond] = between(troupe, "Igor", "Lady Vasquez")
    assert (bond["level"], bond["status"]) == (3, "active")
    assert "p. 296" in bond["entries"][0]["note"]

    moved = bind(troupe.storyteller, igor, typed("Marcus", "Brujah"))
    assert moved.status_code == 200, moved.text
    [old] = between(troupe, "Igor", "Lady Vasquez")
    assert old["status"] == "ended"
    assert "the bond to the old one had faded" in old["ended_reason"]
    [new] = between(troupe, "Igor", "Marcus")
    assert (new["level"], new["status"]) == (3, "active")
    # Bound again to the same domitor: nothing more is added.
    assert bind(troupe.storyteller, igor, typed("Marcus", "Brujah")).status_code == 200
    assert len(between(troupe, "Igor", "Marcus")) == 1


def test_a_ghoul_accepted_by_its_home_troupe_is_bound_to_its_domitor(troupe: Troupe) -> None:
    track(troupe)

    ghoul = vivian(troupe)

    [bond] = between(troupe, "Vivian", "The Vizier")
    assert (bond["level"], bond["status"]) == (3, "active")
    # A full bond makes the ghoul immune to others: an Embrace by someone else adds none.
    embraced(troupe, ghoul)
    assert between(troupe, "Vivian", MALKAVIAN["name"]) == []


def give_sire(troupe: Troupe, childe: str, **body: Any) -> None:
    """Staff give the character its sire on the sheet (#707)."""
    given = troupe.storyteller.client.put(f"/characters/{childe}/sire", json=body)
    assert given.status_code == 200, given.text


def made_on(troupe: Troupe, character_id: str) -> str:
    """The day the character was made in Horatio, as the API gives dates."""
    character = troupe.session.get(Character, uuid.UUID(character_id))
    assert character is not None
    return character.created_at.astimezone(UTC).date().isoformat()


def test_the_sire_on_the_sheet_is_offered_and_filled_in_kept_secret(troupe: Troupe) -> None:
    anna = member(troupe, "Anna")
    elsa = made(troupe, name="Old Elsa", npc_kind="vampire")["id"]
    give_sire(troupe, anna, character_id=elsa, secret=True)
    track(troupe)
    # Never added on its own: only offered.
    assert bonds(troupe) == []

    [item] = known(troupe).json()
    assert (item["why"], item["level"], item["night"]) == ("sire", 1, made_on(troupe, anna))
    assert (item["thrall"]["character_id"], item["regnant"]["character_id"]) == (anna, elsa)
    assert "p. 295" in item["reason"]

    filled = troupe.storyteller.client.post(f"/troupes/{troupe.id}/bonds/known")
    assert filled.status_code == 200, filled.text
    [added] = filled.json()["added"]
    assert (added["thrall"]["name"], added["regnant"]["name"], added["level"]) == (
        "Anna",
        "Old Elsa",
        1,
    )
    # A secret sire stays with those who know it: the childe's player, whose bond it
    # is, and staff; the regnant's side sees it only once staff mark it known.
    assert added["known_to_regnant"] is False
    card = troupe.player.client.get(f"/characters/{anna}/bonds").json()
    assert [b["name"] for b in card["bound_to"]] == ["Old Elsa"]
    assert known(troupe).json() == []


def test_a_sire_known_by_name_gives_a_bond_to_the_name(troupe: Troupe) -> None:
    anna = member(troupe, "Anna")
    give_sire(troupe, anna, name="Marcus", clan="Brujah")
    track(troupe)

    [item] = known(troupe).json()
    assert item["why"] == "sire"
    assert (item["regnant"]["character_id"], item["regnant"]["name"]) == (None, "Marcus")


def test_no_sire_bond_where_one_stands_or_a_full_bond_makes_them_immune(troupe: Troupe) -> None:
    anna = member(troupe, "Anna")
    berit = member(troupe, "Berit")
    give_sire(troupe, anna, name="Marcus", clan="Brujah")
    give_sire(troupe, berit, name="Marcus", clan="Brujah")
    track(troupe)
    assert {i["thrall"]["name"] for i in known(troupe).json()} == {"Anna", "Berit"}

    def enter(thrall: str, regnant: str, level: int) -> None:
        entered = troupe.storyteller.client.post(
            f"/troupes/{troupe.id}/bonds",
            json={
                "thrall": {"character_id": thrall},
                "regnant": {"name": regnant},
                "level": level,
                "night": "2026-10-01",
                "reason": "Known from before.",
            },
        )
        assert entered.status_code == 201, entered.text

    # Anna already has a bond to her sire; Berit is fully bound to someone else.
    enter(anna, "Marcus", 1)
    enter(berit, "Lady Vasquez", 3)
    assert known(troupe).json() == []


def test_an_embrace_in_play_isnt_offered_twice_from_the_sheet(troupe: Troupe) -> None:
    ghoul = vivian(troupe)
    embraced(troupe, ghoul)
    track(troupe)
    # The Embrace named her sire on the sheet too: one offer, from the Embrace.
    [item] = known(troupe).json()
    assert item["why"] == "embrace"


def test_no_domitor_bond_is_added_while_bonds_are_off(troupe: Troupe) -> None:
    igor = made(troupe, name="Igor", npc_kind="ghoul")["id"]
    assert bind(troupe.storyteller, igor, typed("Lady Vasquez", "Toreador")).status_code == 200
    track(troupe)
    assert bonds(troupe) == []
    [item] = known(troupe).json()
    assert (item["why"], item["level"]) == ("domitor", 3)


def nosferatu_with_bocephus(troupe: Troupe) -> str:
    """An accepted Nosferatu with Bocephus, a four-dot Retainer (the book's, p. 105)."""
    character_id = new_character(troupe, troupe.player, "Lucien", clan="Nosferatu")
    make_home(troupe, character_id)
    give_retainers(troupe, character_id, 4, "Bocephus")
    return character_id


def test_a_ghoul_retainer_is_bound_to_its_vampire_and_follows_its_npc(troupe: Troupe) -> None:
    track(troupe)
    lucien = nosferatu_with_bocephus(troupe)

    # Not a ghoul: no bond.
    plain = put(troupe.player, lucien, [{**BOCEPHUS, "ghoul": False, "discipline": ""}])
    assert plain.status_code == 200, plain.text
    assert bonds(troupe) == []

    saved = put(troupe.player, lucien, [BOCEPHUS])
    assert saved.status_code == 200, saved.text
    [bond] = between(troupe, "Bocephus", "Lucien")
    assert (bond["level"], bond["thrall"]["character_id"]) == (3, None)
    # Its player made the Retainer a ghoul: the bond is known to them.
    assert bond["known_to_regnant"] is True
    card = troupe.player.client.get(f"/characters/{lucien}/bonds").json()
    assert [b["name"] for b in card["bound_by"]] == ["Bocephus"]

    # Staff link the Retainer to an NPC: the bond goes with it.
    npc = make_npc(troupe, "Bocephus the ghoul")
    listed = saved.json()["retainers"][0]
    linked = put(troupe.storyteller, lucien, [{**listed, "npc_id": npc}])
    assert linked.status_code == 200, linked.text
    [bond] = [b for b in bonds(troupe) if b["regnant"]["name"] == "Lucien"]
    assert (bond["thrall"]["character_id"], bond["thrall"]["name"]) == (npc, "Bocephus the ghoul")
