"""Stolen Potential (MET: VTM p. 265, #310): the flaw names an attribute, which takes no
focus at creation, and none after it while the flaw is held."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe
from tests.test_api_creation import FULL_BUILD, creating, creation, pick, sheet

pytestmark = pytest.mark.usefixtures("without_bank")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def flaws(person: Person, character_id: str, picks: list[tuple[str, str]]) -> Any:
    """Save the Merits & flaws step's flaws: (name, detail) each."""
    return person.client.put(
        f"/characters/{character_id}/creation/categories/flaws",
        json={"picks": [{"name": n, "detail": d} for n, d in picks]},
    )


def focuses(person: Person, character_id: str, category: str, names: list[str]) -> Any:
    return person.client.put(
        f"/characters/{character_id}/creation/categories/{category}",
        json={"picks": [{"name": n, "rating": 1} for n in names]},
    )


def focus_pools(state: dict[str, Any]) -> dict[str, tuple[int, int]]:
    """Each focus category's starting picks: (allowed, remaining)."""
    return {
        p["category"]: (p["allowed"], p["remaining"])
        for p in state["pools"]
        if p["category"].startswith("focus_")
    }


def finish(person: Person, character_id: str) -> Any:
    return person.client.post(f"/characters/{character_id}/creation/complete")


def build_but(person: Person, character_id: str, skip: str) -> None:
    for category, name, rating in FULL_BUILD:
        if category != skip:
            assert pick(person, character_id, category, name, rating).status_code == 200, name


def test_the_catalogue_offers_the_three_attributes(troupe: Troupe) -> None:
    catalogue = troupe.player.client.get("/rules/vampire").json()
    flaw = next(
        t
        for t in catalogue["traits"]
        if (t["category"], t["name"]) == ("flaws", "Stolen Potential")
    )
    assert flaw["choices"] == ["Physical", "Social", "Mental"]
    assert flaw["page_reference"] == "265"


def test_the_flaw_asks_which_attribute(troupe: Troupe) -> None:
    character_id = creating(troupe)
    refused = flaws(troupe.player, character_id, [("Stolen Potential", "")])
    assert refused.status_code == 409
    assert "Stolen Potential: choose Physical, Social or Mental." in refused.json()["detail"]
    # Not greyed out in the list for want of the choice it asks for when ticked.
    offered = troupe.player.client.get(
        f"/characters/{character_id}/refusals", params={"category": "flaws"}
    ).json()
    assert "Stolen Potential" not in offered


def test_with_mental_named_no_mental_focus_is_needed_to_finish(troupe: Troupe) -> None:
    character_id = creating(troupe)
    player = troupe.player
    build_but(player, character_id, "focus_mentals")
    # Without the flaw, the Mental focus holds finishing back.
    assert finish(player, character_id).status_code == 409

    assert flaws(player, character_id, [("Stolen Potential", "Mental")]).status_code == 200

    state = creation(player, character_id)
    # No Mental focus picks at all; the other two attributes keep theirs.
    assert focus_pools(state) == {"focus_physicals": (1, 0), "focus_socials": (1, 0)}
    assert {
        "category": "focus_mentals",
        "because": [{"category": "flaws", "name": "Stolen Potential"}],
    } in state["budget_changes"]
    # One is refused, saying why.
    refused = pick(player, character_id, "focus_mentals", "Wits")
    assert refused.status_code == 422
    assert refused.json()["detail"] == ("Stolen Potential: there are no Mental Focus picks at 1.")
    assert focuses(player, character_id, "focus_mentals", ["Wits"]).status_code == 422

    finished = finish(player, character_id)
    assert finished.status_code == 200, finished.text
    traits = sheet(player, character_id)["traits"]
    assert not [t for t in traits if t["category"] == "focus_mentals"]
    held = next(t for t in traits if t["name"] == "Stolen Potential")
    assert held["detail"] == "Mental"


def test_another_attribute_named_changes_nothing_for_the_mental_focus(troupe: Troupe) -> None:
    character_id = creating(troupe)
    player = troupe.player
    assert flaws(player, character_id, [("Stolen Potential", "Social")]).status_code == 200
    state = creation(player, character_id)
    assert focus_pools(state) == {"focus_physicals": (1, 1), "focus_mentals": (1, 1)}
    assert [c["category"] for c in state["budget_changes"]] == ["focus_socials"]


def test_a_focus_already_chosen_stays_until_it_is_taken_back(troupe: Troupe) -> None:
    character_id = creating(troupe)
    player = troupe.player
    build_but(player, character_id, "")

    # The flaw is taken over the Mental focus chosen before it: not refused.
    assert flaws(player, character_id, [("Stolen Potential", "Mental")]).status_code == 200

    # The focus is kept, in picks with nothing allowed, saying what took them away.
    stray = next(
        p for p in creation(player, character_id)["pools"] if p["category"] == "focus_mentals"
    )
    assert (stray["allowed"], stray["remaining"]) == (0, -1)
    assert [t["name"] for t in stray["traits"]] == ["Wits"]
    assert stray["because"] == [{"category": "flaws", "name": "Stolen Potential"}]
    refused = finish(player, character_id)
    assert refused.status_code == 409
    assert "Wits at 1" in refused.json()["detail"]
    # Saved as it was, it stays; nothing new goes there; taken back, it goes.
    assert focuses(player, character_id, "focus_mentals", ["Wits"]).status_code == 200
    assert focuses(player, character_id, "focus_mentals", ["Perception"]).status_code == 422
    assert focuses(player, character_id, "focus_mentals", []).status_code == 200

    assert focus_pools(creation(player, character_id)) == {
        "focus_physicals": (1, 0),
        "focus_socials": (1, 0),
    }
    assert finish(player, character_id).status_code == 200


def test_taking_the_flaw_back_brings_the_mental_focus_back(troupe: Troupe) -> None:
    character_id = creating(troupe)
    player = troupe.player
    build_but(player, character_id, "focus_mentals")
    assert flaws(player, character_id, [("Stolen Potential", "Mental")]).status_code == 200
    assert "focus_mentals" not in focus_pools(creation(player, character_id))

    assert flaws(player, character_id, []).status_code == 200

    assert focus_pools(creation(player, character_id))["focus_mentals"] == (1, 1)
    assert finish(player, character_id).status_code == 409
    assert pick(player, character_id, "focus_mentals", "Wits").status_code == 200
    assert finish(player, character_id).status_code == 200


def test_after_creation_a_mental_focus_is_refused_while_the_flaw_is_held(
    troupe: Troupe,
) -> None:
    character_id = creating(troupe)
    player = troupe.player
    build_but(player, character_id, "focus_mentals")
    assert flaws(player, character_id, [("Stolen Potential", "Mental")]).status_code == 200
    assert finish(player, character_id).status_code == 200

    refusals = player.client.get(
        f"/characters/{character_id}/refusals", params={"category": "focus_mentals"}
    ).json()
    assert refusals["Wits"]["message"] == "Stolen Potential: no Mental focus. (p. 265)"
    added = player.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "focus_mentals", "name": "Wits", "rating": 1},
    )
    assert added.status_code == 409
    assert "Stolen Potential: no Mental focus." in added.json()["detail"]
    # The other attributes are as ever.
    social = player.client.get(
        f"/characters/{character_id}/refusals", params={"category": "focus_socials"}
    ).json()
    assert "Manipulation" not in social
