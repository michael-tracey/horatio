"""Traits that give other traits: health, Willpower, focuses, free dots, higher caps."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import CharacterTrait, TraitCategory, TraitDefinition
from tests.api_helpers import Person, Troupe, new_character


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def take(
    person: Person,
    character_id: str,
    category: str,
    name: str,
    rating: int | None = 1,
    detail: str = "",
) -> Any:
    return person.client.put(
        f"/characters/{character_id}/traits",
        json={"category": category, "name": name, "rating": rating, "detail": detail},
    )


def sheet(person: Person, character_id: str) -> Any:
    return person.client.get(f"/characters/{character_id}/sheet").json()


def ratings(person: Person, character_id: str, category: str) -> dict[str, Any]:
    return {
        t["name"] + (f": {t['detail']}" if t["detail"] else ""): t["rating"]
        for t in sheet(person, character_id)["traits"]
        if t["category"] == category
    }


def test_rugged_adds_a_health_level_to_each_track_and_takes_it_back(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    assert take(troupe.player, character_id, "merits", "Rugged", 3).status_code == 200
    health = ratings(troupe.player, character_id, "health_levels")
    assert health == {"Healthy": 4, "Injured": 4, "Incapacitated": 4}
    healthy = next(
        t for t in sheet(troupe.player, character_id)["traits"] if t["name"] == "Healthy"
    )
    assert (healthy["granted_rating"], healthy["granted_by"]) == (1, ["Rugged"])

    take(troupe.player, character_id, "merits", "Rugged", 0)

    assert ratings(troupe.player, character_id, "health_levels") == {
        "Healthy": 3,
        "Injured": 3,
        "Incapacitated": 3,
    }


def test_flaws_can_take_traits_away(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    take(troupe.player, character_id, "flaws", "Low Pain Threshold", 3)
    take(troupe.player, character_id, "flaws", "Short Attention Span", 4)

    assert ratings(troupe.player, character_id, "health_levels") == {
        "Healthy": 3,
        "Injured": 2,
        "Incapacitated": 2,
    }
    assert ratings(troupe.player, character_id, "willpower_sources") == {"Willpower": 5}


def test_unyielding_raises_willpower(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    take(troupe.player, character_id, "merits", "Unyielding", 4)

    assert ratings(troupe.player, character_id, "willpower_sources") == {"Willpower": 7}


def test_a_chosen_grant_needs_its_choice(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Followers of Set")

    refused = take(troupe.player, character_id, "merits", "Personal Cult", 1)

    assert refused.status_code == 409
    assert refused.json()["detail"] == (
        "Say which for Personal Cult: put Haven, Herd, Resources in its detail."
    )
    catalogue = troupe.player.client.get("/rules/vampire").json()["traits"]
    cult = next(t for t in catalogue if t["name"] == "Personal Cult")
    assert cult["choices"] == ["Haven", "Herd", "Resources"]


def test_free_dots_refund_what_was_bought_and_go_with_the_merit(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Followers of Set")
    take(troupe.player, character_id, "backgrounds", "Resources", 2)  # a Neonate pays 1 + 2
    before = sheet(troupe.player, character_id)["xp"]["balance"]

    taken = take(troupe.player, character_id, "merits", "Personal Cult", 1, "Resources")

    assert taken.status_code == 200, taken.text
    after = sheet(troupe.player, character_id)
    resources = next(t for t in after["traits"] if t["name"] == "Resources")
    assert (resources["rating"], resources["free_rating"], resources["granted_rating"]) == (5, 5, 5)
    # The merit costs 1; the 3 XP paid for Resources comes back.
    assert after["xp"]["balance"] == before - 1 + 3
    # Granted dots cannot be sold back.
    assert take(troupe.player, character_id, "backgrounds", "Resources", 4).status_code == 422

    take(troupe.player, character_id, "merits", "Personal Cult", 0, "Resources")

    assert "Resources" not in ratings(troupe.player, character_id, "backgrounds")
    # Dropping the merit refunds its 1 XP like any merit bought since; the free
    # dots simply go.
    assert sheet(troupe.player, character_id)["xp"]["balance"] == before - 1 + 3 + 1


def test_skills_stop_at_five_unless_a_grant_raises_them(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Toreador")
    troupe.custodian.client.post(
        f"/characters/{character_id}/xp", json={"amount": 100, "reason": "Test"}
    )

    refused = take(troupe.player, character_id, "skills", "Brawl", 6)
    assert refused.status_code == 422
    assert refused.json()["detail"] == "Brawl cannot go above 5."

    take(troupe.player, character_id, "merits", "Artist's Blessing", 1, "Performance: Singing")

    assert ratings(troupe.player, character_id, "skills") == {"Performance: Singing": 3}
    assert (
        take(troupe.player, character_id, "skills", "Performance", 7, "Singing").status_code == 200
    )
    assert (
        take(troupe.player, character_id, "skills", "Performance", 8, "Singing").status_code == 422
    )


def test_one_focus_per_attribute_unless_granted(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Lasombra")
    take(troupe.player, character_id, "focus_socials", "Manipulation")

    refused = take(troupe.player, character_id, "focus_socials", "Appearance")
    assert refused.status_code == 409
    assert "only merits can grant more" in refused.json()["detail"]

    assert take(troupe.player, character_id, "merits", "Angelic Visage", 1).status_code == 200
    assert ratings(troupe.player, character_id, "focus_socials") == {
        "Charisma": 1,
        "Manipulation": 1,
    }


def test_a_chosen_focus(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Malkavian")

    take(troupe.player, character_id, "merits", "Expanded Consciousness", 1, "Wits")

    assert ratings(troupe.player, character_id, "focus_mentals") == {"Wits": 1}


def test_npcs_get_their_grants_too(troupe: Troupe) -> None:
    npc = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/npcs", json={"name": "Tough"}
    ).json()["id"]

    troupe.storyteller.client.put(
        f"/characters/{npc}/npc/ratings",
        json={"category": "merits", "name": "Rugged", "rating": 3},
    )

    assert ratings(troupe.storyteller, npc, "health_levels")["Healthy"] == 4


def test_stamina_focus_and_fortitude_add_health(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Ventrue")
    take(troupe.player, character_id, "focus_physicals", "Stamina")

    take(troupe.player, character_id, "disciplines", "Fortitude", 1)

    assert ratings(troupe.player, character_id, "health_levels") == {
        "Healthy": 4,
        "Injured": 4,
        "Incapacitated": 4,
    }
    healthy = next(
        t for t in sheet(troupe.player, character_id)["traits"] if t["name"] == "Healthy"
    )
    assert healthy["granted_by"] == ["Fortitude"]


def test_fortitude_without_the_stamina_focus_adds_nothing(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Ventrue")
    take(troupe.player, character_id, "focus_physicals", "Strength")

    take(troupe.player, character_id, "disciplines", "Fortitude", 1)

    assert ratings(troupe.player, character_id, "health_levels")["Healthy"] == 3


def test_health_and_willpower_are_not_set_by_hand(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    for category, name in (("health_levels", "Healthy"), ("willpower_sources", "Willpower")):
        refused = take(troupe.player, character_id, category, name, 7)
        assert refused.status_code == 422
        assert "come from the rest of the sheet" in refused.json()["detail"]


def test_supernatural_aria_halves_singing(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Daughters of Cacophony")
    take(troupe.player, character_id, "merits", "Supernatural Aria", 1)

    singing = troupe.player.client.post(
        f"/characters/{character_id}/quote",
        json={"category": "skills", "name": "Performance", "detail": "Singing", "rating": 2},
    )
    dancing = troupe.player.client.post(
        f"/characters/{character_id}/quote",
        json={"category": "skills", "name": "Performance", "detail": "Dancing", "rating": 2},
    )

    # A Neonate pays 1 + 2 = 3 for two dots; half of that, rounded up, is 2.
    assert (singing.json()["cost"], dancing.json()["cost"]) == (2, 3)


def test_thaumaturgic_expertise_prices_another_path_in_clan(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Tremere")

    def price(path: str) -> int:
        return troupe.player.client.post(
            f"/characters/{character_id}/quote",
            json={"category": "disciplines", "name": path, "rating": 1},
        ).json()["cost"]

    out_of_clan = price("Thaumaturgy: Path of Conjuring")
    take(
        troupe.player,
        character_id,
        "merits",
        "Thaumaturgic Expertise",
        1,
        "Thaumaturgy: Path of Conjuring",
    )

    assert (
        price("Thaumaturgy: Path of Conjuring") == price("Thaumaturgy: Path of Blood") < out_of_clan
    )
    assert price("Thaumaturgy: Lure of Flames") == out_of_clan


def test_a_path_merit_converts_humanity_and_back(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Lasombra")

    assert take(troupe.player, character_id, "merits", "Path of Night", 3).status_code == 200
    assert ratings(troupe.player, character_id, "paths") == {"Night": 5}
    # On a Path now, so Personal Masquerade is out of reach.
    assert take(troupe.player, character_id, "merits", "Personal Masquerade", 1).status_code == 409

    take(troupe.player, character_id, "merits", "Path of Night", 0)

    assert ratings(troupe.player, character_id, "paths") == {"Humanity": 5}


def test_a_path_comes_only_from_its_merit(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    refused = take(troupe.player, character_id, "paths", "Night", 1)

    assert refused.status_code == 409


def test_infernal_heritage_is_already_on_evil_revelations(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Baali")

    take(troupe.player, character_id, "merits", "Infernal Heritage", 1)

    assert ratings(troupe.player, character_id, "paths") == {"Evil Revelations": 5}


# --- merits that give other traits (#140) -------------------------------------------


def granted(person: Person, character_id: str, category: str) -> dict[str, Any]:
    """Each trait in the category: (rating, granted rating, what grants it)."""
    return {
        t["name"] + (f": {t['detail']}" if t["detail"] else ""): (
            t["rating"],
            t["granted_rating"],
            t["granted_by"],
        )
        for t in sheet(person, character_id)["traits"]
        if t["category"] == category
    }


def merit_points(person: Person, character_id: str) -> int:
    limits = sheet(person, character_id)["limits"]
    return next(item["used"] for item in limits if item["category"] == "merits")


ESP = ["Extrasensory Perceptions"]


def test_extrasensory_perceptions_gives_acute_senses_and_perception_and_takes_them_back(
    troupe: Troupe,
) -> None:
    character_id = new_character(troupe, troupe.player, clan="Nosferatu: Creeps")
    take(troupe.player, character_id, "focus_mentals", "Intelligence")
    before = sheet(troupe.player, character_id)["xp"]["balance"]

    taken = take(troupe.player, character_id, "merits", "Extrasensory Perceptions")

    assert taken.status_code == 200, taken.text
    assert granted(troupe.player, character_id, "merits") == {
        "Acute Sense: Hearing": (1, 1, ESP),
        "Acute Sense: Smell": (1, 1, ESP),
        "Extrasensory Perceptions": (1, 0, []),
    }
    # A second Mental focus, past the usual one per attribute (p. 90).
    assert granted(troupe.player, character_id, "focus_mentals") == {
        "Intelligence": (1, 0, []),
        "Perception": (1, 1, ESP),
    }
    # Only the merit itself is paid for, and counts toward the 7 merit points.
    assert sheet(troupe.player, character_id)["xp"]["balance"] == before - 1
    assert merit_points(troupe.player, character_id) == 1
    # What it gives cannot be sold back on its own.
    assert (
        take(troupe.player, character_id, "merits", "Acute Sense", 0, "Hearing").status_code == 422
    )

    take(troupe.player, character_id, "merits", "Extrasensory Perceptions", 0)

    assert granted(troupe.player, character_id, "merits") == {}
    assert granted(troupe.player, character_id, "focus_mentals") == {
        "Intelligence": (1, 0, []),
    }


def test_extrasensory_perceptions_while_creating(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, finished=False, clan="Nosferatu: Creeps")

    def step(category: str, picks: list[tuple[str, int]]) -> Any:
        return troupe.player.client.put(
            f"/characters/{character_id}/creation/categories/{category}",
            json={"picks": [{"name": n, "rating": r} for n, r in picks]},
        )

    taken = step("merits", [("Extrasensory Perceptions", 1)])
    assert taken.status_code == 200, taken.text
    merits = next(p for p in taken.json()["pools"] if p["category"] == "merits")
    # Only the merit takes points from the budget.
    assert merits["used"] == 1
    assert granted(troupe.player, character_id, "merits")["Acute Sense: Smell"] == (1, 1, ESP)
    # The Mental focus pick is still the player's own, next to the granted one.
    assert step("focus_mentals", [("Wits", 1)]).status_code == 200
    assert granted(troupe.player, character_id, "focus_mentals") == {
        "Perception": (1, 1, ESP),
        "Wits": (1, 0, []),
    }

    assert step("merits", []).status_code == 200

    assert granted(troupe.player, character_id, "merits") == {}
    assert granted(troupe.player, character_id, "focus_mentals") == {"Wits": (1, 0, [])}


def test_a_sense_already_bought_is_refunded_and_another_can_still_be_bought(
    troupe: Troupe,
) -> None:
    character_id = new_character(troupe, troupe.player, clan="Nosferatu: Creeps")
    take(troupe.player, character_id, "merits", "Acute Sense", 1, "Hearing")
    before = sheet(troupe.player, character_id)["xp"]["balance"]

    take(troupe.player, character_id, "merits", "Extrasensory Perceptions")

    # The merit costs 1; the 1 XP paid for Acute Sense: Hearing comes back.
    assert sheet(troupe.player, character_id)["xp"]["balance"] == before - 1 + 1
    assert granted(troupe.player, character_id, "merits")["Acute Sense: Hearing"] == (1, 1, ESP)
    # The granted senses are not copies the player bought: Sight can still be.
    assert take(troupe.player, character_id, "merits", "Acute Sense", 1, "Sight").status_code == 200
    assert take(troupe.player, character_id, "merits", "Acute Sense", 1, "Taste").status_code == 409


def test_a_granted_trait_still_answers_to_the_checks(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Nosferatu: Creeps")
    take(troupe.player, character_id, "flaws", "Hard of Hearing", 2)

    refused = take(troupe.player, character_id, "merits", "Extrasensory Perceptions")

    assert refused.status_code == 409
    assert "Hard of Hearing" in refused.json()["detail"]


def test_a_granted_merit_grants_in_turn(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Assamite")

    taken = take(troupe.player, character_id, "merits", "Web of Knives", 3)

    assert taken.status_code == 200, taken.text
    assert granted(troupe.player, character_id, "merits")["Path of Blood"] == (
        3,
        3,
        ["Web of Knives"],
    )
    # The Path of Blood merit converts Humanity, and Potence becomes in-clan.
    assert ratings(troupe.player, character_id, "paths") == {"Blood": 5}
    assert ratings(troupe.player, character_id, "extra_in_clan_disciplines") == {"Potence": 1}

    take(troupe.player, character_id, "merits", "Web of Knives", 0)

    assert ratings(troupe.player, character_id, "paths") == {"Humanity": 5}
    assert "Path of Blood" not in ratings(troupe.player, character_id, "merits")
    assert ratings(troupe.player, character_id, "extra_in_clan_disciplines") == {}


def test_merits_give_innate_status(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    take(troupe.player, character_id, "merits", "Prestigious Sire", 1)

    assert granted(troupe.player, character_id, "status_traits") == {
        "Loyal": (1, 1, ["Prestigious Sire"])
    }


def test_path_adherent_follows_the_path_its_detail_names(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    unchosen = take(troupe.player, character_id, "merits", "Path Adherent", 2)
    assert unchosen.status_code == 409
    assert "Say which for Path Adherent" in unchosen.json()["detail"]

    assert (
        take(troupe.player, character_id, "merits", "Path Adherent", 2, "Night").status_code == 200
    )
    assert ratings(troupe.player, character_id, "paths") == {"Night": 5}


def test_a_choice_missing_from_before_does_not_hold_up_other_changes(
    troupe: Troupe, session: Session
) -> None:
    character_id = new_character(troupe, troupe.player, clan="Gangrel")
    # Taken before Seasoned Traveler said which skill it gives.
    definition = session.scalars(
        select(TraitDefinition)
        .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
        .where(TraitCategory.key == "merits", TraitDefinition.name == "Seasoned Traveler")
    ).one()
    session.add(
        CharacterTrait(
            character_id=uuid.UUID(character_id),
            trait_definition_id=definition.id,
            rating=1,
            free_rating=1,
        )
    )
    session.flush()

    assert take(troupe.player, character_id, "skills", "Brawl", 1).status_code == 200
