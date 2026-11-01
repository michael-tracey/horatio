"""The rules browser (issue #422): every trait with its prices, checks, powers and a
clan's rarity, as the book has them, or as played in one troupe, its house rules
applied and the traits it does not allow listed."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe

pytestmark = pytest.mark.usefixtures("without_bank")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def browse(person: Person, troupe: Troupe | None = None) -> dict[str, Any]:
    params = {"troupe_id": troupe.id} if troupe else {}
    response = person.client.get("/rules/vampire/browse", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def trait(read: dict[str, Any], category: str, name: str) -> dict[str, Any] | None:
    return next(
        (t for t in read["catalogue"]["traits"] if (t["category"], t["name"]) == (category, name)),
        None,
    )


def test_the_book_has_every_trait_with_its_powers_prices_and_checks(troupe: Troupe) -> None:
    read = browse(troupe.stranger)

    assert read["troupe_name"] is None
    assert trait(read, "merits", "Absent Sway") is not None
    majesty = next(p for p in read["powers"] if p["name"] == "Majesty")
    assert (majesty["discipline"], majesty["level"]) == ("Presence", 5)
    assert "no one can act against you" in majesty["note"]
    merits = [p for p in read["prices"] if p["category"] == "merits" and p["trait"] is None]
    assert [(p["price"], p["house"]) for p in merits] == [("1 XP per point", False)]
    disciplines = {p["when"]: p["price"] for p in read["prices"] if p["category"] == "disciplines"}
    assert disciplines["in-clan"] == "3 XP × the new rating"
    sway = [r for r in read["requirements"] if r["trait"] == "Absent Sway"]
    assert [(r["message"], r["page"]) for r in sway] == [
        ("Absent Sway is only for Toreador.", "243")
    ]
    # A whole category's check has no trait.
    assert any(
        r["category"] == "elder_disciplines" and r["trait"] is None for r in read["requirements"]
    )
    assert read["not_allowed"] == []
    rarity = {r["clan"]: r for r in read["rarities"]}
    assert rarity["Assamite"]["house"] is False
    assert "for the Camarilla" in rarity["Assamite"]["text"]


def test_as_played_in_a_troupe_its_house_rules_apply(troupe: Troupe) -> None:
    st = troupe.storyteller.client
    priced = st.post(
        f"/troupes/{troupe.id}/costs",
        json={"category": "merits", "trait": "Absent Sway", "scheme": "fixed", "rate": 2},
    )
    assert priced.status_code == 201, priced.text
    banned = st.post(
        f"/troupes/{troupe.id}/costs",
        json={
            "category": "merits",
            "trait": "Calm Heart",
            "scheme": "not_allowed",
            "text": "No calm hearts here",
        },
    )
    assert banned.status_code == 201, banned.text
    st.put(f"/troupes/{troupe.id}/checks/merits/Calm Heart/1", json={"strength": "off"})
    st.put(f"/troupes/{troupe.id}/clan-rarity", json={"rarities": {"Tremere": "rare"}})
    st.post(
        f"/troupes/{troupe.id}/house-traits",
        json={
            "category": "merits",
            "name": "Crossroads Child",
            "points": 2,
            "availability": "building",
        },
    )
    old = st.post(
        f"/troupes/{troupe.id}/house-traits",
        json={"category": "flaws", "name": "Old Debt", "points": 1, "availability": "staff"},
    ).json()
    st.put(f"/troupes/{troupe.id}/house-traits/{old['id']}/archived", json={"archived": True})

    read = browse(troupe.stranger, troupe)

    assert read["troupe_name"] == "Lords of the Night"
    sway = trait(read, "merits", "Absent Sway")
    assert sway is not None and sway["fixed_rating"] == 2
    [price] = [p for p in read["prices"] if p["trait"] == "Absent Sway"]
    assert (price["price"], price["house"], price["book"]) == ("2 XP", True, "3 points")
    assert read["not_allowed"] == [
        {"category": "merits", "name": "Calm Heart", "text": "No calm hearts here"}
    ]
    [check] = [r for r in read["requirements"] if r["key"] == "merits/Calm Heart/1"]
    assert (check["strength"], check["house"]) == ("refuse", "off")
    rarity = {r["clan"]: r for r in read["rarities"]}
    assert (rarity["Tremere"]["text"], rarity["Tremere"]["house"]) == ("Rare", True)
    child = trait(read, "merits", "Crossroads Child")
    assert child is not None and child["house"]["label"] == "House merit of Lords of the Night"
    assert trait(read, "flaws", "Old Debt") is None
    # The book stays as it was.
    book = browse(troupe.stranger)
    assert trait(book, "merits", "Crossroads Child") is None
    assert book["not_allowed"] == []


def test_a_category_barred_bars_what_no_other_price_can_beat(troupe: Troupe) -> None:
    st = troupe.storyteller.client
    for category in ("rituals", "skills"):
        added = st.post(
            f"/troupes/{troupe.id}/costs", json={"category": category, "scheme": "not_allowed"}
        )
        assert added.status_code == 201, added.text

    barred = {(t["category"], t["name"]) for t in browse(troupe.player, troupe)["not_allowed"]}

    assert ("rituals", "Thaumaturgy: Bind the Accusing Tongue") in barred
    # The book's own price for skills at Generation 1 beats a price with no condition.
    assert not any(category == "skills" for category, _ in barred)


def test_an_archived_or_unknown_troupe_is_not_found(troupe: Troupe) -> None:
    unknown = "00000000-0000-0000-0000-000000000000"
    response = troupe.player.client.get("/rules/vampire/browse", params={"troupe_id": unknown})
    assert response.status_code == 404
    troupe.lead.client.post(f"/troupes/{troupe.id}/archive", json={"reason": "Done"})
    params = {"troupe_id": troupe.id}
    assert troupe.player.client.get("/rules/vampire/browse", params=params).status_code == 404
    assert troupe.custodian.client.get("/rules/vampire/browse", params=params).status_code == 200


def test_signed_out_visitors_cannot_browse(client_for: Callable[[], TestClient]) -> None:
    assert client_for().get("/rules/vampire/browse").status_code == 401
