"""A group of Stock NPCs as one (issue #1056): four shovelheads, rating 2. Each
member has the group's stat block and its own health levels and resource, tapped
as "member:<n>/health" and "member:<n>/blood", undone and reset like anyone's.
The book has no rule for groups: each member is a Stock NPC (MET: VTM p. 490),
like the four Blood Brothers with an identical sheet (p. 504). Staff choose which
member carries each item, or leave it with the group."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Troupe, backstory_optional
from tests.test_api_play import send, tap, texts, view
from tests.test_api_play_stock import stock_npc
from tests.test_api_renames import character_log
from tests.test_api_troupe_equipment import DAGGER, RIFLE, given
from tests.test_api_troupe_import import by_name, run, troupe_zip


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def shovelheads(troupe: Troupe, count: int = 4) -> str:
    return stock_npc(troupe, "vampire", 2, stock={"rating": 2, "count": count})


def members(state: dict[str, Any]) -> list[tuple[str, list[str], int]]:
    return [(m["name"], m["marks"], m["blood"]["value"]) for m in state["stock_members"]]


def stock(troupe: Troupe, npc: str) -> dict[str, Any]:
    response = troupe.storyteller.client.get(f"/characters/{npc}/npc/stock")
    assert response.status_code == 200, response.text
    return response.json()


def change(troupe: Troupe, npc: str, **changes: Any) -> Any:
    now = stock(troupe, npc)
    body = {
        "npc_kind": now["npc_kind"],
        "rating": now["rating"],
        "specializations": now["specializations"],
        "notes": now["notes"],
        **changes,
    }
    return troupe.storyteller.client.put(f"/characters/{npc}/npc/stock", json=body)


def carried_by(troupe: Troupe, npc: str, item: str, member: int | None) -> Any:
    return troupe.storyteller.client.put(
        f"/characters/{npc}/npc/stock/items/{item}", json={"member": member}
    )


def test_a_group_has_a_count_and_each_member_its_own_health_and_blood(troupe: Troupe) -> None:
    group = shovelheads(troupe)
    state = view(troupe.storyteller, group)

    assert state["stock"]["count"] == 4
    # One stat block for them all.
    assert state["stock"]["stats"]["pool"] == 4
    assert state["stock"]["stats"]["health"] == 2
    assert members(state) == [
        ("Member 1", [], 10),
        ("Member 2", [], 10),
        ("Member 3", [], 10),
        ("Member 4", [], 10),
    ]
    assert state["stock_members"][0]["blood"] == {"value": 10, "most": 10, "start": 10}
    # The NPCs tab and the roster say how many.
    npcs = troupe.storyteller.client.get(f"/troupes/{troupe.id}/npcs").json()
    assert [(n["stock_rating"], n["stock_count"]) for n in npcs] == [(2, 4)]
    roster = troupe.storyteller.client.get(f"/troupes/{troupe.id}/characters").json()
    assert [(r["stock_rating"], r["stock_count"]) for r in roster if r["kind"] == "npc"] == [(2, 4)]


def test_a_single_stock_npc_has_no_members(troupe: Troupe) -> None:
    wolf = stock_npc(troupe, "werewolf", 3)
    state = view(troupe.storyteller, wolf)

    assert state["stock"]["count"] == 1
    assert state["stock_members"] == []
    # Its own health still takes the damage, and a member tap changes nothing.
    state = send(
        troupe.storyteller,
        wolf,
        tap("health", 1, damage="normal"),
        tap("member:1/health", 1, at=1, damage="normal"),
    )
    assert state["health"]["marks"] == ["normal"]
    assert texts(state)[0] == "Member 1: took 1 normal (not on the sheet now)"


def test_members_take_damage_separately_and_are_out_at_no_health_left(troupe: Troupe) -> None:
    group = shovelheads(troupe)
    blood = tap("member:2/blood", -1, at=1)
    state = send(
        troupe.storyteller,
        group,
        tap("member:1/health", 1, damage="normal"),
        blood,
        tap("member:3/health", 5, at=2, damage="aggravated"),
    )

    # No more damage than its health levels: member 3 is out of the fight (p. 490).
    assert members(state) == [
        ("Member 1", ["normal"], 10),
        ("Member 2", [], 9),
        ("Member 3", ["aggravated", "aggravated"], 10),
        ("Member 4", [], 10),
    ]
    assert texts(state) == [
        "Member 3: took 5 aggravated (0 → 2 marked)",
        "Member 2: Blood 10 → 9",
        "Member 1: took 1 normal (0 → 1 marked)",
    ]

    # Healed, and undone, member by member.
    state = send(
        troupe.storyteller,
        group,
        tap("member:3/health", -1, at=3, damage="aggravated"),
        {
            "id": str(uuid.uuid4()),
            "happened_at": tap(at=4)["happened_at"],
            "kind": "undo",
            "undoes": blood["id"],
        },
    )
    assert members(state)[1:3] == [
        ("Member 2", [], 10),
        ("Member 3", ["aggravated"], 10),
    ]
    assert texts(state)[:2] == [
        "Undid: Member 2: Blood 10 → 9",
        "Member 3: healed 1 aggravated (2 → 1 marked)",
    ]


def test_a_group_has_no_health_or_blood_of_its_own_and_no_fifth_member(troupe: Troupe) -> None:
    group = shovelheads(troupe)
    state = send(
        troupe.storyteller,
        group,
        tap("health", 1, damage="normal"),
        tap("blood", -1, at=1),
        tap("member:5/health", 1, at=2, damage="normal"),
    )

    assert state["health"]["marks"] == []
    assert all(marks == [] and blood == 10 for _, marks, blood in members(state))
    assert texts(state) == [
        "Member 5: took 1 normal (not on the sheet now)",
        "Blood −1 (not on the sheet now)",
        "Health: took 1 normal (not on the sheet now)",
    ]
    # A member's health says what damage it is, as anyone's does.
    response = troupe.storyteller.client.post(
        f"/characters/{group}/play/taps", json={"taps": [tap("member:1/health", 1)]}
    )
    assert response.status_code == 422


def test_reset_restores_every_member(troupe: Troupe) -> None:
    group = shovelheads(troupe)
    send(
        troupe.storyteller,
        group,
        tap("member:1/health", 2, damage="normal"),
        tap("member:4/health", 1, at=1, damage="aggravated"),
        tap("member:4/blood", -3, at=2),
    )
    response = troupe.storyteller.client.post(f"/characters/{group}/play/reset", json={})
    assert response.status_code == 200, response.text
    state = response.json()

    assert state["game"]["number"] == 2
    assert all(marks == [] and blood == 10 for _, marks, blood in members(state))
    games = troupe.storyteller.client.get(f"/characters/{group}/play/games").json()
    assert [g["taps"] for g in games] == [3]


def test_staff_change_the_count_and_a_change_without_it_keeps_it(troupe: Troupe) -> None:
    group = shovelheads(troupe)

    assert change(troupe, group, notes="From the Sabbat's war party").json()["count"] == 4
    send(troupe.storyteller, group, tap("member:3/health", 1, damage="normal"))
    response = change(troupe, group, count=2)
    assert response.status_code == 200, response.text
    assert response.json()["count"] == 2
    # Members past the count are gone, with their taps.
    assert members(view(troupe.storyteller, group)) == [
        ("Member 1", [], 10),
        ("Member 2", [], 10),
    ]
    # Back to one, it is a single Stock NPC again.
    change(troupe, group, count=1)
    assert view(troupe.storyteller, group)["stock_members"] == []

    for wrong in (0, 21):
        assert change(troupe, group, count=wrong).status_code == 422
    made = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/npcs",
        json={"name": "Too many", "npc_form": "stock", "stock": {"rating": 1, "count": 21}},
    )
    assert made.status_code == 422


def test_staff_choose_which_member_carries_each_item(troupe: Troupe) -> None:
    group = shovelheads(troupe)
    rifle = given(troupe, group, **RIFLE)["id"]
    dagger = given(troupe, group, **DAGGER)["id"]

    response = carried_by(troupe, group, rifle, 2)
    assert response.status_code == 200, response.text
    assert response.json()["item_members"] == {rifle: 2}
    # The Play View has both items, and who carries the rifle; the dagger is the group's.
    state = view(troupe.storyteller, group)
    assert {i["name"] for i in state["stock_items"]} == {"Hunting rifle", "Silver Dagger"}
    assert state["stock"]["item_members"] == {rifle: 2}
    assert character_log(troupe.storyteller, group)[0] == (
        "storyteller set who carries Hunting rifle in the Stock NPC group Bites-the-Hand: Member 2."
    )

    assert carried_by(troupe, group, dagger, 4).json()["item_members"] == {rifle: 2, dagger: 4}
    assert carried_by(troupe, group, dagger, None).json()["item_members"] == {rifle: 2}
    # Only a member it has, an item it holds, and staff.
    assert carried_by(troupe, group, dagger, 5).status_code == 422
    assert carried_by(troupe, group, str(uuid.uuid4()), 1).status_code == 404
    by_player = troupe.player.client.put(
        f"/characters/{group}/npc/stock/items/{dagger}", json={"member": 1}
    )
    assert by_player.status_code in (403, 404)

    # A smaller group leaves an item its gone member carried with the group.
    assert change(troupe, group, count=1).json()["item_members"] == {}
    assert change(troupe, group, count=4).json()["item_members"] == {}


def test_a_group_is_not_given_one_full_sheet(troupe: Troupe) -> None:
    group = shovelheads(troupe)

    response = troupe.storyteller.client.post(f"/characters/{group}/npc/sheeted")
    assert response.status_code == 409
    assert "group of 4" in response.json()["detail"]
    change(troupe, group, count=1)
    assert troupe.storyteller.client.post(f"/characters/{group}/npc/sheeted").status_code == 200


def test_a_scene_pins_a_group_with_its_count(troupe: Troupe) -> None:
    group = shovelheads(troupe, 3)
    made = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/scenes", json={"name": "Ambush", "characters": [group]}
    )
    assert made.status_code == 201, made.text

    assert [(p["rating"], p["count"]) for p in made.json()["stock"]] == [(2, 3)]


def test_a_group_comes_into_another_troupe_with_its_count(troupe: Troupe, session: Session) -> None:
    shovelheads(troupe)
    made = troupe.custodian.client.post(
        "/troupes", json={"name": "Court of Echoes", "lead_handle": troupe.storyteller.handle}
    )
    assert made.status_code == 201, made.text
    other = made.json()["id"]
    backstory_optional(session, other)

    done = run(troupe.storyteller, other, troupe_zip(troupe))
    assert done.status_code == 201, done.text
    copy = by_name(done.json())["Bites-the-Hand"]["character_id"]

    assert stock(troupe, copy)["count"] == 4
