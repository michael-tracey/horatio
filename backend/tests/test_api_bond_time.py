"""Blood bonds fading with time (#665; MET: VTM p. 296, and the Errata's p. 295): a full
bond drops to two drinks after three months without drinking, a two-drink bond ends
after six months apart, a one-drink bond after a year. Games both checked in at, and
meetings staff or players log, keep a lesser bond alive. The thrall's player learns of
a change only with the next downtime results. In "players_report" staff confirm each
change. Staff recording past a full bond's immunity need a reason."""

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.bonds import add_months, today
from horatio.models import (
    BloodBond,
    BondEntry,
    Character,
    GameAttendance,
    ScheduledGame,
)
from horatio.models import (
    Troupe as TroupeRow,
)
from tests.api_helpers import Troupe
from tests.test_api_bond_fading import bell, deliver, staff_bond, thrall_card
from tests.test_api_bond_reports import Players, tonight


@pytest.fixture
def scene(client_for: Callable[[], TestClient], session: Session) -> Players:
    return Players(Troupe(client_for, session))


def age(session: Session, scene: Players, bond_id: str, days: int, clock: bool = True) -> None:
    """Move a bond, its log and (with `clock`) the troupe's clock `days` into the past,
    as time passing would."""
    back = timedelta(days=days)
    bond = session.get_one(BloodBond, uuid.UUID(bond_id))
    bond.created_at = bond.created_at - back
    for entry in session.scalars(select(BondEntry).where(BondEntry.bond_id == bond.id)):
        entry.night = entry.night - back
    if clock:
        troupe = session.get_one(TroupeRow, uuid.UUID(scene.troupe.id))
        troupe.bond_clock_from = troupe.bond_clock_from - back
    session.commit()


def months(n: int) -> int:
    """Days enough for `n` months to have passed, whatever the months."""
    return (today() - add_months(today(), -n)).days + 1


def both_came(session: Session, scene: Players, *characters: str, days_ago: int) -> None:
    """A game both characters checked in at, `days_ago`."""
    starts = datetime.now(UTC) - timedelta(days=days_ago)
    game = ScheduledGame(
        troupe_id=uuid.UUID(scene.troupe.id), starts_at=starts, ends_at=starts + timedelta(hours=4)
    )
    session.add(game)
    session.flush()
    for character_id in characters:
        character = session.get_one(Character, uuid.UUID(character_id))
        assert character.player_id is not None
        session.add(
            GameAttendance(
                game_id=game.id, character_id=character.id, checked_in_by=character.player_id
            )
        )
    session.commit()


def nights(n: int) -> list[str]:
    return [(today() - timedelta(days=i)).isoformat() for i in range(n, 0, -1)]


def card_level(scene: Players) -> list[int]:
    return [b["level"] for b in thrall_card(scene)["bound_to"]]


def test_a_full_bond_drops_after_three_months_and_the_thrall_learns_at_results(
    scene: Players, session: Session
) -> None:
    bond = scene.drunk(scene.agnes, scene.bram, *nights(3))
    assert bond["level"] == 3
    assert bond["next_change"]["kind"] == "drop"
    age(session, scene, bond["id"], months(3))

    # Staff see the truth at once: two drinks, and when it ends unless the two meet.
    dropped = staff_bond(scene, bond["id"])
    assert (dropped["status"], dropped["level"]) == ("active", 2)
    assert dropped["entries"][-1]["kind"] == "dropped"
    assert dropped["entries"][-1]["recorded_by"] is None
    assert dropped["next_change"]["kind"] == "end"
    assert any("dropped to two drinks" in m for m in scene.messages())
    # The thrall's player still sees a full bond, and hears nothing yet.
    assert card_level(scene) == [3]
    assert not any("weakened" in s for s in bell(scene.troupe.player))

    deliver(scene)
    assert card_level(scene) == [2]
    assert "Agnes's bond to Bram has weakened." in bell(scene.troupe.player)
    deliver(scene)
    assert bell(scene.troupe.player).count("Agnes's bond to Bram has weakened.") == 1


def test_lesser_bonds_end_after_six_months_or_a_year_apart(
    scene: Players, session: Session
) -> None:
    two = scene.drunk(scene.agnes, scene.bram, *nights(2))
    one = scene.drunk(scene.cora, scene.bram, *nights(1))
    age(session, scene, two["id"], months(7))

    ended = staff_bond(scene, two["id"])
    assert (ended["status"], ended["fade_reason"], ended["thrall_told"]) == (
        "ended",
        "apart",
        False,
    )
    # The thrall's sheet shows it until the results, which say only that it faded.
    assert card_level(scene) == [2]
    deliver(scene)
    assert thrall_card(scene)["bound_to"] == []
    assert "Agnes's bond to Bram has faded." in bell(scene.troupe.player)

    # A single drink lasts a year.
    age(session, scene, one["id"], months(7), clock=False)
    assert staff_bond(scene, one["id"])["status"] == "active"
    age(session, scene, one["id"], months(6))
    assert staff_bond(scene, one["id"])["status"] == "ended"


def test_games_both_checked_in_at_and_logged_meetings_keep_a_lesser_bond(
    scene: Players, session: Session
) -> None:
    bond = scene.drunk(scene.agnes, scene.bram, *nights(2))
    age(session, scene, bond["id"], months(7))
    both_came(session, scene, scene.agnes, scene.bram, days_ago=30)
    kept = staff_bond(scene, bond["id"])
    assert kept["status"] == "active"
    assert kept["last_met"] == (today() - timedelta(days=30)).isoformat()
    # A game only one of them came to is no meeting.
    other = scene.drunk(scene.cora, scene.bram, *nights(2))
    age(session, scene, other["id"], months(7))
    both_came(session, scene, scene.cora, days_ago=10)
    assert staff_bond(scene, other["id"])["status"] == "ended"

    # Staff log a meeting, such as one in a downtime.
    third = scene.drunk(scene.agnes, scene.vidal, *nights(1))
    met = scene.troupe.storyteller.client.post(
        f"{scene.path}/{third['id']}/meetings",
        json={"night": tonight(), "source": "downtime", "note": "Tea at the Elysium"},
    )
    assert met.status_code == 201, met.text
    assert met.json()["last_met"] == tonight()
    assert met.json()["entries"][-1]["kind"] == "meeting"
    assert met.json()["level"] == 1
    assert any("meeting on" in m for m in scene.messages())


def test_in_players_report_staff_confirm_each_change(scene: Players, session: Session) -> None:
    bond = scene.drunk(scene.agnes, scene.bram, *nights(3))
    assert scene.set("players_report").status_code == 200
    age(session, scene, bond["id"], months(3))

    waiting = staff_bond(scene, bond["id"])
    assert waiting["level"] == 3
    assert waiting["next_change"]["kind"] == "drop"
    assert waiting["next_change"]["due"] is True
    path = f"{scene.path}/{bond['id']}/confirm-change"
    for person in (scene.troupe.player, scene.troupe.narrator):
        assert person.client.post(path).status_code in (403, 404)
    confirmed = scene.troupe.storyteller.client.post(path)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["level"] == 2
    assert confirmed.json()["entries"][-1]["recorded_by"] is not None
    # Nothing more is due.
    assert scene.troupe.storyteller.client.post(path).status_code == 409


def test_players_log_meetings_by_the_troupes_mode(scene: Players) -> None:
    bond = scene.drunk(scene.agnes, scene.bram, *nights(2))
    path = f"/characters/{scene.agnes}/bonds/{bond['id']}/meetings"
    body: dict[str, Any] = {"night": tonight(), "source": "downtime"}

    # Staff manage: players don't log them.
    assert scene.troupe.player.client.post(path, json=body).status_code == 409
    assert thrall_card(scene)["bound_to"][0]["can_meet"] is False

    assert scene.set("players_manage").status_code == 200
    assert thrall_card(scene)["bound_to"][0]["can_meet"] is True
    # Only for their own character's bond.
    assert (
        scene.other.client.post(
            f"/characters/{scene.bram}/bonds/{bond['id']}/meetings", json=body
        ).status_code
        == 422
    )
    recorded = scene.troupe.player.client.post(path, json=body)
    assert recorded.status_code == 201, recorded.text
    assert recorded.json()["outcome"] == "recorded"
    assert staff_bond(scene, bond["id"])["entries"][-1]["kind"] == "meeting"

    assert scene.set("players_report").status_code == 200
    waits = scene.troupe.player.client.post(path, json=body)
    assert waits.status_code == 201, waits.text
    assert waits.json()["outcome"] == "staff"
    [asked] = scene.queue()
    assert asked["bond"]["kind"] == "meeting"
    assert asked["bond"]["refused"] is None
    [mine] = scene.card_reports(scene.agnes, scene.troupe.player)
    assert (mine["kind"], mine["status"]) == ("meeting", "pending")
    approved = scene.troupe.storyteller.client.post(f"/approvals/{asked['id']}/approve", json={})
    assert approved.status_code == 200, approved.text
    meetings = [e for e in staff_bond(scene, bond["id"])["entries"] if e["kind"] == "meeting"]
    assert len(meetings) == 2
    assert any("and Bram meeting on" in s for s in scene.notes(scene.troupe.player))


def test_staff_recording_past_a_full_bond_need_a_reason(scene: Players) -> None:
    scene.drunk(scene.agnes, scene.bram, *nights(3))
    refused = scene.drink(scene.agnes, scene.vidal, tonight())
    assert refused.status_code == 409
    assert "immune" in refused.json()["detail"]
    assert "Give a reason" in refused.json()["detail"]
    entered = scene.enter(scene.agnes, scene.vidal, level=1)
    assert entered.status_code == 409

    anyway = scene.drink(scene.agnes, scene.vidal, tonight(), override="The Prince's command")
    assert anyway.status_code == 201, anyway.text
    assert any(
        "though a full bond made them immune: The Prince's command" in m
        for m in scene.messages()
    )
    # The regnant of the full bond can always add to it.
    assert scene.drink(scene.agnes, scene.bram, tonight()).status_code == 201


def test_switching_bonds_back_on_restarts_the_clocks(scene: Players, session: Session) -> None:
    bond = scene.drunk(scene.agnes, scene.bram, *nights(3))
    assert scene.set("off").status_code == 200
    age(session, scene, bond["id"], months(4))
    assert scene.set("staff").status_code == 200
    kept = staff_bond(scene, bond["id"])
    assert kept["level"] == 3
    assert kept["next_change"]["on"] == add_months(today(), 3).isoformat()


def test_add_months_keeps_to_the_month() -> None:
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)
    assert add_months(date(2026, 5, 15), 12) == date(2027, 5, 15)
