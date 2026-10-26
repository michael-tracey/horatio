"""The Disciplines step's budget and choices (#192): Thin Blooded's smaller budget, Inept,
the extra in-clan discipline that starts without a free dot, and Morality starting at 4
for a Path merit bought in creation."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe
from tests.test_api_creation import FULL_BUILD, creating, creation, pick, sheet
from tests.test_api_creation_rules import caitiff_build, give_xp, take


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def finish(person: Person, character_id: str) -> Any:
    return person.client.post(f"/characters/{character_id}/creation/complete")


def save_disciplines(person: Person, character_id: str, picks: list[tuple[str, int]]) -> Any:
    return person.client.put(
        f"/characters/{character_id}/creation/categories/disciplines",
        json={"picks": [{"name": n, "rating": r} for n, r in picks]},
    )


def disciplines(person: Person, character_id: str) -> list[dict[str, Any]]:
    return [p for p in creation(person, character_id)["pools"] if p["category"] == "disciplines"]


# --- Thin Blooded -------------------------------------------------------------------


def test_thin_blooded_taken_after_the_disciplines_keeps_the_dot_at_2_and_names_the_flaw(
    troupe: Troupe,
) -> None:
    character_id = caitiff_build(troupe, thin_blooded=False)
    player = troupe.player
    for name, rating in (("Celerity", 2), ("Auspex", 1), ("Potence", 1)):
        assert pick(player, character_id, "disciplines", name, rating).status_code == 200

    assert pick(player, character_id, "flaws", "Thin Blooded", 2).status_code == 200

    pools = disciplines(player, character_id)
    # The new budget: one dot in each of two. The dot at 2 has no pool now, and is shown.
    assert [(p["rating"], p["allowed"], p["remaining"]) for p in pools] == [(2, 0, -1), (1, 2, 0)]
    stray = pools[0]
    assert stray["because"] == [{"category": "flaws", "name": "Thin Blooded"}]
    assert [t["name"] for t in stray["traits"]] == ["Celerity"]
    # Finishing refuses it, and the step still saves it as it was.
    refused = finish(player, character_id)
    assert refused.status_code == 409
    assert "Celerity at 2" in refused.json()["detail"]
    assert (
        save_disciplines(player, character_id, [("Celerity", 2), ("Auspex", 1)]).status_code == 200
    )
    assert [t["name"] for t in disciplines(player, character_id)[0]["traits"]] == ["Celerity"]
    # Nothing new goes where the pool is gone.
    assert (
        save_disciplines(player, character_id, [("Potence", 2), ("Auspex", 1)]).status_code == 422
    )

    assert (
        save_disciplines(player, character_id, [("Celerity", 1), ("Auspex", 1)]).status_code == 200
    )

    assert [(p["rating"], p["remaining"]) for p in disciplines(player, character_id)] == [(1, 0)]
    assert finish(player, character_id).status_code == 200


# --- Inept ----------------------------------------------------------------------------


def test_inept_takes_the_free_dot_from_the_discipline_it_names(troupe: Troupe) -> None:
    character_id = creating(troupe)
    player = troupe.player
    inept = player.client.put(
        f"/characters/{character_id}/creation/picks",
        json={"category": "flaws", "name": "Inept", "rating": 3, "detail": "Presence"},
    )
    assert inept.status_code == 200, inept.text

    pools = disciplines(player, character_id)
    assert pools[0]["without_dot"] == [
        {"name": "Presence", "because": [{"category": "flaws", "name": "Inept"}]}
    ]
    # Priced out-of-clan, so not among the in-clan disciplines, and no starting pick.
    assert pools[0]["options"] == ["Celerity", "Potence"]
    refused = pick(player, character_id, "disciplines", "Presence", 1)
    assert refused.status_code == 422
    assert "Inept" in refused.json()["detail"]
    assert save_disciplines(player, character_id, [("Presence", 2)]).status_code == 422
    for name, rating in (("Celerity", 2), ("Potence", 1)):
        assert pick(player, character_id, "disciplines", name, rating).status_code == 200


def test_inept_leaves_one_pick_at_1_fewer_and_the_build_finishes(troupe: Troupe) -> None:
    character_id = creating(troupe)
    player = troupe.player
    for category, name, rating in FULL_BUILD:
        if category != "disciplines":
            assert pick(player, character_id, category, name, rating).status_code == 200
    assert (
        player.client.put(
            f"/characters/{character_id}/creation/picks",
            json={"category": "flaws", "name": "Inept", "rating": 3, "detail": "Presence"},
        ).status_code
        == 200
    )

    # Brujah's other two get the dots: one at 2 and one at 1.
    assert [(p["rating"], p["allowed"]) for p in disciplines(player, character_id)] == [
        (2, 1),
        (1, 1),
    ]
    assert pick(player, character_id, "disciplines", "Celerity", 2).status_code == 200
    assert finish(player, character_id).status_code == 409
    assert pick(player, character_id, "disciplines", "Potence", 1).status_code == 200

    assert finish(player, character_id).status_code == 200


def test_inept_taken_after_the_disciplines_keeps_and_marks_the_dots(troupe: Troupe) -> None:
    character_id = creating(troupe)
    player = troupe.player
    for name, rating in (("Celerity", 2), ("Potence", 1), ("Presence", 1)):
        assert pick(player, character_id, "disciplines", name, rating).status_code == 200

    inept = player.client.put(
        f"/characters/{character_id}/creation/picks",
        json={"category": "flaws", "name": "Inept", "rating": 3, "detail": "Presence"},
    )
    assert inept.status_code == 200, inept.text

    at_one = disciplines(player, character_id)[1]
    # One pick fewer at 1 than there are now, and the dot on Presence is marked, not dropped.
    assert (at_one["allowed"], at_one["remaining"]) == (1, -1)
    assert at_one["because"] == [{"category": "flaws", "name": "Inept"}]
    kept = next(t for t in at_one["traits"] if t["name"] == "Presence")
    assert kept["fits"] is False
    assert kept["because"] == [{"category": "flaws", "name": "Inept"}]
    assert finish(player, character_id).status_code == 409

    assert (
        save_disciplines(player, character_id, [("Celerity", 2), ("Potence", 1)]).status_code == 200
    )
    assert [t["name"] for p in disciplines(player, character_id) for t in p["traits"]] == [
        "Celerity",
        "Potence",
    ]


def first_dot_costs(person: Person, character_id: str, discipline: str) -> int | None:
    cart = person.client.post(
        f"/characters/{character_id}/cart",
        json={
            "dry_run": True,
            "changes": [
                {"kind": "set", "category": "disciplines", "name": discipline, "rating": 1}
            ],
        },
    )
    assert cart.status_code == 200, cart.text
    return cart.json()["lines"][0]["cost"]


def test_inept_discipline_costs_the_out_of_clan_rate(troupe: Troupe) -> None:
    player = troupe.player
    inept, plain = creating(troupe), creating(troupe)
    for character_id in (inept, plain):
        for category, name, rating in FULL_BUILD:
            if category != "disciplines":
                assert pick(player, character_id, category, name, rating).status_code == 200
    assert (
        player.client.put(
            f"/characters/{inept}/creation/picks",
            json={"category": "flaws", "name": "Inept", "rating": 3, "detail": "Presence"},
        ).status_code
        == 200
    )
    for name, rating in (("Celerity", 2), ("Potence", 1)):
        assert pick(player, inept, "disciplines", name, rating).status_code == 200
    for name, rating in (("Celerity", 2), ("Potence", 1), ("Presence", 1)):
        assert pick(player, plain, "disciplines", name, rating).status_code == 200
    assert finish(player, inept).status_code == 200
    # Neither has bought a dot of Dementation, and the plain Brujah has a dot of Presence
    # already; compare a dot of Auspex (out-of-clan for both) with Inept's Presence.
    assert first_dot_costs(player, inept, "Presence") == first_dot_costs(player, inept, "Auspex")
    assert first_dot_costs(player, inept, "Celerity") != first_dot_costs(player, inept, "Auspex")


def test_inept_needs_an_in_clan_discipline_to_finish(troupe: Troupe) -> None:
    character_id = creating(troupe)
    player = troupe.player
    for category, name, rating in FULL_BUILD:
        if name != "Presence":
            assert pick(player, character_id, category, name, rating).status_code == 200
    # Auspex is not Brujah's: allowed to be named, but finishing wants an in-clan one.
    assert (
        player.client.put(
            f"/characters/{character_id}/creation/picks",
            json={"category": "flaws", "name": "Inept", "rating": 3, "detail": "Auspex"},
        ).status_code
        == 200
    )

    refused = finish(player, character_id)

    assert refused.status_code == 409
    assert "Inept: choose one of your in-clan disciplines" in refused.json()["detail"]
    # The Merits step saves it again naming an in-clan one, and the build finishes.
    renamed = player.client.put(
        f"/characters/{character_id}/creation/categories/flaws",
        json={"picks": [{"name": "Inept", "rating": 3, "detail": "Presence"}]},
    )
    assert renamed.status_code == 200, renamed.text
    assert finish(player, character_id).status_code == 200


def test_inept_without_a_discipline_is_refused(troupe: Troupe) -> None:
    character_id = creating(troupe)

    refused = pick(troupe.player, character_id, "flaws", "Inept", 3)

    assert refused.status_code == 409
    assert "Say which for Inept" in refused.json()["detail"]


# --- the fourth in-clan discipline ----------------------------------------------------


def test_a_fourth_in_clan_discipline_from_a_merit_starts_without_a_free_dot(
    troupe: Troupe,
) -> None:
    character_id = creating(troupe)
    player = troupe.player
    assert (
        pick(player, character_id, "merits", "Additional Common Discipline", 4).status_code == 200
    )
    assert take(player, character_id, "extra_in_clan_disciplines", "Auspex").status_code == 200

    pools = disciplines(player, character_id)

    # In-clan, so it is among the options and costs in-clan XP, but it takes no pick.
    assert pools[0]["options"] == ["Auspex", "Celerity", "Potence", "Presence"]
    assert pools[0]["without_dot"] == [
        {
            "name": "Auspex",
            "because": [{"category": "merits", "name": "Additional Common Discipline"}],
        }
    ]
    refused = pick(player, character_id, "disciplines", "Auspex", 1)
    assert refused.status_code == 422
    assert "Additional Common Discipline" in refused.json()["detail"]
    for name, rating in (("Celerity", 2), ("Potence", 1), ("Presence", 1)):
        assert pick(player, character_id, "disciplines", name, rating).status_code == 200


def test_a_caitiff_with_a_fourth_discipline_still_has_dots_for_three(troupe: Troupe) -> None:
    character_id = creating(troupe, clan="Caitiff")
    player = troupe.player
    assert (
        pick(player, character_id, "merits", "Additional Common Discipline", 4).status_code == 200
    )
    for name in ("Auspex", "Celerity", "Potence", "Dominate"):
        assert take(player, character_id, "extra_in_clan_disciplines", name).status_code == 200

    assert disciplines(player, character_id)[0]["without_dot"] == []
    for name, rating in (("Dominate", 2), ("Auspex", 1), ("Potence", 1)):
        assert pick(player, character_id, "disciplines", name, rating).status_code == 200


# --- Morality -------------------------------------------------------------------------


def morality(person: Person, character_id: str) -> tuple[str, int, int]:
    found = next(t for t in sheet(person, character_id)["traits"] if t["category"] == "paths")
    return found["name"], found["rating"], found["free_rating"]


def test_a_path_merit_bought_in_creation_starts_the_path_at_4(troupe: Troupe) -> None:
    character_id = creating(troupe)
    player = troupe.player
    assert morality(player, character_id) == ("Humanity", 5, 5)

    assert pick(player, character_id, "merits", "Path of Caine", 3).status_code == 200

    assert morality(player, character_id) == ("Caine", 4, 4)
    assert creation(player, character_id)["path_starts"] == [
        {
            "category": "paths",
            "name": "Caine",
            "rating": 4,
            "because": [{"category": "merits", "name": "Path of Caine"}],
            "page": "306",
        }
    ]
    # Dropping the merit puts Humanity back at its usual 5.
    removed = player.client.post(
        f"/characters/{character_id}/creation/picks/remove",
        json={"category": "merits", "name": "Path of Caine"},
    )
    assert removed.status_code == 200
    assert morality(player, character_id) == ("Humanity", 5, 5)
    assert creation(player, character_id)["path_starts"] == []


def test_a_path_merit_bought_after_creation_keeps_the_morality_it_has(troupe: Troupe) -> None:
    character_id = creating(troupe)
    player = troupe.player
    for category, name, rating in FULL_BUILD:
        assert pick(player, character_id, category, name, rating).status_code == 200
    assert finish(player, character_id).status_code == 200
    give_xp(troupe, character_id, 20)

    bought = take(player, character_id, "merits", "Path of Caine", 3)

    assert bought.status_code == 200, bought.text
    assert morality(player, character_id) == ("Caine", 5, 5)
    assert creation(player, character_id)["path_starts"] == []
