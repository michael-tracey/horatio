"""Generation stays open until a first home troupe accepts the character: raised or
lowered in the cart, with every earlier buy repriced (MET: VTM pp. 99, 106)."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.models import XpEntry
from tests.api_helpers import Person, Troupe
from tests.test_api_cart import rating, sheet, spend
from tests.test_api_creation import build, creating

# Balances here are about repricing, not banking creation XP.
pytestmark = pytest.mark.usefixtures("without_bank")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def neonate(troupe: Troupe) -> str:
    """A Brujah built through creation at Generation 1, with 30 XP to spend."""
    character_id = creating(troupe)
    build(troupe.player, character_id)
    return character_id


def buy(person: Person, character_id: str, *changes: dict[str, Any]) -> list[Any]:
    response = spend(person, character_id, *changes)
    assert response.status_code == 200, response.text
    assert response.json()["applied"], response.text
    return response.json()["lines"]


def generation(to: int, was: int) -> dict[str, Any]:
    return rating("backgrounds", "Generation", to, from_rating=was)


def history(person: Person, character_id: str, kind: str) -> list[tuple[str, int]]:
    entries = person.client.get(f"/characters/{character_id}/xp").json()
    return [(e["reason"], e["amount"]) for e in entries if e["kind"] == kind]


def balance(person: Person, character_id: str) -> int:
    return person.client.get(f"/characters/{character_id}/sheet").json()["xp"]["balance"]


def priced(lines: list[Any]) -> list[tuple[int, str | None, list[tuple[str, int]]]]:
    return [
        (line["cost"], line["refused"], [(r["purchase"], r["cost"]) for r in line["repriced"]])
        for line in lines
    ]


def make_home(troupe: Troupe, character_id: str) -> None:
    request = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    )
    assert request.status_code in (200, 201), request.text
    approved = troupe.lead.client.post(f"/approvals/{request.json()['id']}/approve", json={})
    assert approved.status_code == 200, approved.text


def give_xp(troupe: Troupe, character_id: str, amount: int) -> None:
    troupe.session.add(
        XpEntry(
            character_id=uuid.UUID(character_id),
            kind="award",
            amount=amount,
            reason="Test",
            entered_by=uuid.UUID(troupe.custodian.id),
        )
    )
    troupe.session.flush()


def test_a_finished_neonate_raises_generation_and_earlier_buys_are_repriced(
    troupe: Troupe,
) -> None:
    character_id = neonate(troupe)
    # A Neonate pays new level × 1 for skills and backgrounds (p. 99); in-clan and
    # out-of-clan disciplines cost the same at Generation 1 and 2.
    buy(
        troupe.player,
        character_id,
        rating("skills", "Brawl", 5, from_rating=4),
        rating("backgrounds", "Resources", 2, from_rating=0),
        rating("disciplines", "Potence", 2, from_rating=1),
    )
    assert balance(troupe.player, character_id) == 30 - 5 - 3 - 6

    dry_run = spend(troupe.player, character_id, generation(2, 1), dry_run=True)
    spent = buy(troupe.player, character_id, generation(2, 1))

    # 4 XP for the second dot, and the skill and background at × 2.
    expected = [(12, None, [("Brawl 4 → 5", 5), ("Resources 0 → 2", 3)])]
    assert priced(dry_run.json()["lines"]) == expected
    assert dry_run.json()["applied"] is False
    assert priced(spent) == expected
    assert balance(troupe.player, character_id) == 16 - 12
    assert history(troupe.player, character_id, "reprice") == [
        ("Generation 1 → 2: Brawl 4 → 5 repriced", -5),
        ("Generation 1 → 2: Resources 0 → 2 repriced", -3),
    ]
    assert ("Generation 1 → 2", -4) in history(troupe.player, character_id, "purchase")
    # Buys from now on are at the new Generation's prices.
    next_dot = spend(
        troupe.player, character_id, rating("skills", "Dodge", 4, from_rating=3), dry_run=True
    )
    assert next_dot.json()["lines"][0]["cost"] == 8


def test_lowering_generation_again_refunds_its_dots_and_reprices_back(troupe: Troupe) -> None:
    character_id = neonate(troupe)
    buy(troupe.player, character_id, generation(2, 1))
    # At Generation 2, a skill dot costs new level × 2.
    buy(
        troupe.player,
        character_id,
        rating("skills", "Brawl", 5, from_rating=4),
        rating("backgrounds", "Resources", 1, from_rating=0),
    )
    assert balance(troupe.player, character_id) == 30 - 4 - 10 - 2

    dry_run = spend(troupe.player, character_id, generation(1, 2), dry_run=True)
    lowered = buy(troupe.player, character_id, generation(1, 2))

    expected = [(-4 - 5 - 1, None, [("Brawl 4 → 5", -5), ("Resources 0 → 1", -1)])]
    assert priced(dry_run.json()["lines"]) == expected
    assert priced(lowered) == expected
    assert balance(troupe.player, character_id) == 30 - 5 - 1
    assert history(troupe.player, character_id, "reprice") == [
        ("Generation 2 → 1: Brawl 4 → 5 repriced", 5),
        ("Generation 2 → 1: Resources 0 → 1 repriced", 1),
    ]


def test_generation_cannot_go_below_the_creation_pick(troupe: Troupe) -> None:
    character_id = neonate(troupe)
    give_xp(troupe, character_id, 10)
    buy(troupe.player, character_id, generation(2, 1))

    refused = spend(troupe.player, character_id, generation(0, 2))

    assert priced(refused.json()["lines"]) == [
        (
            None,
            "Generation was chosen at 1 in character creation: "
            "only the dots bought with XP since can be taken back.",
            [],
        )
    ]
    assert refused.json()["applied"] is False


def test_once_a_home_troupe_accepts_the_character_generation_is_fixed(troupe: Troupe) -> None:
    character_id = neonate(troupe)
    request = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    ).json()
    # Staff see the Generation they are accepting, and the generation it gives, with
    # who asked and when.
    queued = troupe.lead.client.get(f"/troupes/{troupe.id}/approvals").json()
    asked = next(a for a in queued if a["id"] == request["id"])
    assert asked["locks"] == [{"name": "Generation", "rating": 1, "generation": 11}]
    assert (asked["clan"], asked["age"]) == ("Brujah", "Neonate")
    assert asked["player_name"] == troupe.player.email.removesuffix("@example.com")
    assert asked["asked_at"]
    troupe.lead.client.post(f"/approvals/{request['id']}/approve", json={})

    refused = spend(troupe.player, character_id, generation(2, 1))

    assert refused.json()["lines"][0]["refused"] == (
        "Generation can't change once a home troupe has accepted the character."
    )
    # Leaving the troupe does not open it again.
    left = troupe.player.client.delete(f"/characters/{character_id}/troupes/{troupe.id}")
    assert left.status_code == 204, left.text
    again = spend(troupe.player, character_id, generation(2, 1))
    assert again.json()["lines"][0]["refused"] == (
        "Generation can't change once a home troupe has accepted the character."
    )


def test_other_creation_only_traits_still_lock_when_creation_is_finished(troupe: Troupe) -> None:
    character_id = neonate(troupe)

    refused = spend(troupe.player, character_id, rating("merits", "Bloodline: Ishtarri", 2))

    assert "can only be chosen during character creation" in refused.json()["lines"][0]["refused"]


def test_generation_4_with_a_technique_is_refused_until_the_technique_comes_out(
    troupe: Troupe,
) -> None:
    character_id = neonate(troupe)
    give_xp(troupe, character_id, 30)
    # A Pretender Elder (3) learns techniques, at 20 XP a dot (p. 101).
    buy(
        troupe.player,
        character_id,
        generation(2, 1),
        generation(3, 2),
        rating("disciplines", "Potence", 2, from_rating=1),
        rating("disciplines", "Presence", 2, from_rating=1),
        rating("techniques", "Fearful Blow", 1, from_rating=0),
    )
    assert balance(troupe.player, character_id) == 60 - 4 - 6 - 6 - 6 - 20

    refused = spend(troupe.player, character_id, generation(4, 3))
    assert refused.json()["applied"] is False
    assert refused.json()["lines"][0]["refused"] == (
        "A Master or Luminary Elder cannot learn techniques. (p. 101)"
    )

    # Taken out in the same cart, it is refunded at what it cost.
    lines = buy(
        troupe.player,
        character_id,
        rating("techniques", "Fearful Blow", 0, from_rating=1),
        generation(4, 3),
    )
    assert [line["cost"] for line in lines] == [-20, 8]
    assert balance(troupe.player, character_id) == 18 + 20 - 8


def attribute(name: str, to: int, was: int) -> dict[str, Any]:
    return rating("attributes", name, to, from_rating=was)


def test_attributes_stop_at_the_limit_generation_gives(troupe: Troupe) -> None:
    character_id = neonate(troupe)
    give_xp(troupe, character_id, 500)
    # Physical starts at 7 from creation: a Neonate may take one attribute to 11.
    buy(troupe.player, character_id, attribute("Physical", 11, 7))
    refused = spend(troupe.player, character_id, attribute("Physical", 12, 11))
    assert refused.status_code == 200, refused.text
    assert not refused.json()["applied"]
    assert "Generation rating" in refused.json()["lines"][0]["refused"]
    second = spend(troupe.player, character_id, attribute("Social", 11, 5))
    assert not second.json()["applied"]

    buy(troupe.player, character_id, generation(3, 1))
    # A Pretender: 11 / 11 / 11 is fine, but 12 and 12 is not.
    buy(troupe.player, character_id, attribute("Social", 11, 5), attribute("Mental", 11, 3))
    held = {t["name"]: t["rating"] for t in sheet(troupe.player, character_id)["traits"]}
    assert (held["Physical"], held["Social"], held["Mental"]) == (11, 11, 11)
    assert not spend(troupe.player, character_id, attribute("Physical", 12, 11)).json()["applied"]
    # Or all three points on one attribute, by bringing the others down.
    buy(
        troupe.player,
        character_id,
        attribute("Physical", 13, 11),
        attribute("Social", 10, 11),
        attribute("Mental", 10, 11),
    )
    assert not spend(
        troupe.player, character_id, attribute("Social", 12, 10), attribute("Mental", 12, 10)
    ).json()["applied"]


def test_generation_cannot_drop_below_what_the_attributes_need(troupe: Troupe) -> None:
    character_id = neonate(troupe)
    give_xp(troupe, character_id, 500)
    buy(troupe.player, character_id, generation(3, 1))
    buy(troupe.player, character_id, attribute("Physical", 13, 7))

    lowered = spend(troupe.player, character_id, generation(2, 3))
    assert not lowered.json()["applied"]
    # Bringing the attribute down in the same cart makes it fine.
    buy(troupe.player, character_id, generation(2, 3), attribute("Physical", 12, 13))
