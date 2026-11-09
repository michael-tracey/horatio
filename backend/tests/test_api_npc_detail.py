"""Staff set the detail of an NPC's trait in the quick builder: a merit's choice
(Thaumaturgic Expertise's path), a skill's field (issue #570)."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe
from tests.test_api_npc_picks import cost_of, picks, placed
from tests.test_api_npcs_titles import make_npc

PATH = "Thaumaturgy: Path of Caelestikinesis"
TRAINING = "A path of Thaumaturgy needs Thaumaturgic Training"


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def rated(
    person: Person, npc: str, category: str, name: str, rating: int | None, detail: str = ""
) -> Any:
    response = person.client.put(
        f"/characters/{npc}/npc/ratings",
        json={"category": category, "name": name, "detail": detail, "rating": rating},
    )
    assert response.status_code == 200, response.text
    return response.json()


def detail(person: Person, npc: str, category: str, name: str, to: str, before: str = "") -> Any:
    return person.client.put(
        f"/characters/{npc}/npc/detail",
        json={"category": category, "name": name, "detail": before, "to": to},
    )


def problems(person: Person, npc: str) -> list[str]:
    sheet = person.client.get(f"/characters/{npc}/sheet")
    assert sheet.status_code == 200, sheet.text
    return [p["message"] for p in sheet.json()["problems"]]


def held(person: Person, npc: str, name: str) -> list[tuple[str, int]]:
    sheet = person.client.get(f"/characters/{npc}/sheet").json()
    return [(t["detail"], t["rating"]) for t in sheet["traits"] if t["name"] == name]


def test_choosing_thaumaturgic_expertises_path_makes_it_in_clan(troupe: Troupe) -> None:
    staff = troupe.storyteller
    npc = make_npc(troupe)["id"]
    rated(staff, npc, "clan", "Tremere", None)
    rated(staff, npc, "disciplines", "Thaumaturgy: Path of Blood", 3)
    rated(staff, npc, "disciplines", PATH, 3)
    # As a Yorick import leaves it: the merit with no path.
    before = rated(staff, npc, "merits", "Thaumaturgic Expertise", 1)

    found = problems(staff, npc)
    assert "Choose what Thaumaturgic Expertise applies to." in found
    assert any(m.startswith(TRAINING) for m in found)

    response = detail(staff, npc, "merits", "Thaumaturgic Expertise", PATH)
    assert response.status_code == 200, response.text
    after = response.json()
    # Priced in-clan now, so cheaper; the merit keeps its rating.
    assert cost_of(after, PATH) < cost_of(before, PATH)
    assert held(staff, npc, "Thaumaturgic Expertise") == [(PATH, 1)]
    found = problems(staff, npc)
    assert "Choose what Thaumaturgic Expertise applies to." not in found
    assert not any(m.startswith(TRAINING) for m in found)

    # Setting the merit's rating again keeps its detail rather than adding another.
    rated(staff, npc, "merits", "Thaumaturgic Expertise", 1, detail=PATH)
    assert held(staff, npc, "Thaumaturgic Expertise") == [(PATH, 1)]


def test_a_skills_field_changes_and_keeps_its_rating_and_pick(troupe: Troupe) -> None:
    staff = troupe.storyteller
    npc = make_npc(troupe)["id"]
    rated(staff, npc, "skills", "Crafts", 3)
    assert placed(picks(staff, npc), "skills") == {"Crafts": (3, "fit")}

    named = detail(staff, npc, "skills", "Crafts", " Illumination ")
    assert named.status_code == 200, named.text
    assert held(staff, npc, "Crafts") == [("Illumination", 3)]
    assert placed(picks(staff, npc), "skills") == {"Crafts": (3, "fit")}

    # A pick placed by hand stays with it too.
    pinned = staff.client.put(
        f"/characters/{npc}/npc/picks",
        json={"category": "skills", "name": "Crafts", "detail": "Illumination", "rating": 3},
    )
    assert pinned.status_code == 200, pinned.text
    assert placed(pinned.json(), "skills") == {"Crafts": (3, "staff")}
    renamed = detail(staff, npc, "skills", "Crafts", "Painting", before="Illumination")
    assert renamed.status_code == 200, renamed.text
    assert held(staff, npc, "Crafts") == [("Painting", 3)]
    found = picks(staff, npc)
    crafts = next(
        p
        for pool in found["pools"]
        if pool["category"] == "skills"
        for p in pool["placed"]
        if p["name"] == "Crafts"
    )
    assert (crafts["detail"], crafts["pick"], crafts["by"]) == ("Painting", 3, "staff")


def test_a_detail_must_be_held_and_not_clash(troupe: Troupe) -> None:
    staff = troupe.storyteller
    npc = make_npc(troupe)["id"]
    rated(staff, npc, "skills", "Crafts", 2, detail="Painting")
    rated(staff, npc, "skills", "Crafts", 1, detail="Carpentry")

    clash = detail(staff, npc, "skills", "Crafts", "Painting", before="Carpentry")
    assert clash.status_code == 409
    assert clash.json()["detail"] == "The NPC already has Crafts: Painting."
    missing = detail(staff, npc, "skills", "Crafts", "Sculpture", before="Pottery")
    assert missing.status_code == 409
    assert missing.json()["detail"] == "The NPC does not have Crafts: Pottery."
    # Players can't change an NPC.
    refused = detail(troupe.player, npc, "skills", "Crafts", "Sculpture", before="Painting")
    assert refused.status_code in (403, 404)
