"""A troupe's chronicle (#711): its history in one timeline, gathered from what Horatio
records with dates, every event for its running staff, and for its players, where
the troupe lets them, only what it already shows them."""

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.models import Boonbreaker, Diablerie, Embrace, HeldStatus
from tests.api_helpers import Person, Troupe
from tests.test_api_leaving import retire
from tests.test_api_npc_copies import built, copied
from tests.test_api_sect_status import add, entitle, member


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def chronicle(person: Person, troupe: Troupe) -> dict[str, Any]:
    response = person.client.get(f"/troupes/{troupe.id}/chronicle")
    assert response.status_code == 200, response.text
    return response.json()


def kinds(found: dict[str, Any]) -> set[tuple[str, str, str]]:
    return {(e["kind"], e["character_name"], e["label"]) for e in found["events"]}


def embraced(troupe: Troupe, character_id: str, on: date, **more: Any) -> None:
    """An Embrace run in play, written straight: the chronicle only reads it."""
    troupe.session.add(
        Embrace(
            character_id=uuid.UUID(character_id),
            troupe_id=uuid.UUID(troupe.id),
            result=more.pop("result", "vampire"),
            embraced_on=on,
            sire_name=more.pop("sire_name", "Lucien"),
            sire_clan=more.pop("sire_clan", "Ventrue"),
            recorded_by=uuid.UUID(troupe.storyteller.id),
            **more,
        )
    )
    troupe.session.flush()


def diablerized(troupe: Troupe, character_id: str, on: date, *, recorded: bool = True) -> None:
    troupe.session.add(
        Diablerie(
            character_id=uuid.UUID(character_id),
            troupe_id=uuid.UUID(troupe.id),
            committed_on=on,
            victim="Elder Mercy",
            requested_by=uuid.UUID(troupe.storyteller.id),
            recorded_by=uuid.UUID(troupe.storyteller.id) if recorded else None,
            recorded_at=datetime.now(UTC) if recorded else None,
        )
    )
    troupe.session.flush()


def history(troupe: Troupe) -> dict[str, str]:
    """A troupe with something of every kind: returns the characters by name."""
    agnes = member(troupe, "Agnes")
    roth = member(troupe, "Roth")
    lena = member(troupe, "Lena")
    entitle(troupe, agnes, "Prince")
    given = add(troupe.storyteller, roth, "Loyal", given_on="1890-03-01", reason="Held Elysium")
    assert given.status_code == 200, given.text
    embraced(troupe, lena, date(1791, 6, 2))
    diablerized(troupe, roth, date(2026, 10, 3))
    diablerized(troupe, agnes, date(2026, 10, 4), recorded=False)  # waits on an approval
    retire(troupe.player, lena, reason="final_death", listed=True)
    return {"Agnes": agnes, "Roth": roth, "Lena": lena}


def test_staff_see_every_kind_of_event_with_its_dates(troupe: Troupe) -> None:
    history(troupe)
    found = chronicle(troupe.storyteller, troupe)
    assert found["full"] is True and found["players_see"] is False
    assert {
        ("title", "Agnes", "Prince"),
        ("status", "Roth", "Loyal"),
        ("embrace", "Lena", "Embraced"),
        ("diablerie", "Roth", "Diablerie"),
        ("death", "Lena", "Final Death"),
        ("arrival", "Agnes", "Accepted as home"),
    } <= kinds(found)
    # A diablerie waiting on its approval isn't history yet.
    assert ("diablerie", "Agnes", "Diablerie") not in kinds(found)

    by = {(e["kind"], e["character_name"]): e for e in found["events"]}
    assert by["embrace", "Lena"]["on"] == "1791-06-02"
    assert by["embrace", "Lena"]["detail"] == "By Lucien (Ventrue)"
    assert by["status", "Roth"]["on"] == "1890-03-01"
    assert by["diablerie", "Roth"]["detail"] == "Of Elder Mercy"
    # Joining, retiring and dying have no in-game date.
    assert by["death", "Lena"]["on"] is None
    assert by["arrival", "Agnes"]["on"] is None
    # A title held still is a span with no end.
    prince = by["title", "Agnes"]
    assert prince["ongoing"] is True and prince["ends_at"] is None
    # Oldest first, by when Horatio recorded it.
    moments = [e["at"] for e in found["events"]]
    assert moments == sorted(moments)


def test_events_recorded_together_keep_the_order_they_were_made(troupe: Troupe) -> None:
    """Rows written in one transaction share created_at: the id breaks the tie (#733)."""
    agnes = member(troupe, "Agnes")
    # Status first, then an Embrace, both in this one transaction: the kinds' names
    # would sort the other way.
    troupe.session.add(
        HeldStatus(
            character_id=uuid.UUID(agnes),
            name="Loyal",
            troupe_id=uuid.UUID(troupe.id),
            given_on=date(1890, 3, 1),
        )
    )
    troupe.session.flush()
    embraced(troupe, agnes, date(1791, 6, 2))
    found = [
        e["kind"]
        for e in chronicle(troupe.storyteller, troupe)["events"]
        if e["kind"] in ("status", "embrace")
    ]
    assert found == ["status", "embrace"]


def test_an_npc_is_added_and_a_copy_says_whose_it_is(troupe: Troupe) -> None:
    member(troupe, "Abiding")  # the player stays a member
    viktor = built(troupe)
    retire(troupe.player, viktor, reason="off_field", listed=True)
    npc = copied(troupe.storyteller, viktor)["character"]
    arrival = next(
        e
        for e in chronicle(troupe.storyteller, troupe)["events"]
        if e["kind"] == "arrival" and e["character_id"] == npc["id"]
    )
    assert arrival["label"] == "Added as an NPC"
    assert arrival["detail"] == "A copy of Viktor, retired"

    # Listed on the Who's Who, the players see it join, and no more.
    listed = troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/npcs/{npc['id']}/whos-who", json={"listed": True}
    )
    assert listed.status_code < 300, listed.text
    troupe.storyteller.client.patch(f"/troupes/{troupe.id}", json={"chronicle_players": True})
    seen = [e for e in chronicle(troupe.player, troupe)["events"] if e["character_id"] == npc["id"]]
    assert [(e["kind"], e["label"], e["detail"]) for e in seen] == [
        ("arrival", "Joined the troupe", "")
    ]


def test_a_boonbreakers_disgraced_names_the_declaration(troupe: Troupe) -> None:
    roth = member(troupe, "Roth")
    held = HeldStatus(
        character_id=uuid.UUID(roth),
        name="Disgraced",
        troupe_id=uuid.UUID(troupe.id),
        given_on=date(2026, 11, 1),
        patron_text="Declared a Boonbreaker by staff",
        story="Refused a major boon.",
    )
    troupe.session.add(held)
    troupe.session.flush()
    troupe.session.add(
        Boonbreaker(
            troupe_id=uuid.UUID(troupe.id), character_id=uuid.UUID(roth), held_status_id=held.id
        )
    )
    troupe.session.flush()
    disgraced = next(
        e for e in chronicle(troupe.storyteller, troupe)["events"] if e["label"] == "Disgraced"
    )
    assert disgraced["detail"] == "Declared a Boonbreaker by staff. Refused a major boon."


def test_assistants_see_it_and_narrators_do_not(troupe: Troupe) -> None:
    history(troupe)
    assert chronicle(troupe.assistant, troupe)["full"] is True
    refused = troupe.narrator.client.get(f"/troupes/{troupe.id}/chronicle")
    assert refused.status_code == 403


def test_players_see_it_only_where_the_troupe_lets_them(troupe: Troupe) -> None:
    history(troupe)
    refused = troupe.player.client.get(f"/troupes/{troupe.id}/chronicle")
    assert refused.status_code == 403

    shown = troupe.storyteller.client.patch(
        f"/troupes/{troupe.id}", json={"chronicle_players": True}
    )
    assert shown.status_code == 200, shown.text
    found = chronicle(troupe.player, troupe)
    assert found["full"] is False and found["players_see"] is True
    # What the troupe already shows them: titles, those on the Who's Who joining it, and
    # the departures listed under No longer with us.
    assert kinds(found) == {
        ("title", "Agnes", "Prince"),
        ("arrival", "Agnes", "Accepted as home"),
        ("arrival", "Roth", "Accepted as home"),
        ("arrival", "Lena", "Accepted as home"),
        ("death", "Lena", "Final Death"),
    }
    assert all(e["detail"] == "" for e in found["events"])

    stranger = troupe.stranger.client.get(f"/troupes/{troupe.id}/chronicle")
    assert stranger.status_code == 403


def test_an_unlisted_departure_stays_staffs(troupe: Troupe) -> None:
    member(troupe, "Staying")  # the player stays a member
    gone = member(troupe, "Quiet")
    retire(troupe.player, gone, reason="off_field", listed=False)
    troupe.storyteller.client.patch(f"/troupes/{troupe.id}", json={"chronicle_players": True})

    assert ("departure", "Quiet", "Off-field") in kinds(chronicle(troupe.storyteller, troupe))
    assert not any(
        e["character_name"] == "Quiet" for e in chronicle(troupe.player, troupe)["events"]
    )


def test_the_setting_is_logged_and_only_staff_change_it(troupe: Troupe) -> None:
    refused = troupe.player.client.patch(f"/troupes/{troupe.id}", json={"chronicle_players": True})
    assert refused.status_code == 403
    shown = troupe.storyteller.client.patch(
        f"/troupes/{troupe.id}", json={"chronicle_players": True}
    )
    assert shown.status_code == 200 and shown.json()["chronicle_players"] is True
    log = troupe.storyteller.client.get(f"/troupes/{troupe.id}/log").json()
    entries = log["entries"] if isinstance(log, dict) else log
    assert any("chronicle" in str(e) for e in entries)
