"""What the retire dialog warns of (#748): the bonds a character is the regnant of,
which fade unfelt at its Final Death (#662), and the shared backgrounds it has dots in
with others; staff see all of it, its player only what they may know."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe
from tests.test_api_bonds import Scene

TROUPE = "Lords of the Night"


@pytest.fixture
def scene(client_for: Callable[[], TestClient], session: Session) -> Scene:
    return Scene(Troupe(client_for, session))


def warnings(person: Person, character_id: str) -> Any:
    found = person.client.get(f"/characters/{character_id}/leaving/warnings")
    assert found.status_code == 200, found.text
    return found.json()


def share(scene: Scene, *character_ids: str) -> dict[str, Any]:
    made = scene.troupe.storyteller.client.post(
        f"/troupes/{scene.troupe.id}/shared-backgrounds",
        json={
            "name": "The coterie's Haven",
            "background": "Haven",
            "notes": "",
            "contributions": [{"character_id": c, "dots": 1} for c in character_ids],
        },
    )
    assert made.status_code == 201, made.text
    return made.json()


def test_staff_see_every_bond_its_player_only_those_known_to_the_regnant(scene: Scene) -> None:
    bond = scene.drunk(scene.agnes, scene.bram, "2026-10-03")
    scene.drunk(scene.cora, scene.bram, "2026-10-03")

    staff = warnings(scene.troupe.storyteller, scene.bram)
    assert staff["staff"] is True
    assert sorted(t["name"] for t in staff["thralls"]) == ["Agnes", "Cora"]
    assert {t["troupe"] for t in staff["thralls"]} == {TROUPE}

    # Bram's player knows of no bond yet: the warning tells them of none.
    player = warnings(scene.other, scene.bram)
    assert (player["staff"], player["thralls"]) == (False, [])

    known = scene.troupe.storyteller.client.put(
        f"{scene.path}/{bond['id']}/known", json={"known": True}
    )
    assert known.status_code == 200, known.text
    assert [t["name"] for t in warnings(scene.other, scene.bram)["thralls"]] == ["Agnes"]


def test_only_bonds_it_is_the_regnant_of_still_felt_fading_too(scene: Scene) -> None:
    # Bram is Agnes's regnant; Bram's own bond to Vidal is no concern of its thralls.
    scene.drunk(scene.agnes, scene.bram, "2026-10-03")
    scene.drunk(scene.bram, scene.vidal, "2026-10-03")
    assert [t["name"] for t in warnings(scene.troupe.storyteller, scene.bram)["thralls"]] == [
        "Agnes"
    ]

    # Bram retired with Final Death, unlisted: its bond fades, still felt, so listing
    # Bram later is still what would tell Agnes's player.
    retired = scene.other.client.post(
        f"/characters/{scene.bram}/retire",
        json={"reason": "final_death", "note": "", "listed": False},
    )
    assert retired.status_code == 200, retired.text
    assert [t["name"] for t in warnings(scene.troupe.storyteller, scene.bram)["thralls"]] == [
        "Agnes"
    ]

    # With the troupe's bonds switched off, there is nothing to warn of.
    assert scene.set("off").status_code == 200
    assert warnings(scene.troupe.storyteller, scene.bram)["thralls"] == []


def test_nothing_of_bonds_while_the_troupe_tracks_none(scene: Scene) -> None:
    scene.drunk(scene.agnes, scene.bram, "2026-10-03")
    assert scene.set("off").status_code == 200
    assert warnings(scene.troupe.storyteller, scene.bram)["thralls"] == []


def test_shared_backgrounds_it_still_has_dots_in_with_others(scene: Scene) -> None:
    shared = share(scene, scene.bram, scene.cora)
    for person in (scene.troupe.storyteller, scene.other):
        found = warnings(person, scene.bram)["shared"]
        assert found == [
            {
                "name": "The coterie's Haven",
                "background": "Haven",
                "troupe": TROUPE,
                "others": ["Cora"],
            }
        ]

    # Once its dots are out, the withdrawal has been logged: nothing left to warn of.
    out = scene.troupe.storyteller.client.post(
        f"/shared-backgrounds/{shared['id']}/entries",
        json={
            "kind": "withdrawal",
            "character_id": scene.bram,
            "dots": 1,
            "happened_at": "2026-10-17T21:15:00+00:00",
        },
    )
    assert out.status_code == 201, out.text
    assert warnings(scene.troupe.storyteller, scene.bram)["shared"] == []


def test_alone_in_a_shared_background_there_is_no_one_to_tell(scene: Scene) -> None:
    share(scene, scene.bram)
    assert warnings(scene.troupe.storyteller, scene.bram)["shared"] == []


def test_only_its_player_and_its_staff_ask(scene: Scene) -> None:
    for person in (scene.troupe.player, scene.third):
        refused = person.client.get(f"/characters/{scene.bram}/leaving/warnings")
        assert refused.status_code in (403, 404), refused.text
    narrator = scene.troupe.narrator.client.get(f"/characters/{scene.bram}/leaving/warnings")
    assert narrator.status_code in (403, 404), narrator.text
