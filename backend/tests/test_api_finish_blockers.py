"""Characters the creation wizard could not finish (#312): a Salubri, an Angelis Ater,
a Nagaraja with Blight of the Ever-Hungry, a ghoul with Stolen Potential and a
Toreador with Artist's Blessing. And restricted picks that cannot all be placed say
why, on the creation state and at Finish."""

from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.creation import in_clan_gaps
from horatio.rules.checks import Context, violations
from horatio.rules.files import DATA_DIR, load_rule_set
from horatio.rules.model import SheetTrait, TroupeRules
from horatio.rules.splats import SPLATS
from tests.api_helpers import Person, Troupe
from tests.test_api_creation import FULL_BUILD, creating, creation, pick, sheet
from tests.test_api_ghouls import BUILD, ghoul_of, typed

pytestmark = pytest.mark.usefixtures("without_bank")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def finish(person: Person, character_id: str) -> Any:
    return person.client.post(f"/characters/{character_id}/creation/complete")


# Every pick but the disciplines, with Allies for Herd, which a Salubri cannot take.
BUILD_BUT_DISCIPLINES = [
    (c, "Allies" if n == "Herd" else n, r) for c, n, r in FULL_BUILD if c != "disciplines"
]


def build_but_disciplines(person: Person, character_id: str) -> None:
    for category, name, rating in BUILD_BUT_DISCIPLINES:
        placed = pick(person, character_id, category, name, rating)
        assert placed.status_code == 200, (name, placed.text)


def in_clan_options(state: dict[str, Any]) -> list[str]:
    return next(p["options"] for p in state["pools"] if p["restriction"] == "in_clan")


def place_disciplines(person: Person, character_id: str, names: list[str]) -> None:
    """The first at 2, the rest at 1."""
    for i, name in enumerate(names):
        placed = pick(person, character_id, "disciplines", name, 2 if i == 0 else 1)
        assert placed.status_code == 200, placed.text


def merits(person: Person, character_id: str, picks: list[tuple[str, str]]) -> Any:
    return person.client.put(
        f"/characters/{character_id}/creation/categories/merits",
        json={"picks": [{"name": n, "detail": d} for n, d in picks]},
    )


def choose_clan(person: Person, character_id: str, clan: str, detail: str = "") -> Any:
    return person.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "clan", "name": clan, "detail": detail, "rating": None},
    )


# --- 1. Salubri ---------------------------------------------------------------------


def test_a_salubri_places_valeren_and_finishes(troupe: Troupe) -> None:
    character_id = creating(troupe, "Salubri")
    player = troupe.player
    build_but_disciplines(player, character_id)

    state = creation(player, character_id)
    assert in_clan_options(state) == ["Auspex", "Fortitude", "Valeren"]
    assert state["shortfalls"] == []
    place_disciplines(player, character_id, ["Valeren", "Auspex", "Fortitude"])

    assert finish(player, character_id).status_code == 200


# --- 2. Baali: Angelis Ater ------------------------------------------------------------


def test_angelis_ater_chooses_its_third_in_clan_discipline(troupe: Troupe) -> None:
    character_id = creating(troupe, "Baali: Angelis Ater")
    player = troupe.player
    build_but_disciplines(player, character_id)

    state = creation(player, character_id)
    assert state["clan_choice"] == {
        "clan": "Baali: Angelis Ater",
        "choices": ["Potence", "Presence", "Obfuscate"],
        "chosen": None,
        "page": "72",
    }
    assert in_clan_options(state) == ["Daimoinon", "Dominate"]
    assert [s["message"] for s in state["shortfalls"]] == [
        "Only 2 in-clan disciplines for 3 starting picks: Baali: Angelis Ater has one more"
        " to choose, from Potence, Presence or Obfuscate (p. 72)."
    ]
    place_disciplines(player, character_id, ["Daimoinon", "Dominate"])
    # Finish says what the missing pick waits on.
    refused = finish(player, character_id)
    assert refused.status_code == 409
    assert refused.json()["detail"] == (
        "Place every pick first: 1 disciplines at 1. Only 2 in-clan disciplines for 3"
        " starting picks: Baali: Angelis Ater has one more to choose, from Potence,"
        " Presence or Obfuscate (p. 72)."
    )

    # Only one of the three can be chosen.
    wrong = choose_clan(player, character_id, "Baali: Angelis Ater", "Animalism")
    assert wrong.status_code == 422
    assert wrong.json()["detail"] == ("Baali: Angelis Ater: choose Potence, Presence or Obfuscate.")
    assert choose_clan(player, character_id, "Baali: Angelis Ater", "Presence").status_code == 200

    state = creation(player, character_id)
    assert state["clan_choice"]["chosen"] == "Presence"
    assert in_clan_options(state) == ["Daimoinon", "Dominate", "Presence"]
    assert state["shortfalls"] == []
    # The starting dots already placed stay where they are.
    assert pick(player, character_id, "disciplines", "Presence").status_code == 200
    assert finish(player, character_id).status_code == 200
    clan = next(t for t in sheet(player, character_id)["traits"] if t["category"] == "clan")
    assert (clan["name"], clan["detail"]) == ("Baali: Angelis Ater", "Presence")


def test_shadows_of_the_past_leaves_angelis_ater_nothing_to_choose(troupe: Troupe) -> None:
    character_id = creating(troupe, "Baali: Angelis Ater")
    player = troupe.player
    assert merits(player, character_id, [("Shadows of the Past", "")]).status_code == 200

    state = creation(player, character_id)
    assert state["clan_choice"] is None
    assert in_clan_options(state) == ["Daimoinon", "Dominate", "Obtenebration"]
    assert state["shortfalls"] == []


def test_another_clan_takes_no_choice(troupe: Troupe) -> None:
    character_id = creating(troupe)
    assert creation(troupe.player, character_id)["clan_choice"] is None
    refused = choose_clan(troupe.player, character_id, "Brujah", "Presence")
    # Brujah has no choice to keep: its detail is free text as any other clan's.
    assert refused.status_code == 200
    assert in_clan_options(creation(troupe.player, character_id)) == [
        "Celerity",
        "Potence",
        "Presence",
    ]


@pytest.mark.usefixtures("ghoul_rules")
def test_an_angelis_ater_ghoul_has_its_domitors_choice(troupe: Troupe) -> None:
    player = troupe.player
    vampire = creating(troupe, "Baali: Angelis Ater")
    assert choose_clan(player, vampire, "Baali: Angelis Ater", "Obfuscate").status_code == 200

    ghoul = ghoul_of(player, {"character_id": vampire})

    found = player.client.get(f"/characters/{ghoul}/domitor").json()
    assert found["in_clan"] == ["Daimoinon", "Dominate", "Obfuscate"]
    # And follows its domitor's player changing it.
    assert choose_clan(player, vampire, "Baali: Angelis Ater", "Potence").status_code == 200
    found = player.client.get(f"/characters/{ghoul}/domitor").json()
    assert found["in_clan"] == ["Daimoinon", "Dominate", "Potence"]


# --- 3. Blight of the Ever-Hungry ---------------------------------------------------


def test_a_nagaraja_with_blight_places_the_graveborne_path_and_finishes(troupe: Troupe) -> None:
    character_id = creating(troupe, "Nagaraja")
    player = troupe.player
    build_but_disciplines(player, character_id)
    assert merits(player, character_id, [("Blight of the Ever-Hungry", "")]).status_code == 200

    graveborne = "Necromancy: Path of the Graveborne"
    state = creation(player, character_id)
    assert in_clan_options(state) == ["Auspex", graveborne, "Potence"]
    assert state["shortfalls"] == []
    place_disciplines(player, character_id, ["Potence", "Auspex", graveborne])

    finished = finish(player, character_id)
    assert finished.status_code == 200, finished.text


# --- 4. A ghoul's Stolen Potential --------------------------------------------------


@pytest.mark.usefixtures("ghoul_rules")
def test_a_ghoul_with_stolen_potential_takes_no_mental_focus(troupe: Troupe) -> None:
    player = troupe.player
    ghoul = ghoul_of(player, typed())
    for category, name, rating in BUILD:
        if category != "focus_mentals":
            assert pick(player, ghoul, category, name, rating).status_code == 200, name
    assert finish(player, ghoul).status_code == 409

    flaw = player.client.put(
        f"/characters/{ghoul}/creation/categories/flaws",
        json={"picks": [{"name": "Stolen Potential", "detail": "Mental"}]},
    )
    assert flaw.status_code == 200, flaw.text

    state = creation(player, ghoul)
    assert not [p for p in state["pools"] if p["category"] == "focus_mentals"]
    assert {
        "category": "focus_mentals",
        "because": [{"category": "flaws", "name": "Stolen Potential"}],
    } in state["budget_changes"]
    refused = pick(player, ghoul, "focus_mentals", "Wits")
    assert refused.status_code == 422
    assert refused.json()["detail"] == "Stolen Potential: there are no Mental Focus picks at 1."

    finished = finish(player, ghoul)
    assert finished.status_code == 200, finished.text

    # After creation, a Mental focus is refused while the flaw is held.
    refusals = player.client.get(
        f"/characters/{ghoul}/refusals", params={"category": "focus_mentals"}
    ).json()
    assert refusals["Wits"]["message"] == "Stolen Potential: no Mental focus. (p. 265)"
    added = player.client.put(
        f"/characters/{ghoul}/traits",
        json={"category": "focus_mentals", "name": "Wits", "rating": 1},
    )
    assert added.status_code == 409
    assert "Stolen Potential: no Mental focus." in added.json()["detail"]


# --- 5. Artist's Blessing ---------------------------------------------------------


@pytest.mark.parametrize("detail", ["Performance", "Crafts", "Performance:", "Crafts:  "])
def test_artists_blessing_needs_the_skill_with_its_field(troupe: Troupe, detail: str) -> None:
    character_id = creating(troupe, "Toreador")

    refused = merits(troupe.player, character_id, [("Artist's Blessing", detail)])

    assert refused.status_code == 409
    assert refused.json()["detail"] == (
        "Artist's Blessing: name the skill with its field, such as Performance: Singing or"
        " Crafts: Painting. (p. 243)"
    )


def test_artists_blessing_is_offered_before_its_field_is_named(troupe: Troupe) -> None:
    character_id = creating(troupe, "Toreador")
    offered = troupe.player.client.get(
        f"/characters/{character_id}/refusals", params={"category": "merits"}
    ).json()
    assert "Artist's Blessing" not in offered


def test_artists_blessing_with_a_field_finishes(troupe: Troupe) -> None:
    character_id = creating(troupe, "Toreador")
    player = troupe.player
    build_but_disciplines(player, character_id)
    place_disciplines(player, character_id, ["Auspex", "Celerity", "Presence"])

    taken = merits(player, character_id, [("Artist's Blessing", "Performance: Singing")])
    assert taken.status_code == 200, taken.text

    singing = next(t for t in sheet(player, character_id)["traits"] if t["name"] == "Performance")
    assert (singing["detail"], singing["rating"]) == ("Singing", 3)
    finished = finish(player, character_id)
    assert finished.status_code == 200, finished.text


# --- 6. Why picks cannot all be placed ------------------------------------------------


@pytest.fixture(scope="module")
def rules() -> TroupeRules:
    return TroupeRules(load_rule_set(DATA_DIR / "bns_met_vampire.toml"))


def with_clan(rules: TroupeRules, clan: str, in_clan: list[str]) -> TroupeRules:
    """The rules with a clan's in-clan disciplines set to these."""
    traits = dict(rules.rule_set.traits)
    found = traits[("clan", clan)]
    traits[("clan", clan)] = replace(found, properties={**found.properties, "in_clan": in_clan})
    return TroupeRules(replace(rules.rule_set, traits=traits))


def test_a_name_the_catalogue_lacks_is_said_to_be_missing(rules: TroupeRules) -> None:
    misspelt = with_clan(rules, "Salubri", ["Auspex", "Fortitude", "Valeran"])
    sheet_ = [SheetTrait(category="clan", name="Salubri")]

    assert in_clan_gaps(misspelt, "vampire", sheet_, "disciplines") == [
        "Valeran is not a discipline Horatio has. Ask your storyteller."
    ]
    assert in_clan_gaps(rules, "vampire", sheet_, "disciplines") == []


def test_an_unmade_clan_choice_is_said(rules: TroupeRules) -> None:
    unchosen = [SheetTrait(category="clan", name="Baali: Angelis Ater")]
    chosen = [SheetTrait(category="clan", name="Baali: Angelis Ater", detail="Potence")]

    assert in_clan_gaps(rules, "vampire", unchosen, "disciplines") == [
        "Baali: Angelis Ater has one more to choose, from Potence, Presence or Obfuscate (p. 72)."
    ]
    assert in_clan_gaps(rules, "vampire", chosen, "disciplines") == []


def test_a_skill_given_without_its_field_is_the_merits_to_fix(rules: TroupeRules) -> None:
    """Artist's Blessing held as plain Performance from before (#312): the merit says to
    name the field, on Merits & flaws; the free Performance it gives is not held to the
    Skills step's field check."""
    held = [
        SheetTrait(category="clan", name="Toreador"),
        SheetTrait(category="backgrounds", name="Generation", rating=1),
        SheetTrait(category="merits", name="Artist's Blessing", rating=1, detail="Performance"),
        SheetTrait(category="skills", name="Performance", rating=3, granted_rating=3),
        SheetTrait(category="skills", name="Crafts", rating=1),
    ]
    native = frozenset(SPLATS["vampire"].in_clan(rules, held))
    found = violations(rules.checks(), held, Context(in_clan=native, native=native))

    assert sorted((v.subject.name, v.message) for v in found) == [
        (
            "Artist's Blessing",
            "Artist's Blessing: name the skill with its field, such as Performance: Singing or"
            " Crafts: Painting. (p. 243)",
        ),
        (
            "Crafts",
            "Crafts, Performance and Science need a field, such as Performance: Singing. (p. 92)",
        ),
    ]
