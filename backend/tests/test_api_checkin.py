"""Game-night check-in (issue #421): staff open a game's check-in with a code for the
door, players check in and their night starts on the Play View, staff check people
in and out by hand, and the game's XP goes to everyone there in one go, with a
warning past the book's monthly guidance."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import checkin, xp_range
from horatio.models import Character, PlayGame, ScheduledGame, XpEntry
from horatio.models import Troupe as TroupeRecord
from tests.api_helpers import Person, Troupe
from tests.test_api_character_search import member
from tests.test_api_downtimes import member_character
from tests.test_api_troupe_profiles import add_game


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def game(troupe: Troupe, starts_in: timedelta = timedelta(hours=1)) -> str:
    response = add_game(troupe, starts_in)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def past_game(troupe: Troupe, session: Session, days_ago: int = 3) -> str:
    """A game already over, as one on the schedule becomes."""
    start = datetime.now(UTC) - timedelta(days=days_ago)
    found = ScheduledGame(
        troupe_id=uuid.UUID(troupe.id), starts_at=start, ends_at=start + timedelta(hours=5)
    )
    session.add(found)
    session.flush()
    return str(found.id)


def path(troupe: Troupe, game_id: str, rest: str = "") -> str:
    return f"/troupes/{troupe.id}/games/{game_id}{rest}"


def open_checkin(troupe: Troupe, game_id: str, person: Person | None = None) -> dict[str, Any]:
    response = (person or troupe.assistant).client.put(path(troupe, game_id, "/checkin"))
    assert response.status_code == 200, response.text
    return response.json()


def night(troupe: Troupe, game_id: str) -> dict[str, Any]:
    response = troupe.assistant.client.get(path(troupe, game_id, "/night"))
    assert response.status_code == 200, response.text
    return response.json()


def check_in(person: Person, troupe: Troupe, game_id: str, character_id: str, **body: Any) -> Any:
    return person.client.post(
        path(troupe, game_id, "/attendance"), json={"character_id": character_id, **body}
    )


def view(person: Person, character_id: str) -> dict[str, Any]:
    response = person.client.get(f"/characters/{character_id}/play")
    assert response.status_code == 200, response.text
    return response.json()


def tap(tracker: str, amount: int, at: datetime) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "happened_at": at.isoformat(),
        "kind": "change",
        "tracker": tracker,
        "amount": amount,
    }


def send(person: Person, character_id: str, *taps: dict[str, Any]) -> None:
    response = person.client.post(f"/characters/{character_id}/play/taps", json={"taps": taps})
    assert response.status_code == 200, response.text


def test_staff_open_check_in_and_a_player_checks_in_with_the_code(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    tonight = game(troupe)

    opened = open_checkin(troupe, tonight)
    code = opened["checkin"]["code"]
    assert opened["checkin"]["open"] is True
    assert len(code) == checkin.CODE_LENGTH
    assert set(code) <= set(checkin.CODE_LETTERS)
    assert [o["character_name"] for o in opened["others"]] == ["Agnes"]

    # Typed in lower case with a dash, as a sign might show it.
    offered = troupe.player.client.get(f"/checkin/{code[:3].lower()}-{code[3:].lower()}")
    assert offered.status_code == 200, offered.text
    assert offered.json()["game_id"] == tonight
    assert offered.json()["troupe_name"] == "Lords of the Night"
    assert offered.json()["characters"] == [{"id": agnes, "name": "Agnes", "checked_in": False}]

    response = check_in(troupe.player, troupe, tonight, agnes)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "character_id": agnes,
        "character_name": "Agnes",
        "already": False,
        "play_started": True,
    }
    # The night started on the Play View.
    assert view(troupe.player, agnes)["game"]["number"] == 1
    # Twice changes nothing.
    again = check_in(troupe.player, troupe, tonight, agnes)
    assert again.json()["already"] is True

    seen = night(troupe, tonight)
    assert [
        (a["character_name"], a["home"], a["by_staff"], a["rested"]) for a in seen["attendees"]
    ] == [("Agnes", True, False, True)]
    assert seen["others"] == []
    listed = troupe.player.client.get(f"/troupes/{troupe.id}/games").json()[0]
    assert (listed["checkin_open"], listed["checked_in"], listed["my_checked_in"]) == (
        True,
        1,
        ["Agnes"],
    )


def test_a_code_works_only_while_check_in_is_open(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    tonight = game(troupe)

    # Not open yet: the player can't check in, from the code or the game.
    refused = check_in(troupe.player, troupe, tonight, agnes)
    assert refused.status_code == 422
    assert troupe.player.client.get(path(troupe, tonight, "/checkin")).status_code == 422

    old = open_checkin(troupe, tonight)["checkin"]["code"]
    new = open_checkin(troupe, tonight)["checkin"]["code"]
    assert new != old
    assert troupe.player.client.get(f"/checkin/{old}").status_code == 404
    assert troupe.player.client.get(f"/checkin/{new}").status_code == 200

    closed = troupe.assistant.client.delete(path(troupe, tonight, "/checkin"))
    assert closed.json()["checkin"] == {
        "open": False,
        "code": None,
        "can_open": True,
        "opens_at": closed.json()["checkin"]["opens_at"],
    }
    assert troupe.player.client.get(f"/checkin/{new}").status_code == 404
    assert check_in(troupe.player, troupe, tonight, agnes).status_code == 422


def test_check_in_opens_twelve_hours_before_and_closes_when_the_game_ends(
    troupe: Troupe, session: Session
) -> None:
    later = game(troupe, timedelta(days=2))
    refused = troupe.assistant.client.put(path(troupe, later, "/checkin"))
    assert refused.status_code == 422
    assert refused.json()["detail"] == "Check-in opens 12 hours before the game starts."
    assert night(troupe, later)["checkin"]["can_open"] is False

    tonight = game(troupe)
    code = open_checkin(troupe, tonight)["checkin"]["code"]
    # The game ends: the code no longer works.
    found = session.get_one(ScheduledGame, uuid.UUID(tonight))
    found.starts_at -= timedelta(days=1)
    found.ends_at = datetime.now(UTC) - timedelta(minutes=1)
    session.flush()
    assert troupe.player.client.get(f"/checkin/{code}").status_code == 404
    assert night(troupe, tonight)["checkin"]["open"] is False


def test_who_runs_check_in(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    tonight = game(troupe)
    for person in (troupe.narrator, troupe.player, troupe.stranger):
        assert person.client.put(path(troupe, tonight, "/checkin")).status_code == 403
        assert person.client.get(path(troupe, tonight, "/night")).status_code == 403
    code = open_checkin(troupe, tonight, troupe.storyteller)["checkin"]["code"]

    # Only the troupe's players see what a code is for, and check in only their own.
    assert troupe.stranger.client.get(f"/checkin/{code}").status_code == 403
    assert check_in(troupe.narrator, troupe, tonight, agnes).status_code == 403
    assert check_in(troupe.stranger, troupe, tonight, agnes).status_code == 403
    assert check_in(troupe.assistant, troupe, tonight, str(uuid.uuid4())).status_code == 404


def test_staff_check_characters_in_and_out_by_hand(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    vera = member(troupe, troupe.player, "Vera", "Toreador")
    tonight = game(troupe)

    # By hand, check-in need not be open.
    response = check_in(troupe.assistant, troupe, tonight, vera)
    assert response.status_code == 200, response.text
    seen = night(troupe, tonight)
    assert [(a["character_name"], a["home"], a["by_staff"]) for a in seen["attendees"]] == [
        ("Vera", False, True)
    ]
    assert [o["character_name"] for o in seen["others"]] == ["Agnes"]

    out = troupe.assistant.client.delete(path(troupe, tonight, f"/attendance/{vera}"))
    assert out.status_code == 200, out.text
    assert out.json()["attendees"] == []
    # Her Play View night stays as it is.
    assert view(troupe.player, vera)["game"]["number"] == 1
    assert agnes in [o["character_id"] for o in out.json()["others"]]


def test_a_second_check_in_the_same_night_joins_its_game(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    first = game(troupe, timedelta(minutes=-30))
    assert check_in(troupe.assistant, troupe, first, agnes).status_code == 200
    # Two Willpower spent at that game, which nobody reset afterwards.
    send(troupe.player, agnes, tap("willpower", -2, datetime.now(UTC) - timedelta(minutes=5)))
    assert view(troupe.player, agnes)["willpower"]["value"] == 4

    # A second check-in the same night joins the game.
    other = game(troupe, timedelta(minutes=-10))
    assert check_in(troupe.assistant, troupe, other, agnes).status_code == 200
    assert view(troupe.player, agnes)["game"]["number"] == 1
    assert view(troupe.player, agnes)["willpower"]["value"] == 4


def test_without_a_full_days_rest_willpower_starts_where_the_last_game_left_it(
    troupe: Troupe, session: Session
) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    beatrix = member_character(troupe, troupe.player, "Beatrix")
    long_ago = datetime(2026, 10, 17, 20, 0, tzinfo=UTC)
    for character_id in (agnes, beatrix):
        send(
            troupe.player, character_id, tap("willpower", -2, long_ago), tap("blood", -3, long_ago)
        )

    tonight = game(troupe)
    open_checkin(troupe, tonight)
    tired = check_in(troupe.player, troupe, tonight, agnes, rested=False)
    assert tired.status_code == 200, tired.text
    rested = check_in(troupe.player, troupe, tonight, beatrix, rested=True)
    assert rested.status_code == 200, rested.text

    # The old game ended, kept, and the next began: Blood is full again either way.
    for character_id in (agnes, beatrix):
        state = view(troupe.player, character_id)
        assert state["game"]["number"] == 2
        assert state["blood"]["value"] == 10
        assert state["log"] == []
    assert view(troupe.player, agnes)["willpower"] == {"value": 4, "most": 6, "start": 4}
    assert view(troupe.player, beatrix)["willpower"] == {"value": 6, "most": 6, "start": 6}
    ended = session.scalar(
        select(PlayGame).where(PlayGame.character_id == uuid.UUID(agnes), PlayGame.number == 1)
    )
    assert ended is not None and ended.ended_at is not None
    seen = {a["character_name"]: a["rested"] for a in night(troupe, tonight)["attendees"]}
    assert seen == {"Agnes": False, "Beatrix": True}


def test_starting_blood_follows_the_troupe_and_its_feeding_setting(
    troupe: Troupe, session: Session
) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    beatrix = member_character(troupe, troupe.player, "Beatrix")
    record = session.get_one(TroupeRecord, uuid.UUID(troupe.id))
    record.starting_blood = 8
    # Both fed short last downtime.
    for character_id in (agnes, beatrix):
        session.get_one(Character, uuid.UUID(character_id)).half_blood_next_game = True
    session.flush()

    tonight = game(troupe)
    assert check_in(troupe.assistant, troupe, tonight, agnes).status_code == 200
    assert view(troupe.player, agnes)["blood"]["start"] == 5
    assert view(troupe.player, agnes)["half_blood"] is True

    # With feeding switched off, half Blood no longer applies: the house's 8.
    record.feeding = "off"
    session.flush()
    assert check_in(troupe.assistant, troupe, tonight, beatrix).status_code == 200
    assert view(troupe.player, beatrix)["blood"]["start"] == 8
    assert view(troupe.player, beatrix)["half_blood"] is False


def test_a_game_already_over_records_attendance_without_starting_a_night(
    troupe: Troupe, session: Session
) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    over = past_game(troupe, session)
    response = check_in(troupe.assistant, troupe, over, agnes)
    assert response.status_code == 200, response.text
    assert response.json()["play_started"] is False
    assert view(troupe.player, agnes)["game"] is None
    # Not by its player, though.
    assert check_in(troupe.player, troupe, over, agnes).status_code == 422

    past = troupe.assistant.client.get(f"/troupes/{troupe.id}/games/past").json()
    assert [(g["id"], g["attended"], g["xp_awarded"]) for g in past] == [(over, 1, None)]
    assert troupe.player.client.get(f"/troupes/{troupe.id}/games/past").status_code == 403


def awarded(person: Person, character_id: str) -> list[tuple[str, int]]:
    history = person.client.get(f"/characters/{character_id}/xp").json()
    return [(e["reason"], e["amount"]) for e in history if e["reason"].startswith("Game")]


def test_the_games_xp_goes_to_everyone_there_whose_home_it_is(
    troupe: Troupe, session: Session
) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    beatrix = member_character(troupe, troupe.player, "Beatrix")
    vera = member(troupe, troupe.player, "Vera", "Toreador")
    tonight = game(troupe, timedelta(minutes=-60))
    for character_id in (agnes, vera):
        assert check_in(troupe.assistant, troupe, tonight, character_id).status_code == 200
    before = xp_range.figures(session, session.get_one(TroupeRecord, uuid.UUID(troupe.id)))

    seen = night(troupe, tonight)
    assert (seen["session_xp"], seen["game_xp_low"], seen["game_xp_high"]) == (8, 3, 5)
    assert seen["monthly_xp"] == 10
    assert seen["can_award"] is True
    # Starting experience is not XP earned this month.
    assert {a["character_name"]: a["month_xp"] for a in seen["attendees"]} == {
        "Agnes": 0,
        "Vera": 0,
    }

    response = troupe.assistant.client.post(
        path(troupe, tonight, "/xp"), json={"amount": 4, "reason": "Game, 1 November"}
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"characters": 1, "total": 4, "past_monthly": []}
    assert awarded(troupe.player, agnes) == [("Game, 1 November", 4)]
    # Beatrix wasn't there; Vera's home troupe awards her own.
    assert awarded(troupe.player, beatrix) == []
    assert awarded(troupe.player, vera) == []
    after = xp_range.figures(session, session.get_one(TroupeRecord, uuid.UUID(troupe.id)))
    assert (after.floor - before.floor, after.ceiling - before.ceiling) == (4, 4)

    seen = night(troupe, tonight)
    assert seen["xp"]["amount"] == 4
    assert seen["xp"]["awarded_by"]["handle"] == troupe.assistant.handle
    assert {a["character_name"]: a["month_xp"] for a in seen["attendees"]}["Agnes"] == 4
    # Once a game; and check-in is over once it is awarded.
    again = troupe.assistant.client.post(
        path(troupe, tonight, "/xp"), json={"amount": 4, "reason": "Game, 1 November"}
    )
    assert again.status_code == 409
    assert seen["checkin"]["open"] is False
    assert check_in(troupe.assistant, troupe, tonight, beatrix).status_code == 409
    assert (
        troupe.assistant.client.delete(path(troupe, tonight, f"/attendance/{agnes}")).status_code
        == 409
    )


def test_an_award_past_the_monthly_guidance_is_warned_of_not_refused(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    beatrix = member_character(troupe, troupe.player, "Beatrix")
    earlier = troupe.lead.client.post(
        f"/characters/{agnes}/xp", json={"amount": 7, "reason": "Game, earlier this month"}
    )
    assert earlier.status_code == 201, earlier.text
    tonight = game(troupe, timedelta(minutes=-60))
    for character_id in (agnes, beatrix):
        assert check_in(troupe.assistant, troupe, tonight, character_id).status_code == 200
    assert {a["character_name"]: a["month_xp"] for a in night(troupe, tonight)["attendees"]} == {
        "Agnes": 7,
        "Beatrix": 0,
    }

    response = troupe.assistant.client.post(
        path(troupe, tonight, "/xp"),
        json={"amount": 5, "reason": "Game, 1 November", "to_range": False},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"characters": 2, "total": 10, "past_monthly": ["Agnes"]}


def test_who_awards_a_games_xp_and_when(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    later = game(troupe, timedelta(hours=2))
    assert check_in(troupe.assistant, troupe, later, agnes).status_code == 200
    body = {"amount": 4, "reason": "Game"}
    assert troupe.narrator.client.post(path(troupe, later, "/xp"), json=body).status_code == 403
    assert troupe.player.client.post(path(troupe, later, "/xp"), json=body).status_code == 403
    # Not before the game starts.
    assert troupe.assistant.client.post(path(troupe, later, "/xp"), json=body).status_code == 422
    empty = game(troupe, timedelta(minutes=-60))
    nobody = troupe.assistant.client.post(path(troupe, empty, "/xp"), json=body)
    assert nobody.status_code == 422


def test_a_game_someone_came_to_stays_on_the_schedule(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    tonight = game(troupe)
    unattended = game(troupe, timedelta(days=5))
    assert check_in(troupe.assistant, troupe, tonight, agnes).status_code == 200
    assert (
        troupe.storyteller.client.delete(f"/troupes/{troupe.id}/games/{tonight}").status_code == 409
    )
    assert (
        troupe.storyteller.client.delete(f"/troupes/{troupe.id}/games/{unattended}").status_code
        == 204
    )


def test_a_characters_games_attended(troupe: Troupe, session: Session) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    over = past_game(troupe, session, days_ago=10)
    tonight = game(troupe)
    for game_id in (over, tonight):
        assert check_in(troupe.assistant, troupe, game_id, agnes).status_code == 200

    response = troupe.player.client.get(f"/characters/{agnes}/attendance")
    assert response.status_code == 200, response.text
    assert [(g["game_id"], g["troupe_name"], g["play_game_number"]) for g in response.json()] == [
        (tonight, "Lords of the Night", 1),
        (over, "Lords of the Night", None),
    ]
    assert troupe.stranger.client.get(f"/characters/{agnes}/attendance").status_code == 404


def test_the_log_says_who_checked_in(troupe: Troupe, session: Session) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    tonight = game(troupe)
    open_checkin(troupe, tonight)
    assert check_in(troupe.player, troupe, tonight, agnes).status_code == 200
    log = troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()
    messages = [e["message"] for e in log]
    assert any("checked Agnes in to the game on" in m for m in messages), messages
    assert any("opened check-in for the game on" in m for m in messages), messages


def test_earned_xp_counts_this_month_only(troupe: Troupe, session: Session) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    character_id = uuid.UUID(agnes)
    lead = session.scalar(select(XpEntry.entered_by).where(XpEntry.character_id == character_id))
    assert lead is not None
    today = datetime.now(UTC).date()
    last_month = checkin.month_start(today) - timedelta(days=1)
    session.add_all(
        [
            XpEntry(
                character_id=character_id, kind="award", amount=6, reason="Game", entered_by=lead
            ),
            XpEntry(
                character_id=character_id,
                kind="award",
                amount=9,
                reason="Game, last month",
                entered_by=lead,
                entered_on=last_month,
            ),
            XpEntry(
                character_id=character_id,
                kind="award",
                amount=5,
                reason="Top-up to Lords of the Night's XP floor of 35",
                entered_by=lead,
            ),
        ]
    )
    session.flush()
    assert checkin.earned_this_month(session, [character_id]) == {character_id: 6}
