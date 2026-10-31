"""Hard as Steel, Trials of the Blood and Shrinking Violet on a sheet: the picker
offers the one power each opens past the character's Generation, the cart buys it at
the merit's price, the sheet and the XP history say which it is, and taking the merit
away (or a diablerie) judges it as normal again (issue #308)."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import CharacterTrait, RuleSet, TraitCategory, TraitDefinition
from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_cart import rating, sheet, spend
from tests.test_api_generation_until_accepted import give_xp, history, make_home

pytestmark = pytest.mark.usefixtures("without_bank")

TOO_THIN = "A Neonate's or Ancilla's blood is too thin for elder powers. (p. 101)"


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def put(troupe: Troupe, character_id: str, category: str, name: str, value: int) -> None:
    """A trait on the sheet without going through the rules, for set-up: free."""
    definition = troupe.session.scalars(
        select(TraitDefinition)
        .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
        .join(RuleSet, TraitCategory.rule_set_id == RuleSet.id)
        .where(
            RuleSet.key == "bns-met-vampire",
            TraitCategory.key == category,
            TraitDefinition.name == name,
        )
    ).one()
    troupe.session.add(
        CharacterTrait(
            character_id=uuid.UUID(character_id),
            trait_definition_id=definition.id,
            rating=value,
            free_rating=value,
        )
    )
    troupe.session.flush()


def vampire(troupe: Troupe, clan: str, generation: int, **disciplines: int) -> str:
    character_id = new_character(troupe, troupe.player, clan=clan)
    put(troupe, character_id, "backgrounds", "Generation", generation)
    for name, dots in disciplines.items():
        put(troupe, character_id, "disciplines", name, dots)
    give_xp(troupe, character_id, 200)
    return character_id


def take_merit(troupe: Troupe, character_id: str, name: str) -> None:
    taken = spend(troupe.player, character_id, rating("merits", name, 3))
    assert taken.json()["applied"], taken.text


def crusader(troupe: Troupe, *, merit: bool = True) -> str:
    """A Neonate Crusader with Fortitude 5, and Hard as Steel."""
    character_id = vampire(troupe, "Ventrue: Crusader", 1, Fortitude=5)
    if merit:
        take_merit(troupe, character_id, "Hard as Steel")
    return character_id


def line(response: Any) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    return response.json()["lines"][0]


def refused(person: Person, character_id: str, category: str) -> dict[str, str]:
    return person.client.get(
        f"/characters/{character_id}/unavailable", params={"category": category}
    ).json()


def opened(person: Person, character_id: str, *categories: str) -> dict[str, dict[str, str]]:
    found = person.client.post(
        f"/characters/{character_id}/opened", json={"categories": list(categories)}
    )
    assert found.status_code == 200, found.text
    return found.json()


def balance(person: Person, character_id: str) -> int:
    return sheet(person, character_id)["xp"]["balance"]


def on_sheet(person: Person, character_id: str, name: str) -> dict[str, Any]:
    return next(t for t in sheet(person, character_id)["traits"] if t["name"] == name)


def test_a_neonate_crusader_buys_one_fortitude_elder_power_for_20_xp(troupe: Troupe) -> None:
    character_id = crusader(troupe)
    player = troupe.player

    # The picker offers Fortitude's elder powers, at the merit's price, and nothing else.
    shown = opened(player, character_id, "elder_disciplines", "luminary_disciplines")
    assert shown["elder_disciplines"]["Fortitude: Personal Armor"] == "Hard as Steel: 20 XP"
    assert all(name.startswith("Fortitude: ") for name in shown["elder_disciplines"])
    assert shown["luminary_disciplines"] == {}
    assert "Fortitude: Personal Armor" not in refused(player, character_id, "elder_disciplines")
    quote = player.client.post(
        f"/characters/{character_id}/quote",
        json={"category": "elder_disciplines", "name": "Fortitude: Personal Armor", "rating": 1},
    ).json()
    assert (quote["cost"], quote["because"]) == (20, "Hard as Steel: 20 XP")

    xp = balance(player, character_id)
    bought = spend(
        player, character_id, rating("elder_disciplines", "Fortitude: Personal Armor", 1)
    )

    assert bought.json()["applied"], bought.text
    assert (line(bought)["cost"], line(bought)["because"]) == (20, "Hard as Steel: 20 XP")
    assert balance(player, character_id) == xp - 20
    # Which power it is, on the sheet and in the XP history.
    assert on_sheet(player, character_id, "Fortitude: Personal Armor")["opened_by"] == (
        "Hard as Steel"
    )
    assert on_sheet(player, character_id, "Hard as Steel")["opened"] == [
        "Fortitude: Personal Armor"
    ]
    assert history(player, character_id, "purchase")[-1] == (
        "Fortitude: Personal Armor 0 → 1, through Hard as Steel",
        -20,
    )
    assert sheet(player, character_id)["problems"] == []

    # One only: a second is refused, with the reason, and so is the luminary power.
    assert refused(player, character_id, "elder_disciplines")["Fortitude: Resilient Mind"] == (
        TOO_THIN
    )
    assert opened(player, character_id, "elder_disciplines")["elder_disciplines"] == {}
    second = spend(
        player, character_id, rating("elder_disciplines", "Fortitude: Resilient Mind", 1)
    )
    assert line(second)["refused"] == TOO_THIN
    assert "Fortitude: Indestructible" in refused(player, character_id, "luminary_disciplines")
    luminary = spend(
        player, character_id, rating("luminary_disciplines", "Fortitude: Indestructible", 1)
    )
    assert line(luminary)["refused"] == (
        "Luminary Disciplines can be bought only in-clan, Generation background 5 or more."
    )


def test_two_in_one_cart_buys_the_first_and_refuses_the_second(troupe: Troupe) -> None:
    character_id = crusader(troupe)

    both = spend(
        troupe.player,
        character_id,
        rating("elder_disciplines", "Fortitude: Personal Armor", 1),
        rating("elder_disciplines", "Fortitude: Resilient Mind", 1),
        dry_run=True,
    )

    first, second = both.json()["lines"]
    assert (first["cost"], first["refused"]) == (20, None)
    assert second["refused"]
    # The picker, judging the sheet as the cart would leave it, agrees.
    planned = troupe.player.client.post(
        f"/characters/{character_id}/unavailable",
        json={
            "categories": ["elder_disciplines"],
            "changes": [rating("elder_disciplines", "Fortitude: Personal Armor", 1)],
        },
    ).json()
    assert planned["elder_disciplines"]["Fortitude: Resilient Mind"] == TOO_THIN


def test_without_the_merit_a_neonate_is_refused_as_before(troupe: Troupe) -> None:
    character_id = crusader(troupe, merit=False)

    assert refused(troupe.player, character_id, "elder_disciplines")[
        "Fortitude: Personal Armor"
    ] == (TOO_THIN)
    assert opened(troupe.player, character_id, "elder_disciplines") == {"elder_disciplines": {}}
    bought = spend(
        troupe.player, character_id, rating("elder_disciplines", "Fortitude: Personal Armor", 1)
    )
    assert line(bought)["refused"] == TOO_THIN


def test_the_elder_power_still_needs_five_dots(troupe: Troupe) -> None:
    character_id = vampire(troupe, "Ventrue: Crusader", 1, Fortitude=4)
    take_merit(troupe, character_id, "Hard as Steel")

    assert refused(troupe.player, character_id, "elder_disciplines")[
        "Fortitude: Personal Armor"
    ] == ("An elder power needs all 5 dots of its discipline first. (p. 212)")


def vizier(troupe: Troupe, *, merit: bool = True) -> str:
    """A Pretender Elder Vizier with Auspex 5, one Auspex elder power, and Trials of the
    Blood."""
    character_id = vampire(troupe, "Assamite: Vizier", 3, Auspex=5)
    first = spend(
        troupe.player, character_id, rating("elder_disciplines", "Auspex: Clairvoyance", 1)
    )
    assert line(first)["cost"] == 18 and line(first)["because"] is None, first.text
    if merit:
        take_merit(troupe, character_id, "Trials of the Blood")
    return character_id


def test_a_pretender_elder_vizier_buys_a_second_auspex_elder_power_for_20_xp(
    troupe: Troupe,
) -> None:
    character_id = vizier(troupe)
    xp = balance(troupe.player, character_id)

    assert opened(troupe.player, character_id, "elder_disciplines")["elder_disciplines"][
        "Auspex: Fog of War"
    ] == ("Trials of the Blood: 20 XP")
    bought = spend(
        troupe.player, character_id, rating("elder_disciplines", "Auspex: Fog of War", 1)
    )

    assert bought.json()["applied"], bought.text
    assert balance(troupe.player, character_id) == xp - 20
    assert sheet(troupe.player, character_id)["problems"] == []
    # A third is refused.
    third = spend(
        troupe.player, character_id, rating("elder_disciplines", "Auspex: Psychic Assault", 1)
    )
    assert "A Pretender Elder can learn only one elder power." in line(third)["refused"]


def test_without_the_merit_a_pretender_elder_has_one_elder_power(troupe: Troupe) -> None:
    character_id = vizier(troupe, merit=False)

    second = spend(
        troupe.player, character_id, rating("elder_disciplines", "Auspex: Fog of War", 1)
    )

    assert "A Pretender Elder can learn only one elder power." in line(second)["refused"]


def creep(troupe: Troupe, *, merit: bool = True) -> str:
    """A Master Elder Creep with Shrinking Violet, and the disciplines Misleading
    Wounds and Animal Succulence need."""
    character_id = vampire(troupe, "Nosferatu: Creeps", 4, Obfuscate=5, Animalism=5, Fortitude=5)
    if merit:
        take_merit(troupe, character_id, "Shrinking Violet")
    return character_id


def test_a_master_elder_creep_buys_a_technique_needing_obfuscate_for_12_xp(troupe: Troupe) -> None:
    character_id = creep(troupe)
    player = troupe.player

    shown = opened(player, character_id, "techniques")["techniques"]
    assert shown["Misleading Wounds"] == "Shrinking Violet: 12 XP"
    assert "Animal Succulence" not in shown
    picker = refused(player, character_id, "techniques")
    assert "Misleading Wounds" not in picker
    assert "Animal Succulence" in picker
    # Its other prerequisites still apply.
    assert picker["Vanishing Act"] == (
        "Vanishing Act needs Chimerstry 1 and Obfuscate 2. (Vol. 2 Issue 1, p. 84)"
    )
    bought = spend(player, character_id, rating("techniques", "Misleading Wounds", 1))

    assert bought.json()["applied"], bought.text
    assert (line(bought)["cost"], line(bought)["because"]) == (12, "Shrinking Violet: 12 XP")
    # A technique without Obfuscate is still refused.
    other = spend(player, character_id, rating("techniques", "Animal Succulence", 1))
    assert not other.json()["applied"] and line(other)["refused"]


def test_without_the_merit_a_master_elder_learns_no_technique(troupe: Troupe) -> None:
    character_id = creep(troupe, merit=False)

    assert refused(troupe.player, character_id, "techniques")["Misleading Wounds"] == (
        "A Master or Luminary Elder cannot learn techniques. (p. 101)"
    )


def test_the_power_sold_back_frees_the_merit_for_another(troupe: Troupe) -> None:
    character_id = crusader(troupe)
    xp = balance(troupe.player, character_id)
    spend(troupe.player, character_id, rating("elder_disciplines", "Fortitude: Personal Armor", 1))

    sold = spend(
        troupe.player, character_id, rating("elder_disciplines", "Fortitude: Personal Armor", 0)
    )

    assert sold.json()["applied"], sold.text
    assert balance(troupe.player, character_id) == xp
    assert on_sheet(troupe.player, character_id, "Hard as Steel")["opened"] == []
    again = spend(
        troupe.player, character_id, rating("elder_disciplines", "Fortitude: Resilient Mind", 1)
    )
    assert line(again)["cost"] == 20 and again.json()["applied"], again.text


def test_the_merit_taken_away_takes_its_power_with_the_xp_back(troupe: Troupe) -> None:
    character_id = vampire(troupe, "Ventrue: Crusader", 1, Fortitude=5)
    xp = balance(troupe.player, character_id)
    take_merit(troupe, character_id, "Hard as Steel")
    spend(troupe.player, character_id, rating("elder_disciplines", "Fortitude: Personal Armor", 1))

    gone = spend(troupe.player, character_id, rating("merits", "Hard as Steel", 0))

    assert gone.json()["applied"], gone.text
    names = {t["name"] for t in sheet(troupe.player, character_id)["traits"]}
    assert not {"Hard as Steel", "Fortitude: Personal Armor"} & names
    assert balance(troupe.player, character_id) == xp
    assert (
        "Fortitude: Personal Armor 1 → 0, lost with Hard as Steel",
        20,
    ) in history(troupe.player, character_id, "purchase")


def test_a_diablerie_keeps_the_technique_the_merit_opened(troupe: Troupe) -> None:
    character_id = creep(troupe)
    spend(troupe.player, character_id, rating("techniques", "Misleading Wounds", 1))
    make_home(troupe, character_id)

    found = troupe.storyteller.client.get(f"/characters/{character_id}/diablerie/plan").json()
    assert found["refused"] is None and found["techniques"] == []
    done = troupe.storyteller.client.post(
        f"/characters/{character_id}/diablerie", json={"committed_on": "2026-10-24"}
    )

    assert done.status_code == 200, done.text
    assert on_sheet(troupe.player, character_id, "Generation")["rating"] == 5
    assert on_sheet(troupe.player, character_id, "Misleading Wounds")["opened_by"] == (
        "Shrinking Violet"
    )


def test_a_diablerie_takes_a_technique_the_merit_did_not_open_and_the_merit_opens_it_after(
    troupe: Troupe,
) -> None:
    # A Pretender Elder Crusader learns a Fortitude technique at the usual 20 XP.
    character_id = vampire(troupe, "Ventrue: Crusader", 3, Fortitude=5, Obfuscate=2)
    take_merit(troupe, character_id, "Hard as Steel")
    learnt = spend(troupe.player, character_id, rating("techniques", "Displacement Aura", 1))
    assert (line(learnt)["cost"], line(learnt)["because"]) == (20, None)
    make_home(troupe, character_id)

    found = troupe.storyteller.client.get(f"/characters/{character_id}/diablerie/plan").json()
    assert found["techniques"] == [
        {"name": "Displacement Aura", "detail": "", "rating": 1, "refund": 20}
    ]
    done = troupe.storyteller.client.post(
        f"/characters/{character_id}/diablerie", json={"committed_on": "2026-10-24"}
    )

    # Lost with its XP, as any technique a Master Elder cannot hold; the merit is unspent.
    assert done.status_code == 200, done.text
    names = {t["name"] for t in sheet(troupe.player, character_id)["traits"]}
    assert "Displacement Aura" not in names
    again = spend(troupe.player, character_id, rating("techniques", "Displacement Aura", 1))
    assert (line(again)["cost"], line(again)["because"]) == (12, "Hard as Steel: 12 XP")
    assert again.json()["applied"], again.text
