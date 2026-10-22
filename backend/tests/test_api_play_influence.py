"""Spending influence on the Play View logs it in the troupe's influence log, and
shares one pool a month with downtimes (issue #133; MET: VtM core, p. 510)."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import Character, InfluenceEntry, OwedAction
from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_downtimes import member_character, my_downtime, new_cycle, open_cycle
from tests.test_api_play import T0, send, tap, texts, view

ELITE = "trait:backgrounds/Influences: The Elite/"
GOSSIP = {
    "action": "gossip_and_insider_trading",
    "specialization": "News Media",
    "purpose": "To hear what is said about the mayor",
}


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def agnes(troupe: Troupe) -> str:
    """At home in the troupe, with Elite 3 and a News Media specialisation."""
    character_id = member_character(troupe, troupe.player, "Agnes", elite=3)
    taken = troupe.player.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "influence_elite_specializations", "name": "News Media", "rating": 1},
    )
    assert taken.status_code == 200, taken.text
    return character_id


def spend(
    amount: int = -1, *, at: int = 0, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    return tap(ELITE, amount, at=at, **({"influence": details} if details else {}))


def undo(of: dict[str, Any], *, at: int = 30) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "happened_at": tap(at=at)["happened_at"],
        "kind": "undo",
        "undoes": of["id"],
    }


def elite(state: dict[str, Any]) -> dict[str, Any]:
    return next(e for e in state["expendables"] if e["key"] == ELITE)


def entries(troupe: Troupe, **query: Any) -> list[dict[str, Any]]:
    found = troupe.storyteller.client.get(f"/troupes/{troupe.id}/influence-log", params=query)
    assert found.status_code == 200, found.text
    return found.json()["entries"]


def elite_allowance(troupe: Troupe, character_id: str) -> int:
    return my_downtime(troupe.player, character_id).json()["allowance"]["influence_elite"]


def reset(person: Person, character_id: str) -> None:
    response = person.client.post(f"/characters/{character_id}/play/reset", json={})
    assert response.status_code == 200, response.text


# --- logging ----------------------------------------------------------------------------


def test_spending_with_details_logs_one_entry_sourced_to_the_game(
    troupe: Troupe, agnes: str
) -> None:
    before = view(troupe.player, agnes)
    assert (elite(before)["influence"], elite(before)["uses"], elite(before)["owed"]) == (
        "elite",
        3,
        0,
    )
    standing = next(s for s in before["influence"] if s["type"] == "elite")
    assert standing["held"] == ["News Media"]

    spent = spend(at=5, details=GOSSIP)
    state = send(troupe.player, agnes, spent)

    assert elite(state)["left"] == 2
    [entry] = entries(troupe)
    assert {k: entry[k] for k in ("short_id", "name", "source", "action", "times")} == {
        "short_id": "E1",
        "name": "Agnes",
        "source": "game",
        "action": "2: Gossip and Insider Trading",
        "times": 1,
    }
    assert (entry["specialization"], entry["purpose"]) == ("News Media", GOSSIP["purpose"])
    assert entry["needs_details"] is False
    assert entry["happened_at"].startswith("2026-10-17T20:05")
    assert entry["logged_by_name"] == "player"
    assert entry["play_event_id"] is not None
    assert texts(state)[0] == (
        "Elite: 2: Gossip and Insider Trading (News Media), To hear what is said about the mayor"
    )
    assert state["log"][0]["influence"]["short_id"] == "E1"


def test_skipping_the_details_still_logs_it_as_needing_them(troupe: Troupe, agnes: str) -> None:
    state = send(troupe.player, agnes, spend())

    [entry] = entries(troupe)
    assert entry["needs_details"] is True
    assert entry["action_key"] is None
    assert entries(troupe, needs_details=True) == [entry]
    assert texts(state)[0] == "Elite: details to come"


def test_several_uses_at_once_are_one_entry_taken_that_many_times(
    troupe: Troupe, agnes: str
) -> None:
    state = send(troupe.player, agnes, spend(-2, details=GOSSIP))

    assert elite(state)["left"] == 1
    [entry] = entries(troupe)
    assert entry["times"] == 2
    assert texts(state)[0].startswith("Elite ×2: 2: Gossip and Insider Trading")


def test_details_that_do_not_fit_are_kept_and_the_entry_needs_details(
    troupe: Troupe, agnes: str
) -> None:
    # Sent from a phone that was offline: refusing it would lose every later tap.
    send(
        troupe.player,
        agnes,
        spend(details={"action": "no_party_crashers", "specialization": "Finance"}),
    )

    [entry] = entries(troupe)
    assert entry["action"] == "5: No Party Crashers"
    assert entry["specialization"] == ""
    assert entry["needs_details"] is True


def test_staff_spending_for_a_player_are_recorded_as_theirs(troupe: Troupe, agnes: str) -> None:
    send(troupe.storyteller, agnes, spend(details=GOSSIP))

    [entry] = entries(troupe)
    assert entry["logged_by_name"] == "storyteller"


def test_other_uses_a_game_log_nothing(troupe: Troupe, agnes: str, session: Session) -> None:
    bought = troupe.player.client.put(
        f"/characters/{agnes}/traits",
        json={"category": "backgrounds", "name": "Herd", "rating": 2},
    )
    assert bought.status_code == 200, bought.text

    state = send(troupe.player, agnes, tap("trait:backgrounds/Herd/", -1, note="fed"))

    assert texts(state)[0] == "Herd 2 → 1"
    assert entries(troupe) == []
    assert session.scalars(select(OwedAction)).all() == []


def test_an_npc_logs_in_the_troupe_that_keeps_it_and_owes_nothing(
    troupe: Troupe, session: Session
) -> None:
    made = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/npcs", json={"name": "Lucien", "wizard": False}
    )
    assert made.status_code == 201, made.text
    npc = made.json()["id"]
    rated = troupe.storyteller.client.put(
        f"/characters/{npc}/npc/ratings",
        json={"category": "backgrounds", "name": "Influences: The Elite", "rating": 2},
    )
    assert rated.status_code == 200, rated.text

    send(troupe.storyteller, npc, spend(details={**GOSSIP, "specialization": ""}))

    [entry] = entries(troupe)
    assert (entry["name"], entry["needs_details"]) == ("Lucien", False)
    assert session.scalars(select(OwedAction)).all() == []


def test_a_character_in_no_troupe_spends_as_before(troupe: Troupe) -> None:
    loner = new_character(troupe, troupe.player, "Loner")
    bought = troupe.player.client.put(
        f"/characters/{loner}/traits",
        json={"category": "backgrounds", "name": "Influences: The Elite", "rating": 1},
    )
    assert bought.status_code == 200, bought.text

    state = send(troupe.player, loner, spend())

    assert state["influence"] == []
    assert elite(state)["left"] == 0
    assert texts(state)[0] == "Influences: The Elite 1 → 0"


# --- undo -------------------------------------------------------------------------------


def test_undo_takes_the_entry_off_the_log_and_cancels_what_is_owed(
    troupe: Troupe, agnes: str, session: Session
) -> None:
    spent = spend(details=GOSSIP)
    send(troupe.player, agnes, spent)
    assert len(session.scalars(select(OwedAction)).all()) == 1

    state = send(troupe.player, agnes, undo(spent))

    assert elite(state)["left"] == 3
    assert entries(troupe) == []
    assert session.scalars(select(OwedAction)).all() == []
    assert texts(state)[0] == "Undid: Influences: The Elite 3 → 2"


def test_the_log_says_when_staff_have_changed_a_spend(troupe: Troupe, agnes: str) -> None:
    spent = spend()
    state = send(troupe.player, agnes, spent)
    assert state["log"][0]["influence"]["changed_by_staff"] is False
    entry = state["log"][0]["influence"]

    changed = troupe.storyteller.client.put(
        f"/influence-entries/{entry['entry_id']}",
        json={
            "type": "elite",
            "happened_at": T0.isoformat(),
            "character_id": agnes,
            "action_key": "a_friend_in_need",
            "purpose": "Finished by staff",
        },
    )
    assert changed.status_code == 200, changed.text

    state = view(troupe.player, agnes)
    assert state["log"][0]["influence"]["changed_by_staff"] is True
    assert texts(state)[0] == "Elite: 1: A Friend in Need, Finished by staff"


# --- details later ----------------------------------------------------------------------


def test_the_player_adds_details_until_the_game_ends(troupe: Troupe, agnes: str) -> None:
    spent = spend()
    send(troupe.player, agnes, spent)
    path = f"/characters/{agnes}/play/taps/{spent['id']}/influence"

    given = troupe.player.client.put(path, json=GOSSIP)

    assert given.status_code == 200, given.text
    [entry] = entries(troupe)
    assert (entry["action_key"], entry["needs_details"]) == (GOSSIP["action"], False)
    assert given.json()["log"][0]["influence"]["changed_by_staff"] is False
    log = troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()
    assert any("gave the details of E1 at a game" in e["message"] for e in log)

    # Details that do not fit are refused here: the player is there to fix them.
    unreachable = troupe.player.client.put(path, json={**GOSSIP, "action": "no_party_crashers"})
    assert unreachable.status_code == 422

    reset(troupe.player, agnes)
    late = troupe.player.client.put(path, json={**GOSSIP, "purpose": "Changed my mind"})
    assert late.status_code == 403
    by_staff = troupe.storyteller.client.put(path, json={**GOSSIP, "purpose": "Tidied"})
    assert by_staff.status_code == 200, by_staff.text
    assert entries(troupe)[0]["purpose"] == "Tidied"


def test_details_need_a_tap_that_spent_influence(troupe: Troupe, agnes: str) -> None:
    blood = tap()
    send(troupe.player, agnes, blood)

    found = troupe.player.client.put(
        f"/characters/{agnes}/play/taps/{blood['id']}/influence", json=GOSSIP
    )

    assert found.status_code == 404


# --- one pool a month -------------------------------------------------------------------


def test_spending_two_at_a_game_leaves_the_next_cycle_two_lower(troupe: Troupe, agnes: str) -> None:
    send(troupe.player, agnes, spend(details=GOSSIP), spend(at=10))
    assert elite(view(troupe.player, agnes))["owed"] == 0  # its own taps count them

    cycle = open_cycle(troupe, new_cycle(troupe))

    assert elite_allowance(troupe, agnes) == 1
    adjustments = my_downtime(troupe.player, agnes).json()["adjustments"]
    assert [(a["action_kind"], a["delta"], a["reason"]) for a in adjustments] == [
        ("influence_elite", -1, "Spent at the 17 Oct game"),
        ("influence_elite", -1, "Spent at the 17 Oct game"),
    ]
    [participant] = troupe.storyteller.client.get(f"/cycles/{cycle['id']}/participants").json()
    assert participant["shortfall"] == {}


def test_undo_after_the_cycle_took_it_gives_the_action_back(troupe: Troupe, agnes: str) -> None:
    spent = spend(-2, details=GOSSIP)
    send(troupe.player, agnes, spent)
    open_cycle(troupe, new_cycle(troupe))
    assert elite_allowance(troupe, agnes) == 1

    send(troupe.player, agnes, undo(spent))

    assert elite_allowance(troupe, agnes) == 3
    assert my_downtime(troupe.player, agnes).json()["adjustments"] == []


def test_a_game_starts_lower_by_what_earlier_games_spent(troupe: Troupe, agnes: str) -> None:
    send(troupe.player, agnes, spend(-2, details=GOSSIP))
    reset(troupe.player, agnes)

    state = view(troupe.player, agnes)
    assert (elite(state)["uses"], elite(state)["left"], elite(state)["owed"]) == (1, 1, 2)

    # A cycle takes them off, and the next game has the whole rating again.
    open_cycle(troupe, new_cycle(troupe))
    state = view(troupe.player, agnes)
    assert (elite(state)["uses"], elite(state)["left"], elite(state)["owed"]) == (3, 3, 0)


def test_the_allowance_stops_at_zero_and_staff_see_the_shortfall(
    troupe: Troupe, agnes: str
) -> None:
    # Two phones, both offline at the game, spent five between them.
    send(troupe.player, agnes, spend(-3, details=GOSSIP), spend(-2, at=5))

    cycle = open_cycle(troupe, new_cycle(troupe))

    assert elite_allowance(troupe, agnes) == 0
    [participant] = troupe.storyteller.client.get(f"/cycles/{cycle['id']}/participants").json()
    assert participant["allowance"]["influence_elite"] == 0
    assert participant["shortfall"] == {"influence_elite": 2}


def test_spends_wait_for_the_next_cycle_even_while_one_is_open(
    troupe: Troupe, agnes: str, session: Session
) -> None:
    open_cycle(troupe, new_cycle(troupe))

    send(troupe.player, agnes, spend(details=GOSSIP))

    assert elite_allowance(troupe, agnes) == 3
    [debt] = session.scalars(select(OwedAction)).all()
    assert debt.participant_id is None
    assert session.scalars(select(InfluenceEntry.source)).all() == ["game"]


def test_only_spends_at_games_lower_the_next_game(
    troupe: Troupe, agnes: str, session: Session
) -> None:
    # Owed influence from anything else, such as an Attack (#136), reaches the
    # counter through the rating, so it is not counted twice.
    character = session.get_one(Character, uuid.UUID(agnes))
    assert character.home_troupe_id is not None
    session.add(
        OwedAction(
            character_id=character.id,
            troupe_id=character.home_troupe_id,
            action_kind="influence_elite",
            amount=1,
            reason="Lost to an Attack",
            owed_by=character.player_id,
        )
    )
    session.flush()
    send(troupe.player, agnes, spend(details=GOSSIP))
    reset(troupe.player, agnes)

    state = view(troupe.player, agnes)
    assert (elite(state)["uses"], elite(state)["owed"]) == (2, 1)
