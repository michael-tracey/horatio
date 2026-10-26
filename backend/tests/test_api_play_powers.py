"""Forms and powers in use on the Play View (issue #200): switched on and off by
taps, one form at a time, with a form's wound levels on the health tracker; and
the choices made when buying a power, such as Shape of the Beast's template."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import AuditEvent, CharacterTrait, TraitCategory, TraitDefinition
from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_play import send, tap, texts, view
from tests.test_api_sheets import make_home_troupe_member

FIGHT = "power:fight form"
FLIGHT = "power:flight form"


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def give(session: Session, character_id: str, category: str, name: str, rating: int) -> None:
    definition = session.scalars(
        select(TraitDefinition)
        .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
        .where(TraitCategory.key == category, TraitDefinition.name == name)
    ).one()
    session.add(
        CharacterTrait(
            character_id=uuid.UUID(character_id), trait_definition_id=definition.id, rating=rating
        )
    )
    session.flush()


@pytest.fixture
def ursula(troupe: Troupe, session: Session) -> str:
    """A character with Protean 4 (Shape of the Beast) and Celerity 2, not yet in a
    home troupe."""
    character_id = new_character(troupe, troupe.player, "Ursula")
    give(session, character_id, "disciplines", "Protean", 4)
    give(session, character_id, "disciplines", "Celerity", 2)
    return character_id


def choose(person: Person, character_id: str, **values: str) -> Any:
    return person.client.put(
        f"/characters/{character_id}/power-choices",
        json={"discipline": "Protean", "power": "Shape of the Beast", "values": values},
    )


def powers(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {p["key"]: p for p in state["powers"]}


def on(state: dict[str, Any]) -> set[str]:
    return {p["key"] for p in state["powers"] if p["on"]}


def test_the_sheet_lists_its_forms_and_powers_all_off(troupe: Troupe, ursula: str) -> None:
    state = view(troupe.player, ursula)

    found = powers(state)
    assert {"flight form", "fight form", "Feral Claws", "Earth Meld", "Celerity"} <= set(found)
    assert on(state) == set()
    assert found["fight form"]["name"] == "Shape of the Beast: fight form (wolf)"
    assert found["fight form"]["form"] and not found["Feral Claws"]["form"]
    assert found["fight form"]["changes"] == ["+2 Brawl attacks", "Brawl damage aggravated"]


def test_a_huge_fight_form_adds_two_healthy_levels_while_on(troupe: Troupe, ursula: str) -> None:
    assert choose(troupe.player, ursula, fight="bear", template="Huge").status_code == 200
    state = send(troupe.player, ursula, tap(FIGHT, 1))
    fight = powers(state)["fight form"]
    assert fight["on"] and fight["name"] == "Shape of the Beast: fight form (bear, Huge)"
    assert fight["health"] == [{"level": "Healthy", "boxes": 2}]

    # Five damage: the sheet's three Healthy levels, then the form's two.
    state = send(troupe.player, ursula, tap("health", 5, at=1, damage="normal"))
    assert len(state["health"]["marks"]) == 5
    # Out of the form, its levels go and the damage in them with them.
    state = send(troupe.player, ursula, tap(FIGHT, -1, at=2))
    assert on(state) == set()
    assert len(state["health"]["marks"]) == 3
    assert texts(state)[0] == (
        "Out of Shape of the Beast: fight form (bear, Huge): 2 damage in its levels gone"
    )
    assert texts(state)[2] == "Turned into Shape of the Beast: fight form (bear, Huge)"

    # Undo puts the form back, with its damage.
    last = state["log"][0]["id"]
    state = send(troupe.player, ursula, {**tap(at=3), "kind": "undo", "undoes": last})
    assert on(state) == {"fight form"}
    assert len(state["health"]["marks"]) == 5


def test_damage_in_the_sheets_own_levels_stays_when_a_form_ends(
    troupe: Troupe, ursula: str
) -> None:
    choose(troupe.player, ursula, template="Huge")
    send(troupe.player, ursula, tap(FIGHT, 1), tap("health", 2, at=1, damage="aggravated"))

    state = send(troupe.player, ursula, tap(FIGHT, -1, at=2))
    assert state["health"]["marks"] == ["aggravated", "aggravated"]
    assert texts(state)[0] == "Out of Shape of the Beast: fight form (wolf, Huge)"


def test_one_form_at_a_time_but_powers_go_with_it(troupe: Troupe, ursula: str) -> None:
    send(
        troupe.player,
        ursula,
        tap(FIGHT, 1),
        tap("power:Feral Claws", 1, at=1),
        tap("power:Celerity", 1, at=2),
    )
    assert on(view(troupe.player, ursula)) == {"fight form", "Feral Claws", "Celerity"}

    state = send(troupe.player, ursula, tap(FLIGHT, 1, at=3))
    assert on(state) == {"flight form", "Feral Claws", "Celerity"}
    assert texts(state)[0] == (
        "Turned into Shape of the Beast: flight form (bat): "
        "out of Shape of the Beast: fight form (wolf)"
    )
    assert texts(state)[1] == "Celerity on"
    assert texts(state)[2] == "Feral Claws on"


def test_another_device_sees_the_form_and_reset_turns_everything_off(
    troupe: Troupe, ursula: str, session: Session
) -> None:
    make_home_troupe_member(session, troupe, ursula)
    send(troupe.player, ursula, tap(FIGHT, 1), tap("power:Celerity", 1, at=1))

    # The storyteller's device sees it, and can switch it too.
    assert on(view(troupe.storyteller, ursula)) == {"fight form", "Celerity"}
    state = send(troupe.storyteller, ursula, tap("power:Celerity", -1, at=2))
    assert on(state) == {"fight form"}
    assert state["log"][0]["by_staff"]

    state = troupe.player.client.post(f"/characters/{ursula}/play/reset", json={}).json()
    assert on(state) == set()
    assert state["game"]["number"] == 2


def test_a_power_the_sheet_lacks_changes_nothing(troupe: Troupe, ursula: str) -> None:
    state = send(troupe.player, ursula, tap("power:Horrid Form", 1))
    assert on(state) == set()
    assert (
        troupe.player.client.post(
            f"/characters/{ursula}/play/taps", json={"taps": [tap("power:", 1)]}
        ).status_code
        == 422
    )


def test_blood_of_potency_grows_the_pool_until_it_ends(troupe: Troupe, session: Session) -> None:
    character_id = new_character(troupe, troupe.player, "Tremere")
    give(session, character_id, "disciplines", "Thaumaturgy: Path of Blood", 3)
    state = send(troupe.player, character_id, tap("power:Blood of Potency", 1))
    assert state["blood"]["most"] == 15 and state["blood_usual"] == 10
    assert powers(state)["Blood of Potency"]["blood_per_turn"] == 2

    state = send(troupe.player, character_id, tap("blood", 4, at=1))
    assert state["blood"]["value"] == 14
    state = send(troupe.player, character_id, tap("power:Blood of Potency", -1, at=2))
    assert state["blood"] == {"value": 10, "most": 10, "start": 10}


# --- Choices made when buying a power ----------------------------------------


def choices(person: Person, character_id: str) -> dict[str, Any]:
    response = person.client.get(f"/characters/{character_id}/power-choices")
    assert response.status_code == 200, response.text
    return {c["power"]: c for c in response.json()}


def test_the_player_chooses_once_and_staff_can_change_it(
    troupe: Troupe, ursula: str, session: Session
) -> None:
    beast = choices(troupe.player, ursula)["Shape of the Beast"]
    assert (beast["chosen"], beast["can_change"]) == (False, True)
    assert [(c["key"], c["default"], c["value"]) for c in beast["choices"]] == [
        ("flight", "bat", ""),
        ("fight", "wolf", ""),
        ("template", "", ""),
    ]
    assert choose(troupe.player, ursula, template="Enormous").status_code == 422

    assert choose(troupe.player, ursula, flight="raven", template="Agile").status_code == 200
    # With no home troupe, the player still edits freely.
    assert choose(troupe.player, ursula, flight="owl", template="Agile").status_code == 200
    make_home_troupe_member(session, troupe, ursula)

    beast = choices(troupe.player, ursula)["Shape of the Beast"]
    assert (beast["chosen"], beast["can_change"]) == (True, False)
    assert [c["value"] for c in beast["choices"]] == ["owl", "", "Agile"]
    refused = choose(troupe.player, ursula, template="Huge")
    assert refused.status_code == 403
    assert "fixed once chosen" in refused.json()["detail"]

    assert choose(troupe.storyteller, ursula, template="Huge").status_code == 200
    assert powers(view(troupe.player, ursula))["fight form"]["health"] == [
        {"level": "Healthy", "boxes": 2}
    ]
    changed = session.scalars(
        select(AuditEvent).where(AuditEvent.action == "sheet.power_choices")
    ).all()
    assert [e.data["after"] for e in changed][-1] == {"flight": "owl", "template": "Huge"}

    assert troupe.stranger.client.get(f"/characters/{ursula}/power-choices").status_code == 404
    assert choose(troupe.stranger, ursula, template="Fast").status_code == 404


def test_only_powers_the_character_has_reached_ask(troupe: Troupe, session: Session) -> None:
    character_id = new_character(troupe, troupe.player, "Cub")
    give(session, character_id, "disciplines", "Protean", 3)
    assert choices(troupe.player, character_id) == {}
    assert choose(troupe.player, character_id, template="Huge").status_code == 409
