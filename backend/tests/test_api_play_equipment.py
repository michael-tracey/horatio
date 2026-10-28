"""Equipment in the Pools drawer (issue #306): items equipped at a game by Play View
taps, within the book's limits (two hands of weapons, one piece of protective gear,
one piece of miscellaneous gear's bonus), kept from game to game, with each quality's
pool effect a modifier while its item is equipped; no longer equipped once it leaves
the character."""

import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import EquipmentEvent
from tests.api_helpers import Person, Troupe
from tests.test_api_downtimes import member_character
from tests.test_api_equipment_passing import give_to
from tests.test_api_play import send, tap, texts, view
from tests.test_api_renames import summaries
from tests.test_api_troupe_equipment import DAGGER, change, give, given, path

KATANA = {
    "name": "Katana",
    "kind": "melee",
    "grade": "standard",
    "qualities": [{"name": "Accurate"}, {"name": "Brutal"}],
}
VEST = {
    "name": "Flak Vest",
    "kind": "protective",
    "grade": "standard",
    "qualities": [{"name": "Ballistic"}, {"name": "Chest Plate"}],
}
MAIL = {
    "name": "Chain Mail",
    "kind": "protective",
    "grade": "standard",
    "qualities": [{"name": "Chest Plate"}, {"name": "Hardened"}],
}
PISTOL = {
    "name": "Pistol",
    "kind": "ranged",
    "grade": "standard",
    "qualities": [{"name": "Fast"}, {"name": "Accurate"}],
}
BOW = {
    "name": "Bow",
    "kind": "ranged",
    "grade": "standard",
    "qualities": [{"name": "Accurate"}, {"name": "Deadly"}],
    "archaic": True,
}
THROWING_KNIFE = {
    "name": "Throwing Knife",
    "kind": "melee",
    "grade": "standard",
    "qualities": [{"name": "Balanced"}, {"name": "Accurate"}],
}
KNIFE = {"name": "Knife", "kind": "melee", "grade": "cheap", "qualities": [{"name": "Fast"}]}
LAPTOP = {
    "name": "Laptop",
    "kind": "miscellaneous",
    "grade": "special",
    "qualities": [
        {"name": "Superior"},
        {"name": "Superior"},
        {"name": "Customized", "detail": "hacking"},
    ],
}
PICKS = {
    "name": "Lock-picks",
    "kind": "miscellaneous",
    "grade": "cheap",
    "qualities": [{"name": "Superior"}],
}


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def agnes(troupe: Troupe) -> str:
    return member_character(troupe, troupe.player, "Agnes")


def equip(item: dict[str, Any], amount: int = 1, at: int = 0) -> dict[str, Any]:
    return tap(f"equip:{item['id']}", amount, at=at)


def equipped(state: dict[str, Any]) -> list[str]:
    names = {i["id"]: i["name"] for i in state["equipment"]}
    return [names[i] for i in state["equipped"]]


def modifiers(item: dict[str, Any]) -> list[tuple[str, int, str, str, bool]]:
    return [
        (m["label"], m["amount"], m["pools"], m["when"], m["situational"])
        for m in item["modifiers"]
    ]


def test_each_item_says_what_its_qualities_do_to_the_pools_while_equipped(
    troupe: Troupe, agnes: str
) -> None:
    katana = given(troupe, agnes, **KATANA)
    vest = given(troupe, agnes, **VEST)
    laptop = given(troupe, agnes, **LAPTOP)
    pistol = given(troupe, agnes, **PISTOL)

    # Accurate on the weapon's own attack; Brutal changes no pool.
    assert modifiers(katana) == [
        ("Katana: Accurate", 2, "pool:attack:Melee", "attacks with it", False)
    ]
    assert modifiers(pistol) == [
        ("Pistol: Fast", 3, "pool:initiative", "fighting with it", False),
        ("Pistol: Accurate", 2, "pool:attack:Firearms", "attacks with it", False),
    ]
    # Ballistic, as the Vol. II Issue 1 errata has it: on Dodge, against what it says.
    assert modifiers(vest) == [
        ("Flak Vest: Ballistic", 3, "pool:dodge", "against firearms", True),
        ("Flak Vest: Ballistic", 1, "pool:dodge", "against Brawl, Melee and thrown weapons", True),
    ]
    # Superior taken twice adds up; Customized names its circumstance.
    assert modifiers(laptop) == [
        ("Laptop: Superior", 2, "purpose", "for its purpose, with the skill", False),
        ("Laptop: Customized", 2, "purpose", "for hacking, with the skill", False),
    ]
    # The Play View has the same, for the items the character holds.
    state = view(troupe.player, agnes)
    assert [i["name"] for i in state["equipment"]] == ["Flak Vest", "Katana", "Laptop", "Pistol"]
    assert state["equipment"][0]["modifiers"] == vest["modifiers"]
    assert [i["hands"] for i in state["equipment"]] == [None, 2, None, 1]
    assert state["equipped"] == []


def test_a_weapons_bonus_counts_on_every_attack_it_can_make(troupe: Troupe, agnes: str) -> None:
    bow = given(troupe, agnes, **BOW)
    knife = given(troupe, agnes, **THROWING_KNIFE)
    pistol = given(troupe, agnes, **PISTOL)

    # A bow is archaic: it shoots with Firearms or Athletics (MET: VTM p. 279).
    assert bow["archaic"]
    assert [(m["quality"], m["pools"]) for m in bow["modifiers"]] == [
        ("Accurate", "pool:attack:Firearms"),
        ("Accurate", "pool:attack:Athletics"),
        ("Deadly", "pool:attack:Firearms"),
        ("Deadly", "pool:attack:Athletics"),
    ]
    # A Balanced knife is thrown with Athletics, or used in hand with Melee.
    assert [(m["quality"], m["pools"]) for m in knife["modifiers"]] == [
        ("Accurate", "pool:attack:Melee"),
        ("Accurate", "pool:attack:Athletics"),
    ]
    # A pistol only with Firearms.
    assert [m["pools"] for m in pistol["modifiers"] if m["quality"] == "Accurate"] == [
        "pool:attack:Firearms"
    ]


def test_only_a_ranged_weapon_is_archaic(troupe: Troupe, agnes: str) -> None:
    refused = give(troupe, agnes, **{**THROWING_KNIFE, "archaic": True})
    assert refused.status_code == 422, refused.text
    assert "Only a ranged weapon is archaic (a bow or crossbow)." in refused.text
    # The book's Bow is archaic, and a change says so.
    rules = troupe.storyteller.client.get("/rules/vampire/equipment").json()
    assert [t["archaic"] for t in rules["templates"] if t["name"] == "Bow"] == [True]
    pistol = given(troupe, agnes, **PISTOL)
    changed = change(troupe, pistol, archaic=True, reason="It's a crossbow")
    assert changed.status_code == 200, changed.text
    assert changed.json()["archaic"]
    assert any("now archaic" in s for s in summaries(troupe.player)), summaries(troupe.player)


def test_equipping_is_a_tap_with_undo_kept_from_game_to_game(troupe: Troupe, agnes: str) -> None:
    katana = given(troupe, agnes, **KATANA)
    vest = given(troupe, agnes, **VEST)
    put_on = equip(vest, at=1)

    state = send(troupe.player, agnes, equip(katana), put_on)
    assert equipped(state) == ["Katana", "Flak Vest"]
    assert texts(state)[:2] == ["Equipped Flak Vest", "Equipped Katana"]

    # Undo takes it off again.
    state = send(troupe.player, agnes, {**tap(at=2), "kind": "undo", "undoes": put_on["id"]})
    assert equipped(state) == ["Katana"]
    state = send(troupe.player, agnes, equip(vest, at=3))

    # Reset leaves it as it is: it is what the character carries.
    state = troupe.player.client.post(f"/characters/{agnes}/play/reset", json={}).json()
    assert state["game"]["number"] == 2
    assert equipped(state) == ["Katana", "Flak Vest"]
    state = send(troupe.player, agnes, equip(katana, -1, at=10))
    assert texts(state)[0] == "Unequipped Katana"
    assert equipped(view(troupe.storyteller, agnes)) == ["Flak Vest"]

    # The printed sheet has what is equipped now.
    printed = troupe.player.client.get(f"/characters/{agnes}/print").json()
    assert printed["equipped"] == [vest["id"]]
    assert [i["modifiers"] for i in printed["equipment"] if i["id"] == vest["id"]] == [
        vest["modifiers"]
    ]


def test_one_piece_of_protective_gear_and_one_of_miscellaneous_gear_at_a_time(
    troupe: Troupe, agnes: str
) -> None:
    vest = given(troupe, agnes, **VEST)
    mail = given(troupe, agnes, **MAIL)
    laptop = given(troupe, agnes, **LAPTOP)
    picks = given(troupe, agnes, **PICKS)

    state = send(troupe.player, agnes, equip(vest), equip(laptop, at=1))
    state = send(troupe.player, agnes, equip(mail, at=2), equip(picks, at=3))
    assert equipped(state) == ["Chain Mail", "Lock-picks"]
    assert texts(state)[:2] == [
        "Equipped Lock-picks: put away Laptop (one piece's bonus at a time)",
        "Equipped Chain Mail: took off Flak Vest (one worn at a time)",
    ]


def test_weapons_take_two_hands_at_most(troupe: Troupe, agnes: str) -> None:
    katana = given(troupe, agnes, **KATANA)
    pistol = given(troupe, agnes, **PISTOL)
    knife = given(troupe, agnes, **KNIFE)
    dagger = given(troupe, agnes, **DAGGER)

    # A pistol and a knife, one hand each.
    state = send(troupe.player, agnes, equip(pistol), equip(knife, at=1))
    assert equipped(state) == ["Pistol", "Knife"]
    # A third hand's worth puts away the one equipped longest.
    state = send(troupe.player, agnes, equip(dagger, at=2))
    assert equipped(state) == ["Knife", "Silver Dagger"]
    assert texts(state)[0] == "Equipped Silver Dagger: put away Pistol (two hands at most)"
    # The two-handed Katana needs both.
    state = send(troupe.player, agnes, equip(katana, at=3))
    assert equipped(state) == ["Katana"]
    assert texts(state)[0] == (
        "Equipped Katana: put away Knife (two hands at most), put away Silver Dagger"
        " (two hands at most)"
    )


def test_an_item_that_leaves_is_no_longer_equipped(
    troupe: Troupe, agnes: str, session: Session
) -> None:
    bram = member_character(troupe, troupe.player, "Bram")
    katana = given(troupe, agnes, **KATANA)
    vest = given(troupe, agnes, **VEST)
    send(troupe.player, agnes, equip(katana), equip(vest))

    # Given away: Agnes no longer has it equipped, and Bram hasn't equipped it.
    assert give_to(troupe.player, agnes, katana, bram).status_code == 200
    assert equipped(view(troupe.player, agnes)) == ["Flak Vest"]
    assert view(troupe.player, bram)["equipped"] == []

    # Given back later, it comes back put away.
    assert give_to(troupe.player, bram, katana, agnes).status_code == 200
    back = session.scalars(
        select(EquipmentEvent)
        .where(EquipmentEvent.item_id == uuid.UUID(katana["id"]))
        .order_by(EquipmentEvent.created_at.desc(), EquipmentEvent.id.desc())
    ).first()
    assert back is not None
    back.created_at += timedelta(minutes=1)
    session.flush()
    assert equipped(view(troupe.player, agnes)) == ["Flak Vest"]

    # Taken back by staff: gone from what is equipped.
    taken = troupe.storyteller.client.post(
        f"{path(troupe)}/{vest['id']}/take-back", json={"reason": "Borrowed"}
    )
    assert taken.status_code == 200, taken.text
    assert equipped(view(troupe.player, agnes)) == []


def test_an_item_the_character_doesnt_hold_changes_nothing(troupe: Troupe, agnes: str) -> None:
    bram = member_character(troupe, troupe.player, "Bram")
    theirs = given(troupe, bram, **KATANA)

    state = send(troupe.player, agnes, equip(theirs))
    assert state["equipped"] == []
    assert view(troupe.player, bram)["equipped"] == []
    # Only a real item's id is a tracker.
    bad = tap("equip:katana", 1)
    response = troupe.player.client.post(f"/characters/{agnes}/play/taps", json={"taps": [bad]})
    assert response.status_code == 422


def test_a_stranger_cant_equip_it(troupe: Troupe, agnes: str) -> None:
    katana = given(troupe, agnes, **KATANA)
    stranger: Person = troupe.stranger
    response = stranger.client.post(
        f"/characters/{agnes}/play/taps", json={"taps": [equip(katana)]}
    )
    assert response.status_code == 404
    assert view(troupe.player, agnes)["equipped"] == []
