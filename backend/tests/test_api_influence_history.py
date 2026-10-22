"""A character's influence history (#135), and what the Log influence tool (#134)
needs: who sees the history, what it shows and hides, Findable now, finishing a
game entry, and a character's specialisations and allowance for the tool."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import influence_log
from horatio.models import OwedAction, PlayEvent, ScheduledGame
from horatio.models import Troupe as TroupeRow
from tests.api_helpers import Person, Troupe
from tests.test_api_influence_log import AT, Scene
from tests.test_api_play import send, tap

NOW = datetime.now(UTC)


@pytest.fixture
def scene(client_for: Callable[[], TestClient], session: Session) -> Scene:
    return Scene(Troupe(client_for, session), session)


def history(scene: Scene, by: Person | None = None, character: str | None = None) -> Any:
    return (by or scene.troupe.player).client.get(
        f"/characters/{character or scene.agnes}/influence"
    )


def entries(scene: Scene, by: Person | None = None) -> list[dict[str, Any]]:
    found = history(scene, by)
    assert found.status_code == 200, found.text
    return found.json()["entries"]


def game_entry(scene: Scene) -> dict[str, Any]:
    """An Elite use Agnes spent at a game still going, logged without its details."""
    first = tap()
    send(scene.troupe.player, scene.agnes, first)
    event = scene.session.scalars(
        select(PlayEvent).where(PlayEvent.client_id == uuid.UUID(first["id"]))
    ).one()
    troupe = scene.session.get_one(TroupeRow, uuid.UUID(scene.troupe.id))
    entry = influence_log.add_entry(
        scene.session,
        None,
        troupe,
        influence_log.Details(
            influence_type="elite",
            happened_at=NOW,
            character_id=uuid.UUID(scene.agnes),
            needs_details=True,
        ),
        source="game",
        play_event_id=event.id,
    )
    return next(e for e in entries(scene) if e["id"] == str(entry.id))


# --- who sees it ------------------------------------------------------------------------


def test_the_player_sees_their_characters_own_entries_from_every_source(scene: Scene) -> None:
    scene.log(scene.responses[0], "To hear about the mayor")
    scene.add(
        type="elite",
        character_id=scene.agnes,
        action_key="smooth_over",
        happened_at=AT.isoformat(),
        cycle_id=scene.cycle["id"],
    )
    # Someone else's, naming Agnes in its purpose: never hers to see.
    scene.add(purpose="To find out where Agnes sleeps")

    found = entries(scene)

    # Newest first: the downtime was submitted today, the other logged for July.
    assert [(e["short_id"], e["source"]) for e in found] == [("E1", "downtime"), ("E2", "hand")]
    downtime, by_hand = found
    assert (by_hand["action"], by_hand["cycle_name"]) == ("4: Smooth Over", "October 2026")
    assert (downtime["specialization"], downtime["action"], downtime["purpose"]) == (
        "News Media",
        "2: Gossip and Insider Trading",
        "To hear about the mayor",
    )
    assert (downtime["troupe_name"], downtime["other_troupe"]) == ("Lords of the Night", False)
    # Staff see nothing a player could use to learn who logged it, or others' blocks.
    assert "blocks" not in downtime and "logged_by_name" not in downtime and "name" not in downtime


def test_the_home_troupes_storytellers_see_it_and_no_one_else(scene: Scene) -> None:
    troupe = scene.troupe
    for person in (troupe.lead, troupe.storyteller, troupe.assistant, troupe.custodian):
        assert history(scene, person).status_code == 200
    for person in (troupe.narrator, troupe.stranger):
        assert history(scene, person).status_code == 404
    assert history(scene).json()["log_troupe_id"] is None
    assert history(scene, troupe.assistant).json()["log_troupe_id"] == troupe.id


def test_an_npcs_history_is_for_its_troupes_staff(scene: Scene) -> None:
    npc = scene.troupe.storyteller.client.post(
        f"/troupes/{scene.troupe.id}/npcs", json={"name": "Prince Vasquez"}
    ).json()
    scene.add(type="elite", character_id=npc["id"], action_key="smooth_over")

    seen = history(scene, scene.troupe.assistant, npc["id"])

    assert seen.status_code == 200, seen.text
    assert [e["action"] for e in seen.json()["entries"]] == ["4: Smooth Over"]
    assert history(scene, scene.troupe.player, npc["id"]).status_code == 404
    assert history(scene, scene.troupe.narrator, npc["id"]).status_code == 404


def test_entries_from_a_troupe_it_has_left_stay_labelled_with_that_troupe(scene: Scene) -> None:
    scene.log(scene.responses[0], "To hear about the mayor")

    left = scene.troupe.player.client.delete(f"/characters/{scene.agnes}/troupes/{scene.troupe.id}")

    assert left.status_code == 204, left.text
    kept = entries(scene)
    assert [(e["short_id"], e["troupe_name"], e["other_troupe"]) for e in kept] == [
        ("E1", "Lords of the Night", True)
    ]
    # Its old troupe's staff no longer see its history.
    assert history(scene, scene.troupe.assistant).status_code == 404


# --- what it shows ----------------------------------------------------------------------


def test_blocks_others_placed_never_show(scene: Scene) -> None:
    scene.add(type="elite", character_id=scene.agnes, action_key="smooth_over", blocks=2)

    assert [e["own_blocks"] for e in entries(scene)] == [0]


def test_findable_now_is_the_lookback_to_the_minute_without_conflict_actions(
    scene: Scene,
) -> None:
    now = datetime.now(UTC)

    def add(days: float, action: str = "smooth_over", **extra: Any) -> None:
        when = now - timedelta(days=days)
        added = scene.add(
            type="elite",
            character_id=scene.agnes,
            action_key=action,
            happened_at=when.isoformat(),
            **extra,
        )
        assert added.status_code == 201, added.text

    add(90, "a_friend_in_need")  # a minute or so outside, by the time it is read
    add(89.99)
    add(1, "attack", target={"character_id": scene.agnes})

    found = history(scene).json()

    assert found["lookback_days"] == 90
    assert [(e["action"], e["findable"]) for e in found["entries"]] == [
        ("Attack", False),
        ("4: Smooth Over", True),
        ("1: A Friend in Need", False),
    ]


def test_the_months_summary_has_ratings_and_actions_owed(scene: Scene) -> None:
    from horatio.models import User

    lead = scene.session.scalars(select(User).where(User.email == "lead@example.com")).one()
    scene.session.add(
        OwedAction(
            character_id=uuid.UUID(scene.agnes),
            troupe_id=uuid.UUID(scene.troupe.id),
            action_kind="influence_elite",
            amount=2,
            reason="Spent at the 11 Jul game",
            owed_by=lead.id,
        )
    )
    scene.session.flush()

    found = history(scene).json()

    assert {s["type"]: s["rating"] for s in found["standings"]} == {"elite": 2, "underworld": 0}
    assert {o["type"]: o["amount"] for o in found["owed"]} == {"elite": 2, "underworld": 0}


# --- finishing a game entry -------------------------------------------------------------


def test_the_player_finishes_a_game_entry_while_the_game_goes_on(scene: Scene) -> None:
    entry = game_entry(scene)
    assert (entry["needs_details"], entry["can_finish"], entry["action"]) == (
        True,
        True,
        "No action yet",
    )
    assert entry["game_number"] == 1
    path = f"/characters/{scene.agnes}/influence/{entry['id']}"
    player = scene.troupe.player.client

    # Elite 2 reaches level 3 only with one of her own specialisations.
    out_of_reach = player.put(path, json={"action_key": "bureaucratic_errors"})
    assert out_of_reach.status_code == 422
    assert out_of_reach.json()["detail"] == (
        "3: Bureaucratic Errors needs Elite 3, or 2 with one of your Elite specialisations."
    )
    finished = player.put(
        path,
        json={
            "specialization": "News Media",
            "action_key": "bureaucratic_errors",
            "purpose": "To lose the coroner's report",
        },
    )

    assert finished.status_code == 200, finished.text
    assert (finished.json()["action"], finished.json()["needs_details"]) == (
        "3: Bureaucratic Errors",
        False,
    )
    assert finished.json()["can_finish"] is False
    assert scene.messages()[0].startswith("player changed E1 in the influence log:")


def test_a_game_entry_cannot_be_finished_here_once_the_game_ends(scene: Scene) -> None:
    entry = game_entry(scene)
    reset = scene.troupe.player.client.post(f"/characters/{scene.agnes}/play/reset", json={})
    assert reset.status_code == 200, reset.text

    assert entries(scene)[0]["can_finish"] is False
    refused = scene.troupe.player.client.put(
        f"/characters/{scene.agnes}/influence/{entry['id']}", json={"action_key": "smooth_over"}
    )
    assert refused.status_code == 422


def test_only_the_characters_own_entries_can_be_finished(scene: Scene) -> None:
    other = scene.add(action_key=None, needs_details=True).json()

    refused = scene.troupe.player.client.put(
        f"/characters/{scene.agnes}/influence/{other['id']}", json={"action_key": "lockdown"}
    )

    assert refused.status_code == 404


# --- the Log influence tool -------------------------------------------------------------


def test_the_tool_knows_a_characters_specialisations_and_allowance(scene: Scene) -> None:
    scene.log(scene.responses[0], "To hear about the mayor")
    scene.add(type="elite", character_id=scene.agnes, action_key="smooth_over", times=2,
              cycle_id=scene.cycle["id"])  # fmt: skip
    path = f"{scene.path}/characters/{scene.agnes}"

    found = scene.troupe.assistant.client.get(path, params={"cycle_id": scene.cycle["id"]})

    assert found.status_code == 200, found.text
    elite = next(s for s in found.json()["standings"] if s["type"] == "elite")
    assert elite["held"] == ["News Media"]
    assert {c["type"]: (c["allowance"], c["logged"]) for c in found.json()["cycle"]} == {
        "elite": (2, 3),
        "underworld": (0, 0),
    }
    assert scene.troupe.assistant.client.get(path).json()["cycle"] == []
    assert scene.troupe.narrator.client.get(path).status_code == 403


def test_an_npc_has_no_allowance(scene: Scene) -> None:
    npc = scene.troupe.storyteller.client.post(
        f"/troupes/{scene.troupe.id}/npcs", json={"name": "Prince Vasquez"}
    ).json()

    found = scene.troupe.assistant.client.get(
        f"{scene.path}/characters/{npc['id']}", params={"cycle_id": scene.cycle["id"]}
    )

    assert [c["allowance"] for c in found.json()["cycle"]] == [None, None]


def test_the_tool_dates_an_entry_by_a_cycle_or_a_game(scene: Scene) -> None:
    troupe_id = uuid.UUID(scene.troupe.id)
    for days in (10, 3, -5):  # two past games and one to come
        start = NOW - timedelta(days=days)
        scene.session.add(
            ScheduledGame(troupe_id=troupe_id, starts_at=start, ends_at=start + timedelta(hours=4))
        )
    scene.session.flush()

    choices = scene.troupe.assistant.client.get(f"{scene.path}/choices").json()

    assert [datetime.fromisoformat(g["starts_at"]).date() for g in choices["games"]] == [
        (NOW - timedelta(days=3)).date(),
        (NOW - timedelta(days=10)).date(),
    ]
    cycle = choices["cycles"][0]
    assert cycle["opened_at"] is not None and cycle["closes_at"] == scene.cycle["closes_at"]
