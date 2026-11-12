"""Blood bonds fading (#662): when a regnant meets Final Death its bonds fade over 30
days (MET: VTM p. 296), and nothing the thrall's player sees says so; on the day it
ends, and the thrall's player is told only that it faded, with the next downtime
results. A thrall's Final Death ends its bonds; Off-field and Inactive leave them."""

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from horatio.bonds import FADE_DAYS, today
from horatio.models import BloodBond
from tests.api_helpers import Person, Troupe
from tests.test_api_bonds import Scene
from tests.test_api_downtimes import new_cycle, open_cycle


@pytest.fixture
def scene(client_for: Callable[[], TestClient], session: Session) -> Scene:
    return Scene(Troupe(client_for, session))


def retire(person: Person, character_id: str, reason: str | None, listed: bool = False) -> Any:
    body = None if reason is None else {"reason": reason, "note": "", "listed": listed}
    retired = person.client.post(f"/characters/{character_id}/retire", json=body)
    assert retired.status_code == 200, retired.text
    return retired.json()


def staff_bond(scene: Scene, bond_id: str) -> dict[str, Any]:
    return next(b for b in scene.bonds() if b["id"] == bond_id)


def thrall_card(scene: Scene) -> Any:
    card = scene.card(scene.agnes, scene.troupe.player)
    assert card.status_code == 200, card.text
    return card.json()


def faded_by(session: Session, bond_id: str, on: date) -> None:
    """Move a fading bond's last day, as time passing would."""
    session.execute(update(BloodBond).where(BloodBond.id == bond_id).values(fades_on=on))
    session.commit()


def deliver(scene: Scene) -> None:
    """Deliver a closed downtime cycle's results, which tells thralls of fades."""
    troupe = scene.troupe
    cycle_id = getattr(scene, "cycle_id", None)
    if cycle_id is None:
        cycle_id = open_cycle(troupe, new_cycle(troupe))["id"]
        assert troupe.storyteller.client.post(f"/cycles/{cycle_id}/close").status_code == 200
        scene.cycle_id = cycle_id  # type: ignore[attr-defined]
    delivered = troupe.storyteller.client.post(f"/cycles/{cycle_id}/deliver")
    assert delivered.status_code == 200, delivered.text


def bell(person: Person) -> list[str]:
    return [i["summary"] for i in person.client.get("/notifications").json()["items"]]


def test_a_dead_regnants_bond_fades_unseen_by_the_thrall(scene: Scene, session: Session) -> None:
    bond = scene.drunk(scene.agnes, scene.bram, "2026-10-03", "2026-10-10")
    before = thrall_card(scene)
    thrall_log = scene.character_log(scene.agnes, scene.troupe.player)

    retire(scene.other, scene.bram, "final_death")

    # Staff see the truth at once, with the day it ends.
    fading = staff_bond(scene, bond["id"])
    assert fading["status"] == "fading"
    assert fading["fade_reason"] == "regnant_died"
    assert fading["fades_on"] == (today() + timedelta(days=FADE_DAYS)).isoformat()
    assert any(
        m.startswith("Agnes's bond to Bram began to fade, as its regnant met Final Death")
        for m in scene.messages()
    )
    # The thrall's player sees nothing change: not the card, its order, nor their log.
    assert thrall_card(scene) == before
    assert scene.character_log(scene.agnes, scene.troupe.player) == thrall_log
    assert not any("Bram" in s for s in bell(scene.troupe.player))

    # The day comes: it ends, but the thrall's sheet still shows it until they're told.
    faded_by(session, bond["id"], today())
    ended = staff_bond(scene, bond["id"])
    assert (ended["status"], ended["thrall_told"]) == ("ended", False)
    assert ended["ended_reason"] == "Faded: its regnant met Final Death."
    assert thrall_card(scene)["bound_to"] == before["bound_to"]
    assert scene.character_log(scene.agnes, scene.troupe.player) == thrall_log

    # With the next downtime results, they learn only that it faded.
    deliver(scene)
    assert thrall_card(scene)["bound_to"] == []
    assert "Agnes's bond to Bram has faded." in bell(scene.troupe.player)
    told = scene.character_log(scene.agnes, scene.troupe.player)
    assert any(m.endswith("'s bond to Bram has faded.") for m in told)
    assert not any("Final Death" in m or "retired" in m for m in told)
    assert staff_bond(scene, bond["id"])["thrall_told"] is True
    # Told once only.
    deliver(scene)
    assert bell(scene.troupe.player).count("Agnes's bond to Bram has faded.") == 1


def test_staff_move_the_end_of_a_fade_or_end_it_now(scene: Scene) -> None:
    bond = scene.drunk(scene.agnes, scene.bram, "2026-10-03")
    path = f"{scene.path}/{bond['id']}/fade"
    later = (today() + timedelta(days=45)).isoformat()
    not_fading = scene.troupe.storyteller.client.put(path, json={"fades_on": later, "reason": "x"})
    assert not_fading.status_code == 409

    retire(scene.other, scene.bram, "final_death")
    for person in (scene.troupe.player, scene.other, scene.troupe.narrator):
        refused = person.client.put(path, json={"fades_on": later, "reason": "Slow blood"})
        assert refused.status_code in (403, 404), refused.text
    no_reason = scene.troupe.storyteller.client.put(path, json={"fades_on": later, "reason": " "})
    assert no_reason.status_code == 422

    moved = scene.troupe.storyteller.client.put(path, json={"fades_on": later, "reason": "Slow"})
    assert moved.status_code == 200, moved.text
    assert (moved.json()["status"], moved.json()["fades_on"]) == ("fading", later)

    now = scene.troupe.storyteller.client.put(
        path, json={"fades_on": today().isoformat(), "reason": "The story moves on"}
    )
    assert now.status_code == 200, now.text
    assert (now.json()["status"], now.json()["thrall_told"]) == ("ended", False)
    messages = scene.messages()
    assert any("moved the end of Agnes's fading bond to Bram" in m for m in messages)
    assert "Agnes's bond to Bram has faded." in messages


def test_off_field_and_inactive_regnants_leave_the_bond_alone(scene: Scene) -> None:
    bond = scene.drunk(scene.agnes, scene.bram, "2026-10-03")
    retire(scene.other, scene.bram, "off_field")
    assert staff_bond(scene, bond["id"])["status"] == "active"

    # A thrall whose player stopped playing it keeps its bonds too.
    to_vidal = scene.drunk(scene.agnes, scene.vidal, "2026-10-03")
    retire(scene.troupe.player, scene.agnes, "inactive")
    assert staff_bond(scene, to_vidal["id"])["status"] == "active"


def test_changing_why_a_regnant_left_starts_or_stops_the_fade(scene: Scene) -> None:
    bond = scene.drunk(scene.agnes, scene.bram, "2026-10-03")
    retire(scene.other, scene.bram, "off_field")
    leaving = f"/characters/{scene.bram}/leaving"

    to_death = scene.troupe.storyteller.client.put(
        leaving, json={"reason": "final_death", "note": "Staked at dawn", "listed": False}
    )
    assert to_death.status_code == 200, to_death.text
    assert staff_bond(scene, bond["id"])["status"] == "fading"

    back = scene.troupe.storyteller.client.put(
        leaving, json={"reason": "off_field", "note": "He got away", "listed": False}
    )
    assert back.status_code == 200, back.text
    restored = staff_bond(scene, bond["id"])
    assert (restored["status"], restored["fades_on"], restored["fade_reason"]) == (
        "active",
        None,
        "",
    )
    assert "Agnes's bond to Bram stopped fading: Bram no longer met Final Death." in (
        scene.messages()
    )


def test_a_thralls_death_ends_its_bonds_and_the_regnant_still_sees_it(scene: Scene) -> None:
    bond = scene.drunk(scene.bram, scene.vidal, "2026-10-03")
    known = scene.drunk(scene.agnes, scene.bram, "2026-10-03")
    scene.troupe.storyteller.client.put(f"{scene.path}/{known['id']}/known", json={"known": True})
    regnant_before = scene.card(scene.bram, scene.other).json()["bound_by"]
    assert [b["name"] for b in regnant_before] == ["Agnes"]

    retire(scene.troupe.player, scene.agnes, "final_death")

    ended = staff_bond(scene, known["id"])
    assert (ended["status"], ended["kept_for_regnant"]) == ("ended", True)
    # The regnant has no sense of the thrall's death: their player sees it as it was.
    assert scene.card(scene.bram, scene.other).json()["bound_by"] == regnant_before
    # Bram's own bond, as thrall to Vidal, is untouched.
    assert staff_bond(scene, bond["id"])["status"] == "active"

    cleared = scene.troupe.storyteller.client.post(f"{scene.path}/{known['id']}/clear-kept")
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["kept_for_regnant"] is False
    assert scene.card(scene.bram, scene.other).json()["bound_by"] == []


def test_a_thrall_with_no_player_has_no_one_to_tell(scene: Scene, session: Session) -> None:
    bond = scene.drunk(scene.ghislaine, scene.bram, "2026-10-03")
    retire(scene.other, scene.bram, "final_death")
    faded_by(session, bond["id"], today() - timedelta(days=1))
    ended = staff_bond(scene, bond["id"])
    assert (ended["status"], ended["thrall_told"]) == ("ended", True)


def test_nothing_fades_while_bonds_are_off(scene: Scene) -> None:
    bond = scene.drunk(scene.agnes, scene.bram, "2026-10-03")
    assert scene.set("off").status_code == 200
    retire(scene.other, scene.bram, "final_death")
    assert scene.set("staff").status_code == 200
    assert staff_bond(scene, bond["id"])["status"] == "active"


def test_a_wiped_fading_bond_never_tells_the_thrall_it_faded(scene: Scene) -> None:
    fading = scene.drunk(scene.agnes, scene.bram, "2026-10-03")
    retire(scene.other, scene.bram, "final_death")
    scene.drunk(scene.agnes, scene.vidal, "2026-10-03", "2026-10-10", "2026-10-17")
    wiped = staff_bond(scene, fading["id"])
    assert (wiped["status"], wiped["fade_reason"]) == ("ended", "")
    deliver(scene)
    assert not any("faded" in s for s in bell(scene.troupe.player))
