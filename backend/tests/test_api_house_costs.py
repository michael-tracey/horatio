"""Troupes set their own prices: the most specific price wins, whoever set it, and
a price change applies to new purchases only."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, finish, new_character
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
    assert by_subject[("skills", None, "Generation 1")]["price_text"] == (
        "1 XP × the new dot's number"
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
        ("skills", "Generation 1"),
    ]


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
    # A condition is only a rule set price's own, to replace it.
    made_up = add(troupe, category="skills", condition={"generation": 4}, scheme="per_dot", rate=1)
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
    assert changed.json()["price_text"] == "1 XP × the new dot's number"
    # What was bought keeps what it cost; the next dot is priced the new way.
    assert sheet(troupe.player, character_id)["xp"]["spent"] == spent
    assert buy(troupe.player, character_id, "attributes", "Physical", 2).json()["cost"] == 2

    assert troupe.storyteller.client.delete(url).status_code == 204
    assert troupe.storyteller.client.delete(url).status_code == 404
    assert buy(troupe.player, character_id, "attributes", "Physical", 3).json()["cost"] == 3
    assert not [c for c in costs(troupe)["costs"] if c["house"]]
    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert (
        "storyteller removed the troupe's price for Attributes (1 XP × the new dot's number)."
        in log
    )
