"""Exceptions: a player asks staff for a trait the rules refuse, at cost or free;
staff give one free or despite the rules; the sheet stops flagging the rule an
exception covers, and only that one."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import CharacterTrait, TraitDefinition, TraitException, XpEntry
from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_creation import build, creating
from tests.test_api_house_checks import accepted_brujah, house

pytestmark = pytest.mark.usefixtures("without_bank")

REFUSED = "Brujah cannot take Calm Heart (True Brujah can). (p. 249)"


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def calm_heart(reason: str = "Raised among the True Brujah", free: bool = False) -> dict[str, Any]:
    return {
        "kind": "set",
        "category": "merits",
        "name": "Calm Heart",
        "rating": 1,
        "from_rating": 0,
        "exception": {"reason": reason, "free": free},
    }


def spend(person: Person, character_id: str, *changes: dict[str, Any], dry_run: bool = False):  # noqa: ANN201
    return person.client.post(
        f"/characters/{character_id}/cart", json={"changes": list(changes), "dry_run": dry_run}
    )


def sheet(person: Person, character_id: str) -> dict[str, Any]:
    return person.client.get(f"/characters/{character_id}/sheet").json()


def waiting(troupe: Troupe, **query: str) -> list[dict[str, Any]]:
    response = troupe.lead.client.get(f"/troupes/{troupe.id}/approvals", params=query)
    assert response.status_code == 200, response.text
    return response.json()


def give(person: Person, character_id: str, **body: Any):  # noqa: ANN201
    return person.client.post(
        f"/characters/{character_id}/give",
        json={"category": "merits", "name": "Calm Heart", "rating": 1, **body},
    )


def history(person: Person, character_id: str) -> list[dict[str, Any]]:
    return person.client.get(f"/characters/{character_id}/xp").json()


def test_a_refused_trait_is_asked_for_and_approved(troupe: Troupe) -> None:
    character_id = accepted_brujah(troupe)
    before = sheet(troupe.player, character_id)["xp"]["balance"]
    # Without asking, the rules refuse it.
    plain = {k: v for k, v in calm_heart().items() if k != "exception"}
    assert spend(troupe.player, character_id, plain).json()["lines"][0]["refused"] == REFUSED

    priced = spend(troupe.player, character_id, calm_heart(), dry_run=True).json()
    [line] = priced["lines"]
    assert (line["refused"], line["needs_approval"], line["breaks"]) == (None, True, [REFUSED])
    cost = line["cost"]
    assert cost > 0

    spent = spend(troupe.player, character_id, calm_heart())

    assert spent.json()["applied"] is True, spent.text
    after = sheet(troupe.player, character_id)
    held = next(t for t in after["traits"] if t["name"] == "Calm Heart")
    assert held["pending_from"] == 0
    assert after["xp"]["balance"] == before - cost
    assert REFUSED not in [p["message"] for p in after["problems"]]
    [exception] = after["exceptions"]
    assert (exception["status"], exception["breaks"], exception["free"]) == (
        "waiting",
        [REFUSED],
        False,
    )

    [request] = waiting(troupe, kind="exception")
    assert waiting(troupe, kind="discipline") == []
    assert request["exception"] == {
        "breaks": [REFUSED],
        "reason": "Raised among the True Brujah",
        "free": False,
        "normal_cost": cost,
        "set_aside": [],
        "bloodline": None,
    }
    approved = troupe.lead.client.post(f"/approvals/{request['id']}/approve", json={})
    assert approved.status_code == 200, approved.text

    after = sheet(troupe.player, character_id)
    [exception] = after["exceptions"]
    assert (exception["status"], exception["by"]) == ("approved", "lead")
    assert exception["at"] is not None
    assert REFUSED not in [p["message"] for p in after["problems"]]
    assert after["xp"]["balance"] == before - cost


def test_a_free_ask_costs_nothing_and_approving_at_normal_cost_charges_it(
    troupe: Troupe,
) -> None:
    character_id = accepted_brujah(troupe)
    before = sheet(troupe.player, character_id)["xp"]["balance"]

    spent = spend(troupe.player, character_id, calm_heart("A plot reward", free=True))

    assert spent.json()["lines"][0]["cost"] == 0, spent.text
    after = sheet(troupe.player, character_id)
    assert after["xp"]["balance"] == before
    held = next(t for t in after["traits"] if t["name"] == "Calm Heart")
    assert (held["rating"], held["free_rating"]) == (1, 1)
    line = history(troupe.player, character_id)[-1]
    assert (line["amount"], line["reason"]) == (
        0,
        "Calm Heart 0 → 1, free by exception: A plot reward",
    )

    [request] = waiting(troupe)
    assert request["exception"]["free"] is True
    normal = request["exception"]["normal_cost"]
    assert normal > 0
    approved = troupe.lead.client.post(
        f"/approvals/{request['id']}/approve", json={"at_cost": True}
    )
    assert approved.status_code == 200, approved.text

    after = sheet(troupe.player, character_id)
    assert after["xp"]["balance"] == before - normal
    held = next(t for t in after["traits"] if t["name"] == "Calm Heart")
    assert held["free_rating"] == 0
    assert after["exceptions"][0]["free"] is False


def test_approving_at_normal_cost_is_refused_without_the_xp(troupe: Troupe) -> None:
    character_id = accepted_brujah(troupe)
    spend(troupe.player, character_id, calm_heart("A plot reward", free=True))
    balance = sheet(troupe.player, character_id)["xp"]["balance"]
    troupe.session.add(
        XpEntry(
            character_id=uuid.UUID(character_id),
            kind="fee",
            amount=-balance,
            reason="Spent elsewhere",
            entered_by=uuid.UUID(troupe.player.id),
        )
    )
    troupe.session.flush()
    [request] = waiting(troupe)

    refused = troupe.lead.client.post(f"/approvals/{request['id']}/approve", json={"at_cost": True})

    assert refused.status_code == 409
    assert "and Agnes has 0" in refused.json()["detail"]
    # Approving it free still can.
    approved = troupe.lead.client.post(f"/approvals/{request['id']}/approve", json={})
    assert approved.status_code == 200, approved.text


def test_declining_takes_it_back_and_refunds(troupe: Troupe) -> None:
    character_id = accepted_brujah(troupe)
    before = sheet(troupe.player, character_id)["xp"]["balance"]
    spend(troupe.player, character_id, calm_heart())
    [request] = waiting(troupe)

    troupe.lead.client.post(f"/approvals/{request['id']}/decline", json={})

    after = sheet(troupe.player, character_id)
    assert "Calm Heart" not in [t["name"] for t in after["traits"]]
    assert after["xp"]["balance"] == before
    assert after["exceptions"] == []
    assert troupe.session.scalars(select(TraitException)).all() == []


def test_storytellers_give_a_trait_free_and_despite_the_rules(troupe: Troupe) -> None:
    character_id = accepted_brujah(troupe)
    before = sheet(troupe.player, character_id)["xp"]["balance"]
    for person in (troupe.player, troupe.narrator):
        assert give(person, character_id, free=True, reason="Plot").status_code in (403, 404)

    trial = give(troupe.storyteller, character_id, free=True, reason="Plot", trial=True).json()
    assert (trial["given"], trial["cost"], trial["breaks"]) == (False, 0, [REFUSED])
    assert trial["refused"] == REFUSED
    # Not despite the rules, it is refused.
    assert give(troupe.storyteller, character_id, free=True, reason="Plot").status_code == 409

    given = give(
        troupe.assistant,
        character_id,
        free=True,
        despite=True,
        reason="A gift from the Prince",
    )

    assert given.status_code == 200, given.text
    assert (given.json()["given"], given.json()["breaks"]) == (True, [REFUSED])
    after = sheet(troupe.player, character_id)
    assert after["xp"]["balance"] == before
    assert REFUSED not in [p["message"] for p in after["problems"]]
    [exception] = after["exceptions"]
    assert (exception["status"], exception["by"], exception["free"]) == ("given", "assistant", True)
    assert exception["reason"] == "A gift from the Prince"
    # No approval waits, a 0 XP line says why, and the player is told.
    assert waiting(troupe) == []
    line = history(troupe.player, character_id)[-1]
    assert (line["amount"], line["reason"]) == (
        0,
        "Calm Heart 0 → 1, free by exception: A gift from the Prince",
    )
    told = troupe.player.client.get("/notifications").json()["items"]
    assert any(
        n["summary"] == "assistant gave Agnes Calm Heart 1, free: A gift from the Prince"
        for n in told
    )
    # The player cannot take it away again for XP: removing it is asked of staff,
    # with nothing back (horatio.merit_requests).
    removed = troupe.player.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "merits", "name": "Calm Heart", "rating": 0},
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["cost"] == 0
    assert "Calm Heart" in [t["name"] for t in removed.json()["sheet"]["traits"]]


def test_an_excepted_rule_is_not_flagged_while_another_is(troupe: Troupe) -> None:
    character_id = accepted_brujah(troupe)
    give(troupe.storyteller, character_id, despite=True, reason="Ruling")
    checks = troupe.lead.client.get(f"/troupes/{troupe.id}/checks").json()
    ritual_master = next(c["key"] for c in checks if c["message"].startswith("Ritual Master is"))
    house(troupe, troupe.storyteller, ritual_master, "note")
    bought = troupe.player.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "merits", "name": "Ritual Master", "rating": 1},
    )
    assert bought.status_code == 200, bought.text
    # Asked of staff once accepted; approved, it is on the sheet.
    [request] = [a for a in waiting(troupe) if a["kind"] == "merit_flaw"]
    troupe.lead.client.post(f"/approvals/{request['id']}/approve", json={})

    problems = [p["name"] for p in sheet(troupe.player, character_id)["problems"]]

    assert "Ritual Master" in problems
    assert "Calm Heart" not in problems


def test_the_exception_goes_with_the_trait(troupe: Troupe) -> None:
    character_id = accepted_brujah(troupe)
    give(troupe.storyteller, character_id, despite=True, reason="Ruling")
    definition = troupe.session.scalars(
        select(TraitDefinition).where(TraitDefinition.name == "Calm Heart")
    ).first()
    assert definition is not None
    trait = troupe.session.scalars(
        select(CharacterTrait).where(
            CharacterTrait.character_id == uuid.UUID(character_id),
            CharacterTrait.trait_definition_id == definition.id,
        )
    ).one()

    troupe.session.delete(trait)
    troupe.session.flush()
    troupe.session.expire_all()

    assert troupe.session.scalars(select(TraitException)).all() == []
    # Taken again, the rule refuses it as before.
    again = troupe.player.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "merits", "name": "Calm Heart", "rating": 1},
    )
    assert again.status_code == 409


def test_an_exception_covers_only_up_to_the_rating_given(troupe: Troupe) -> None:
    """Raising a trait above the rating it was given at is judged as normal."""
    character_id = accepted_brujah(troupe)
    give(troupe.storyteller, character_id, despite=True, reason="Ruling")
    exception = troupe.session.scalars(select(TraitException)).one()
    assert REFUSED not in [p["message"] for p in sheet(troupe.player, character_id)["problems"]]

    exception.rating = 0
    troupe.session.flush()

    assert REFUSED in [p["message"] for p in sheet(troupe.player, character_id)["problems"]]


# --- traits chosen at creation only (#461) ------------------------------------------

CREEPS = "Bloodline: Creeps can only be chosen during character creation."
SET_ASIDE = "Chosen after creation, by exception."


def accepted(troupe: Troupe, clan: str) -> str:
    """A finished character of `clan`, accepted by the troupe as its home."""
    character_id = new_character(troupe, troupe.player, clan=clan)
    request = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    ).json()
    troupe.lead.client.post(f"/approvals/{request['id']}/approve", json={})
    return character_id


def creeps(**exception: Any) -> dict[str, Any]:
    line = {
        "kind": "set",
        "category": "merits",
        "name": "Bloodline: Creeps",
        "rating": 2,
        "from_rating": 0,
    }
    return {**line, "exception": exception} if exception else line


def clan(person: Person, character_id: str) -> str:
    return next(t["name"] for t in sheet(person, character_id)["traits"] if t["category"] == "clan")


def auspex_cost(person: Person, character_id: str) -> int:
    line = {
        "kind": "set",
        "category": "disciplines",
        "name": "Auspex",
        "rating": 1,
        "from_rating": 0,
    }
    return spend(person, character_id, line, dry_run=True).json()["lines"][0]["cost"]


def test_a_bloodline_is_asked_for_after_creation_and_approved(troupe: Troupe) -> None:
    character_id = accepted(troupe, "Nosferatu")
    before = sheet(troupe.player, character_id)["xp"]["balance"]
    out_of_clan = auspex_cost(troupe.player, character_id)
    # Without asking, it is refused, but asking staff can make it.
    [plain] = spend(troupe.player, character_id, creeps(), dry_run=True).json()["lines"]
    assert (plain["refused"], plain["askable"], plain["unaskable"]) == (CREEPS, True, None)

    spent = spend(troupe.player, character_id, creeps(reason="Found in the Depths"))

    assert spent.json()["applied"] is True, spent.text
    [line] = spent.json()["lines"]
    assert (line["refused"], line["needs_approval"], line["breaks"]) == (None, True, [CREEPS])
    assert line["cost"] == 2
    after = sheet(troupe.player, character_id)
    assert after["xp"]["balance"] == before - 2
    assert CREEPS not in [p["message"] for p in after["problems"]]
    # It waits as Nosferatu until staff approve.
    assert clan(troupe.player, character_id) == "Nosferatu"
    [request] = waiting(troupe, kind="exception")
    assert request["exception"] == {
        "breaks": [],
        "reason": "Found in the Depths",
        "free": False,
        "normal_cost": 2,
        "set_aside": [SET_ASIDE],
        "bloodline": "Nosferatu: Creeps",
    }
    told = troupe.lead.client.get("/notifications").json()["items"]
    assert any(
        n["summary"] == "Agnes asks for Bloodline: Creeps 0 → 2 by exception" for n in told
    ), told

    approved = troupe.lead.client.post(f"/approvals/{request['id']}/approve", json={})

    assert approved.status_code == 200, approved.text
    after = sheet(troupe.player, character_id)
    # Of the bloodline now, as if chosen at creation: Auspex is in-clan.
    assert clan(troupe.player, character_id) == "Nosferatu: Creeps"
    assert "Bloodline: Creeps" in [t["name"] for t in after["traits"]]
    assert auspex_cost(troupe.player, character_id) < out_of_clan
    assert after["xp"]["balance"] == before - 2
    [exception] = after["exceptions"]
    assert (exception["status"], exception["breaks"]) == ("approved", [CREEPS])
    assert not [p for p in after["problems"] if p["name"] == "Bloodline: Creeps"]
    # The lock stays set aside: the rest of the sheet still changes freely.
    more = spend(
        troupe.player,
        character_id,
        {"kind": "set", "category": "skills", "name": "Brawl", "rating": 1, "from_rating": 0},
    )
    assert more.json()["applied"] is True, more.text


def test_declining_a_bloodline_takes_it_back_and_refunds(troupe: Troupe) -> None:
    character_id = accepted(troupe, "Nosferatu")
    before = sheet(troupe.player, character_id)["xp"]["balance"]
    spend(troupe.player, character_id, creeps(reason="Found in the Depths"))
    [request] = waiting(troupe, kind="exception")

    troupe.lead.client.post(f"/approvals/{request['id']}/decline", json={})

    after = sheet(troupe.player, character_id)
    assert "Bloodline: Creeps" not in [t["name"] for t in after["traits"]]
    assert clan(troupe.player, character_id) == "Nosferatu"
    assert after["xp"]["balance"] == before
    assert after["exceptions"] == []


def test_a_bloodline_of_another_clan_keeps_the_clan(troupe: Troupe) -> None:
    character_id = accepted(troupe, "Brujah")
    spend(troupe.player, character_id, creeps(reason="A ruling"))
    [request] = waiting(troupe, kind="exception")
    # Its clan requirement is set aside too, but a Brujah does not become a Creep.
    assert request["exception"]["bloodline"] is None
    assert request["exception"]["breaks"] == [
        "Bloodline: Creeps is only for Nosferatu. (Vol. 2, p. 45)"
    ]

    troupe.lead.client.post(f"/approvals/{request['id']}/approve", json={})

    assert clan(troupe.player, character_id) == "Brujah"


def test_staff_give_a_bloodline_after_creation_despite_the_rules(troupe: Troupe) -> None:
    character_id = accepted(troupe, "Nosferatu")

    def given(**body: Any):  # noqa: ANN202
        return troupe.storyteller.client.post(
            f"/characters/{character_id}/give",
            json={"category": "merits", "name": "Bloodline: Creeps", "rating": 2, **body},
        )

    trial = given(reason="Found in the Depths", trial=True).json()
    assert (trial["breaks"], trial["refused"]) == ([CREEPS], CREEPS)
    # Not despite the rules, the lock refuses it.
    assert given(reason="Found in the Depths").status_code == 409

    done = given(reason="Found in the Depths", despite=True, free=True)

    assert done.status_code == 200, done.text
    assert done.json()["breaks"] == [CREEPS]
    assert clan(troupe.player, character_id) == "Nosferatu: Creeps"
    after = sheet(troupe.player, character_id)
    [exception] = after["exceptions"]
    assert (exception["status"], exception["breaks"]) == ("given", [CREEPS])
    assert not [p for p in after["problems"] if p["name"] == "Bloodline: Creeps"]
    kept = troupe.session.scalars(select(TraitException)).one()
    assert kept.checks == [{"key": "lock:finished", "message": CREEPS}]


FIXED = "Generation can't change once a home troupe has accepted the character."


def generation(**exception: Any) -> dict[str, Any]:
    line = {
        "kind": "set",
        "category": "backgrounds",
        "name": "Generation",
        "rating": 2,
        "from_rating": 1,
    }
    return {**line, "exception": exception} if exception else line


def accepted_at_generation_1(troupe: Troupe) -> str:
    character_id = creating(troupe)
    build(troupe.player, character_id)
    request = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    ).json()
    troupe.lead.client.post(f"/approvals/{request['id']}/approve", json={})
    return character_id


def test_generation_is_asked_for_once_accepted(troupe: Troupe) -> None:
    character_id = accepted_at_generation_1(troupe)
    [plain] = spend(troupe.player, character_id, generation(), dry_run=True).json()["lines"]
    assert (plain["refused"], plain["askable"]) == (FIXED, True)

    spent = spend(troupe.player, character_id, generation(reason="Diablerie long ago"))

    assert spent.json()["applied"] is True, spent.text
    assert spent.json()["lines"][0]["breaks"] == [FIXED]
    [request] = waiting(troupe, kind="exception")
    assert request["exception"]["set_aside"] == [
        "Changed after a home troupe accepted the character, by exception."
    ]
    approved = troupe.lead.client.post(f"/approvals/{request['id']}/approve", json={})
    assert approved.status_code == 200, approved.text
    held = next(
        t for t in sheet(troupe.player, character_id)["traits"] if t["name"] == "Generation"
    )
    assert held["rating"] == 2


def test_staff_give_generation_once_accepted_despite_the_rules(troupe: Troupe) -> None:
    character_id = accepted_at_generation_1(troupe)

    def given(**body: Any):  # noqa: ANN202
        return troupe.storyteller.client.post(
            f"/characters/{character_id}/give",
            json={"category": "backgrounds", "name": "Generation", "rating": 2, **body},
        )

    assert given(reason="A ruling", trial=True).json()["refused"] == FIXED

    done = given(reason="A ruling", despite=True)

    assert done.status_code == 200, done.text
    assert done.json()["breaks"] == [FIXED]


def test_a_refusal_an_exception_cannot_set_aside_is_not_askable(troupe: Troupe) -> None:
    character_id = accepted(troupe, "Nosferatu")
    take = troupe.player.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "focus_physicals", "name": "Strength", "rating": 1},
    )
    assert take.status_code == 200, take.text
    second = {"kind": "set", "category": "focus_physicals", "name": "Dexterity", "rating": 1}

    # A second focus is for a merit to give, not an exception.
    [line] = spend(troupe.player, character_id, {**second, "from_rating": 0}, dry_run=True).json()[
        "lines"
    ]

    assert line["refused"] == "A character holds 1 physical focus; only merits can grant more."
    assert (line["askable"], line["unaskable"]) == (False, "Asking staff can't help with this.")

    # Without the XP, asking would be refused even so.
    balance = sheet(troupe.player, character_id)["xp"]["balance"]
    troupe.session.add(
        XpEntry(
            character_id=uuid.UUID(character_id),
            kind="fee",
            amount=-balance,
            reason="Spent elsewhere",
            entered_by=uuid.UUID(troupe.player.id),
        )
    )
    troupe.session.flush()
    [poor] = spend(troupe.player, character_id, creeps(), dry_run=True).json()["lines"]
    assert poor["refused"] == CREEPS
    assert poor["askable"] is False
    assert poor["unaskable"].startswith("Asking staff can't help: ")
