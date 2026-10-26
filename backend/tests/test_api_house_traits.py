"""House merits and flaws: a troupe's own, for its own characters only, given by
staff or picked when building for the troupe, and marked as the troupe's."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, finish, new_character
from tests.test_api_cart import rating, spend
from tests.test_api_creation import creating, pick
from tests.test_api_npcs_titles import make_npc
from tests.test_api_renames import character_log, other_troupe, troupe_log, visit
from tests.test_api_sheets import buy, make_home_troupe_member, sheet

pytestmark = pytest.mark.usefixtures("without_bank")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def make(troupe: Troupe, person: Person | None = None, **fields: Any) -> Any:
    body = {
        "category": "merits",
        "name": "Child of the Crossroads",
        "points": 2,
        "availability": "building",
        "description": "Knows every back road out of town.",
        **fields,
    }
    return (person or troupe.storyteller).client.post(
        f"/troupes/{troupe.id}/house-traits", json=body
    )


def made(troupe: Troupe, **fields: Any) -> dict[str, Any]:
    response = make(troupe, **fields)
    assert response.status_code == 201, response.text
    return response.json()


def homed(troupe: Troupe, name: str = "Agnes") -> str:
    character_id = new_character(troupe, troupe.player, name)
    make_home_troupe_member(troupe.session, troupe, character_id)
    return character_id


def apply(
    troupe: Troupe, character_id: str, house_id: str, person: Person | None = None, **options: Any
) -> Any:
    return (person or troupe.assistant).client.post(
        f"/characters/{character_id}/house-traits",
        json={"house_trait_id": house_id, "reason": "A gift of the Prince", **options},
    )


def remove(troupe: Troupe, character_id: str, house_id: str, person: Person | None = None) -> Any:
    return (person or troupe.assistant).client.post(
        f"/characters/{character_id}/house-traits/{house_id}/remove",
        json={"reason": "The favour is spent"},
    )


def trait(person: Person, character_id: str, name: str) -> dict[str, Any] | None:
    return next((t for t in sheet(person, character_id)["traits"] if t["name"] == name), None)


def catalogue(person: Person, troupe_id: str | None) -> dict[str, dict[str, Any]]:
    query = f"?troupe_id={troupe_id}" if troupe_id else ""
    response = person.client.get(f"/rules/vampire{query}")
    assert response.status_code == 200, response.text
    return {t["name"]: t for t in response.json()["traits"] if t["category"] in ("merits", "flaws")}


# --- Making them --------------------------------------------------------------------------


def test_storytellers_make_house_merits_and_the_troupe_log_says_so(troupe: Troupe) -> None:
    assert make(troupe, troupe.assistant).status_code == 403
    assert make(troupe, troupe.player).status_code == 403

    house = made(troupe, kind="Clan", requirement="Nosferatu")

    assert (house["label"], house["page"], house["holders"]) == (
        "House merit of Lords of the Night",
        "House rule — Lords of the Night",
        0,
    )
    listed = troupe.assistant.client.get(f"/troupes/{troupe.id}/house-traits")
    assert [h["name"] for h in listed.json()] == ["Child of the Crossroads"]
    assert troupe.narrator.client.get(f"/troupes/{troupe.id}/house-traits").status_code == 403
    assert (
        "storyteller made a house merit, ★ Child of the Crossroads (2 points, available when"
        " building for the troupe)." in troupe_log(troupe.lead, troupe.id)
    )


def test_a_house_name_must_not_be_the_books_nor_the_troupes_again(troupe: Troupe) -> None:
    made(troupe)

    assert make(troupe, name="Acute Sense").status_code == 409
    assert make(troupe, name="acute sense", category="flaws").status_code == 409
    again = make(troupe, name="Child of the Crossroads", category="flaws")
    assert again.status_code == 409
    assert "already has a house merit" in again.json()["detail"]
    assert make(troupe, points=8).status_code == 422


def test_the_catalogue_has_them_for_the_troupe_only(troupe: Troupe) -> None:
    made(troupe)
    made(troupe, name="Marked by the Prince", category="flaws", points=1, availability="staff")
    elsewhere = other_troupe(troupe)

    here = catalogue(troupe.player, troupe.id)
    assert here["Child of the Crossroads"]["fixed_rating"] == 2
    assert here["Child of the Crossroads"]["page_reference"] == "House rule — Lords of the Night"
    assert here["Child of the Crossroads"]["house"]["label"] == (
        "House merit of Lords of the Night"
    )
    assert here["Child of the Crossroads"]["house"]["offered"] is True
    assert here["Marked by the Prince"]["house"]["label"] == "House flaw of Lords of the Night"
    assert here["Marked by the Prince"]["house"]["offered"] is False
    assert here["Acute Sense"]["house"] is None
    assert "Child of the Crossroads" not in catalogue(troupe.player, None)
    assert "Child of the Crossroads" not in catalogue(troupe.player, elsewhere)


# --- Who can take them ----------------------------------------------------------------------


def test_home_and_building_characters_buy_one_like_a_book_merit(troupe: Troupe) -> None:
    made(troupe)
    home = homed(troupe)
    building = troupe.player.client.post(
        "/characters",
        json={"splat": "vampire", "name": "Bram", "building_troupe_id": troupe.id},
    ).json()["id"]
    finish(troupe, building)

    bought = buy(troupe.player, home, "merits", "Child of the Crossroads", 2)
    assert bought.status_code == 200, bought.text
    assert bought.json()["cost"] == 2
    assert buy(troupe.player, building, "merits", "Child of the Crossroads", 2).json()["cost"] == 2
    held = trait(troupe.player, home, "Child of the Crossroads")
    assert held is not None
    assert held["house"]["label"] == "House merit of Lords of the Night"
    assert held["house"]["applied"] is None
    assert "player bought ★ Child of the Crossroads 2 for Agnes (2 XP)." in character_log(
        troupe.player, home
    )


def test_a_visiting_character_can_neither_take_one_nor_be_given_one(troupe: Troupe) -> None:
    buildable = made(troupe)
    staff_only = made(troupe, name="Favour of the Court", availability="staff")
    elsewhere = other_troupe(troupe)
    visitor = new_character(troupe, troupe.player, "Visiting Vera")
    visit(troupe.player, visitor, troupe.id)
    visit(troupe.player, visitor, elsewhere)

    refused = buy(troupe.player, visitor, "merits", "Child of the Crossroads", 2)
    assert refused.status_code == 422
    for house in (buildable, staff_only):
        assigned = apply(troupe, visitor, house["id"], free=True)
        assert assigned.status_code == 409, assigned.text
        assert "only for characters whose home troupe" in assigned.json()["detail"]
    assert trait(troupe.player, visitor, "Child of the Crossroads") is None


def test_a_staff_only_merit_is_refused_through_the_cart(troupe: Troupe) -> None:
    made(troupe, name="Favour of the Court", availability="staff", points=3)
    character_id = homed(troupe)

    refused = buy(troupe.player, character_id, "merits", "Favour of the Court", 3)
    assert refused.status_code == 409
    assert (
        refused.json()["detail"]
        == "Favour of the Court is given by Lords of the Night's staff only."
    )
    line = spend(troupe.player, character_id, rating("merits", "Favour of the Court", 3))
    assert line.json()["lines"][0]["refused"] is not None
    unavailable = troupe.player.client.get(
        f"/characters/{character_id}/unavailable", params={"category": "merits"}
    ).json()
    assert "Favour of the Court" in unavailable


# --- Staff apply and remove ---------------------------------------------------------------


def test_staff_apply_one_free_with_a_reason_for_both_logs(troupe: Troupe) -> None:
    house = made(troupe, name="Favour of the Court", availability="staff", points=3)
    character_id = homed(troupe)
    before = sheet(troupe.player, character_id)["xp"]["balance"]

    assert apply(troupe, character_id, house["id"], troupe.narrator, free=True).status_code == 404
    assert apply(troupe, character_id, house["id"], troupe.player, free=True).status_code == 403
    applied = apply(troupe, character_id, house["id"], free=True)

    assert applied.status_code == 200, applied.text
    held = next(t for t in applied.json()["traits"] if t["name"] == "Favour of the Court")
    assert (held["rating"], held["free_rating"]) == (3, 3)
    assert held["house"]["applied"] == {
        "free": True,
        "counts_toward_limit": True,
        "reason": "A gift of the Prince",
    }
    assert sheet(troupe.player, character_id)["xp"]["balance"] == before
    message = (
        "assistant gave Agnes (player) the house merit of Lords of the Night"
        " ★ Favour of the Court (free): A gift of the Prince"
    )
    assert message in troupe_log(troupe.lead, troupe.id)
    assert any(
        "★ Favour of the Court (free)" in m for m in character_log(troupe.player, character_id)
    )
    xp = troupe.player.client.get(f"/characters/{character_id}/xp").json()
    assert any("given free by staff: A gift of the Prince" in e["reason"] for e in xp)

    # Only staff take it away.
    assert buy(troupe.player, character_id, "merits", "Favour of the Court", 0).status_code == 409
    assert apply(troupe, character_id, house["id"], free=True).status_code == 409
    removed = remove(troupe, character_id, house["id"])
    assert removed.status_code == 200, removed.text
    assert trait(troupe.player, character_id, "Favour of the Court") is None
    assert any(
        "took the house merit of Lords of the Night ★ Favour of the Court off Agnes" in m
        for m in troupe_log(troupe.lead, troupe.id)
    )


def test_a_charged_merit_costs_its_points(troupe: Troupe) -> None:
    house = made(troupe, name="Favour of the Court", availability="staff", points=3)
    character_id = homed(troupe)
    before = sheet(troupe.player, character_id)["xp"]["balance"]

    applied = apply(troupe, character_id, house["id"], free=False)

    assert applied.status_code == 200, applied.text
    assert applied.json()["xp"]["balance"] == before - 3
    held = trait(troupe.player, character_id, "Favour of the Court")
    assert held is not None
    assert (held["rating"], held["free_rating"]) == (3, 0)


def test_a_free_merit_counts_toward_the_limit_unless_staff_say_not(troupe: Troupe) -> None:
    counted = made(troupe, name="Favour of the Court", availability="staff", points=3)
    outside = made(troupe, name="Blessing of the Elders", availability="staff", points=3)
    character_id = homed(troupe)
    for name in ("Iron Will", "Rugged"):  # 3 points each
        assert buy(troupe.player, character_id, "merits", name, 3).status_code == 200

    over = apply(troupe, character_id, counted["id"], free=True)
    assert over.status_code == 409
    assert "at most 7" in over.json()["detail"]
    given = apply(troupe, character_id, outside["id"], free=True, counts_toward_limit=False)
    assert given.status_code == 200, given.text
    # Left out of the 7 points: a 1-point merit still fits.
    assert buy(troupe.player, character_id, "merits", "Acute Sense", 1).status_code == 200


def test_staff_give_an_npc_one(troupe: Troupe) -> None:
    house = made(troupe, name="Favour of the Court", availability="staff")
    npc = make_npc(troupe)["id"]

    assert apply(troupe, npc, house["id"]).status_code == 200
    held = trait(troupe.assistant, npc, "Favour of the Court")
    assert held is not None
    assert held["house"]["troupe_name"] == "Lords of the Night"


# --- Archiving, deleting and changing --------------------------------------------------------


def test_archived_holders_keep_it_and_no_one_new_takes_it(troupe: Troupe) -> None:
    house = made(troupe)
    holder = homed(troupe)
    newcomer = homed(troupe, "Bram")
    assert buy(troupe.player, holder, "merits", "Child of the Crossroads", 2).status_code == 200

    archived = troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/house-traits/{house['id']}/archived", json={"archived": True}
    )

    assert archived.status_code == 200
    assert archived.json()["archived"] is True
    assert trait(troupe.player, holder, "Child of the Crossroads") is not None
    refused = buy(troupe.player, newcomer, "merits", "Child of the Crossroads", 2)
    assert refused.status_code == 409
    assert "archived" in refused.json()["detail"]
    assert (
        catalogue(troupe.player, troupe.id)["Child of the Crossroads"]["house"]["offered"] is False
    )


def test_deleting_is_only_for_one_nobody_holds(troupe: Troupe) -> None:
    house = made(troupe, availability="staff")
    character_id = homed(troupe)
    apply(troupe, character_id, house["id"], free=True)
    url = f"/troupes/{troupe.id}/house-traits/{house['id']}"

    refused = troupe.storyteller.client.delete(url)
    assert refused.status_code == 409
    assert "Agnes holds Child of the Crossroads" in refused.json()["detail"]
    remove(troupe, character_id, house["id"])
    assert troupe.storyteller.client.delete(url).status_code == 204
    assert troupe.storyteller.client.get(f"/troupes/{troupe.id}/house-traits").json() == []
    # The name is free again, and the XP history still reads.
    assert make(troupe).status_code == 201
    xp = troupe.player.client.get(f"/characters/{character_id}/xp").json()
    assert any("removed by staff" in e["reason"] for e in xp)


def test_a_change_applies_to_every_holder_and_xp_stays(troupe: Troupe) -> None:
    house = made(troupe)
    first, second = homed(troupe), homed(troupe, "Bram")
    for character_id in (first, second):
        assert (
            buy(troupe.player, character_id, "merits", "Child of the Crossroads", 2).status_code
            == 200
        )
    balances = [sheet(troupe.player, c)["xp"]["balance"] for c in (first, second)]

    holders = troupe.storyteller.client.get(
        f"/troupes/{troupe.id}/house-traits/{house['id']}/holders"
    ).json()
    assert [h["name"] for h in holders] == ["Agnes", "Bram"]
    changed = troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/house-traits/{house['id']}",
        json={
            "category": "merits",
            "name": "Child of the Old Roads",
            "points": 3,
            "availability": "building",
            "description": "Knows every road.",
        },
    )

    assert changed.status_code == 200, changed.text
    for character_id, balance in zip((first, second), balances, strict=True):
        held = trait(troupe.player, character_id, "Child of the Old Roads")
        assert held is not None
        assert held["rating"] == 3
        assert sheet(troupe.player, character_id)["xp"]["balance"] == balance
    assert catalogue(troupe.player, troupe.id)["Child of the Old Roads"]["description"] == (
        "Knows every road."
    )
    flipped = troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/house-traits/{house['id']}",
        json={
            "category": "flaws",
            "name": "Child of the Old Roads",
            "points": 3,
            "availability": "building",
        },
    )
    assert flipped.status_code == 409


# --- Creation ---------------------------------------------------------------------------------


def test_a_creation_only_house_merit_is_picked_in_creation(troupe: Troupe) -> None:
    made(troupe, creation_only=True)
    made(troupe, name="Favour of the Court", availability="staff")
    character_id = creating(troupe)
    troupe.player.client.put(
        f"/characters/{character_id}/building-troupe", json={"troupe_id": troupe.id}
    )

    assert pick(troupe.player, character_id, "merits", "Favour of the Court").status_code == 409
    picked = pick(troupe.player, character_id, "merits", "Child of the Crossroads")
    assert picked.status_code == 200, picked.text
    held = trait(troupe.player, character_id, "Child of the Crossroads")
    assert held is not None
    assert held["rating"] == 2

    # Moving away from the troupe would take its house merit with it.
    moved = troupe.player.client.put(
        f"/characters/{character_id}/building-troupe", json={"troupe_id": None}
    )
    assert moved.status_code == 409
    assert "Lords of the Night's own" in moved.json()["detail"]


def test_a_creation_only_house_merit_cannot_be_bought_afterwards(troupe: Troupe) -> None:
    made(troupe, creation_only=True)
    character_id = homed(troupe)

    refused = buy(troupe.player, character_id, "merits", "Child of the Crossroads", 2)

    assert refused.status_code == 409
    assert "only be chosen during character creation" in refused.json()["detail"]


# --- Effects on the sheet (part 2 of #232) -----------------------------------------------------

OLD_MONEY = [
    {"kind": "free_up_to", "category": "backgrounds", "names": ["Resources"], "amount": 2},
    {
        "kind": "requires",
        "test": "trait",
        "category": "backgrounds",
        "name": "Resources",
        "rating": 1,
    },
]


def old_money(troupe: Troupe, **fields: Any) -> dict[str, Any]:
    return made(
        troupe,
        name="Old Money",
        points=2,
        description="The family fortune.",
        effects=OLD_MONEY,
        **fields,
    )


def preview(troupe: Troupe, **body: Any) -> dict[str, Any]:
    trait = {
        "category": "merits",
        "name": "Old Money",
        "points": 2,
        "availability": "building",
        "effects": OLD_MONEY,
    }
    response = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/house-traits/preview", json={"trait": trait, **body}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_a_house_merit_with_effects_says_what_it_does(troupe: Troupe) -> None:
    house = old_money(troupe)

    summary = "The first 2 dots of Resources are free. Needs Resources 1 or more."
    assert house["summary"] == summary
    assert [b["kind"] for b in house["effects"]] == ["free_up_to", "requires"]
    assert house["effects"][0]["names"] == ["Resources"]
    assert catalogue(troupe.player, troupe.id)["Old Money"]["house"]["summary"] == summary


def test_a_holder_gets_its_free_dots_and_its_summary(troupe: Troupe) -> None:
    old_money(troupe)
    character_id = homed(troupe)

    bought = buy(troupe.player, character_id, "merits", "Old Money", 2)

    assert bought.status_code == 200, bought.text
    resources = trait(troupe.player, character_id, "Resources")
    assert resources is not None
    assert (resources["rating"], resources["free_rating"], resources["granted_by"]) == (
        2,
        2,
        ["Old Money"],
    )
    held = trait(troupe.player, character_id, "Old Money")
    assert held is not None
    assert held["house"]["summary"].startswith("The first 2 dots of Resources are free.")


def test_one_taken_through_the_cart_meets_its_own_check_with_its_free_dots(troupe: Troupe) -> None:
    old_money(troupe)
    character_id = homed(troupe)
    merit = rating("merits", "Old Money", 2, detail="")

    tried = spend(troupe.player, character_id, merit, dry_run=True)
    assert tried.status_code == 200, tried.text
    assert [line["refused"] for line in tried.json()["lines"]] == [None]
    bought = spend(troupe.player, character_id, merit)

    assert bought.status_code == 200, bought.text
    resources = trait(troupe.player, character_id, "Resources")
    assert resources is not None
    assert (resources["rating"], resources["free_rating"]) == (2, 2)


def test_blocks_the_rules_cannot_use_are_refused_in_plain_words(troupe: Troupe) -> None:
    refused = make(
        troupe,
        effects=[
            {"kind": "free_up_to", "category": "backgrounds", "names": ["Wealth"], "amount": 2},
            {"kind": "raise_max", "category": "skills", "names": ["Lore"], "amount": 2},
            {"kind": "requires", "test": "clan", "names": []},
        ],
    )

    assert refused.status_code == 422
    assert refused.json()["detail"] == (
        "Effect 1: Wealth is not one of the backgrounds. Effect 3: Choose at least one clan."
    )
    assert make(troupe, effects=[{"kind": "pool_bonus"}]).status_code == 422


def test_the_preview_shows_what_a_new_character_would_get(troupe: Troupe) -> None:
    found = preview(troupe)

    assert found["sample"] == "a new character"
    assert found["summary"] == "The first 2 dots of Resources are free. Needs Resources 1 or more."
    assert found["changes"] == ["Resources: 0 → 2, all free."]
    assert found["checks"] == [
        {"text": "Old Money: needs Resources 1 or more.", "met": True, "strength": "refuse"}
    ]
    assert found["problems"] == []


def test_the_preview_tries_it_on_one_of_the_troupes_characters(troupe: Troupe) -> None:
    character_id = homed(troupe)
    assert buy(troupe.player, character_id, "backgrounds", "Resources", 3).status_code == 200
    raised = {"kind": "raise_max", "category": "backgrounds", "names": ["Resources"], "amount": 1}
    priced = {
        "kind": "cost_percent",
        "category": "backgrounds",
        "names": ["Resources"],
        "amount": 50,
    }
    not_rich = {
        "kind": "forbids",
        "test": "trait",
        "category": "backgrounds",
        "name": "Resources",
        "rating": 3,
        "strength": "review",
    }

    found = preview(
        troupe,
        character_id=character_id,
        trait={
            "category": "merits",
            "name": "Old Money",
            "points": 2,
            "availability": "building",
            "effects": [*OLD_MONEY, raised, priced, not_rich],
        },
    )

    assert found["sample"] == "Agnes"
    assert [s["name"] for s in found["samples"]] == ["Agnes"]
    assert found["changes"][0] == (
        "Resources: 3 → 3, 2 of them free; the 2 already bought there would be refunded."
    )
    assert found["changes"][1] == "Resources: up to 6 (otherwise 5)."
    assert found["changes"][2].startswith("Resources: dot 4 costs ")
    assert "(otherwise" in found["changes"][2]
    assert [c["met"] for c in found["checks"]] == [True, False]


def test_the_preview_is_only_tried_on_the_troupes_own_characters(troupe: Troupe) -> None:
    # Isaure has no home troupe, nor one she is built for.
    character_id = new_character(troupe, troupe.player, "Isaure")

    refused = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/house-traits/preview",
        json={
            "trait": {
                "category": "merits",
                "name": "Old Money",
                "points": 2,
                "availability": "building",
            },
            "character_id": character_id,
        },
    )

    assert refused.status_code == 409
    assert (
        troupe.assistant.client.post(
            f"/troupes/{troupe.id}/house-traits/preview",
            json={
                "trait": {
                    "category": "merits",
                    "name": "Old Money",
                    "points": 2,
                    "availability": "building",
                }
            },
        ).status_code
        == 403
    )


def test_changing_its_effects_changes_every_holder_and_xp_stays(troupe: Troupe) -> None:
    house = old_money(troupe)
    first, second = homed(troupe), homed(troupe, "Bram")
    for character_id in (first, second):
        assert buy(troupe.player, character_id, "merits", "Old Money", 2).status_code == 200
    balances = [sheet(troupe.player, c)["xp"]["balance"] for c in (first, second)]

    changed = troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/house-traits/{house['id']}",
        json={
            "category": "merits",
            "name": "Old Money",
            "points": 2,
            "availability": "building",
            "effects": [
                {"kind": "free_up_to", "category": "backgrounds", "names": ["Herd"], "amount": 1},
            ],
        },
    )

    assert changed.status_code == 200, changed.text
    assert changed.json()["summary"] == "The first dot of Herd is free."
    for character_id, balance in zip((first, second), balances, strict=True):
        assert trait(troupe.player, character_id, "Resources") is None
        herd = trait(troupe.player, character_id, "Herd")
        assert herd is not None
        assert (herd["rating"], herd["granted_by"]) == (1, ["Old Money"])
        assert sheet(troupe.player, character_id)["xp"]["balance"] == balance
    assert any("(description, effects)" in line for line in troupe_log(troupe.lead, troupe.id))
