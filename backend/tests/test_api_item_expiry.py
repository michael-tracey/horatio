"""Items that expire (issue #443): a troupe's setting, off by default; an expiry on a
date, after a number of the holder's games, or at the end of the open downtime cycle,
set when an item is given and extended or removed later; a warning before it comes;
and the take-back when it does, kept in the item's history."""

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio import item_expiry
from horatio.models import EquipmentItem
from tests.api_helpers import Troupe
from tests.test_api_checkin import check_in, game, past_game
from tests.test_api_downtimes import member_character, new_cycle, open_cycle
from tests.test_api_renames import character_log, summaries
from tests.test_api_troupe_equipment import change, give, given, path

BLESSING = {
    "name": "Blessing of Saulot",
    "kind": "miscellaneous",
    "grade": "special",
    "effects": [{"name": "Calm", "effect": "Once a game, ignore a frenzy test."}],
}


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def agnes(troupe: Troupe) -> str:
    return member_character(troupe, troupe.player, "Agnes")


@pytest.fixture
def expiring(troupe: Troupe) -> Troupe:
    """The troupe, with Items can expire switched on."""
    switch(troupe, on=True)
    return troupe


def switch(troupe: Troupe, *, on: bool) -> dict[str, Any]:
    response = troupe.storyteller.client.put(f"/troupes/{troupe.id}/item-expiry", json={"on": on})
    assert response.status_code == 200, response.text
    return response.json()


def held(troupe: Troupe, character_id: str) -> list[dict[str, Any]]:
    response = troupe.player.client.get(f"/characters/{character_id}/equipment")
    assert response.status_code == 200, response.text
    return response.json()["items"]


def detail(troupe: Troupe, item_id: str) -> dict[str, Any]:
    response = troupe.storyteller.client.get(f"{path(troupe)}/{item_id}")
    assert response.status_code == 200, response.text
    return response.json()


def record(session: Session, item: dict[str, Any]) -> EquipmentItem:
    return session.get_one(EquipmentItem, uuid.UUID(item["id"]))


def tomorrow_utc() -> datetime:
    """When today is over in UTC, where a player with no time zone is."""
    return datetime.combine(datetime.now(UTC).date() + timedelta(days=1), datetime.min.time(), UTC)


# --- the setting ---------------------------------------------------------------------------


def test_items_cannot_expire_until_the_troupe_switches_it_on(troupe: Troupe, agnes: str) -> None:
    assert troupe.storyteller.client.get(f"/troupes/{troupe.id}").json()["items_expire"] is False
    choices = troupe.storyteller.client.get(f"{path(troupe)}/expiry").json()
    assert choices == {"on": False, "cycle_id": None, "cycle_name": None, "cycle_closes_at": None}

    refused = give(troupe, agnes, **BLESSING, expiry={"kind": "games", "games": 2})
    assert refused.status_code == 422
    assert "switch on Items can expire" in refused.json()["detail"]

    item = given(troupe, agnes, **BLESSING)
    assert item["expiry"] is None
    assert item_expiry.check_due(troupe.session) == 0


def test_only_storytellers_switch_it(troupe: Troupe) -> None:
    response = troupe.assistant.client.put(f"/troupes/{troupe.id}/item-expiry", json={"on": True})
    assert response.status_code == 403
    assert switch(troupe, on=True)["on"] is True
    assert troupe.storyteller.client.get(f"/troupes/{troupe.id}").json()["items_expire"] is True
    log = troupe.storyteller.client.get(f"/troupes/{troupe.id}/log").json()
    assert "storyteller switched Items can expire on." in [e["message"] for e in log]


def test_switched_off_an_expiry_hides_and_waits(
    expiring: Troupe, agnes: str, session: Session
) -> None:
    today = datetime.now(UTC).date()
    item = given(expiring, agnes, **BLESSING, expiry={"kind": "date", "on": today.isoformat()})
    switch(expiring, on=False)

    assert held(expiring, agnes)[0]["expiry"] is None
    assert item_expiry.check_due(session, tomorrow_utc() + timedelta(minutes=1)) == 0
    assert record(session, item).status == "held"

    # Switched on again, it comes due as it would have.
    switch(expiring, on=True)
    assert item_expiry.check_due(session, tomorrow_utc() + timedelta(minutes=1)) == 1
    assert record(session, item).status == "taken_back"


# --- each kind -----------------------------------------------------------------------------


def test_an_item_expires_once_its_last_day_is_over(
    expiring: Troupe, agnes: str, session: Session
) -> None:
    today = datetime.now(UTC).date()
    item = given(
        expiring,
        agnes,
        **BLESSING,
        expiry={"kind": "date", "on": today.isoformat(), "note": "The blessing fades."},
    )
    assert item["expiry"] == {
        "kind": "date",
        "on": today.isoformat(),
        "games_left": None,
        "cycle_name": None,
        "cycle_closes_at": None,
        "note": "The blessing fades.",
    }
    told = summaries(expiring.player)
    assert told[0].endswith(f"It expires on {item_expiry.day_text(today)}.")

    assert item_expiry.check_due(session, tomorrow_utc() - timedelta(minutes=1)) == 0
    assert record(session, item).status == "held"
    assert item_expiry.check_due(session, tomorrow_utc()) == 1
    assert held(expiring, agnes) == []


def test_a_date_ends_where_the_player_is(expiring: Troupe, agnes: str, session: Session) -> None:
    response = expiring.player.client.patch(
        "/preferences", json={"time_zone": "America/Los_Angeles"}
    )
    assert response.status_code == 200, response.text
    today = datetime.now(UTC).date()
    item = given(expiring, agnes, **BLESSING, expiry={"kind": "date", "on": today.isoformat()})

    # Midnight UTC is still that day in California.
    assert item_expiry.check_due(session, tomorrow_utc() + timedelta(hours=1)) == 0
    assert item_expiry.check_due(session, tomorrow_utc() + timedelta(hours=9)) == 1
    assert record(session, item).status == "taken_back"


def test_a_past_day_is_refused(expiring: Troupe, agnes: str) -> None:
    yesterday = datetime.now(UTC).date() - timedelta(days=1)
    response = give(expiring, agnes, **BLESSING, expiry={"kind": "date", "on": str(yesterday)})
    assert response.status_code == 422
    assert response.json()["detail"] == "Choose a day from today on for it to expire."


def test_an_item_expires_after_the_holders_games(
    expiring: Troupe, agnes: str, session: Session
) -> None:
    item = given(expiring, agnes, **BLESSING, expiry={"kind": "games", "games": 1})
    assert item["expiry"]["games_left"] == 1
    tonight = game(expiring)
    response = check_in(expiring.assistant, expiring, tonight, agnes)
    assert response.status_code == 200, response.text

    # Held all night: it goes once the game is over.
    assert held(expiring, agnes)[0]["expiry"]["games_left"] == 1
    assert item_expiry.check_due(session) == 0
    later = datetime.now(UTC) + timedelta(hours=7)
    assert item_expiry.check_due(session, later) == 1
    assert record(session, item).status == "taken_back"


def test_a_game_recorded_after_it_ended_takes_it_at_once(
    expiring: Troupe, agnes: str, session: Session
) -> None:
    item = given(expiring, agnes, **BLESSING, expiry={"kind": "games", "games": 2})
    # Given a week and a half ago, so the past games count.
    record(session, item).expiry_from = datetime.now(UTC) - timedelta(days=10)
    session.flush()
    before = past_game(expiring, session, days_ago=8)
    last = past_game(expiring, session, days_ago=3)
    # A game the character came to before the expiry was set doesn't count.
    earlier = past_game(expiring, session, days_ago=12)
    assert check_in(expiring.assistant, expiring, earlier, agnes).status_code == 200
    assert held(expiring, agnes)[0]["expiry"]["games_left"] == 2

    assert check_in(expiring.assistant, expiring, before, agnes).status_code == 200
    assert held(expiring, agnes)[0]["expiry"]["games_left"] == 1
    assert "Agnes's Blessing of Saulot expires after its next game." in summaries(expiring.player)

    # Staff check it in by hand after the game: the check-in takes it.
    assert check_in(expiring.assistant, expiring, last, agnes).status_code == 200
    assert record(session, item).status == "taken_back"


# --- the cycle -----------------------------------------------------------------------------


def test_an_item_expires_when_the_cycle_closes(
    expiring: Troupe, agnes: str, session: Session
) -> None:
    refused = give(expiring, agnes, **BLESSING, expiry={"kind": "cycle"})
    assert refused.status_code == 422
    assert "No downtime cycle is open" in refused.json()["detail"]

    cycle = open_cycle(expiring, new_cycle(expiring, closes_in=timedelta(days=14)))
    choices = expiring.storyteller.client.get(f"{path(expiring)}/expiry").json()
    assert (choices["on"], choices["cycle_name"]) == (True, "October 2026")
    item = given(expiring, agnes, **BLESSING, expiry={"kind": "cycle"})
    assert item["expiry"]["cycle_name"] == "October 2026"

    # A week before its deadline, the player is warned.
    closes = datetime.fromisoformat(cycle["closes_at"])
    assert item_expiry.check_due(session, closes - timedelta(days=8)) == 0
    assert record(session, item).expiry_warned_at is None
    assert item_expiry.check_due(session, closes - timedelta(days=6)) == 0
    warning = "Agnes's Blessing of Saulot expires when the downtime cycle October 2026 closes."
    assert warning in summaries(expiring.player)
    # Once only.
    item_expiry.check_due(session, closes - timedelta(days=5))
    assert summaries(expiring.player).count(warning) == 1

    closed = expiring.storyteller.client.post(f"/cycles/{cycle['id']}/close")
    assert closed.status_code == 200, closed.text
    assert record(session, item).status == "taken_back"
    assert held(expiring, agnes) == []


def test_warned_at_once_when_set_inside_the_week(
    expiring: Troupe, agnes: str, session: Session
) -> None:
    open_cycle(expiring, new_cycle(expiring, closes_in=timedelta(days=3)))
    item = given(expiring, agnes, **BLESSING, expiry={"kind": "cycle"})
    # The gift said when it expires: no second message.
    assert record(session, item).expiry_warned_at is not None
    before = len(summaries(expiring.player))
    item_expiry.check_due(session)
    assert len(summaries(expiring.player)) == before


# --- taken back ----------------------------------------------------------------------------


def test_expiry_takes_it_back_with_its_history_and_tells_everyone(
    expiring: Troupe, agnes: str, session: Session
) -> None:
    today = datetime.now(UTC).date()
    item = given(
        expiring,
        agnes,
        **BLESSING,
        expiry={"kind": "date", "on": today.isoformat(), "note": "The blessing fades."},
    )
    item_expiry.check_due(session, tomorrow_utc())

    found = detail(expiring, item["id"])
    assert found["status"] == "taken_back"
    assert found["expiry"] is None
    assert found["can_change"] is False
    last = found["history"][-1]
    assert (last["action"], last["reason"], last["actor_name"]) == ("taken_back", "Expired", None)
    assert last["summary"] == "Expired, and taken back from Agnes"
    assert last["troupe_name"] == "Lords of the Night"
    assert found["history"][0]["summary"].endswith(f"; it expires on {item_expiry.day_text(today)}")

    assert (
        "Agnes's Blessing of Saulot has expired and is no longer held. The blessing fades."
        in summaries(expiring.player)
    )
    staff_told = "Agnes's Blessing of Saulot has expired, and was taken back."
    assert staff_told in summaries(expiring.storyteller)
    assert staff_told in summaries(expiring.assistant)
    assert "Blessing of Saulot expired, and was taken back from Agnes (player)." in character_log(
        expiring.storyteller, agnes
    )
    # Its qualities and effects go with it: the Play View no longer has it.
    play = expiring.player.client.get(f"/characters/{agnes}/play").json()
    assert play["equipment"] == []


# --- extended and removed ------------------------------------------------------------------


def test_staff_extend_and_remove_an_expiry(expiring: Troupe, agnes: str, session: Session) -> None:
    item = given(expiring, agnes, **BLESSING, expiry={"kind": "games", "games": 1})

    # Another change keeps it.
    kept = change(expiring, item, description="Faintly warm.", reason="Described")
    assert kept.status_code == 200, kept.text
    item = kept.json()
    assert item["expiry"]["games_left"] == 1
    # The same expiry sent back unchanged is no change.
    same = change(expiring, item, expiry={"kind": "games", "games": 1})
    assert same.status_code == 422
    assert same.json()["detail"] == "Nothing has changed."

    unsaid = change(expiring, item, expiry={"kind": "games", "games": 3})
    assert unsaid.status_code == 422
    longer = change(expiring, item, expiry={"kind": "games", "games": 3}, reason="Fed again")
    assert longer.status_code == 200, longer.text
    item = longer.json()
    assert item["expiry"]["games_left"] == 3
    assert item["history"][-1]["summary"] == "Changed: now expires after 3 more games"
    assert item["history"][-1]["changes"]["expiry"] == {
        "from": {"kind": "games", "games": 1, "note": ""},
        "to": {"kind": "games", "games": 3, "note": ""},
    }
    assert (
        "storyteller changed Agnes's Blessing of Saulot: now expires after 3 more games"
        " (Fed again)." in summaries(expiring.player)
    )

    later = (date.today() + timedelta(days=30)).isoformat()
    dated = change(expiring, item, expiry={"kind": "date", "on": later}, reason="A month")
    assert dated.status_code == 200, dated.text
    item = dated.json()
    assert item["expiry"]["on"] == later

    removed = change(expiring, item, expiry=None, reason="It stays")
    assert removed.status_code == 200, removed.text
    assert removed.json()["expiry"] is None
    assert removed.json()["history"][-1]["summary"] == "Changed: no longer expires"
    assert record(session, item).expiry_kind is None
    assert "storyteller changed Agnes's Blessing of Saulot: no longer expires (It stays)." in (
        summaries(expiring.player)
    )


def test_a_new_note_alone_is_a_change(expiring: Troupe, agnes: str) -> None:
    item = given(expiring, agnes, **BLESSING, expiry={"kind": "games", "games": 2})
    noted = change(
        expiring,
        item,
        expiry={"kind": "games", "games": 2, "note": "The blessing fades."},
        reason="Said what happens",
    )
    assert noted.status_code == 200, noted.text
    assert noted.json()["expiry"]["note"] == "The blessing fades."
    assert noted.json()["history"][-1]["summary"] == (
        "Changed: a new note on what happens when it expires"
    )
