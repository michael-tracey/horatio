"""Choosing the night's status at check-in (issue #441, horatio.play_status): where the
troupe's house rule says so, a character's source of abiding status is chosen as it
checks in and fixed for the game; its only source is chosen for it; staff change it
with a reason noted in the game's log; status for a single night never takes its
place; and with the rule off, nothing changes."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import GameAttendance, PlayGame, ScheduledGame
from tests.api_helpers import Person, Troupe
from tests.test_api_checkin import check_in, game, night, open_checkin, path
from tests.test_api_game_xp import configure, mark
from tests.test_api_play_status import carried, choose, view
from tests.test_api_sect_status import add, entitle, logged, member, put_trait


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def switch_on(troupe: Troupe, on: bool = True) -> dict[str, Any]:
    response = troupe.storyteller.client.patch(
        f"/troupes/{troupe.id}", json={"status_at_checkin": on}
    )
    assert response.status_code == 200, response.text
    return response.json()


def elder_seneschal(troupe: Troupe, name: str = "Agnes") -> str:
    """A Camarilla elder holding Seneschal: two sources, the title and social age."""
    agnes = member(troupe, name)
    entitle(troupe, agnes, "Seneschal")
    put_trait(troupe.session, agnes, "backgrounds", "Generation", 3)
    return agnes


def offer(person: Person, troupe: Troupe, game_id: str, character_id: str) -> dict[str, Any]:
    response = person.client.get(path(troupe, game_id, "/checkin"))
    assert response.status_code == 200, response.text
    return next(c for c in response.json()["characters"] if c["id"] == character_id)


def attendee(troupe: Troupe, game_id: str, character_id: str) -> dict[str, Any]:
    return next(a for a in night(troupe, game_id)["attendees"] if a["character_id"] == character_id)


def night_status(session: Session, character_id: str) -> dict[str, Any]:
    found = session.scalars(
        select(PlayGame).where(
            PlayGame.character_id == uuid.UUID(character_id), PlayGame.ended_at.is_(None)
        )
    ).one()
    session.refresh(found)
    return found.status


def test_the_setting_is_off_by_default_and_staff_switch_it_on_in_the_log(troupe: Troupe) -> None:
    seen = troupe.storyteller.client.get(f"/troupes/{troupe.id}").json()
    assert seen["status_at_checkin"] is False
    rules = troupe.player.client.get(f"/troupes/{troupe.id}/house-rules").json()
    assert "The night's status" not in [o["name"] for o in rules["other"]]

    refused = troupe.player.client.patch(f"/troupes/{troupe.id}", json={"status_at_checkin": True})
    assert refused.status_code == 403
    assert switch_on(troupe)["status_at_checkin"] is True
    # Setting it to what it is already logs nothing more.
    switch_on(troupe)
    rules = troupe.player.client.get(f"/troupes/{troupe.id}/house-rules").json()
    [rule] = [o for o in rules["other"] if o["name"] == "The night's status"]
    assert "as it checks in" in rule["text"]
    assert "p. 311" in rule["book_text"]
    switch_on(troupe, False)
    log = troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()
    said = [e["message"] for e in log if "night's status source" in e["message"]]
    assert sorted(said) == [
        "storyteller set the night's status source: chosen at check-in and fixed for the game.",
        "storyteller set the night's status source: chosen on the Play View, as the book has it.",
    ]


def test_a_player_chooses_the_source_at_check_in_and_it_is_fixed(troupe: Troupe) -> None:
    switch_on(troupe)
    agnes = elder_seneschal(troupe)
    tonight = game(troupe)
    open_checkin(troupe, tonight)

    offered = offer(troupe.player, troupe, tonight, agnes)
    assert offered["status_at_checkin"] is True
    assert [s["name"] for s in offered["status_sources"]] == ["Seneschal", "Elder"]
    assert offered["status_source"] is None

    # It must choose one, and one it has.
    missing = check_in(troupe.player, troupe, tonight, agnes)
    assert missing.status_code == 422
    assert "Choose the one source of abiding status Agnes carries tonight" in missing.text
    assert night(troupe, tonight)["attendees"] == []
    assert check_in(troupe.player, troupe, tonight, agnes, source="Primogen").status_code == 422

    done = check_in(troupe.player, troupe, tonight, agnes, source="Elder")
    assert done.status_code == 200, done.text
    state = view(troupe.player, agnes)
    status = state["status"]
    assert (status["source"], status["source_chosen"], status["source_fixed"]) == (
        "Elder",
        True,
        True,
    )
    assert not status["choosing"]
    assert [n for n, _ in carried(state)] == ["Confirmed", "Established", "Privileged"]
    assert [e["choice"] for e in logged(troupe.session, agnes, "play.status_chosen")] == [
        "Elder as its source of abiding status, at check-in"
    ]

    # Fixed for the game: the player cannot change it on the Play View.
    refused = choose(troupe.player, agnes, source="Seneschal")
    assert refused.status_code == 409
    assert "chosen as you check in" in refused.json()["detail"]
    assert view(troupe.player, agnes)["status"]["source"] == "Elder"

    # Staff see it on the attendance list.
    seen = attendee(troupe, tonight, agnes)
    assert (seen["status_source"], seen["status_to_choose"]) == ("Elder", False)


def test_the_only_source_is_chosen_for_it(troupe: Troupe) -> None:
    switch_on(troupe)
    agnes = member(troupe)
    entitle(troupe, agnes, "Prince")
    tonight = game(troupe)
    open_checkin(troupe, tonight)
    assert [s["name"] for s in offer(troupe.player, troupe, tonight, agnes)["status_sources"]] == [
        "Prince"
    ]

    done = check_in(troupe.player, troupe, tonight, agnes)
    assert done.status_code == 200, done.text
    assert night_status(troupe.session, agnes)["source"] == "Prince"
    assert night_status(troupe.session, agnes)["checked_in"] == tonight
    assert view(troupe.player, agnes)["status"]["source_fixed"] is True
    assert attendee(troupe, tonight, agnes)["status_source"] == "Prince"


def test_a_character_with_no_source_checks_in_with_nothing_to_choose(troupe: Troupe) -> None:
    switch_on(troupe)
    agnes = member(troupe)
    tonight = game(troupe)
    open_checkin(troupe, tonight)
    assert offer(troupe.player, troupe, tonight, agnes)["status_sources"] == []
    assert check_in(troupe.player, troupe, tonight, agnes).status_code == 200
    seen = attendee(troupe, tonight, agnes)
    assert (seen["status_source"], seen["status_to_choose"]) == (None, False)


def test_staff_change_a_fixed_source_giving_a_reason_for_the_games_log(troupe: Troupe) -> None:
    switch_on(troupe)
    agnes = elder_seneschal(troupe)
    tonight = game(troupe)
    open_checkin(troupe, tonight)
    assert check_in(troupe.player, troupe, tonight, agnes, source="Elder").status_code == 200

    unexplained = choose(troupe.storyteller, agnes, source="Seneschal")
    assert unexplained.status_code == 422
    assert "Give a reason" in unexplained.text
    changed = choose(
        troupe.storyteller, agnes, source="Seneschal", reason="She told the door the wrong one"
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["status"]["source"] == "Seneschal"
    note = changed.json()["log"][0]
    assert (note["kind"], note["text"], note["note"], note["by_staff"]) == (
        "note",
        "Source of abiding status changed",
        "From Elder to Seneschal: She told the door the wrong one",
        True,
    )
    assert logged(troupe.session, agnes, "play.status_chosen")[-1]["choice"] == (
        "Seneschal as its source of abiding status (She told the door the wrong one)"
    )
    assert attendee(troupe, tonight, agnes)["status_source"] == "Seneschal"
    # Still fixed for the player.
    assert choose(troupe.player, agnes, source="Elder").status_code == 409


def test_staff_checking_in_by_hand_leave_a_choice_of_several_to_staff(troupe: Troupe) -> None:
    switch_on(troupe)
    agnes = elder_seneschal(troupe)
    tonight = game(troupe)
    assert check_in(troupe.assistant, troupe, tonight, agnes).status_code == 200

    seen = attendee(troupe, tonight, agnes)
    assert (seen["status_source"], seen["status_to_choose"]) == (None, True)
    status = view(troupe.player, agnes)["status"]
    assert status["choosing"] and status["source_fixed"]
    # Not its player's to choose; staff choose it, with no reason needed for a first choice.
    assert choose(troupe.player, agnes, source="Elder").status_code == 409
    chosen = choose(troupe.assistant, agnes, source="Elder")
    assert chosen.status_code == 200, chosen.text
    assert chosen.json()["log"][0]["note"] == "Elder"
    seen = attendee(troupe, tonight, agnes)
    assert (seen["status_source"], seen["status_to_choose"]) == ("Elder", False)


def test_the_choice_at_check_in_is_the_one_and_checking_in_again_keeps_it(
    troupe: Troupe,
) -> None:
    agnes = elder_seneschal(troupe)
    tonight = game(troupe)
    # Chosen on the Play View before the troupe switched the rule on: check-in chooses.
    assert choose(troupe.player, agnes, source="Seneschal").status_code == 200
    switch_on(troupe)
    open_checkin(troupe, tonight)
    assert offer(troupe.player, troupe, tonight, agnes)["status_source"] is None
    assert check_in(troupe.player, troupe, tonight, agnes, source="Elder").status_code == 200
    assert view(troupe.player, agnes)["status"]["source"] == "Elder"

    # Checked out and in again, it keeps the source it came with.
    out = troupe.assistant.client.delete(path(troupe, tonight, f"/attendance/{agnes}"))
    assert out.status_code == 200, out.text
    assert offer(troupe.player, troupe, tonight, agnes)["status_source"] == "Elder"
    assert check_in(troupe.player, troupe, tonight, agnes).status_code == 200
    assert attendee(troupe, tonight, agnes)["status_source"] == "Elder"


def test_a_night_left_untapped_since_an_earlier_game_asks_again(troupe: Troupe) -> None:
    switch_on(troupe)
    agnes = elder_seneschal(troupe)
    earlier = game(troupe)
    open_checkin(troupe, earlier)
    assert check_in(troupe.player, troupe, earlier, agnes, source="Elder").status_code == 200
    # Nothing tapped all night, so the next check-in joins the same Play View game.
    over = troupe.session.get_one(ScheduledGame, uuid.UUID(earlier))
    over.checkin_code = None
    over.starts_at = datetime.now(UTC) - timedelta(days=7)
    over.ends_at = over.starts_at + timedelta(hours=5)
    troupe.session.flush()
    tonight = game(troupe)
    open_checkin(troupe, tonight)
    assert offer(troupe.player, troupe, tonight, agnes)["status_source"] is None
    assert check_in(troupe.player, troupe, tonight, agnes).status_code == 422
    assert check_in(troupe.player, troupe, tonight, agnes, source="Seneschal").status_code == 200
    assert view(troupe.player, agnes)["status"]["source"] == "Seneschal"


def test_status_for_a_single_night_never_takes_the_sources_place(troupe: Troupe) -> None:
    switch_on(troupe)
    rook = member(troupe, "Rook", sect="Sabbat", clan="Lasombra")
    entitle(troupe, rook, "Bishop")
    tonight = game(troupe)
    open_checkin(troupe, tonight)
    assert check_in(troupe.player, troupe, tonight, rook).status_code == 200

    # The Bishop's Enforcer, chosen for the night on the Play View, is the source's own.
    chosen = choose(troupe.player, rook, chosen={"Bishop": "Enforcer"})
    assert chosen.status_code == 200, chosen.text
    assert chosen.json()["status"]["source"] == "Bishop"
    assert carried(chosen.json()) == [("Enforcer", "Abiding")]
    # Deputised for the night: Defender, given at the game, is held beside it.
    given = troupe.player.client.post(
        f"/characters/{rook}/play/status",
        json={"name": "Defender", "patron_text": "The Sheriff, for tonight"},
    )
    assert given.status_code == 200, given.text
    assert given.json()["status"]["source"] == "Bishop"
    assert carried(given.json()) == [("Enforcer", "Abiding"), ("Defender", "Fleeting")]
    assert night_status(troupe.session, rook)["source"] == "Bishop"


def test_with_the_setting_off_check_in_asks_nothing_and_the_play_view_chooses(
    troupe: Troupe,
) -> None:
    agnes = elder_seneschal(troupe)
    tonight = game(troupe)
    open_checkin(troupe, tonight)
    offered = offer(troupe.player, troupe, tonight, agnes)
    assert (offered["status_at_checkin"], offered["status_sources"]) == (False, [])

    # A source sent anyway is not used.
    assert check_in(troupe.player, troupe, tonight, agnes, source="Elder").status_code == 200
    assert night_status(troupe.session, agnes) == {}
    status = view(troupe.player, agnes)["status"]
    assert (status["choosing"], status["source_fixed"]) == (True, False)
    assert attendee(troupe, tonight, agnes)["status_source"] is None
    assert choose(troupe.player, agnes, source="Seneschal").status_code == 200
    assert choose(troupe.player, agnes, source="Elder").status_code == 409
    # Staff change it as before: no reason, no note in the game's log.
    changed = choose(troupe.storyteller, agnes, source="Elder")
    assert changed.status_code == 200, changed.text
    assert [e for e in changed.json()["log"] if e["kind"] == "note"] == []
    assert attendee(troupe, tonight, agnes)["status_source"] is None


def test_an_absentee_game_chooses_no_source(troupe: Troupe) -> None:
    switch_on(troupe)
    configure(troupe, absentee=True)
    agnes = elder_seneschal(troupe)
    started = game(troupe, timedelta(hours=-1))
    marked = mark(troupe.assistant, troupe, started, agnes)
    assert marked.status_code == 200, marked.text
    [absent] = night(troupe, started)["absentees"]
    assert (absent["status_source"], absent["status_to_choose"]) == (None, False)
    row = troupe.session.scalars(
        select(GameAttendance).where(GameAttendance.character_id == uuid.UUID(agnes))
    ).one()
    assert row.play_game_id is None
    assert (
        troupe.session.scalars(
            select(PlayGame).where(PlayGame.character_id == uuid.UUID(agnes))
        ).all()
        == []
    )

    # It came after all: checking in now chooses, as any check-in does.
    open_checkin(troupe, started)
    assert check_in(troupe.player, troupe, started, agnes).status_code == 422
    assert check_in(troupe.player, troupe, started, agnes, source="Seneschal").status_code == 200
    assert attendee(troupe, started, agnes)["status_source"] == "Seneschal"


def test_whos_who_and_the_others_show_the_source_carried_while_the_game_is_on(
    troupe: Troupe,
) -> None:
    switch_on(troupe)
    agnes = elder_seneschal(troupe)
    bram = member(troupe, "Bram")
    tonight = game(troupe)
    open_checkin(troupe, tonight)
    assert check_in(troupe.player, troupe, tonight, agnes, source="Elder").status_code == 200

    def whos_who() -> str | None:
        found = troupe.player.client.get(f"/troupes/{troupe.id}/whos-who").json()
        return next(e for e in found["entries"] if e["name"] == "Agnes")["carried_source"]

    def others() -> str | None:
        found = troupe.player.client.get(f"/characters/{bram}/play/others").json()
        return next(o for o in found if o["name"] == "Agnes")["carried_source"]

    assert (whos_who(), others()) == ("Elder", "Elder")
    # Bram has not checked in: nothing shows for him.
    found = troupe.player.client.get(f"/characters/{agnes}/play/others").json()
    assert next(o for o in found if o["name"] == "Bram")["carried_source"] is None

    # Once the game is over, its source shows no longer.
    scheduled = troupe.session.get_one(ScheduledGame, uuid.UUID(tonight))
    scheduled.starts_at = datetime.now(UTC) - timedelta(hours=6)
    scheduled.ends_at = datetime.now(UTC) - timedelta(hours=1)
    troupe.session.flush()
    assert (whos_who(), others()) == (None, None)


def test_status_given_at_the_game_keeps_the_fixed_source(troupe: Troupe) -> None:
    switch_on(troupe)
    agnes = elder_seneschal(troupe)
    tonight = game(troupe)
    open_checkin(troupe, tonight)
    assert check_in(troupe.player, troupe, tonight, agnes, source="Seneschal").status_code == 200
    assert add(troupe.player, agnes, "Loyal").status_code == 200
    assert view(troupe.player, agnes)["status"]["source"] == "Seneschal"
