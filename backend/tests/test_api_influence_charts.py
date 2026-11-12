"""The influence log as charts (#710): a slim copy of the log, with each targeted
action's target worked out, and who holds what influence now; for the troupe's
storytellers and assistant storytellers only."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe
from tests.test_api_influence_effects import EARLY, LATE, MIDDLE, Scene


@pytest.fixture
def scene(client_for: Callable[[], TestClient], session: Session) -> Scene:
    return Scene(Troupe(client_for, session), session)


def charts(scene: Scene, by: Person | None = None, **query: Any) -> Any:
    return (by or scene.troupe.assistant).client.get(
        f"/troupes/{scene.troupe.id}/influence-charts", params=query
    )


def holdings(scene: Scene, by: Person | None = None) -> Any:
    return (by or scene.troupe.storyteller).client.get(
        f"/troupes/{scene.troupe.id}/influence-charts/holdings"
    )


def test_staff_get_every_entry_oldest_first_with_its_level_and_target(scene: Scene) -> None:
    docks = scene.logged(
        type="underworld",
        character_id=scene.bea,
        specialization="Transportation",
        action_key="lockdown",
        purpose="To secure the docks",
        happened_at=EARLY.isoformat(),
    )
    scene.logged(
        character_id=scene.agnes,
        action_key="attack",
        times=3,
        happened_at=MIDDLE.isoformat(),
        target={"entry": docks["short_id"]},
    )
    scene.logged(
        character_id=scene.agnes,
        action_key="boost",
        happened_at=LATE.isoformat(),
        target={"character_id": scene.bea},
    )
    scene.logged(
        name="The Prince's ghoul",
        action_key="block",
        happened_at=LATE.isoformat(),
        target={"activity": "acquiring firearms"},
    )

    found = charts(scene)

    assert found.status_code == 200, found.text
    entries = found.json()["entries"]
    assert [e["short_id"] for e in entries] == ["UW1", "E1", "E2", "E3"]
    lockdown, attack, boost, block = entries
    assert (lockdown["name"], lockdown["level"], lockdown["conflict"]) == ("Bea", 5, False)
    assert lockdown["specialization"] == "Transportation"
    # The Attack on UW1 is aimed at whoever took it, though it was logged without a name.
    assert (attack["conflict"], attack["level"], attack["times"]) == (True, None, 3)
    assert (attack["target_character_id"], attack["target_name"]) == (scene.bea, "Bea")
    assert (boost["target_character_id"], boost["target_name"]) == (scene.bea, "Bea")
    assert (block["character_id"], block["name"]) == (None, "The Prince's ghoul")
    assert block["target_activity"] == "acquiring firearms"


def test_since_and_until_narrow_the_entries(scene: Scene) -> None:
    for at in (EARLY, MIDDLE, LATE):
        scene.logged(
            character_id=scene.agnes, action_key="bureaucratic_errors", happened_at=at.isoformat()
        )

    found = charts(
        scene,
        since=(MIDDLE - timedelta(minutes=1)).isoformat(),
        until=(MIDDLE + timedelta(minutes=1)).isoformat(),
    ).json()

    assert [e["happened_at"][:16] for e in found["entries"]] == [MIDDLE.isoformat()[:16]]


def test_holdings_list_the_troupes_characters_with_influence_most_first(scene: Scene) -> None:
    taken = scene.troupe.player.client.put(
        f"/characters/{scene.bea}/traits",
        json={"category": "influence_elite_specializations", "name": "News Media", "rating": 1},
    )
    assert taken.status_code == 200, taken.text

    found = holdings(scene)

    assert found.status_code == 200, found.text
    rows = [
        (h["name"], h["elite"], h["elite_specializations"], h["underworld"])
        for h in found.json()["holdings"]
    ]
    assert rows == [("Agnes", 4, [], 0), ("Bea", 3, ["News Media"], 0)]


@pytest.mark.parametrize("who", ["player", "narrator", "stranger"])
def test_only_the_staff_who_keep_the_log_see_its_charts(scene: Scene, who: str) -> None:
    scene.logged(character_id=scene.agnes, action_key="bureaucratic_errors")
    person: Person = getattr(scene.troupe, who)

    assert charts(scene, by=person).status_code in (403, 404)
    assert holdings(scene, by=person).status_code in (403, 404)
    assert charts(scene, by=scene.troupe.lead).status_code == 200
