"""What a merit or flaw taken on the Merits step changes on an earlier one (#192, part 3):
the focuses and free dots merits give, the picks they leave spent for nothing, and the
flaws that clash with a pick."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe
from tests.test_api_creation import creating, creation, pick, sheet


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def refusals(person: Person, character_id: str, category: str, **query: Any) -> dict[str, Any]:
    response = person.client.get(
        f"/characters/{character_id}/refusals", params={"category": category, **query}
    )
    assert response.status_code == 200, response.text
    return response.json()


def merit(
    person: Person, character_id: str, name: str, detail: str = "", category: str = "merits"
) -> Any:
    return person.client.put(
        f"/characters/{character_id}/creation/picks",
        json={"category": category, "name": name, "rating": 1, "detail": detail},
    )


def picked(state: dict[str, Any], category: str) -> dict[str, dict[str, Any]]:
    return {t["name"]: t for p in state["pools"] if p["category"] == category for t in p["traits"]}


def refs(*pairs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"category": c, "name": n} for c, n in pairs]


# --- picks a merit makes free ------------------------------------------------------------


def test_a_pick_on_herd_is_freed_by_personal_cult(troupe: Troupe) -> None:
    character_id = creating(troupe, "Followers of Set")
    player = troupe.player
    assert pick(player, character_id, "backgrounds", "Herd", 3).status_code == 200
    assert pick(player, character_id, "backgrounds", "Haven", 2).status_code == 200
    assert picked(creation(player, character_id), "backgrounds")["Herd"]["freed_by"] == []

    assert merit(player, character_id, "Personal Cult", "Herd").status_code == 200

    state = creation(player, character_id)
    assert picked(state, "backgrounds")["Herd"]["freed_by"] == refs(("merits", "Personal Cult"))
    # Haven is not the one it made free.
    assert picked(state, "backgrounds")["Haven"]["freed_by"] == []
    # The pick is kept, as it was, until its player moves it.
    assert picked(state, "backgrounds")["Herd"]["pick"] == 3


def test_a_freed_pick_can_go_elsewhere_and_the_trait_stays_free(troupe: Troupe) -> None:
    character_id = creating(troupe, "Followers of Set")
    player = troupe.player
    pick(player, character_id, "backgrounds", "Herd", 3)
    merit(player, character_id, "Personal Cult", "Herd")

    moved = player.client.put(
        f"/characters/{character_id}/creation/categories/backgrounds",
        json={"picks": [{"name": "Resources", "rating": 3}]},
    )

    assert moved.status_code == 200, moved.text
    state = creation(player, character_id)
    assert list(picked(state, "backgrounds")) == ["Resources"]
    herd = next(t for t in sheet(player, character_id)["traits"] if t["name"] == "Herd")
    assert (herd["rating"], herd["free_rating"]) == (5, 5)
    # Held free, with no pick: a pick cannot go on it.
    assert [(g["name"], g["rating"], g["because"]) for g in state["given"]] == [
        ("Herd", 5, refs(("merits", "Personal Cult")))
    ]


def test_a_pick_bigger_than_the_free_dots_is_not_freed(troupe: Troupe) -> None:
    player = troupe.player
    big = creating(troupe, "Daughters of Cacophony")
    pick(player, big, "backgrounds", "Fame", 3)

    assert merit(player, big, "Diva").status_code == 200

    # Diva makes the first 2 dots of Fame free; the pick at 3 is still worth a dot.
    assert picked(creation(player, big), "backgrounds")["Fame"]["freed_by"] == []

    small = creating(troupe, "Daughters of Cacophony")
    pick(player, small, "backgrounds", "Fame", 2)
    assert merit(player, small, "Diva").status_code == 200
    assert picked(creation(player, small), "backgrounds")["Fame"]["freed_by"] == refs(
        ("merits", "Diva")
    )


def test_a_skill_pick_is_freed_by_a_merit_that_gives_the_skill(troupe: Troupe) -> None:
    character_id = creating(troupe, "Gangrel")
    player = troupe.player
    pick(player, character_id, "skills", "Survival", 3)
    pick(player, character_id, "skills", "Brawl", 2)

    assert merit(player, character_id, "Seasoned Traveler", "Survival").status_code == 200

    skills = picked(creation(player, character_id), "skills")
    assert skills["Survival"]["freed_by"] == refs(("merits", "Seasoned Traveler"))
    assert skills["Brawl"]["freed_by"] == []


def test_a_focus_pick_is_freed_by_a_merit_that_gives_the_same_focus(troupe: Troupe) -> None:
    character_id = creating(troupe, "Nosferatu: Creeps")
    player = troupe.player
    pick(player, character_id, "focus_mentals", "Perception", 1)

    assert merit(player, character_id, "Extrasensory Perceptions").status_code == 200

    focuses = picked(creation(player, character_id), "focus_mentals")
    assert focuses["Perception"]["freed_by"] == refs(("merits", "Extrasensory Perceptions"))
    # Not given twice: still one Perception.
    held = [t for t in sheet(player, character_id)["traits"] if t["name"] == "Perception"]
    assert [(t["rating"], t["granted_rating"]) for t in held] == [(1, 0)]


# --- focuses a merit gives ---------------------------------------------------------------


def test_a_focus_a_merit_gives_is_held_with_no_pick_and_a_pick_cannot_go_on_it(
    troupe: Troupe,
) -> None:
    character_id = creating(troupe, "Nosferatu: Creeps")
    player = troupe.player

    taken = merit(player, character_id, "Extrasensory Perceptions")
    assert taken.status_code == 200, taken.text

    state = creation(player, character_id)
    assert [(g["category"], g["name"], g["rating"], g["because"]) for g in state["given"]] == [
        ("focus_mentals", "Perception", 1, refs(("merits", "Extrasensory Perceptions")))
    ]
    # The usual pick is still there to place on another focus.
    assert pick(player, character_id, "focus_mentals", "Wits", 1).status_code == 200
    taken = pick(player, character_id, "focus_mentals", "Perception", 1)
    assert taken.status_code == 409


def test_versatile_gives_the_focus_it_is_told_to_and_not_twice(troupe: Troupe) -> None:
    character_id = creating(troupe, "Brujah")
    player = troupe.player
    pick(player, character_id, "focus_physicals", "Strength", 1)

    # A focus must be named.
    assert merit(player, character_id, "Versatile").status_code == 409
    assert merit(player, character_id, "Versatile", "Wits").status_code == 200

    state = creation(player, character_id)
    assert [(g["category"], g["name"]) for g in state["given"]] == [("focus_mentals", "Wits")]
    assert picked(state, "focus_physicals")["Strength"]["freed_by"] == []


def test_a_focus_a_merit_gives_on_the_same_focus_as_the_pick_is_not_given_twice(
    troupe: Troupe,
) -> None:
    character_id = creating(troupe, "Lasombra")
    player = troupe.player
    pick(player, character_id, "focus_socials", "Charisma", 1)

    assert merit(player, character_id, "Angelic Visage").status_code == 200

    charisma = next(t for t in sheet(player, character_id)["traits"] if t["name"] == "Charisma")
    assert (charisma["rating"], charisma["granted_rating"]) == (1, 0)
    assert picked(creation(player, character_id), "focus_socials")["Charisma"]["freed_by"] == refs(
        ("merits", "Angelic Visage")
    )


# --- flaws that clash with a pick --------------------------------------------------------


def test_archaic_is_refused_for_the_computer_pick_and_names_it(troupe: Troupe) -> None:
    character_id = creating(troupe, "Brujah")
    player = troupe.player
    pick(player, character_id, "skills", "Computer", 2)

    flaws = refusals(player, character_id, "flaws")

    assert flaws["Archaic"]["because"] == refs(("skills", "Computer"))
    assert merit(player, character_id, "Archaic", category="flaws").status_code == 409


def test_computer_is_refused_for_archaic_and_names_it(troupe: Troupe) -> None:
    character_id = creating(troupe, "Brujah")
    player = troupe.player
    assert merit(player, character_id, "Archaic", category="flaws").status_code == 200

    skills = refusals(player, character_id, "skills")

    for name in ("Computer", "Drive", "Science", "Security"):
        assert skills[name]["because"] == refs(("flaws", "Archaic"))
        assert "Archaic" in skills[name]["message"]
    assert "Brawl" not in skills
    assert pick(player, character_id, "skills", "Computer", 2).status_code == 409


def test_a_flaw_that_bars_a_background_names_the_background_and_the_other_way_about(
    troupe: Troupe,
) -> None:
    character_id = creating(troupe, "Brujah")
    player = troupe.player
    pick(player, character_id, "backgrounds", "Herd", 2)

    assert refusals(player, character_id, "flaws")["Methuselah's Thirst"]["because"] == refs(
        ("backgrounds", "Herd")
    )

    player.client.put(
        f"/characters/{character_id}/creation/categories/backgrounds", json={"picks": []}
    )
    assert merit(player, character_id, "Methuselah's Thirst", category="flaws").status_code == 200
    herd = refusals(player, character_id, "backgrounds")["Herd"]
    assert herd["because"] == refs(("flaws", "Methuselah's Thirst"))


def test_childlike_bars_physical_at_7_and_not_below(troupe: Troupe) -> None:
    character_id = creating(troupe, "Brujah")
    player = troupe.player
    assert merit(player, character_id, "Childlike", category="flaws").status_code == 200

    assert refusals(player, character_id, "attributes", rating=5) == {}
    at_7 = refusals(player, character_id, "attributes", rating=7)

    assert list(at_7) == ["Physical"]
    assert at_7["Physical"]["because"] == refs(("flaws", "Childlike"))


def test_childlike_is_refused_for_physical_at_7_and_the_pick_is_named(troupe: Troupe) -> None:
    character_id = creating(troupe, "Brujah")
    player = troupe.player
    pick(player, character_id, "attributes", "Physical", 7)

    assert refusals(player, character_id, "flaws")["Childlike"]["because"] == refs(
        ("attributes", "Physical")
    )


def test_szlachta_and_magic_resistance_name_the_disciplines_they_clash_with(
    troupe: Troupe,
) -> None:
    character_id = creating(troupe, "Tzimisce")
    player = troupe.player
    pick(player, character_id, "disciplines", "Auspex", 2)
    assert refusals(player, character_id, "merits")["Szlachta"]["because"] == []

    # Magic Resistance bars blood magic: a Tremere holding Thaumaturgy.
    wizard = creating(troupe, "Tremere")
    pick(player, wizard, "disciplines", "Thaumaturgy: Path of Blood", 2)
    resistance = refusals(player, wizard, "merits")["Magic Resistance"]
    assert resistance["because"] == refs(("disciplines", "Thaumaturgy: Path of Blood"))


# --- Generation against the merits and flaws that depend on it ---------------------------


def test_thin_blooded_is_refused_for_a_generation_of_2_and_names_it(troupe: Troupe) -> None:
    character_id = creating(troupe, "Caitiff")
    player = troupe.player
    pick(player, character_id, "backgrounds", "Generation", 2)

    thin = refusals(player, character_id, "flaws")["Thin Blooded"]

    assert thin["because"] == refs(("backgrounds", "Generation"))
    assert "Neonate" in thin["message"]


def test_generation_is_barred_above_1_by_thin_blooded_and_above_2_by_a_lesser_one(
    troupe: Troupe,
) -> None:
    player = troupe.player
    thin = creating(troupe, "Caitiff")
    assert merit(player, thin, "Thin Blooded", category="flaws").status_code == 200
    assert "Generation" not in refusals(player, thin, "backgrounds", rating=1)
    two = refusals(player, thin, "backgrounds", rating=2)["Generation"]
    assert two["because"] == refs(("flaws", "Thin Blooded"))
    # At 3 the clan bars it as well.
    three = refusals(player, thin, "backgrounds", rating=3)["Generation"]
    assert refs(("flaws", "Thin Blooded"), ("clan", "Caitiff")) == three["because"]

    lesser = creating(troupe, "Brujah")
    assert merit(player, lesser, "Lesser Generation 1", category="flaws").status_code == 200
    assert "Generation" not in refusals(player, lesser, "backgrounds", rating=2)
    barred = refusals(player, lesser, "backgrounds", rating=3)["Generation"]
    assert barred["because"] == refs(("flaws", "Lesser Generation 1"))
    assert pick(player, lesser, "backgrounds", "Generation", 3).status_code == 409


def test_lesser_generation_2_is_for_a_neonate_only(troupe: Troupe) -> None:
    player = troupe.player
    character_id = creating(troupe, "Brujah")
    pick(player, character_id, "backgrounds", "Generation", 2)

    flaws = refusals(player, character_id, "flaws")

    assert flaws["Lesser Generation 2"]["because"] == refs(("backgrounds", "Generation"))
    assert "Lesser Generation 1" not in flaws
    assert merit(player, character_id, "Lesser Generation 1", category="flaws").status_code == 200


def test_a_caitiff_is_barred_from_generation_3_by_the_clan(troupe: Troupe) -> None:
    character_id = creating(troupe, "Caitiff")

    barred = refusals(troupe.player, character_id, "backgrounds", rating=3)["Generation"]

    assert barred["because"] == refs(("clan", "Caitiff"))
