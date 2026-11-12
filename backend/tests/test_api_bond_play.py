"""A blood bond on the thrall's Play View (#664; MET: VTM p. 295): two drinks lower
Social defence against the regnant's powers by 1, a full bond Social and Mental by
3, each with what harming or crossing the regnant costs in Willpower. One drink has
no rules effect. Only the thrall's side shows, and nothing while bonds are off."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio import reference as ref
from horatio.bond_effects import Felt, lines, with_penalties
from tests.api_helpers import Person, Troupe
from tests.test_api_bond_fading import retire
from tests.test_api_bonds import Scene


@pytest.fixture
def scene(client_for: Callable[[], TestClient], session: Session) -> Scene:
    return Scene(Troupe(client_for, session))


def reference(person: Person, character_id: str) -> dict[str, Any]:
    found = person.client.get(f"/characters/{character_id}/play/reference")
    assert found.status_code == 200, found.text
    return found.json()


def pool(found: dict[str, Any], key: str) -> dict[str, Any]:
    return next(p for p in found["pools"] if p["key"] == key)


def against(found: dict[str, Any], key: str) -> list[tuple[str, int]]:
    """The bond lines under a pool: whom, and by how much it lowers the pool."""
    return [
        (v["when"], v["total"] - pool(found, key)["total"])
        for v in pool(found, key)["variants"]
        if v["parts"] and v["parts"][0]["label"] == "Blood bond"
    ]


def test_two_drinks_lower_social_defence_against_the_regnant(scene: Scene) -> None:
    scene.drunk(scene.agnes, scene.bram, "2026-10-03", "2026-10-10")
    found = reference(scene.troupe.player, scene.agnes)
    assert against(found, "defense:Social") == [("Against Bram's powers", -1)]
    assert against(found, "defense:Mental") == []
    assert against(found, "defense:Physical") == []
    [line] = found["bonds"]
    assert (line["regnant"], line["level"], line["drinks"]) == ("Bram", 2, "Two drinks")
    assert "Directly harming Bram costs 1 Willpower an hour (p. 295)." in line["effects"]


def test_a_full_bond_lowers_social_and_mental_defence_by_three(scene: Scene) -> None:
    scene.drunk(scene.agnes, scene.bram, "2026-10-03", "2026-10-10", "2026-10-17")
    found = reference(scene.troupe.player, scene.agnes)
    assert against(found, "defense:Social") == [("Against Bram's powers", -3)]
    assert against(found, "defense:Mental") == [("Against Bram's powers", -3)]
    [line] = found["bonds"]
    assert (line["level"], line["drinks"]) == (3, "Full bond")
    assert any("would disapprove of costs 1 Willpower" in e for e in line["effects"])
    assert any("costs 3 Willpower an hour" in e for e in line["effects"])


def test_one_drink_is_only_a_quiet_line(scene: Scene) -> None:
    scene.drunk(scene.agnes, scene.bram, "2026-10-03")
    found = reference(scene.troupe.player, scene.agnes)
    assert against(found, "defense:Social") == []
    assert [(b["level"], b["drinks"]) for b in found["bonds"]] == [(1, "One drink")]


def test_the_regnant_sees_nothing_and_nothing_shows_while_off(scene: Scene) -> None:
    scene.drunk(scene.agnes, scene.bram, "2026-10-03", "2026-10-10", "2026-10-17")
    # The regnant's own Play View: nothing of the bonds to them.
    regnant = reference(scene.other, scene.bram)
    assert regnant["bonds"] == []
    assert all(not against(regnant, p["key"]) for p in regnant["pools"])
    # Switched off: nothing on the thrall's either.
    assert scene.set("off").status_code == 200
    thrall = reference(scene.troupe.player, scene.agnes)
    assert thrall["bonds"] == []
    assert against(thrall, "defense:Social") == []


def test_a_fading_bond_keeps_the_regnants_name(scene: Scene) -> None:
    scene.drunk(scene.agnes, scene.bram, "2026-10-03", "2026-10-10")
    retire(scene.other, scene.bram, "final_death")
    found = reference(scene.troupe.player, scene.agnes)
    assert against(found, "defense:Social") == [("Against Bram's powers", -1)]
    assert [b["regnant"] for b in found["bonds"]] == ["Bram"]


def test_staff_see_an_npc_thralls_lines_for_the_scene_view(scene: Scene) -> None:
    scene.drunk(scene.ghislaine, scene.vidal, "2026-10-03", "2026-10-10", "2026-10-17")
    found = reference(scene.troupe.storyteller, scene.ghislaine)
    assert against(found, "defense:Mental") == [("Against Vidal's powers", -3)]
    # Narrators, who don't run bonds, don't.
    narrated = scene.troupe.narrator.client.get(f"/characters/{scene.ghislaine}/play/reference")
    if narrated.status_code == 200:
        assert narrated.json()["bonds"] == []


def defence(key: str, total: int) -> ref.TestPool:
    return ref.TestPool(
        key=key,
        name=key,
        group="Defence",
        parts=[ref.PoolPart(label="Social", value=total)],
        total=total,
    )


def test_penalties_are_lines_of_their_own_per_regnant() -> None:
    pools = [defence("defense:Social", 4), defence("defense:Mental", 5)]
    made = with_penalties(pools, [Felt("Bram", 2), Felt("Vidal", 1)])
    assert [(v.when, v.total) for v in made[0].variants] == [("Against Bram's powers", 3)]
    assert made[1].variants == []
    # Its own total is unchanged: the line counts only against the regnant.
    assert made[0].total == 4
    assert [b.regnant for b in lines([Felt("Vidal", 1), Felt("Bram", 3)])] == ["Bram", "Vidal"]
