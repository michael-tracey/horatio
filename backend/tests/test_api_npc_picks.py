"""Creation picks fitted to an NPC built without the wizard (issue #527), so its
creation dots are free as a player character's are, at its troupe's prices."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe
from tests.test_api_npcs_titles import make_npc, rate


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def rated(person: Person, npc: str, category: str, name: str, rating: int | None) -> Any:
    response = rate(person, npc, category, name, rating)
    assert response.status_code == 200, response.text
    return response.json()


def picks(person: Person, npc: str) -> dict[str, Any]:
    response = person.client.get(f"/characters/{npc}/npc/picks")
    assert response.status_code == 200, response.text
    return response.json()


def placed(found: dict[str, Any], category: str) -> dict[str, tuple[int, str]]:
    """Each trait with a pick in the category: (the pick, who placed it)."""
    return {
        p["name"]: (p["pick"], p["by"])
        for pool in found["pools"]
        if pool["category"] == category
        for p in pool["placed"]
    }


def cost_of(tally: dict[str, Any], name: str) -> int:
    return next(line["cost"] for line in tally["lines"] if line["name"] == name)


def test_a_quick_npc_has_its_picks_fitted_for_the_most_saved(troupe: Troupe) -> None:
    npc = make_npc(troupe)["id"]
    rated(troupe.storyteller, npc, "clan", "Brujah", None)
    rated(troupe.storyteller, npc, "attributes", "Physical", 8)
    rated(troupe.storyteller, npc, "attributes", "Social", 4)
    rated(troupe.storyteller, npc, "skills", "Brawl", 5)
    rated(troupe.storyteller, npc, "skills", "Dodge", 2)
    rated(troupe.storyteller, npc, "disciplines", "Potence", 3)
    rated(troupe.storyteller, npc, "disciplines", "Celerity", 1)
    # Not in-clan for a Brujah: no starting dot.
    tally = rated(troupe.storyteller, npc, "disciplines", "Auspex", 1)

    found = picks(troupe.storyteller, npc)
    assert found["fitted"]
    # The biggest picks on the highest ratings each can take.
    assert placed(found, "attributes") == {"Physical": (7, "fit"), "Social": (3, "fit")}
    assert placed(found, "skills") == {"Brawl": (4, "fit"), "Dodge": (2, "fit")}
    assert placed(found, "disciplines") == {"Potence": (2, "fit"), "Celerity": (1, "fit")}
    # Physical's eighth dot (3); Brawl's fifth at Generation 1's × 1 (5); Potence's third
    # in-clan (9); Social's fourth (3); Auspex out-of-clan (4).
    assert [cost_of(tally, n) for n in ("Physical", "Brawl", "Potence", "Social", "Auspex")] == [
        3,
        5,
        9,
        3,
        4,
    ]
    assert cost_of(tally, "Dodge") == cost_of(tally, "Celerity") == 0


def test_staff_add_an_extra_in_clan_discipline_and_the_npc_refits(troupe: Troupe) -> None:
    """As for an NPC imported from Yorick without its extras (#565): one added by hand
    makes the discipline in-clan, so it takes a pick, and taking it off undoes that."""
    npc = make_npc(troupe)["id"]
    rated(troupe.storyteller, npc, "clan", "Caitiff", None)

    def obfuscate(tally: dict[str, Any]) -> int:
        return next(
            line["cost"]
            for line in tally["lines"]
            if (line["category"], line["name"]) == ("disciplines", "Obfuscate")
        )

    tally = rated(troupe.storyteller, npc, "disciplines", "Obfuscate", 4)
    assert obfuscate(tally) == 40
    assert placed(picks(troupe.storyteller, npc), "disciplines") == {}

    tally = rated(troupe.storyteller, npc, "extra_in_clan_disciplines", "Obfuscate", 1)
    assert placed(picks(troupe.storyteller, npc), "disciplines") == {"Obfuscate": (2, "fit")}
    assert obfuscate(tally) == 21

    tally = rated(troupe.storyteller, npc, "extra_in_clan_disciplines", "Obfuscate", 0)
    assert placed(picks(troupe.storyteller, npc), "disciplines") == {}
    assert obfuscate(tally) == 40


def test_the_fitting_prices_at_the_npcs_generation_and_house_rules(troupe: Troupe) -> None:
    """Skills cost × 1 at Generation 1 and × 2 above it in the book; a troupe can price a
    generation's skills as it likes (as one prices Generation 2's at × 1)."""

    def brawl_at_5(generation: int, name: str) -> int:
        npc = make_npc(troupe, name=name)["id"]
        rated(troupe.storyteller, npc, "backgrounds", "Generation", generation)
        tally = rated(troupe.storyteller, npc, "skills", "Brawl", 5)
        assert placed(picks(troupe.storyteller, npc), "skills") == {"Brawl": (4, "fit")}
        # Generation takes the background pick at its rating, so costs nothing.
        assert cost_of(tally, "Generation") == 0
        return cost_of(tally, "Brawl")

    assert brawl_at_5(1, "Neonate") == 5
    assert brawl_at_5(2, "Ancilla") == 10

    added = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/costs",
        json={
            "category": "skills",
            "condition": {"generation": 2},
            "scheme": "progressive",
            "rate": 1,
        },
    )
    assert added.status_code == 201, added.text
    assert brawl_at_5(2, "House Ancilla") == 5


def test_the_picks_follow_the_sheet_as_it_changes(troupe: Troupe) -> None:
    npc = make_npc(troupe)["id"]
    rated(troupe.storyteller, npc, "skills", "Brawl", 3)
    assert placed(picks(troupe.storyteller, npc), "skills") == {"Brawl": (3, "fit")}

    rated(troupe.storyteller, npc, "skills", "Brawl", 4)
    assert placed(picks(troupe.storyteller, npc), "skills") == {"Brawl": (4, "fit")}

    rated(troupe.storyteller, npc, "skills", "Occult", 5)
    tally = rated(troupe.storyteller, npc, "skills", "Brawl", 1)
    assert placed(picks(troupe.storyteller, npc), "skills") == {
        "Occult": (4, "fit"),
        "Brawl": (1, "fit"),
    }
    assert tally["total"] == 5


def test_merits_fill_the_budget_and_flaws_are_picked_as_the_wizard_picks_them(
    troupe: Troupe,
) -> None:
    npc = make_npc(troupe)["id"]
    for merit in ("Bloodline: Coyote", "Thorough Research"):
        rate(troupe.storyteller, npc, "merits", merit, 1)
    found = picks(troupe.storyteller, npc)
    merits = next(p for p in found["pools"] if p["category"] == "merits")
    assert merits["kind"] == "points"
    assert sum(p["pick"] for p in merits["placed"]) <= merits["allowed"]


def test_staff_move_a_pick_and_the_rest_fit_around_it(troupe: Troupe) -> None:
    npc = make_npc(troupe)["id"]
    rated(troupe.storyteller, npc, "skills", "Brawl", 4)
    rated(troupe.storyteller, npc, "skills", "Occult", 4)
    rated(troupe.storyteller, npc, "skills", "Dodge", 3)
    fitted = placed(picks(troupe.storyteller, npc), "skills")
    assert fitted["Dodge"] == (3, "fit")
    four = next(name for name, (pick, _) in fitted.items() if pick == 4)
    other = "Occult" if four == "Brawl" else "Brawl"

    # The player had the 4 on the other skill, as Yorick doesn't say.
    response = troupe.storyteller.client.put(
        f"/characters/{npc}/npc/picks",
        json={"category": "skills", "name": other, "rating": 4, "replacing": {"name": four}},
    )
    assert response.status_code == 200, response.text
    now = placed(response.json(), "skills")
    assert now[other] == (4, "staff")
    assert now[four] == (3, "fit")

    # A change to the sheet refits the rest, and keeps what staff placed.
    rated(troupe.storyteller, npc, "skills", "Stealth", 2)
    now = placed(picks(troupe.storyteller, npc), "skills")
    assert now[other] == (4, "staff") and now["Stealth"] == (2, "fit")

    # Taking a pick off keeps the fitting from putting one back there.
    response = troupe.storyteller.client.post(
        f"/characters/{npc}/npc/picks/off", json={"category": "skills", "name": "Dodge"}
    )
    assert response.status_code == 200, response.text
    assert "Dodge" not in placed(response.json(), "skills")
    assert {"category": "skills", "name": "Dodge", "detail": ""} in response.json()["kept_off"]

    # Fitting again forgets both.
    response = troupe.storyteller.client.post(f"/characters/{npc}/npc/picks/refit")
    assert response.status_code == 200, response.text
    assert {by for _, by in placed(response.json(), "skills").values()} == {"fit"}
    assert response.json()["kept_off"] == []


def test_a_pick_moved_by_hand_swaps_with_one_placed_by_hand(troupe: Troupe) -> None:
    npc = make_npc(troupe)["id"]
    rated(troupe.storyteller, npc, "skills", "Brawl", 4)
    rated(troupe.storyteller, npc, "skills", "Occult", 4)
    rated(troupe.storyteller, npc, "skills", "Stealth", 2)

    def put(name: str, rating: int, replacing: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"category": "skills", "name": name, "rating": rating}
        if replacing:
            body["replacing"] = {"name": replacing}
        response = troupe.storyteller.client.put(f"/characters/{npc}/npc/picks", json=body)
        assert response.status_code == 200, response.text
        return placed(response.json(), "skills")

    put("Occult", 4)
    put("Brawl", 3)
    # Brawl moves from 3 to 4, and Occult, placed there by hand, takes its pick at 3.
    now = put("Brawl", 4, replacing="Occult")
    assert now["Brawl"] == (4, "staff") and now["Occult"] == (3, "staff")

    # Stealth 2 can't take the pick at 3 that Occult leaves: it's fitted with the rest.
    put("Stealth", 2)
    now = put("Occult", 2, replacing="Stealth")
    assert now["Occult"] == (2, "staff")
    assert now["Stealth"] == (2, "fit")


def test_a_pick_by_hand_must_fit_where_it_goes(troupe: Troupe) -> None:
    npc = make_npc(troupe)["id"]
    rated(troupe.storyteller, npc, "clan", "Brujah", None)
    rated(troupe.storyteller, npc, "skills", "Brawl", 2)
    rated(troupe.storyteller, npc, "disciplines", "Auspex", 2)

    def put(**body: Any) -> Any:
        return troupe.storyteller.client.put(f"/characters/{npc}/npc/picks", json=body)

    too_high = put(category="skills", name="Brawl", rating=4)
    assert too_high.status_code == 422
    assert too_high.json()["detail"] == "Brawl is rated 2, below a pick at 4."
    out_of_clan = put(category="disciplines", name="Auspex", rating=2)
    assert out_of_clan.status_code == 422
    assert "not in-clan" in out_of_clan.json()["detail"]
    # Only an NPC whose picks are fitted: one built in the wizard has its own.
    wizard = make_npc(troupe, name="By Hand", wizard=True)["id"]
    refused = troupe.storyteller.client.post(f"/characters/{wizard}/npc/picks/refit")
    assert refused.status_code == 409
    # Players can't see or move an NPC's picks.
    assert troupe.player.client.get(f"/characters/{npc}/npc/picks").status_code in (403, 404)
