"""Troupes set their own prices: the most specific price wins, whoever set it, and
a price change applies to new purchases only."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, finish, new_character
from tests.test_api_sect_status import put_trait
from tests.test_api_sheets import buy, make_home_troupe_member, sheet

pytestmark = pytest.mark.usefixtures("without_bank")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def costs(troupe: Troupe, person: Person | None = None) -> dict[str, Any]:
    response = (person or troupe.storyteller).client.get(f"/troupes/{troupe.id}/costs")
    assert response.status_code == 200, response.text
    return response.json()


def add(troupe: Troupe, person: Person | None = None, **price: Any) -> Any:
    return (person or troupe.storyteller).client.post(f"/troupes/{troupe.id}/costs", json=price)


def homed(troupe: Troupe, session: Session, **kwargs: Any) -> str:
    character_id = new_character(troupe, troupe.player, **kwargs)
    make_home_troupe_member(session, troupe, character_id)
    return character_id


def test_the_rule_set_prices_are_listed_in_plain_words(troupe: Troupe) -> None:
    listed = costs(troupe, troupe.assistant)

    by_subject = {(c["category"], c["trait"], c["condition_text"]): c for c in listed["costs"]}
    assert by_subject[("attributes", None, None)]["price_text"] == "3 XP per dot"
    assert by_subject[("merits", None, None)]["price_text"] == "1 XP per point"
    assert by_subject[("flaws", None, None)]["price_text"] == "1 XP back per point"
    assert by_subject[("skills", None, "Generation background 1")]["price_text"] == (
        "1 XP × the new rating"
    )
    path = by_subject[("merits", "Path of Blood", "Assamite clan")]
    assert (path["price_text"], path["house"], path["id"]) == ("2 XP", False, None)
    merits = next(c for c in listed["categories"] if c["key"] == "merits")
    assert (merits["per_trait"], merits["unit"]) == (True, "point")
    assert troupe.narrator.client.get(f"/troupes/{troupe.id}/costs").status_code == 403


def test_only_storytellers_set_prices(troupe: Troupe) -> None:
    price = {"category": "attributes", "scheme": "per_dot", "rate": 4}

    assert add(troupe, troupe.assistant, **price).status_code == 403
    added = add(troupe, **price)

    assert added.status_code == 201, added.text
    assert (added.json()["house"], added.json()["price_text"]) == (True, "4 XP per dot")
    log = troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()
    assert "storyteller priced Attributes at 4 XP per dot." in [e["message"] for e in log]


def test_a_troupe_price_is_charged_to_its_characters_only(troupe: Troupe, session: Session) -> None:
    add(troupe, category="attributes", scheme="per_dot", rate=5, text="Training is hard")
    home = homed(troupe, session)
    building = troupe.player.client.post(
        "/characters",
        json={"splat": "vampire", "name": "Bram", "building_troupe_id": troupe.id},
    ).json()["id"]
    elsewhere = new_character(troupe, troupe.player, "Cora")

    assert buy(troupe.player, home, "attributes", "Physical", 1).json()["cost"] == 5
    finish(troupe, building)
    assert buy(troupe.player, building, "attributes", "Physical", 1).json()["cost"] == 5
    assert buy(troupe.player, elsewhere, "attributes", "Physical", 1).json()["cost"] == 3


def test_a_category_price_leaves_more_specific_rule_set_prices_alone(
    troupe: Troupe, session: Session
) -> None:
    """Skills cost less at Generation 1 by the book; a troupe price for all skills
    does not override that, but a price for the Generation 1 row itself does."""
    add(troupe, category="skills", scheme="progressive", rate=3)
    character_id = homed(troupe, session)

    assert buy(troupe.player, character_id, "skills", "Brawl", 1).json()["cost"] == 1

    gen_1 = add(troupe, category="skills", condition={"generation": 1}, scheme="per_dot", rate=4)
    assert gen_1.status_code == 201, gen_1.text
    assert buy(troupe.player, character_id, "skills", "Brawl", 2).json()["cost"] == 4
    replaced = [c for c in costs(troupe)["costs"] if c["replaced"]]
    assert [(c["category"], c["condition_text"]) for c in replaced] == [
        ("skills", None),
        ("skills", "Generation background 1"),
    ]


def test_a_troupe_price_with_its_own_condition(troupe: Troupe, session: Session) -> None:
    """Skills at × 1 for Generation 2 as well as the book's Generation 1 (issue #522)."""
    added = add(
        troupe, category="skills", condition={"generation": 2}, scheme="progressive", rate=1
    )
    assert added.status_code == 201, added.text
    assert (added.json()["condition_text"], added.json()["replaced"]) == (
        "Generation background 2",
        False,
    )
    priced_at = {}
    for rating in (1, 2, 3):
        character_id = homed(troupe, session, name=f"Gen {rating}")
        put_trait(session, character_id, "backgrounds", "Generation", rating)
        priced_at[rating] = buy(troupe.player, character_id, "skills", "Brawl", 2).json()["cost"]

    assert priced_at == {1: 3, 2: 3, 3: 6}
    listed = costs(troupe)
    assert "generation" in listed["facts"]
    ours = [(c["condition_text"], c["price_text"]) for c in listed["costs"] if c["house"]]
    assert ours == [("Generation background 2", "1 XP × the new rating")]
    shown = troupe.player.client.get(f"/troupes/{troupe.id}/house-rules").json()
    assert [c["subject"] for c in shown["splats"][0]["costs"]] == [
        "All Skills, Generation background 2"
    ]
    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert "storyteller priced Skills (Generation background 2) at 1 XP × the new rating." in log


def test_conditions_on_in_clan_and_clan_for_one_trait(troupe: Troupe, session: Session) -> None:
    clan_price = add(
        troupe,
        category="disciplines",
        trait="Potence",
        condition={"clan_family": "Brujah", "generation": {"gte": 2, "lte": 3}},
        scheme="per_dot",
        rate=1,
    )
    assert clan_price.status_code == 201, clan_price.text
    assert clan_price.json()["condition_text"] == (
        "Brujah clan, Generation background 2 or more and 3 or less"
    )
    # As specific as the book's out-of-clan prices, so the troupe's wins.
    out_of_clan = add(
        troupe,
        category="disciplines",
        condition={"in_clan": False, "clan_family": "Brujah"},
        scheme="per_dot",
        rate=9,
    )
    assert out_of_clan.status_code == 201, out_of_clan.text
    brujah = homed(troupe, session, clan="Brujah")
    put_trait(session, brujah, "backgrounds", "Generation", 2)

    assert buy(troupe.player, brujah, "disciplines", "Potence", 1).json()["cost"] == 1
    assert buy(troupe.player, brujah, "disciplines", "Dominate", 1).json()["cost"] == 9


def test_a_condition_must_be_one_a_character_could_meet(troupe: Troupe) -> None:
    def refused(condition: dict[str, Any]) -> str:
        response = add(troupe, category="skills", condition=condition, scheme="per_dot", rate=1)
        assert response.status_code == 422, response.text
        return response.json()["detail"]

    assert "unknown fact 'social_age'" in refused({"social_age": "Ancilla"})
    assert "unknown operator 'about'" in refused({"generation": {"about": 2}})
    assert refused({"generation": 6}) == "No character could meet that condition."
    assert refused({"clan": "Brujah", "clan_family": "Ventrue"}) == (
        "No character could meet that condition."
    )
    assert refused({"generation": {"lte": "two"}}) == "No character could meet that condition."


def test_a_tie_between_troupe_prices_is_refused_when_saved(
    troupe: Troupe, session: Session
) -> None:
    add(troupe, category="skills", condition={"generation": 2}, scheme="progressive", rate=1)

    clash = add(troupe, category="skills", condition={"in_clan": False}, scheme="per_dot", rate=4)
    as_range = add(
        troupe, category="skills", condition={"generation": {"lte": 2}}, scheme="per_dot", rate=4
    )

    assert clash.status_code == 409
    assert clash.json()["detail"].startswith(
        "That ties with the troupe's price for All Skills, Generation background 2:"
    )
    assert as_range.status_code == 409
    # Never both at once, or more specific: no tie.
    other = add(troupe, category="skills", condition={"generation": 3}, scheme="per_dot", rate=4)
    assert other.status_code == 201, other.text
    narrower = add(
        troupe,
        category="skills",
        condition={"generation": 2, "clan_family": "Brujah"},
        scheme="per_dot",
        rate=4,
    )
    assert narrower.status_code == 201, narrower.text
    # Changing a price into a tie is refused as well.
    url = f"/troupes/{troupe.id}/costs/{other.json()['id']}"
    changed = troupe.storyteller.client.put(
        url, json={"scheme": "per_dot", "rate": 4, "condition": {"generation": {"gte": 2}}}
    )
    assert changed.status_code == 409, changed.text
    # No price was left tied, so pricing never has to refuse one.
    character_id = homed(troupe, session)
    put_trait(session, character_id, "backgrounds", "Generation", 2)
    assert buy(troupe.player, character_id, "skills", "Brawl", 1).json()["cost"] == 1


def test_removing_the_price_that_settles_a_tie_is_refused(troupe: Troupe) -> None:
    def price(condition: dict[str, Any]) -> Any:
        added = add(troupe, category="skills", condition=condition, scheme="per_dot", rate=1)
        assert added.status_code == 201, added.text
        return added.json()

    price({"generation": 2})
    settles = price({"generation": 2, "clan_family": "Brujah"})
    # Only Brujah of Generation 2 meet both, and the price above settles that.
    price({"clan_family": "Brujah"})

    removed = troupe.storyteller.client.delete(f"/troupes/{troupe.id}/costs/{settles['id']}")

    assert removed.status_code == 409
    assert "would tie" in removed.json()["detail"]


def test_changing_a_troupe_price_s_condition(troupe: Troupe, session: Session) -> None:
    mine = add(troupe, category="skills", condition={"generation": 2}, scheme="progressive", rate=1)
    url = f"/troupes/{troupe.id}/costs/{mine.json()['id']}"

    assert troupe.narrator.client.put(url, json={"scheme": "fixed", "rate": 1}).status_code == 403
    # Left out, the condition stays.
    kept = troupe.storyteller.client.put(url, json={"scheme": "progressive", "rate": 1})
    assert kept.json()["condition"] == {"generation": 2}
    changed = troupe.storyteller.client.put(
        url, json={"scheme": "progressive", "rate": 1, "condition": {"generation": {"lte": 3}}}
    )

    assert changed.status_code == 200, changed.text
    assert changed.json()["condition_text"] == "Generation background 3 or less"
    character_id = homed(troupe, session)
    put_trait(session, character_id, "backgrounds", "Generation", 3)
    assert buy(troupe.player, character_id, "skills", "Brawl", 2).json()["cost"] == 3

    # A price that replaces the rule set's keeps that price's condition.
    book = add(
        troupe, category="backgrounds", condition={"generation": 1}, scheme="per_dot", rate=1
    )
    book_url = f"/troupes/{troupe.id}/costs/{book.json()['id']}"
    moved = troupe.storyteller.client.put(
        book_url, json={"scheme": "per_dot", "rate": 1, "condition": {"generation": 4}}
    )
    assert moved.status_code == 422
    same = troupe.storyteller.client.put(
        book_url, json={"scheme": "per_dot", "rate": 2, "condition": {"generation": 1}}
    )
    assert same.status_code == 200, same.text


def test_only_storytellers_set_prices_with_conditions(troupe: Troupe) -> None:
    price = {"category": "skills", "condition": {"generation": 2}, "scheme": "free"}

    assert add(troupe, troupe.narrator, **price).status_code == 403
    assert add(troupe, troupe.assistant, **price).status_code == 403
    assert add(troupe, **price).status_code == 201


def test_a_merit_price_beats_the_category_but_not_a_clan_price(
    troupe: Troupe, session: Session
) -> None:
    add(troupe, category="merits", trait="Path of Blood", scheme="fixed", rate=4)
    # Path of Blood is only for Assamites by the book; this troupe lets anyone take it.
    troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/checks/merits/Path of Blood/requirement", json={"strength": "off"}
    )
    assamite = homed(troupe, session, clan="Assamite")
    brujah = homed(troupe, session, clan="Brujah", name="Bram")

    assert buy(troupe.player, assamite, "merits", "Path of Blood", 3).json()["cost"] == 2
    # A fixed price is the merit's value where it applies: a 4-point merit for the Brujah.
    assert buy(troupe.player, brujah, "merits", "Path of Blood", 4).json()["cost"] == 4


def test_prices_that_could_not_apply_are_refused(troupe: Troupe) -> None:
    # Merits are priced one at a time, never as a whole category.
    assert add(troupe, category="merits", scheme="per_dot", rate=2).status_code == 422
    # A condition tests only the splat's facts.
    made_up = add(troupe, category="skills", condition={"rank": 4}, scheme="per_dot", rate=1)
    assert made_up.status_code == 422
    assert add(troupe, category="skills", scheme="per_dot").status_code == 422
    assert add(troupe, category="skills", trait="Juggling", scheme="free").status_code == 422
    assert add(troupe, category="skills", scheme="free").status_code == 201
    assert add(troupe, category="skills", scheme="free").status_code == 409


def test_changing_and_removing_a_price(troupe: Troupe, session: Session) -> None:
    price = add(troupe, category="attributes", scheme="per_dot", rate=5).json()
    character_id = homed(troupe, session)
    buy(troupe.player, character_id, "attributes", "Physical", 1)
    spent = sheet(troupe.player, character_id)["xp"]["spent"]
    url = f"/troupes/{troupe.id}/costs/{price['id']}"

    assert troupe.assistant.client.put(url, json={"scheme": "fixed", "rate": 1}).status_code == 403
    changed = troupe.storyteller.client.put(url, json={"scheme": "progressive", "rate": 1})

    assert changed.status_code == 200, changed.text
    assert changed.json()["price_text"] == "1 XP × the new rating"
    # What was bought keeps what it cost; the next dot is priced the new way.
    assert sheet(troupe.player, character_id)["xp"]["spent"] == spent
    assert buy(troupe.player, character_id, "attributes", "Physical", 2).json()["cost"] == 2

    assert troupe.storyteller.client.delete(url).status_code == 204
    assert troupe.storyteller.client.delete(url).status_code == 404
    assert buy(troupe.player, character_id, "attributes", "Physical", 3).json()["cost"] == 3
    assert not [c for c in costs(troupe)["costs"] if c["house"]]
    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert "storyteller removed the troupe's price for Attributes (1 XP × the new rating)." in log
