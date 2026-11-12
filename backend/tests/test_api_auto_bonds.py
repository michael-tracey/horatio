"""Blood bonds Horatio knows without anyone recording them (#663): a childe's to their
sire from the Embrace (MET: VTM p. 295), a ghoul's full bond to their domitor (p. 296),
and a vampire's ghoul Retainers' to them; added while the troupe's Blood bonds setting
isn't off, and for what came before, filled in when its running staff choose."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_embrace import MALKAVIAN, NIGHT, embrace, vivian
from tests.test_api_generation_until_accepted import make_home
from tests.test_api_ghouls import bind, typed
from tests.test_api_npc_kinds import made
from tests.test_api_retainers import BOCEPHUS, give_retainers, make_npc, put

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
