"""Merits that give free traits the player chooses: Ventrue Royalty, Chosen of
Cappadocius, Old Habits, Piece That Remains, Auspicious and Shadows of the Past
(issue #186). The choices change freely until a home troupe accepts the character."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_cart import rating, spend
from tests.test_api_grants import ratings, sheet, take
from tests.test_api_sheets import make_home_troupe_member


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def trait(person: Person, character_id: str, category: str, name: str) -> dict[str, Any]:
    return next(
        t
        for t in sheet(person, character_id)["traits"]
        if t["category"] == category and t["name"] == name
    )


def grant_key(person: Person, character_id: str, merit: str, category: str | None = None) -> str:
    offers = trait(person, character_id, "merits", merit)["free_choices"]
    return next(o["grant"] for o in offers if category in (None, o["category"]))


def pick(grant: str, name: str, amount: int = 0, detail: str = "") -> dict[str, Any]:
    return {"grant": grant, "name": name, "amount": amount, "detail": detail}


def choose(
    person: Person, character_id: str, merit: str, picks: list[dict[str, Any]], detail: str = ""
) -> Any:
    return person.client.put(
        f"/characters/{character_id}/traits/choices",
        json={"category": "merits", "name": merit, "detail": detail, "picks": picks},
    )


def given(
    person: Person, character_id: str, category: str
) -> dict[str, tuple[int, int, list[str]]]:
    """What the category holds that another trait gives: rating, free rating, and from."""
    return {
        t["name"] + (f": {t['detail']}" if t["detail"] else ""): (
            t["rating"],
            t["free_rating"],
            t["granted_by"],
        )
        for t in sheet(person, character_id)["traits"]
        if t["category"] == category and t["granted_rating"]
    }


def problems(person: Person, character_id: str) -> list[str]:
    """What the sheet breaks, leaving out the Generation these tests never place."""
    return [
        p["message"]
        for p in sheet(person, character_id)["problems"]
        if "Generation" not in p["message"]
    ]


def balance(person: Person, character_id: str) -> int:
    return sheet(person, character_id)["xp"]["balance"]


def ventrue_with_royalty(troupe: Troupe) -> str:
    character_id = new_character(troupe, troupe.player, clan="Ventrue")
    assert take(troupe.player, character_id, "merits", "Ventrue Royalty", 2).status_code == 200
    return character_id


# --- Ventrue Royalty: the shared mechanism -----------------------------------------


def test_the_merit_offers_its_choices_before_any_are_made(troupe: Troupe) -> None:
    character_id = ventrue_with_royalty(troupe)

    offered = trait(troupe.player, character_id, "merits", "Ventrue Royalty")["free_choices"]

    assert len(offered) == 1
    assert offered[0]["places"] == [4, 3, 2]
    assert offered[0]["picks"] == []
    assert offered[0]["complete"] is False
    assert offered[0]["locked"] is None
    assert [o["name"] for o in offered[0]["options"]] == [
        "Allies",
        "Contacts",
        "Fame",
        "Haven",
        "Herd",
        "Influences: The Elite",
        "Influences: The Underworld",
        "Resources",
    ]
    assert given(troupe.player, character_id, "backgrounds") == {}


def test_the_add_panel_asks_what_a_merit_would_offer_before_it_is_taken(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Ventrue")

    offered = troupe.player.client.get(
        f"/characters/{character_id}/free-choices",
        params={"category": "merits", "name": "Ventrue Royalty"},
    ).json()
    nothing = troupe.player.client.get(
        f"/characters/{character_id}/free-choices", params={"category": "merits", "name": "Rugged"}
    ).json()

    assert [(o["grant"], o["places"], o["picks"], o["locked"]) for o in offered] == [
        ("merits/Ventrue Royalty/1", [4, 3, 2], [], None)
    ]
    assert nothing == []


def test_royalty_places_4_3_and_2_as_free_dots(troupe: Troupe) -> None:
    character_id = ventrue_with_royalty(troupe)
    grant = grant_key(troupe.player, character_id, "Ventrue Royalty")
    before = balance(troupe.player, character_id)

    placed = choose(
        troupe.player,
        character_id,
        "Ventrue Royalty",
        [pick(grant, "Resources", 4), pick(grant, "Herd", 3), pick(grant, "Contacts", 2)],
    )

    assert placed.status_code == 200, placed.text
    assert given(troupe.player, character_id, "backgrounds") == {
        "Resources": (4, 4, ["Ventrue Royalty"]),
        "Herd": (3, 3, ["Ventrue Royalty"]),
        "Contacts": (2, 2, ["Ventrue Royalty"]),
    }
    assert balance(troupe.player, character_id) == before
    royalty = trait(troupe.player, character_id, "merits", "Ventrue Royalty")
    assert royalty["free_choices"][0]["complete"] is True
    # A free dot is priced from what is free: the fifth dot of Resources costs 5.
    raised = take(troupe.player, character_id, "backgrounds", "Resources", 5)
    assert raised.status_code == 200, raised.text
    assert raised.json()["cost"] == 5


def test_dots_already_bought_are_refunded_and_a_later_choice_gives_them_back(
    troupe: Troupe,
) -> None:
    character_id = new_character(troupe, troupe.player, clan="Ventrue")
    take(troupe.player, character_id, "backgrounds", "Resources", 2)  # a Neonate pays 1 + 2
    take(troupe.player, character_id, "merits", "Ventrue Royalty", 2)
    grant = grant_key(troupe.player, character_id, "Ventrue Royalty")
    before = balance(troupe.player, character_id)

    choose(
        troupe.player,
        character_id,
        "Ventrue Royalty",
        [pick(grant, "Resources", 4), pick(grant, "Herd", 3), pick(grant, "Contacts", 2)],
    )

    assert balance(troupe.player, character_id) == before + 3
    history = troupe.player.client.get(f"/characters/{character_id}/xp").json()
    assert any(e["reason"].startswith("Resources: dots now free") for e in history)

    # Changing the choice takes Resources' free dots away; the refunded dots are not
    # bought again, so it goes to nothing.
    choose(
        troupe.player,
        character_id,
        "Ventrue Royalty",
        [pick(grant, "Herd", 4), pick(grant, "Contacts", 3), pick(grant, "Fame", 2)],
    )

    assert "Resources" not in ratings(troupe.player, character_id, "backgrounds")
    assert balance(troupe.player, character_id) == before + 3


def test_the_choices_change_freely_before_acceptance(troupe: Troupe) -> None:
    character_id = ventrue_with_royalty(troupe)
    grant = grant_key(troupe.player, character_id, "Ventrue Royalty")
    choose(
        troupe.player,
        character_id,
        "Ventrue Royalty",
        [pick(grant, "Resources", 4), pick(grant, "Herd", 3), pick(grant, "Contacts", 2)],
    )

    moved = choose(
        troupe.player,
        character_id,
        "Ventrue Royalty",
        [pick(grant, "Haven", 4), pick(grant, "Herd", 3), pick(grant, "Fame", 2)],
    )

    assert moved.status_code == 200, moved.text
    assert given(troupe.player, character_id, "backgrounds") == {
        "Haven": (4, 4, ["Ventrue Royalty"]),
        "Herd": (3, 3, ["Ventrue Royalty"]),
        "Fame": (2, 2, ["Ventrue Royalty"]),
    }
    assert "Resources" not in ratings(troupe.player, character_id, "backgrounds")
    # Choosing fewer takes the rest away.
    choose(troupe.player, character_id, "Ventrue Royalty", [pick(grant, "Haven", 4)])
    assert given(troupe.player, character_id, "backgrounds") == {
        "Haven": (4, 4, ["Ventrue Royalty"])
    }


def test_the_choices_are_fixed_once_a_home_troupe_accepts_the_character(troupe: Troupe) -> None:
    character_id = ventrue_with_royalty(troupe)
    grant = grant_key(troupe.player, character_id, "Ventrue Royalty")
    placed = [pick(grant, "Resources", 4), pick(grant, "Herd", 3), pick(grant, "Contacts", 2)]
    choose(troupe.player, character_id, "Ventrue Royalty", placed)
    make_home_troupe_member(troupe.session, troupe, character_id)

    refused = choose(
        troupe.player,
        character_id,
        "Ventrue Royalty",
        [pick(grant, "Haven", 4), pick(grant, "Herd", 3), pick(grant, "Fame", 2)],
    )

    assert refused.status_code == 409
    assert "once a home troupe has accepted" in refused.json()["detail"]
    assert given(troupe.player, character_id, "backgrounds")["Resources"][0] == 4
    royalty = trait(troupe.player, character_id, "merits", "Ventrue Royalty")
    assert royalty["free_choices"][0]["locked"] is not None


def test_a_merit_taken_after_acceptance_is_chosen_for_once(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Ventrue")
    make_home_troupe_member(troupe.session, troupe, character_id)
    take(troupe.player, character_id, "merits", "Ventrue Royalty", 2)
    grant = grant_key(troupe.player, character_id, "Ventrue Royalty")

    first = choose(
        troupe.player,
        character_id,
        "Ventrue Royalty",
        [pick(grant, "Resources", 4), pick(grant, "Herd", 3), pick(grant, "Contacts", 2)],
    )

    assert first.status_code == 200, first.text
    again = choose(troupe.player, character_id, "Ventrue Royalty", [pick(grant, "Fame", 4)])
    assert again.status_code == 409


def test_removing_the_merit_removes_its_free_traits(troupe: Troupe) -> None:
    character_id = ventrue_with_royalty(troupe)
    grant = grant_key(troupe.player, character_id, "Ventrue Royalty")
    choose(
        troupe.player,
        character_id,
        "Ventrue Royalty",
        [pick(grant, "Resources", 4), pick(grant, "Herd", 3), pick(grant, "Contacts", 2)],
    )

    take(troupe.player, character_id, "merits", "Ventrue Royalty", 0)

    assert given(troupe.player, character_id, "backgrounds") == {}
    assert "Resources" not in ratings(troupe.player, character_id, "backgrounds")
    # Taking it again starts with nothing chosen.
    take(troupe.player, character_id, "merits", "Ventrue Royalty", 2)
    again = trait(troupe.player, character_id, "merits", "Ventrue Royalty")
    assert again["free_choices"][0]["picks"] == []
    assert given(troupe.player, character_id, "backgrounds") == {}


@pytest.mark.parametrize(
    ("picks", "message"),
    [
        ([("Resources", 4), ("Herd", 4)], "Place 4, 3, 2, each once"),
        ([("Resources", 4), ("Resources", 3)], "Resources is chosen twice"),
        ([("Resources", 4), ("Herd", 3), ("Contacts", 2), ("Fame", 2)], "Place 4, 3, 2"),
        ([("Generation", 4)], "not one of the traits Ventrue Royalty can give"),
    ],
)
def test_royalty_refuses_choices_that_are_not_4_3_and_2_in_its_backgrounds(
    troupe: Troupe, picks: list[tuple[str, int]], message: str
) -> None:
    character_id = ventrue_with_royalty(troupe)
    grant = grant_key(troupe.player, character_id, "Ventrue Royalty")

    refused = choose(
        troupe.player, character_id, "Ventrue Royalty", [pick(grant, n, a) for n, a in picks]
    )

    assert refused.status_code == 422
    assert message in refused.json()["detail"]
    assert given(troupe.player, character_id, "backgrounds") == {}


def test_a_merit_that_gives_nothing_to_choose_refuses(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Ventrue")
    take(troupe.player, character_id, "merits", "Rugged", 3)

    refused = choose(troupe.player, character_id, "Rugged", [])

    assert refused.status_code == 422
    assert "gives no free traits to choose" in refused.json()["detail"]
    assert choose(troupe.player, character_id, "Iron Will", []).status_code == 422


def test_only_the_player_chooses(troupe: Troupe) -> None:
    character_id = ventrue_with_royalty(troupe)
    grant = grant_key(troupe.player, character_id, "Ventrue Royalty")

    refused = choose(troupe.lead, character_id, "Ventrue Royalty", [pick(grant, "Herd", 4)])

    assert refused.status_code in (403, 404)


def test_royalty_can_be_chosen_in_the_cart_with_the_merit(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Ventrue")
    # The grant's key is known from the rules, not yet from the sheet.
    grant = "merits/Ventrue Royalty/1"
    picks = [pick(grant, "Resources", 4), pick(grant, "Herd", 3), pick(grant, "Contacts", 2)]

    response = spend(
        troupe.player,
        character_id,
        rating("merits", "Ventrue Royalty", 2, from_rating=0, picks=picks),
    )

    assert response.status_code == 200, response.text
    assert response.json()["applied"] is True
    assert given(troupe.player, character_id, "backgrounds") == {
        "Resources": (4, 4, ["Ventrue Royalty"]),
        "Herd": (3, 3, ["Ventrue Royalty"]),
        "Contacts": (2, 2, ["Ventrue Royalty"]),
    }

    bad = spend(
        troupe.player,
        character_id,
        rating("merits", "Iron Will", 3, from_rating=0, picks=picks),
    )
    assert bad.json()["applied"] is False


def test_staff_see_the_choices_where_they_accept_a_home_troupe_request(troupe: Troupe) -> None:
    character_id = ventrue_with_royalty(troupe)
    grant = grant_key(troupe.player, character_id, "Ventrue Royalty")
    choose(
        troupe.player,
        character_id,
        "Ventrue Royalty",
        [pick(grant, "Resources", 4), pick(grant, "Herd", 3)],
    )
    request = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    )
    assert request.status_code in (200, 201), request.text

    queue = troupe.lead.client.get(f"/troupes/{troupe.id}/approvals").json()

    asked = next(a for a in queue if a["kind"] == "home_troupe_change")
    assert asked["free_choices"] == [
        {"merit": "Ventrue Royalty", "picks": ["Resources 4", "Herd 3"], "complete": False}
    ]
    # The sheet is locked while the request waits.
    refused = choose(troupe.player, character_id, "Ventrue Royalty", [pick(grant, "Fame", 4)])
    assert refused.status_code == 409


# --- Chosen of Cappadocius ----------------------------------------------------------


def test_chosen_of_cappadocius_gives_two_free_specialisations_in_three_skills(
    troupe: Troupe,
) -> None:
    character_id = new_character(troupe, troupe.player, clan="Cappadocians")
    take(troupe.player, character_id, "merits", "Chosen of Cappadocius", 1)
    lore, languages, academics = (
        grant_key(troupe.player, character_id, "Chosen of Cappadocius", category)
        for category in (
            "lore_specializations",
            "linguistics_specializations",
            "academics_specializations",
        )
    )

    chosen = choose(
        troupe.player,
        character_id,
        "Chosen of Cappadocius",
        [
            pick(lore, "Giovanni"),
            pick(lore, "Custom", detail="Cappadocian history"),
            pick(languages, "Custom", detail="Latin"),
            pick(languages, "Custom", detail="Greek"),
            pick(academics, "Custom", detail="Theology"),
            pick(academics, "Custom", detail="Law"),
        ],
    )

    assert chosen.status_code == 200, chosen.text
    # Six specialisations, with no dots in Lore, Linguistics or Academics to hold them.
    assert given(troupe.player, character_id, "lore_specializations") == {
        "Giovanni": (1, 1, ["Chosen of Cappadocius"]),
        "Custom: Cappadocian history": (1, 1, ["Chosen of Cappadocius"]),
    }
    assert set(given(troupe.player, character_id, "linguistics_specializations")) == {
        "Custom: Latin",
        "Custom: Greek",
    }
    assert set(given(troupe.player, character_id, "academics_specializations")) == {
        "Custom: Theology",
        "Custom: Law",
    }
    assert problems(troupe.player, character_id) == []
    # Free ones do not use up the one per dot the character has bought.
    take(troupe.player, character_id, "skills", "Lore", 1)
    bought = take(troupe.player, character_id, "lore_specializations", "Camarilla", 1)
    assert bought.status_code == 200, bought.text


def test_a_custom_specialisation_needs_its_words_and_two_is_the_most(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Cappadocians")
    take(troupe.player, character_id, "merits", "Chosen of Cappadocius", 1)
    lore = grant_key(troupe.player, character_id, "Chosen of Cappadocius", "lore_specializations")

    nameless = choose(troupe.player, character_id, "Chosen of Cappadocius", [pick(lore, "Custom")])
    three = choose(
        troupe.player,
        character_id,
        "Chosen of Cappadocius",
        [pick(lore, "Anarch"), pick(lore, "Brujah"), pick(lore, "Camarilla")],
    )

    assert nameless.status_code == 422
    assert "Say what the Custom is" in nameless.json()["detail"]
    assert three.status_code == 422
    assert "gives 2, not 3" in three.json()["detail"]


def test_chosen_of_cappadocius_buys_rituals_at_rating_times_one(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Cappadocians")
    ritual = {"category": "rituals", "name": "Abyssal: Adornment of Ashes", "rating": 3}

    def quote() -> int:
        response = troupe.player.client.post(f"/characters/{character_id}/quote", json=ritual)
        return response.json()["cost"]

    assert quote() == 6

    take(troupe.player, character_id, "merits", "Chosen of Cappadocius", 1)

    assert quote() == 3


# --- merits given whole: Old Habits, Piece That Remains, Auspicious, Shadows --------


def test_old_habits_gives_up_to_three_points_of_sabbat_merits_free(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Toreador: Volgirre")
    take(troupe.player, character_id, "merits", "Old Habits", 3)
    grant = grant_key(troupe.player, character_id, "Old Habits")
    before = balance(troupe.player, character_id)

    too_many = choose(
        troupe.player,
        character_id,
        "Old Habits",
        [pick(grant, "Black Hand Membership"), pick(grant, "Executioner"), pick(grant, "Volatile")],
    )
    chosen = choose(
        troupe.player,
        character_id,
        "Old Habits",
        [pick(grant, "Black Hand Membership"), pick(grant, "Executioner")],
    )

    assert too_many.status_code == 422
    assert "up to 3 points; these are 4" in too_many.json()["detail"]
    assert chosen.status_code == 200, chosen.text
    assert given(troupe.player, character_id, "merits") == {
        "Black Hand Membership": (2, 2, ["Old Habits"]),
        "Executioner": (1, 1, ["Old Habits"]),
    }
    assert balance(troupe.player, character_id) == before
    # A free merit's own grants apply: Black Hand Membership gives the Branded status.
    assert "Branded" in ratings(troupe.player, character_id, "status_traits")
    # Merits given are not merits bought: only Old Habits counts against the limit of 7.
    limit = next(
        lim for lim in sheet(troupe.player, character_id)["limits"] if lim["category"] == "merits"
    )
    assert limit["used"] == 3
    # Other Sabbat merits cannot be chosen, nor merits of other kinds.
    other = choose(troupe.player, character_id, "Old Habits", [pick(grant, "Rugged")])
    assert other.status_code == 422

    choose(troupe.player, character_id, "Old Habits", [])

    assert given(troupe.player, character_id, "merits") == {}
    assert "Branded" not in ratings(troupe.player, character_id, "status_traits")


def test_a_sabbat_merit_that_needs_a_field_asks_for_it(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Toreador: Volgirre")
    take(troupe.player, character_id, "merits", "Old Habits", 3)
    grant = grant_key(troupe.player, character_id, "Old Habits")

    bare = choose(
        troupe.player, character_id, "Old Habits", [pick(grant, "Keeper of a Sacred Text")]
    )
    named = choose(
        troupe.player,
        character_id,
        "Old Habits",
        [pick(grant, "Keeper of a Sacred Text", detail="Sabbat Doctrine")],
    )

    assert bare.status_code == 422
    assert named.status_code == 200, named.text
    assert "Keeper of a Sacred Text: Sabbat Doctrine" in given(
        troupe.player, character_id, "merits"
    )


def test_piece_that_remains_gives_one_clan_merit_of_another_clan(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Caitiff")
    take(troupe.player, character_id, "merits", "Piece That Remains", 2)
    grant = grant_key(troupe.player, character_id, "Piece That Remains")
    offered = {
        o["name"]
        for o in trait(troupe.player, character_id, "merits", "Piece That Remains")["free_choices"][
            0
        ]["options"]
    }
    # Another clan's 1- or 2-point merits, bloodline-only ones included; not a
    # bloodline, nor one that gives disciplines or paths.
    assert {"Aura of Command", "Rhythm of Battle", "Angelic Visage"} <= offered
    assert not offered & {
        "Bloodline: Crusader",
        "Seekers of the Hidden",
        "Prodigy of the Flesh",
        "Kupala's Bounty",
        "Necromantic Insight",
        "Web of Knives",
    }
    assert "Born in Shadow" in offered
    assert not offered & {"Walk the Abyss", "Bloodline: Kiasyd"}  # 3 and 4 points
    before = balance(troupe.player, character_id)

    two = choose(
        troupe.player,
        character_id,
        "Piece That Remains",
        [pick(grant, "Aura of Command"), pick(grant, "Angelic Visage")],
    )
    chosen = choose(
        troupe.player, character_id, "Piece That Remains", [pick(grant, "Angelic Visage")]
    )

    assert two.status_code == 422
    assert chosen.status_code == 200, chosen.text
    # It is a Lasombra merit on a Caitiff: given, so the clan requirement is not held to.
    assert given(troupe.player, character_id, "merits") == {
        "Angelic Visage": (1, 1, ["Piece That Remains"])
    }
    assert problems(troupe.player, character_id) == []
    assert balance(troupe.player, character_id) == before
    # And its own grants apply: the Charisma focus.
    assert "Charisma" in ratings(troupe.player, character_id, "focus_socials")
    # Taking the merit away takes the clan merit with it.
    take(troupe.player, character_id, "merits", "Piece That Remains", 0)
    assert given(troupe.player, character_id, "merits") == {}
    assert "Charisma" not in ratings(troupe.player, character_id, "focus_socials")


def test_piece_that_remains_does_not_offer_the_characters_own_clan(troupe: Troupe) -> None:
    # Only a Caitiff buys it, so every clan merit but a Caitiff's is another clan's.
    character_id = new_character(troupe, troupe.player, clan="Caitiff")
    take(troupe.player, character_id, "merits", "Piece That Remains", 2)
    offered = {
        o["name"]
        for o in trait(troupe.player, character_id, "merits", "Piece That Remains")["free_choices"][
            0
        ]["options"]
    }

    assert "Adaptive" not in offered  # a Caitiff merit


def test_auspicious_copies_a_general_merit_of_three_points_or_less(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Caitiff")
    take(troupe.player, character_id, "merits", "Auspicious", 1)
    grant = grant_key(troupe.player, character_id, "Auspicious")
    take(troupe.player, character_id, "merits", "Lucky", 2)

    clan_merit = choose(troupe.player, character_id, "Auspicious", [pick(grant, "Aura of Command")])
    held_already = choose(troupe.player, character_id, "Auspicious", [pick(grant, "Lucky")])
    two = choose(
        troupe.player, character_id, "Auspicious", [pick(grant, "Rugged"), pick(grant, "Iron Will")]
    )
    chosen = choose(troupe.player, character_id, "Auspicious", [pick(grant, "Rugged")])

    assert clan_merit.status_code == 422
    assert held_already.status_code == 422
    assert two.status_code == 422
    assert chosen.status_code == 200, chosen.text
    assert given(troupe.player, character_id, "merits") == {"Rugged": (3, 3, ["Auspicious"])}
    # Rugged's own grants apply: an extra level in each track.
    assert ratings(troupe.player, character_id, "health_levels")["Healthy"] == 4
    # Auspicious (1) and Lucky (2) count towards the limit; the copy does not.
    limit = next(
        lim for lim in sheet(troupe.player, character_id)["limits"] if lim["category"] == "merits"
    )
    assert limit["used"] == 3


def test_auspicious_does_not_offer_what_is_over_three_points(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Caitiff")
    take(troupe.player, character_id, "merits", "Auspicious", 1)
    offered = {
        o["name"]: o["rating"]
        for o in trait(troupe.player, character_id, "merits", "Auspicious")["free_choices"][0][
            "options"
        ]
    }

    assert offered["Rugged"] == 3
    assert max(offered.values()) == 3
    assert "Ventrue Royalty" not in offered


def test_shadows_of_the_past_gives_up_to_three_points_of_lasombra_merits(
    troupe: Troupe,
) -> None:
    character_id = new_character(troupe, troupe.player, finished=False, clan="Baali: Angelis Ater")
    taken = troupe.player.client.put(
        f"/characters/{character_id}/creation/categories/merits",
        json={"picks": [{"name": "Shadows of the Past", "rating": 3}]},
    )
    assert taken.status_code == 200, taken.text
    grant = grant_key(troupe.player, character_id, "Shadows of the Past")

    four = choose(
        troupe.player,
        character_id,
        "Shadows of the Past",
        [
            pick(grant, "Social Elite"),
            pick(grant, "Trusted Confessor"),
            pick(grant, "Angelic Visage"),
        ],
    )
    bloodline = choose(
        troupe.player, character_id, "Shadows of the Past", [pick(grant, "Bloodline: Corsairs")]
    )
    chosen = choose(
        troupe.player,
        character_id,
        "Shadows of the Past",
        [pick(grant, "Social Elite"), pick(grant, "Trusted Confessor")],
    )

    assert four.status_code == 422
    assert bloodline.status_code == 422
    assert chosen.status_code == 200, chosen.text
    # Two clan merits of different value, given: no clash, and the Lasombra requirement
    # is not held to. Social Elite gives Reputation in turn.
    merits = given(troupe.player, character_id, "merits")
    assert merits["Social Elite"] == (1, 1, ["Shadows of the Past"])
    assert merits["Trusted Confessor"] == (2, 2, ["Shadows of the Past"])
    assert merits["Reputation"] == (2, 2, ["Social Elite"])
    assert problems(troupe.player, character_id) == []
