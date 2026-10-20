"""The Play View's quick game reference (issue #83): pools worked out from the
sheet, with disciplines, focuses, merits and flaws, and notes on powers."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import CharacterTrait, TraitCategory, TraitDefinition
from horatio.reference import catalogue
from horatio.rules.files import DATA_DIR, all_rule_set_files, load_rule_set
from tests.api_helpers import Troupe
from tests.test_api_character_search import member


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def created(troupe: Troupe, name: str, *traits: tuple[str, str, int | None]) -> str:
    """A Brujah in the troupe with `traits` on its sheet."""
    character_id = member(troupe, troupe.player, name, "Brujah")
    for category, trait, rating in traits:
        definition = troupe.session.scalars(
            select(TraitDefinition)
            .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
            .where(TraitCategory.key == category, TraitDefinition.name == trait)
        ).one()
        troupe.session.add(
            CharacterTrait(
                character_id=uuid.UUID(character_id),
                trait_definition_id=definition.id,
                rating=rating,
            )
        )
    troupe.session.flush()
    return character_id


def reference(troupe: Troupe, character_id: str) -> dict[str, Any]:
    response = troupe.player.client.get(f"/characters/{character_id}/play/reference")
    assert response.status_code == 200, response.text
    return response.json()


def pool(found: dict[str, Any], key: str) -> dict[str, Any]:
    return next(p for p in found["pools"] if p["key"] == key)


def variants(p: dict[str, Any]) -> dict[str, int]:
    return {v["when"]: v["total"] for v in p["variants"]}


@pytest.fixture
def swift(troupe: Troupe) -> str:
    """Physical 6, Mental 4, Dexterity focus, Celerity 4 with a Celerity elder
    power and technique, Obfuscate 2, Slippery Customer, Fanatic and Quixotic."""
    return created(
        troupe,
        "Swift",
        ("attributes", "Physical", 6),
        ("attributes", "Social", 3),
        ("attributes", "Mental", 4),
        ("focus_physicals", "Dexterity", None),
        ("skills", "Dodge", 3),
        ("skills", "Brawl", 2),
        ("skills", "Stealth", 3),
        ("disciplines", "Celerity", 4),
        ("disciplines", "Dominate", 2),
        ("disciplines", "Obfuscate", 2),
        ("elder_disciplines", "Celerity: Quickness", None),
        ("techniques", "Instinctive Command", None),
        ("merits", "Slippery Customer", None),
        ("merits", "Fanatic", None),
        ("merits", "Quixotic", None),
    )


def test_initiative_with_and_without_celerity(troupe: Troupe, swift: str) -> None:
    initiative = pool(reference(troupe, swift), "initiative")

    assert initiative["total"] == 6  # Physical, the higher of Physical and Mental
    assert variants(initiative) == {
        # Alacrity: Celerity 4, its elder power and a technique built on it.
        "With Celerity active": 12,
        "While Injured": 9,
        "While Incapacitated": 12,
    }


def test_dodge_counts_merits_focus_and_celerity(troupe: Troupe, swift: str) -> None:
    dodge = pool(reference(troupe, swift), "dodge")

    assert [(p["label"], p["value"]) for p in dodge["parts"]] == [
        ("Physical", 6),
        ("Dodge", 3),
        ("Slippery Customer", 3),
    ]
    # +2 with the Dexterity focus, +2 from Legerity.
    assert variants(dodge) == {"With Celerity active": 16}
    assert any("+2 to one Dodge pool" in n for n in dodge["notes"])


def test_attacks_disciplines_and_defence(troupe: Troupe, swift: str) -> None:
    found = reference(troupe, swift)

    keys = [p["key"] for p in found["pools"]]
    assert "attack:Brawl" in keys and "attack:Melee" not in keys
    assert pool(found, "attack:Brawl")["total"] == 8
    obfuscate = pool(found, "discipline:Obfuscate")
    assert (obfuscate["total"], obfuscate["versus"]) == (7, "Mental + Willpower")
    mental = pool(found, "defense:Mental")
    # Current Willpower is added on the page, never below 3 with Quixotic.
    assert (mental["total"], mental["adds_willpower"], mental["willpower_floor"]) == (4, True, 3)
    # Celerity has no standard test pool.
    assert "discipline:Celerity" not in keys


def test_power_notes_follow_dots_and_focus(troupe: Troupe, swift: str) -> None:
    found = reference(troupe, swift)

    disciplines = {d["name"]: d for d in found["disciplines"]}
    celerity = disciplines["Celerity"]
    assert [p["name"] for p in celerity["powers"]] == [
        "Alacrity",
        "Swiftness",
        "Rapidity",
        "Legerity",
    ]
    assert celerity["focus"] == "+2 to Dodge pools while Celerity is active."
    assert [p["name"] for p in disciplines["Obfuscate"]["powers"]] == [
        "Conceal",
        "Unseen Presence",
    ]
    # Without the Intelligence or Wits focus, no focus notes.
    assert all(p["focus"] is None for p in disciplines["Obfuscate"]["powers"])
    assert {o["name"] for o in found["other_powers"]} == {
        "Celerity: Quickness",
        "Instinctive Command",
    }
    assert any(t["name"] == "Celerity" for t in found["traits"])


def test_substitutes_and_replacements(troupe: Troupe) -> None:
    odd = created(
        troupe,
        "Odd",
        ("attributes", "Physical", 3),
        ("attributes", "Social", 7),
        ("attributes", "Mental", 5),
        ("focus_physicals", "Strength", None),
        ("skills", "Dodge", 1),
        ("skills", "Awareness", 4),
        ("skills", "Brawl", 2),
        ("disciplines", "Potence", 1),
        ("merits", "Rhythm of Battle", None),
        ("merits", "Preternatural Awareness", None),
        ("merits", "Tech Junkie", None),
        ("flaws", "Slow Reactions", None),
    )
    found = reference(troupe, odd)

    initiative = pool(found, "initiative")
    assert initiative["parts"][0] == {"label": "Social", "value": 7}  # Rhythm of Battle
    assert initiative["total"] == 2  # Slow Reactions
    dodge = pool(found, "dodge")
    assert dodge["parts"][1] == {"label": "Awareness (for Dodge)", "value": 4}
    # Potence with the Strength focus: +2 to Brawl and Melee.
    assert pool(found, "attack:Brawl")["total"] == 3 + 2 + 2
    assert "Tech Junkie: +2 to Computers" in found["notes"]


def test_strangers_cannot_read_it(troupe: Troupe, swift: str) -> None:
    response = troupe.stranger.client.get(f"/characters/{swift}/play/reference")
    assert response.status_code in (403, 404)


def test_every_discipline_has_notes_for_each_dot() -> None:
    """The book's quick notes cover every discipline in the rule set, five
    powers each, and every pool effect names a pool the page knows."""
    rule_set = load_rule_set(DATA_DIR / "bns_met_vampire.toml")
    disciplines = {name for category, name in rule_set.traits if category == "disciplines"}
    book = catalogue()
    assert set(book.disciplines) == disciplines
    for name in disciplines:
        assert [p["level"] for p in book.powers[name]] == [1, 2, 3, 4, 5], name
    known = ("initiative", "dodge", "attack", "defense", "discipline", "skill", "frenzy", "all")
    entries = [e for d in book.disciplines.values() for e in d.get("pools", [])] + [
        e for ps in book.powers.values() for p in ps for e in p.get("pools", [])
    ]
    entries += [e for t in rule_set.traits.values() for e in t.properties.get("pools", [])]
    assert entries
    assert all(e["pool"].split(":", 1)[0] in known for e in entries)


def test_the_power_notes_are_not_a_rule_set() -> None:
    assert all(not p.name.endswith("_powers.toml") for p in all_rule_set_files())
