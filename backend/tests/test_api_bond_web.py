"""The web of blood bonds (#708): everyone on either side of the troupe's bonds and
every bond between them, for exactly the staff who run bonds, and nobody else."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.models import CharacterTitle
from tests.api_helpers import Troupe
from tests.test_api_bonds import Scene, named


@pytest.fixture
def scene(client_for: Callable[[], TestClient], session: Session) -> Scene:
    return Scene(Troupe(client_for, session))


def web(scene: Scene, by: Any = None) -> Any:
    return (by or scene.troupe.storyteller).client.get(f"/troupes/{scene.troupe.id}/bond-web")


def test_staff_see_everyone_on_either_side_and_every_bond(scene: Scene) -> None:
    t = scene.troupe
    scene.drunk(scene.agnes, scene.bram, "2026-10-03", "2026-10-10", "2026-10-17")
    # The same name in another case is the same person, shown with its capitals,
    # whichever was recorded first.
    scene.drunk(scene.cora, named("old marguerite"), "2026-10-03")
    scene.drunk(scene.vidal, named("Old Marguerite"), "2026-10-03")
    broken = scene.drunk(scene.ghislaine, scene.vidal, "2026-10-03")
    assert (
        t.storyteller.client.post(
            f"{scene.path}/{broken['id']}/break", json={"reason": "x"}
        ).status_code
        == 200
    )
    t.session.add(
        CharacterTitle(troupe_id=uuid.UUID(t.id), character_id=uuid.UUID(scene.bram), name="Prince")
    )
    t.session.flush()
    retired = scene.third.client.post(
        f"/characters/{scene.cora}/retire",
        json={"reason": "off_field", "note": "", "listed": False},
    )
    assert retired.status_code == 200, retired.text

    for person in (t.storyteller, t.assistant, t.lead):
        found = web(scene, person)
        assert found.status_code == 200, (person.email, found.text)
    body = web(scene).json()
    people = {p["name"]: p for p in body["people"]}
    assert set(people) == {"Agnes", "Bram", "Cora", "Vidal", "Ghislaine", "Old Marguerite"}
    marguerite = people["Old Marguerite"]
    assert (marguerite["key"], marguerite["character_id"], marguerite["kind"]) == (
        "name:old marguerite",
        None,
        None,
    )
    assert people["Bram"]["titles"] == ["Prince"]
    assert people["Bram"]["key"] == scene.bram
    assert people["Cora"]["standing"] == "off_field"
    assert people["Agnes"]["standing"] == "active"
    assert people["Vidal"]["kind"] == "npc"

    links = {(b["thrall"], b["regnant"]): b for b in body["bonds"]}
    assert len(links) == 4
    assert links[(scene.agnes, scene.bram)]["level"] == 3
    assert links[(scene.agnes, scene.bram)]["status"] == "active"
    assert {k for k in links if k[1] == "name:old marguerite"} == {
        (scene.cora, "name:old marguerite"),
        (scene.vidal, "name:old marguerite"),
    }
    assert links[(scene.ghislaine, scene.vidal)]["status"] == "broken"
    assert sum(c["count"] for c in body["clans"]) >= 3


def test_only_the_staff_who_run_bonds_see_it(scene: Scene) -> None:
    t = scene.troupe
    scene.drunk(scene.agnes, scene.bram, "2026-10-03")
    for person in (t.narrator, t.player, scene.other, scene.third, t.stranger):
        assert web(scene, person).status_code == 403, person.email


def test_nothing_while_the_troupe_tracks_no_bonds(scene: Scene) -> None:
    scene.drunk(scene.agnes, scene.bram, "2026-10-03")
    assert scene.set("off").status_code == 200
    assert web(scene).status_code == 404
