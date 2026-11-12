"""Merits and flaws taken in creation, in XP, as the book has it (MET: VTM p. 85,
Steps Eight and Nine; p. 106; issue #657): merits cost initial XP, flaws add to it."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import Character, XpEntry
from horatio.rules.model import CreationRuleData
from horatio.rules.store import set_house_creation_rules
from tests.api_helpers import Person, Troupe
from tests.test_api_creation import build, creating, creation, pick, sheet

# Creation XP banked on acceptance is another matter.
pytestmark = pytest.mark.usefixtures("without_bank")

# Rugged 3, Iron Will 3 and Acute Sense 1: 7 points of merits.
SEVEN_MERITS = [("Rugged", 3), ("Iron Will", 3), ("Acute Sense", 1)]
# Hunted 4, Slow Healing 3: 7 points of flaws.
SEVEN_FLAWS = [("Hunted", 4), ("Slow Healing", 3)]


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def set_picks(
    person: Person, character_id: str, category: str, picks: list[tuple[str, int]]
) -> Any:
    return person.client.put(
        f"/characters/{character_id}/creation/categories/{category}",
        json={"picks": [{"name": n, "rating": r} for n, r in picks]},
    )


def unpick(person: Person, character_id: str, category: str, name: str) -> Any:
    return person.client.post(
        f"/characters/{character_id}/creation/picks/remove",
        json={"category": category, "name": name},
    )


def left(person: Person, character_id: str) -> int:
    found: int = sheet(person, character_id)["xp"]["balance"]
    return found


def lines(session: Session, character_id: str) -> list[tuple[int, str]]:
    session.expire_all()
    found = session.execute(
        select(XpEntry.amount, XpEntry.reason)
        .where(XpEntry.character_id == uuid.UUID(character_id), XpEntry.kind == "creation")
        .order_by(XpEntry.id)
    )
    return [(amount, reason) for amount, reason in found]


@pytest.mark.parametrize(
    ("merits", "flaws", "xp"),
    [
        (SEVEN_MERITS, SEVEN_FLAWS, 30),
        ([], SEVEN_FLAWS, 37),
        (SEVEN_MERITS, [], 23),
    ],
)
def test_merits_cost_initial_xp_and_flaws_add_to_it(
    troupe: Troupe, merits: list[tuple[str, int]], flaws: list[tuple[str, int]], xp: int
) -> None:
    character_id = creating(troupe)

    assert set_picks(troupe.player, character_id, "merits", merits).status_code == 200
    assert set_picks(troupe.player, character_id, "flaws", flaws).status_code == 200

    assert left(troupe.player, character_id) == xp
    spent = sum(p for _, p in merits)
    gave = sum(p for _, p in flaws)
    assert creation(troupe.player, character_id)["xp"] == {
        "starting": 30,
        "merits": spent,
        "flaws": gave,
        "flaw_budget": 7,
        "left": xp,
    }
    # Finishing keeps them, and the rest is spent from the sheet (Step Nine).
    build(troupe.player, character_id)
    assert left(troupe.player, character_id) == xp


def test_each_merit_and_flaw_is_a_line_in_the_xp_history(troupe: Troupe) -> None:
    character_id = creating(troupe)

    pick(troupe.player, character_id, "merits", "Iron Will")
    pick(troupe.player, character_id, "flaws", "Dark Secret")

    assert lines(troupe.session, character_id) == [
        (-3, "Iron Will 0 → 3, taken in creation"),
        (1, "Dark Secret 0 → 1, taken in creation"),
    ]
    history = troupe.player.client.get(f"/characters/{character_id}/xp").json()
    assert [(e["kind"], e["amount"]) for e in history] == [
        ("award", 30),
        ("creation", -3),
        ("creation", 1),
    ]


def test_clan_merits_cost_xp(troupe: Troupe) -> None:
    character_id = creating(troupe, "Gangrel: Coyote")

    # Bloodline: Coyote, 2 points, comes with the clan and costs its XP.
    assert left(troupe.player, character_id) == 28
    assert creation(troupe.player, character_id)["xp"]["merits"] == 2
    # Choosing another clan gives it back.
    troupe.player.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "clan", "name": "Brujah", "rating": None},
    )
    assert left(troupe.player, character_id) == 30


def test_a_merit_costs_what_the_rules_charge_for_it(troupe: Troupe) -> None:
    """Path of Night is 3 points, at 2 XP for a Lasombra (p. 257)."""
    character_id = creating(troupe, "Lasombra")

    assert pick(troupe.player, character_id, "merits", "Path of Night").status_code == 200

    assert left(troupe.player, character_id) == 28
    state = creation(troupe.player, character_id)
    assert next(p for p in state["pools"] if p["category"] == "merits")["used"] == 3


def test_flaws_past_seven_give_no_more(troupe: Troupe) -> None:
    character_id = creating(troupe)
    nine = [*SEVEN_FLAWS, ("Dark Secret", 1), ("Amnesia", 1)]

    assert set_picks(troupe.player, character_id, "flaws", nine).status_code == 200

    assert left(troupe.player, character_id) == 37
    past = ": 0 XP of its 1 point, flaws giving at most 7 (p. 85)"
    assert lines(troupe.session, character_id)[-2:] == [
        (0, f"Dark Secret 0 → 1, taken in creation{past}"),
        (0, f"Amnesia 0 → 1, taken in creation{past}"),
    ]
    # Taking one that gave XP off makes room for the next.
    assert unpick(troupe.player, character_id, "flaws", "Slow Healing").status_code == 200
    assert left(troupe.player, character_id) == 36
    assert lines(troupe.session, character_id)[-3:] == [
        (-3, "Slow Healing 3 → 0, taken back in creation"),
        (1, "Dark Secret: now gives 1 XP, flaws giving at most 7 (p. 85)"),
        (1, "Amnesia: now gives 1 XP, flaws giving at most 7 (p. 85)"),
    ]


def test_a_troupes_flaw_budget_is_the_most_flaws_give(troupe: Troupe) -> None:
    set_house_creation_rules(
        troupe.session,
        uuid.UUID(troupe.id),
        "vampire",
        "flaws",
        [CreationRuleData(category="flaws", points=5)],
    )
    response = troupe.player.client.post(
        "/characters", json={"splat": "vampire", "name": "Bram", "building_troupe_id": troupe.id}
    )
    character_id = response.json()["id"]

    assert set_picks(troupe.player, character_id, "flaws", SEVEN_FLAWS).status_code == 200
    assert left(troupe.player, character_id) == 35

    # The troupe gives more: the character being built gets it at once.
    raised = troupe.lead.client.put(
        f"/troupes/{troupe.id}/creation/flaws",
        json={"rules": [{"points": 6}]},
    )
    assert raised.status_code == 200, raised.text
    assert left(troupe.player, character_id) == 36


def test_taking_merits_and_flaws_back_refunds_and_claws_back(troupe: Troupe) -> None:
    character_id = creating(troupe)
    set_picks(troupe.player, character_id, "merits", [("Iron Will", 3)])
    set_picks(troupe.player, character_id, "flaws", [("Dark Secret", 1)])
    assert left(troupe.player, character_id) == 28

    assert unpick(troupe.player, character_id, "merits", "Iron Will").status_code == 200
    assert left(troupe.player, character_id) == 31
    assert set_picks(troupe.player, character_id, "flaws", []).status_code == 200
    assert left(troupe.player, character_id) == 30


def starting_with(troupe: Troupe, xp: int) -> str:
    """A Brujah built for the troupe, whose starting XP is `xp`."""
    changed = troupe.lead.client.patch(f"/troupes/{troupe.id}", json={"starting_xp": xp})
    assert changed.status_code == 200, changed.text
    response = troupe.player.client.post(
        "/characters", json={"splat": "vampire", "name": "Bram", "building_troupe_id": troupe.id}
    )
    assert response.status_code == 201, response.text
    character_id: str = response.json()["id"]
    troupe.player.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "clan", "name": "Brujah", "rating": None},
    )
    return character_id


def test_a_merit_the_character_cannot_pay_for_is_refused(troupe: Troupe) -> None:
    character_id = starting_with(troupe, 2)

    refused = pick(troupe.player, character_id, "merits", "Iron Will")

    assert refused.status_code == 409
    assert refused.json()["detail"] == "That costs 3 XP, and only 2 XP is left (p. 106)."
    assert left(troupe.player, character_id) == 2


def test_a_flaw_whose_xp_is_spent_cannot_come_off(troupe: Troupe) -> None:
    """Its XP paid for a merit: the merit comes off first."""
    character_id = starting_with(troupe, 0)
    assert pick(troupe.player, character_id, "flaws", "Hunted").status_code == 200
    assert pick(troupe.player, character_id, "merits", "Iron Will").status_code == 200
    assert left(troupe.player, character_id) == 1

    refused = unpick(troupe.player, character_id, "flaws", "Hunted")

    assert refused.status_code == 409
    assert refused.json()["detail"] == (
        "Taking Hunted off takes back the 4 XP it gave, and only 1 XP is unspent."
        " Undo some spends first."
    )
    assert unpick(troupe.player, character_id, "merits", "Iron Will").status_code == 200
    assert unpick(troupe.player, character_id, "flaws", "Hunted").status_code == 200
    assert left(troupe.player, character_id) == 0


def test_the_cart_takes_back_a_merits_xp(troupe: Troupe) -> None:
    character_id = creating(troupe)
    pick(troupe.player, character_id, "merits", "Iron Will")

    spent = troupe.player.client.post(
        f"/characters/{character_id}/cart",
        json={"changes": [{"kind": "unpick", "category": "merits", "name": "Iron Will"}]},
    )

    assert spent.status_code == 200, spent.text
    assert spent.json()["applied"] is True
    # The line says what it gives back, as any refund.
    assert spent.json()["lines"][0]["cost"] == -3
    assert left(troupe.player, character_id) == 30


def test_an_accepted_character_keeps_its_numbers(troupe: Troupe) -> None:
    """A character finished before #657 took its merits and flaws free: nothing here
    changes its XP, not even creation reopened."""
    character_id = creating(troupe)
    character = troupe.session.get_one(Character, uuid.UUID(character_id))
    character.merits_flaws_xp = False
    troupe.session.flush()
    set_picks(troupe.player, character_id, "merits", SEVEN_MERITS)
    set_picks(troupe.player, character_id, "flaws", SEVEN_FLAWS)
    build(troupe.player, character_id)
    asked = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    )
    assert asked.status_code == 201, asked.text
    approved = troupe.lead.client.post(f"/approvals/{asked.json()['id']}/approve", json={})
    assert approved.status_code == 200, approved.text

    assert left(troupe.player, character_id) == 30
    assert creation(troupe.player, character_id)["xp"] is None
    # Creation reopened (a troupe giving more starting dots) still takes nothing.
    troupe.session.expire_all()
    character = troupe.session.get_one(Character, uuid.UUID(character_id))
    character.creation_completed_at = None
    troupe.session.flush()
    assert unpick(troupe.player, character_id, "flaws", "Hunted").status_code == 200
    assert left(troupe.player, character_id) == 30
    assert lines(troupe.session, character_id) == []
