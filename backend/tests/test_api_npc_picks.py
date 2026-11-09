"""Creation picks fitted to an NPC built without the wizard (issue #527), so its
creation dots are free as a player character's are, at its troupe's prices."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio import import_yorick_print
from horatio.models import Character
from horatio.yorick_names import Trait
from tests.api_helpers import Person, Troupe, new_character, sign_up
from tests.test_api_free_choices import choose, grant_key, pick, trait
from tests.test_api_grants import take
from tests.test_api_npc_gifts import given
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
        if pool["category"] == category and pool["grant"] is None
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
    assert {"category": "skills", "name": "Dodge", "detail": "", "kind": "pick"} in response.json()[
        "kept_off"
    ]

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


# --- The free dots a merit places (#566) ------------------------------------------------


def places(found: dict[str, Any], merit: str) -> dict[str, tuple[int, str]]:
    """Each trait with one of the merit's places: (the place, who placed it)."""
    return {
        p["name"]: (p["pick"], p["by"])
        for pool in found["pools"]
        if pool["merit"] == merit
        for p in pool["placed"]
    }


def royal(troupe: Troupe, name: str = "Prince Vasquez") -> str:
    """A Ventrue NPC with Resources 5, Haven 3 and Allies 2, all Ventrue Royalty can
    place dots on, and Retainers 3, which it can't."""
    npc = make_npc(troupe, name=name)["id"]
    rated(troupe.storyteller, npc, "clan", "Ventrue", None)
    for background, rating in (("Resources", 5), ("Haven", 3), ("Allies", 2), ("Retainers", 3)):
        rated(troupe.storyteller, npc, "backgrounds", background, rating)
    return npc


def test_ventrue_royalty_places_4_3_and_2_where_they_save_the_most(troupe: Troupe) -> None:
    npc = royal(troupe)
    before = npc_tally(troupe, npc)

    tally = rated(troupe.storyteller, npc, "merits", "Ventrue Royalty", 2)

    found = picks(troupe.storyteller, npc)
    assert places(found, "Ventrue Royalty") == {
        "Resources": (4, "fit"),
        "Haven": (3, "fit"),
        "Allies": (2, "fit"),
    }
    # A trait takes a pick or a place, never both: the pick at 3 goes on Retainers,
    # which the merit can't place dots on.
    assert placed(found, "backgrounds") == {"Retainers": (3, "fit")}
    # At Generation 1's × 1: only Resources' fifth dot is bought.
    assert [cost_of(tally, n) for n in ("Resources", "Haven", "Allies", "Retainers")] == [
        5,
        0,
        0,
        0,
    ]
    # Before, the picks at 3, 2 and 1 saved 10 of the backgrounds' 30; now they save
    # 25. The merit's 2 points come out of the merit points.
    assert cost_of(tally, "Ventrue Royalty") == 0
    assert tally["total"] == before - 15


def test_a_place_set_by_hand_stays_and_one_taken_off_stays_off(troupe: Troupe) -> None:
    npc = royal(troupe)
    rated(troupe.storyteller, npc, "merits", "Ventrue Royalty", 2)
    grant = next(p["grant"] for p in picks(troupe.storyteller, npc)["pools"] if p["grant"])

    # A place goes only on a trait rated at least the place.
    refused = troupe.storyteller.client.put(
        f"/characters/{npc}/npc/picks",
        json={"category": "backgrounds", "name": "Haven", "rating": 4, "grant": grant},
    )
    assert refused.status_code == 422
    assert refused.json()["detail"] == "Haven is rated 3, below a place of 4."

    # Its player had the 3 on Resources, as Yorick doesn't say: placed there by hand,
    # the 4 goes where else it fits, which is nowhere.
    response = troupe.storyteller.client.put(
        f"/characters/{npc}/npc/picks",
        json={
            "category": "backgrounds",
            "name": "Resources",
            "rating": 3,
            "grant": grant,
            "replacing": {"name": "Haven"},
        },
    )
    assert response.status_code == 200, response.text
    now = places(response.json(), "Ventrue Royalty")
    assert now["Resources"] == (3, "staff")
    assert sorted(p for p, _ in now.values()) == [2, 3]

    # A change to the sheet refits the rest, and keeps what staff placed.
    rated(troupe.storyteller, npc, "backgrounds", "Herd", 4)
    now = places(picks(troupe.storyteller, npc), "Ventrue Royalty")
    assert now["Resources"] == (3, "staff")
    assert now["Herd"] == (4, "fit")

    # Taking a place off keeps the fitting from putting one back there.
    response = troupe.storyteller.client.post(
        f"/characters/{npc}/npc/picks/off",
        json={"category": "backgrounds", "name": "Herd", "grant": grant},
    )
    assert response.status_code == 200, response.text
    assert "Herd" not in places(response.json(), "Ventrue Royalty")
    assert {
        "category": "backgrounds",
        "name": "Herd",
        "detail": "",
        "kind": "place",
    } in response.json()["kept_off"]
    # Herd can still take a creation pick.
    assert "Herd" in placed(response.json(), "backgrounds")
    rated(troupe.storyteller, npc, "backgrounds", "Fame", 1)
    assert "Herd" not in places(picks(troupe.storyteller, npc), "Ventrue Royalty")

    # Fitting again forgets both.
    response = troupe.storyteller.client.post(f"/characters/{npc}/npc/picks/refit")
    assert response.status_code == 200, response.text
    assert {by for _, by in places(response.json(), "Ventrue Royalty").values()} == {"fit"}
    assert response.json()["kept_off"] == []


def test_lowering_a_trait_below_its_place_takes_the_place_off(troupe: Troupe) -> None:
    npc = royal(troupe)
    rated(troupe.storyteller, npc, "merits", "Ventrue Royalty", 2)
    grant = next(p["grant"] for p in picks(troupe.storyteller, npc)["pools"] if p["grant"])
    put = troupe.storyteller.client.put(
        f"/characters/{npc}/npc/picks",
        json={"category": "backgrounds", "name": "Resources", "rating": 4, "grant": grant},
    )
    assert put.status_code == 200, put.text

    tally = rated(troupe.storyteller, npc, "backgrounds", "Resources", 2)

    assert places(picks(troupe.storyteller, npc), "Ventrue Royalty").get("Resources") != (
        4,
        "staff",
    )
    assert cost_of(tally, "Resources") == 0


def test_removing_the_merit_removes_its_places(troupe: Troupe) -> None:
    npc = royal(troupe)
    before = npc_tally(troupe, npc)
    rated(troupe.storyteller, npc, "merits", "Ventrue Royalty", 2)
    assert places(picks(troupe.storyteller, npc), "Ventrue Royalty")

    tally = rated(troupe.storyteller, npc, "merits", "Ventrue Royalty", 0)

    found = picks(troupe.storyteller, npc)
    assert not any(p["grant"] for p in found["pools"])
    # The backgrounds are as they were: the picks at 3, 2 and 1, and the rest bought.
    assert sorted(p for p, _ in placed(found, "backgrounds").values()) == [1, 2, 3]
    assert tally["total"] == before


def on_a_path(troupe: Troupe, rating: int) -> str:
    """An NPC with the Path of Blood merit, its Path put on as the Yorick import puts
    it: straight, in Humanity's place, not converted from it, so with no free dots."""
    npc = make_npc(troupe)["id"]
    character = troupe.session.get_one(Character, uuid.UUID(npc))
    import_yorick_print.put(troupe.session, character, Trait("paths", "Blood", rating=rating))
    rated(troupe.storyteller, npc, "merits", "Path of Blood", 3)
    return npc


def test_a_path_merit_makes_the_paths_dots_free_up_to_the_starting_humanity(
    troupe: Troupe,
) -> None:
    npc = on_a_path(troupe, 5)

    found = picks(troupe.storyteller, npc)
    assert places(found, "Path of Blood") == {"Blood": (5, "fit")}
    assert cost_of(npc_tally_lines(troupe, npc), "Blood") == 0

    # Taken off, the Path is bought, at 10 a dot; put back, it is free again.
    grant = next(p["grant"] for p in found["pools"] if p["merit"] == "Path of Blood")
    body = {"category": "paths", "name": "Blood", "grant": grant}
    off = troupe.storyteller.client.post(f"/characters/{npc}/npc/picks/off", json=body)
    assert off.status_code == 200, off.text
    assert places(off.json(), "Path of Blood") == {}
    assert cost_of(npc_tally_lines(troupe, npc), "Blood") == 50
    back = troupe.storyteller.client.put(f"/characters/{npc}/npc/picks", json=body)
    assert back.status_code == 200, back.text
    assert places(back.json(), "Path of Blood") == {"Blood": (5, "fit")}


def test_a_path_merit_converts_what_the_path_has(troupe: Troupe) -> None:
    npc = on_a_path(troupe, 2)

    assert places(picks(troupe.storyteller, npc), "Path of Blood") == {"Blood": (2, "fit")}
    assert cost_of(npc_tally_lines(troupe, npc), "Blood") == 0

    # Without the merit, the Path turns back into Humanity, which has no place.
    tally = rated(troupe.storyteller, npc, "merits", "Path of Blood", 0)
    assert [line["name"] for line in tally["lines"] if line["category"] == "paths"] == ["Humanity"]
    assert not any(p["grant"] for p in picks(troupe.storyteller, npc)["pools"])


def test_a_wizard_built_characters_own_choices_are_never_touched(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Ventrue")
    take(troupe.player, character_id, "merits", "Ventrue Royalty", 2)
    grant = grant_key(troupe.player, character_id, "Ventrue Royalty")
    chosen = [pick(grant, "Resources", 4), pick(grant, "Herd", 3), pick(grant, "Contacts", 2)]
    assert choose(troupe.player, character_id, "Ventrue Royalty", chosen).status_code == 200

    take(troupe.player, character_id, "backgrounds", "Haven", 2)

    royalty = trait(troupe.player, character_id, "merits", "Ventrue Royalty")
    assert [(c["name"], c["amount"]) for c in royalty["free_choices"][0]["picks"]] == [
        ("Resources", 4),
        ("Herd", 3),
        ("Contacts", 2),
    ]
    # And an NPC built in the wizard has no places fitted.
    wizard = make_npc(troupe, name="By Hand", wizard=True)["id"]
    assert not picks(troupe.storyteller, wizard)["fitted"]


def test_given_to_a_player_the_places_become_the_merits_own_choices(troupe: Troupe) -> None:
    npc = royal(troupe)
    rated(troupe.storyteller, npc, "merits", "Ventrue Royalty", 2)
    heir = sign_up(troupe.client_for, "heir")
    assert npc_tally(troupe, npc) == preview_xp(troupe, npc)

    given(troupe.storyteller, npc, heir)

    royalty = trait(heir, npc, "merits", "Ventrue Royalty")
    assert [(c["name"], c["amount"]) for c in royalty["free_choices"][0]["picks"]] == [
        ("Resources", 4),
        ("Haven", 3),
        ("Allies", 2),
    ]
    resources = trait(heir, npc, "backgrounds", "Resources")
    assert (resources["rating"], resources["free_rating"]) == (5, 4)
    # Its grants are brought into line on its next change, and keep the dots as they are.
    take(heir, npc, "skills", "Brawl", 1)
    resources = trait(heir, npc, "backgrounds", "Resources")
    assert (resources["rating"], resources["free_rating"]) == (5, 4)
    assert trait(heir, npc, "backgrounds", "Allies")["free_rating"] == 2


def npc_tally_lines(troupe: Troupe, npc: str) -> dict[str, Any]:
    response = troupe.storyteller.client.get(f"/characters/{npc}/npc/tally")
    assert response.status_code == 200, response.text
    found: dict[str, Any] = response.json()
    return found


def npc_tally(troupe: Troupe, npc: str) -> int:
    total: int = npc_tally_lines(troupe, npc)["total"]
    return total


def preview_xp(troupe: Troupe, npc: str) -> int:
    response = troupe.storyteller.client.get(f"/characters/{npc}/give-to-player")
    assert response.status_code == 200, response.text
    xp: int = response.json()["xp"]
    return xp
