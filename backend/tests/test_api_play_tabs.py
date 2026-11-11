"""A troupe switches each of the Play View's tabs on or off for its players, all on by
default; with every one off it doesn't use the Play View (issue #673)."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.models import TroupeMembership
from tests.api_helpers import Person, Troupe
from tests.test_api_checkin import check_in, game, open_checkin
from tests.test_api_downtimes import member_character
from tests.test_api_scenes import new_scene, npc
from tests.test_api_troupe_settings_share import apply, exported, second

EVERY = ["sheet", "tracker", "pools", "status", "equipment"]


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def ok(response: Any, code: int = 200) -> Any:
    assert response.status_code == code, response.text
    return response.json()


def switch_off(troupe: Troupe, *tabs: str, troupe_id: str | None = None) -> dict[str, Any]:
    return ok(
        troupe.storyteller.client.patch(
            f"/troupes/{troupe_id or troupe.id}", json={"play_tabs_off": list(tabs)}
        )
    )


def tabs(person: Person, character_id: str) -> list[str]:
    return ok(person.client.get(f"/characters/{character_id}/play"))["tabs"]


def plays(person: Person, character_id: str) -> bool:
    return ok(person.client.get(f"/characters/{character_id}"))["play_view"]


def logged(troupe: Troupe) -> list[str]:
    return [
        e["message"]
        for e in ok(troupe.lead.client.get(f"/troupes/{troupe.id}/log"))
        if e["action"] == "troupe.play_tabs"
    ]


def test_every_tab_is_on_by_default(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")

    assert ok(troupe.player.client.get(f"/troupes/{troupe.id}"))["play_tabs_off"] == []
    assert tabs(troupe.player, agnes) == EVERY
    assert plays(troupe.player, agnes)
    assert all(c["play_view"] for c in ok(troupe.player.client.get("/characters")))


def test_tabs_switched_off_are_gone_for_players_and_logged(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")

    # Sent in any order, kept in the tabs' own.
    assert switch_off(troupe, "equipment", "pools")["play_tabs_off"] == ["pools", "equipment"]

    assert tabs(troupe.player, agnes) == ["sheet", "tracker", "status"]
    # Staff on a PC see what its player does.
    assert tabs(troupe.storyteller, agnes) == ["sheet", "tracker", "status"]
    assert plays(troupe.player, agnes)
    assert logged(troupe) == [
        "storyteller set the Play View's tabs for players: Sheet, Tracker and Status."
    ]
    # The same again changes nothing, and isn't logged.
    switch_off(troupe, "pools", "equipment")
    assert len(logged(troupe)) == 1


def test_only_storytellers_switch_tabs(troupe: Troupe) -> None:
    for person in (troupe.assistant, troupe.narrator, troupe.player):
        response = person.client.patch(f"/troupes/{troupe.id}", json={"play_tabs_off": ["pools"]})
        assert response.status_code == 403, response.text
    refused = troupe.storyteller.client.patch(
        f"/troupes/{troupe.id}", json={"play_tabs_off": ["dice"]}
    )
    assert refused.status_code == 422


def test_staff_see_every_tab_on_an_npc(troupe: Troupe) -> None:
    bram = npc(troupe, "Bram")
    switch_off(troupe, "pools", "tracker")

    assert tabs(troupe.storyteller, bram) == EVERY
    assert plays(troupe.storyteller, bram)


def test_every_tab_off_takes_the_play_view_away(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    bram = npc(troupe, "Bram")
    scene = new_scene(troupe.storyteller, troupe, "The docks")

    switch_off(troupe, *EVERY)

    assert logged(troupe)[-1] == (
        "storyteller set the Play View's tabs for players: no tabs, so the Play View is off."
    )
    # Its characters have no Play, NPCs too, and their Play Views no tabs.
    assert not plays(troupe.player, agnes)
    assert not plays(troupe.storyteller, bram)
    assert [c["play_view"] for c in ok(troupe.player.client.get("/characters"))] == [False]
    assert tabs(troupe.player, agnes) == []
    assert tabs(troupe.storyteller, bram) == []
    at_game = ok(troupe.storyteller.client.get(f"/troupes/{troupe.id}/play"))
    assert {c["character_name"]: c["play_view"] for c in at_game} == {
        "Agnes": False,
        "Bram": False,
    }
    # Nothing is pinned in its scenes.
    pinned = troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/scenes/{scene['id']}/characters/{bram}"
    )
    assert pinned.status_code == 409
    assert pinned.json()["detail"] == "Its troupe doesn't use the Play View."

    # One tab back on brings it all back.
    switch_off(troupe, "sheet", "tracker", "pools", "status")
    assert plays(troupe.player, agnes)
    assert tabs(troupe.player, agnes) == ["equipment"]
    assert tabs(troupe.storyteller, bram) == EVERY


def test_a_visitor_keeps_its_home_troupes_tabs(troupe: Troupe, session: Session) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    away = second(troupe)
    session.add(TroupeMembership(troupe_id=uuid.UUID(away), character_id=uuid.UUID(agnes)))
    session.flush()

    switch_off(troupe, *EVERY, troupe_id=away)
    assert tabs(troupe.player, agnes) == EVERY
    assert plays(troupe.player, agnes)
    at_game = ok(troupe.storyteller.client.get(f"/troupes/{away}/play"))
    assert [c["play_view"] for c in at_game] == [True]

    switch_off(troupe, "pools")
    assert "pools" not in tabs(troupe.storyteller, agnes)


def test_checking_in_says_whether_there_is_a_play_view_to_open(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    tonight = game(troupe)
    code = open_checkin(troupe, tonight)["checkin"]["code"]
    switch_off(troupe, *EVERY)

    offered = ok(troupe.player.client.get(f"/checkin/{code}"))
    assert [c["play_view"] for c in offered["characters"]] == [False]
    done = ok(check_in(troupe.player, troupe, tonight, agnes))
    assert done["play_view"] is False
    # Still checked in, for its XP.
    assert done["already"] is False


def test_the_settings_share_carries_the_tabs(troupe: Troupe) -> None:
    switch_off(troupe, "pools", "status")
    document = exported(troupe.storyteller, troupe.id)
    assert {"type": "setting", "key": "play_tabs_off", "value": ["pools", "status"]} in document[
        "sections"
    ]["at_game"]

    fresh = second(troupe)
    ok(apply(troupe.storyteller, fresh, document, from_troupe_id=troupe.id))

    assert ok(troupe.storyteller.client.get(f"/troupes/{fresh}"))["play_tabs_off"] == [
        "pools",
        "status",
    ]
    # A tab Horatio doesn't have can't come in.
    document["sections"]["at_game"] = [
        {"type": "setting", "key": "play_tabs_off", "value": ["dice"]}
    ]
    assert apply(troupe.storyteller, fresh, document).status_code == 422
