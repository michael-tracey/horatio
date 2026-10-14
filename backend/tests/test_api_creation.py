"""Character creation: starting traits, creation picks, and reconciling starting dots."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.rules.model import CreationRuleData
from horatio.rules.store import set_house_creation_rules
from tests.api_helpers import Person, Troupe, new_character

# One way to place every Vampire creation pick, as the generic rules give them.
FULL_BUILD = [
    ("attributes", "Physical", 7),
    ("attributes", "Social", 5),
    ("attributes", "Mental", 3),
    ("focus_physicals", "Strength", 1),
    ("focus_mentals", "Wits", 1),
    ("focus_socials", "Charisma", 1),
    ("skills", "Brawl", 4),
    ("skills", "Dodge", 3),
    ("skills", "Athletics", 3),
    ("skills", "Awareness", 2),
    ("skills", "Empathy", 2),
    ("skills", "Firearms", 2),
    ("skills", "Investigation", 1),
    ("skills", "Leadership", 1),
    ("skills", "Medicine", 1),
    ("skills", "Melee", 1),
    ("backgrounds", "Fame", 3),
    ("backgrounds", "Herd", 2),
    ("backgrounds", "Generation", 1),
    ("disciplines", "Celerity", 2),
    ("disciplines", "Potence", 1),
    ("disciplines", "Presence", 1),
]


# Balances here are about settlements and purchases, not banking creation XP.
pytestmark = pytest.mark.usefixtures("without_bank")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def creating(troupe: Troupe, clan: str = "Brujah") -> str:
    """A Brujah in character creation. Brujah's in-clan disciplines are Celerity,
    Potence and Presence."""
    character_id = new_character(troupe, troupe.player, finished=False)
    troupe.player.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "clan", "name": clan, "rating": None},
    )
    return character_id


def pick(person: Person, character_id: str, category: str, name: str, rating: int = 1) -> Any:
    return person.client.put(
        f"/characters/{character_id}/creation/picks",
        json={"category": category, "name": name, "rating": rating},
    )


def creation(person: Person, character_id: str) -> dict[str, Any]:
    return person.client.get(f"/characters/{character_id}/creation").json()


def pool(state: dict[str, Any], category: str, rating: int) -> dict[str, Any]:
    return next(p for p in state["pools"] if p["category"] == category and p["rating"] == rating)


def sheet(person: Person, character_id: str) -> dict[str, Any]:
    return person.client.get(f"/characters/{character_id}/sheet").json()


def trait(person: Person, character_id: str, name: str) -> dict[str, Any]:
    return next(t for t in sheet(person, character_id)["traits"] if t["name"] == name)


def build(person: Person, character_id: str) -> None:
    for category, name, rating in FULL_BUILD:
        response = pick(person, character_id, category, name, rating)
        assert response.status_code == 200, (name, response.text)
    response = person.client.post(f"/characters/{character_id}/creation/complete")
    assert response.status_code == 200, response.text


# --- starting traits and picks -----------------------------------------------------------


def test_new_characters_start_with_their_starting_traits_free(troupe: Troupe) -> None:
    character_id = creating(troupe)

    traits = {
        t["name"]: (t["rating"], t["free_rating"])
        for t in sheet(troupe.player, character_id)["traits"]
    }

    assert traits == {
        "Brujah": (None, 0),
        "Humanity": (5, 5),
        "Healthy": (3, 3),
        "Injured": (3, 3),
        "Incapacitated": (3, 3),
        "Willpower": (6, 6),
    }
    assert sheet(troupe.player, character_id)["xp"]["balance"] == 30


def test_the_creation_pools(troupe: Troupe) -> None:
    state = creation(troupe.player, creating(troupe))

    assert state["complete"] is False
    assert [(p["category"], p["rating"], p["kind"], p["allowed"]) for p in state["pools"]] == [
        ("attributes", 7, "picks", 1),
        ("attributes", 5, "picks", 1),
        ("attributes", 3, "picks", 1),
        ("backgrounds", 3, "picks", 1),
        ("backgrounds", 2, "picks", 1),
        ("backgrounds", 1, "picks", 1),
        ("disciplines", 2, "picks", 1),
        ("disciplines", 1, "picks", 2),
        ("flaws", 0, "points", 7),
        ("focus_mentals", 1, "picks", 1),
        ("focus_physicals", 1, "picks", 1),
        ("focus_socials", 1, "picks", 1),
        ("merits", 0, "points", 7),
        ("skills", 4, "picks", 1),
        ("skills", 3, "picks", 2),
        ("skills", 2, "picks", 3),
        ("skills", 1, "picks", 4),
    ]


def test_a_pick_gives_free_dots(troupe: Troupe) -> None:
    character_id = creating(troupe)

    state = pick(troupe.player, character_id, "attributes", "Physical", 7).json()

    assert pool(state, "attributes", 7)["traits"] == [{"name": "Physical", "detail": "", "pick": 7}]
    assert pool(state, "attributes", 7)["remaining"] == 0
    physical = trait(troupe.player, character_id, "Physical")
    assert (physical["rating"], physical["free_rating"]) == (7, 7)
    assert sheet(troupe.player, character_id)["xp"]["balance"] == 30


def test_picks_are_limited_to_what_the_rules_give(troupe: Troupe) -> None:
    character_id = creating(troupe)
    pick(troupe.player, character_id, "attributes", "Physical", 7)

    assert pick(troupe.player, character_id, "attributes", "Social", 7).status_code == 409
    assert pick(troupe.player, character_id, "attributes", "Social", 6).status_code == 422
    assert pick(troupe.player, character_id, "clan", "Brujah", 1).status_code == 422


def test_merits_and_flaws_come_from_a_points_budget(troupe: Troupe) -> None:
    character_id = creating(troupe)

    state = pick(troupe.player, character_id, "merits", "Rugged").json()  # 3 points
    pick(troupe.player, character_id, "merits", "Abyssal Horror")  # 3 points
    over = pick(troupe.player, character_id, "merits", "Additional Common Discipline")  # 4 points

    assert pool(state, "merits", 0)["used"] == 3
    assert over.status_code == 409
    assert pool(creation(troupe.player, character_id), "merits", 0)["remaining"] == 1


def test_taking_a_pick_back(troupe: Troupe) -> None:
    character_id = creating(troupe)
    pick(troupe.player, character_id, "skills", "Brawl", 4)

    state = troupe.player.client.post(
        f"/characters/{character_id}/creation/picks/remove",
        json={"category": "skills", "name": "Brawl"},
    ).json()

    assert pool(state, "skills", 4)["remaining"] == 1
    assert "Brawl" not in [t["name"] for t in sheet(troupe.player, character_id)["traits"]]


def test_finishing_creation_needs_every_pick_placed(troupe: Troupe) -> None:
    character_id = creating(troupe)
    pick(troupe.player, character_id, "attributes", "Physical", 7)

    early = troupe.player.client.post(f"/characters/{character_id}/creation/complete")
    assert early.status_code == 409
    assert "skills at 4" in early.json()["detail"]

    for category, name, rating in FULL_BUILD[1:]:
        pick(troupe.player, character_id, category, name, rating)
    done = troupe.player.client.post(f"/characters/{character_id}/creation/complete")

    assert done.json()["complete"] is True
    assert troupe.player.client.get(f"/characters/{character_id}").json()["creation_complete"]
    # Afterwards dots come from experience.
    assert pick(troupe.player, character_id, "merits", "Acute Sense").status_code == 409


def test_a_home_troupe_waits_for_creation_to_finish(troupe: Troupe) -> None:
    character_id = creating(troupe)

    response = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    )

    assert response.status_code == 409
    assert "Finish character creation" in response.json()["detail"]


def test_only_the_player_places_picks(troupe: Troupe) -> None:
    character_id = creating(troupe)

    assert pick(troupe.stranger, character_id, "attributes", "Physical", 7).status_code == 404


# --- reconciling starting dots --------------------------------------------------------------


def house_creation(troupe: Troupe, category: str, rules: list[tuple[int, int]]) -> None:
    set_house_creation_rules(
        troupe.session,
        uuid.UUID(troupe.id),
        "vampire",
        category,
        [CreationRuleData(category=category, rating=r, picks=n) for r, n in rules],
    )


def preview(troupe: Troupe, character_id: str) -> list[dict[str, Any]]:
    response = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe/preview", json={"troupe_id": troupe.id}
    )
    assert response.status_code == 200, response.text
    return response.json()


def approve_home(troupe: Troupe, character_id: str, settlements: list[dict[str, str]]) -> None:
    requested = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe",
        json={"troupe_id": troupe.id, "settlements": settlements},
    )
    assert requested.status_code == 201, requested.text
    approved = troupe.lead.client.post(f"/approvals/{requested.json()['id']}/approve", json={})
    assert approved.status_code == 200, approved.text


def test_same_rules_nothing_to_reconcile(troupe: Troupe) -> None:
    character_id = creating(troupe)
    build(troupe.player, character_id)

    assert preview(troupe, character_id) == []


def test_fewer_starting_dots_must_be_paid_for_or_removed(troupe: Troupe) -> None:
    character_id = creating(troupe)
    build(troupe.player, character_id)
    # This troupe gives no skill at 4.
    house_creation(troupe, "skills", [(3, 2), (2, 3), (1, 4)])

    differences = preview(troupe, character_id)

    assert [
        (d["name"], d["difference"], d["new_cost"], d["allowed_settlements"]) for d in differences
    ] == [
        # Brawl's four free dots, bought at generation 1 skill prices: 1 + 2 + 3 + 4.
        ("Brawl", "creation_differs", 10, ["pay_for_dots", "remove_dots", "keep_price"])
    ]
    unsettled = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe",
        json={
            "troupe_id": troupe.id,
            "settlements": [
                {
                    "category": "skills",
                    "name": "Brawl",
                    "difference": "creation_differs",
                    "settlement": "keep_price",
                }
            ],
        },
    )
    assert unsettled.status_code == 422
    assert "fewer starting dots" in unsettled.json()["detail"]

    approve_home(
        troupe,
        character_id,
        [
            {
                "category": "skills",
                "name": "Brawl",
                "difference": "creation_differs",
                "settlement": "pay_for_dots",
            }
        ],
    )

    brawl = trait(troupe.player, character_id, "Brawl")
    assert (brawl["rating"], brawl["free_rating"]) == (4, 0)
    assert sheet(troupe.player, character_id)["xp"]["balance"] == 20


def test_removing_a_pick_the_troupe_does_not_give(troupe: Troupe) -> None:
    character_id = creating(troupe)
    build(troupe.player, character_id)
    house_creation(troupe, "skills", [(3, 2), (2, 3), (1, 4)])

    approve_home(
        troupe,
        character_id,
        [
            {
                "category": "skills",
                "name": "Brawl",
                "difference": "creation_differs",
                "settlement": "remove_dots",
            }
        ],
    )

    assert "Brawl" not in [t["name"] for t in sheet(troupe.player, character_id)["traits"]]
    assert sheet(troupe.player, character_id)["xp"]["balance"] == 30


def test_more_starting_dots_reopen_creation_to_place_them(troupe: Troupe) -> None:
    character_id = creating(troupe)
    build(troupe.player, character_id)
    # This troupe gives a fifth skill at 1.
    house_creation(troupe, "skills", [(4, 1), (3, 2), (2, 3), (1, 5)])

    differences = preview(troupe, character_id)
    assert [(d["name"], d["allowed_settlements"]) for d in differences] == [
        ("1 more skills pick at 1", ["add_free_dots", "keep_price"])
    ]
    approve_home(
        troupe,
        character_id,
        [
            {
                "category": "skills",
                "name": "1 more skills pick at 1",
                "difference": "creation_differs",
                "settlement": "add_free_dots",
            }
        ],
    )

    reopened = creation(troupe.player, character_id)
    assert reopened["complete"] is False
    assert pool(reopened, "skills", 1)["remaining"] == 1
    pick(troupe.player, character_id, "skills", "Stealth", 1)
    assert (
        troupe.player.client.post(f"/characters/{character_id}/creation/complete").status_code
        == 200
    )
    # The new free dot is on the sheet straight away; nothing needs approving.
    after = sheet(troupe.player, character_id)
    assert ("Stealth", 1) in [(t["name"], t["rating"]) for t in after["traits"]]
    assert after["pending_approvals"] == []


def test_staff_see_and_can_change_starting_dot_settlements(troupe: Troupe) -> None:
    character_id = creating(troupe)
    build(troupe.player, character_id)
    house_creation(troupe, "skills", [(3, 2), (2, 3), (1, 4)])
    requested = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe",
        json={
            "troupe_id": troupe.id,
            "settlements": [
                {
                    "category": "skills",
                    "name": "Brawl",
                    "difference": "creation_differs",
                    "settlement": "remove_dots",
                }
            ],
        },
    )
    item = troupe.lead.client.get(f"/troupes/{troupe.id}/approvals").json()[0]["reconciliation"][0]
    assert (item["trait"], item["difference"], item["allowed_settlements"]) == (
        "Brawl",
        "creation_differs",
        ["pay_for_dots", "remove_dots", "keep_price"],
    )

    # The storyteller lets the character keep its free Brawl.
    troupe.lead.client.post(
        f"/approvals/{requested.json()['id']}/approve",
        json={"settlements": [{"item_id": item["id"], "settlement": "keep_price"}]},
    )

    brawl = trait(troupe.player, character_id, "Brawl")
    assert (brawl["rating"], brawl["free_rating"]) == (4, 4)


# --- whole steps at once (the wizard) ---------------------------------------------------------


def set_step(person: Person, character_id: str, category: str, picks: list[tuple[str, int]]) -> Any:
    return person.client.put(
        f"/characters/{character_id}/creation/categories/{category}",
        json={"picks": [{"name": n, "rating": r} for n, r in picks]},
    )


def test_a_whole_step_is_saved_in_one_go(troupe: Troupe) -> None:
    character_id = creating(troupe)

    state = set_step(
        troupe.player, character_id, "attributes", [("Physical", 7), ("Social", 5), ("Mental", 3)]
    ).json()

    assert [
        (p["rating"], p["traits"]) for p in state["pools"] if p["category"] == "attributes"
    ] == [
        (7, [{"name": "Physical", "detail": "", "pick": 7}]),
        (5, [{"name": "Social", "detail": "", "pick": 5}]),
        (3, [{"name": "Mental", "detail": "", "pick": 3}]),
    ]


def test_saving_a_step_again_replaces_it(troupe: Troupe) -> None:
    character_id = creating(troupe)
    set_step(
        troupe.player, character_id, "attributes", [("Physical", 7), ("Social", 5), ("Mental", 3)]
    )

    # Swap Physical and Mental.
    set_step(
        troupe.player, character_id, "attributes", [("Mental", 7), ("Social", 5), ("Physical", 3)]
    )

    assert trait(troupe.player, character_id, "Mental")["rating"] == 7
    assert trait(troupe.player, character_id, "Physical")["rating"] == 3
    # Half a step is fine to save; it just is not finished.
    set_step(troupe.player, character_id, "attributes", [("Mental", 7)])
    assert "Physical" not in [t["name"] for t in sheet(troupe.player, character_id)["traits"]]


def test_a_step_must_fit_the_pools(troupe: Troupe) -> None:
    character_id = creating(troupe)

    two_sevens = set_step(
        troupe.player, character_id, "attributes", [("Physical", 7), ("Social", 7)]
    )
    no_sixes = set_step(troupe.player, character_id, "attributes", [("Physical", 6)])
    too_many_points = set_step(
        troupe.player,
        character_id,
        "merits",
        [("Abyssal Horror", 1), ("Additional Uncommon Discipline", 1)],
    )

    assert two_sevens.status_code == 409
    assert no_sixes.status_code == 422
    assert too_many_points.status_code == 409  # 3 + 5 points of 7


def test_merits_in_a_step_use_their_point_value(troupe: Troupe) -> None:
    character_id = creating(troupe)

    state = set_step(
        troupe.player, character_id, "merits", [("Rugged", 1), ("Acute Sense", 1)]
    ).json()

    assert pool(state, "merits", 0)["used"] == 4  # 3 + 1


def test_starting_disciplines_must_be_in_clan(troupe: Troupe) -> None:
    character_id = creating(troupe)

    out_of_clan = pick(troupe.player, character_id, "disciplines", "Dominate", 2)
    in_clan = pick(troupe.player, character_id, "disciplines", "Celerity", 2)

    assert out_of_clan.status_code == 422
    assert "not in-clan" in out_of_clan.json()["detail"]
    assert in_clan.status_code == 200
    assert pool(in_clan.json(), "disciplines", 2)["restriction"] == "in_clan"


def test_without_a_clan_no_discipline_is_in_clan(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, finished=False)

    response = pick(troupe.player, character_id, "disciplines", "Celerity", 2)

    assert response.status_code == 422
    assert "choose the clan first" in response.json()["detail"]


def test_a_whole_step_is_checked_for_in_clan_disciplines(troupe: Troupe) -> None:
    character_id = creating(troupe)

    response = set_step(
        troupe.player, character_id, "disciplines", [("Celerity", 2), ("Dominate", 1)]
    )

    assert response.status_code == 422


def test_changing_clan_after_picking_blocks_finishing(troupe: Troupe) -> None:
    character_id = creating(troupe)
    for category, name, rating in FULL_BUILD:
        pick(troupe.player, character_id, category, name, rating)
    troupe.player.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "clan", "name": "Tremere", "rating": None},
    )

    response = troupe.player.client.post(f"/characters/{character_id}/creation/complete")

    assert response.status_code == 409
    assert "Celerity" in response.json()["detail"]


def test_experience_waits_until_creation_is_finished(troupe: Troupe) -> None:
    """A PC is built through character creation; buying comes after."""
    character_id = creating(troupe)

    early = troupe.player.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "skills", "name": "Brawl", "rating": 1},
    )
    assert early.status_code == 409
    assert "creation wizard" in early.json()["detail"]

    build(troupe.player, character_id)
    later = troupe.player.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "skills", "name": "Brawl", "rating": 5},
    )
    assert later.status_code == 200
    assert later.json()["cost"] == 5  # only the fifth dot: four are free from the pick
