"""A troupe's calendar and RSVPs to its games (issue #420): members say whether
they are coming and staff see who; each member's secret calendar link carries the
games and the open cycles' dates, validates as iCalendar, names no one, and stops
working once reset or once its person is no longer a member."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from icalendar import Calendar
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import calendar_feed
from horatio.models import ScheduledGame, Suspension, TroupeMembership
from tests.api_helpers import Person, Troupe, sign_up
from tests.test_api_character_search import member
from tests.test_api_troupe_profiles import add_game, save


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def visitor(client_for: Callable[[], TestClient]) -> TestClient:
    """A calendar app: not signed in."""
    return client_for()


def game(troupe: Troupe, starts_in: timedelta = timedelta(days=3)) -> str:
    response = add_game(troupe, starts_in)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def rsvp(person: Person, troupe: Troupe, game_id: str, answer: str | None) -> Any:
    path = f"/troupes/{troupe.id}/games/{game_id}/rsvp"
    if answer is None:
        return person.client.delete(path)
    return person.client.put(path, json={"answer": answer})


def games(person: Person, troupe: Troupe) -> Any:
    return person.client.get(f"/troupes/{troupe.id}/games")


def new_link(person: Person, troupe_id: str | None) -> str:
    response = person.client.post("/calendar/links", json={"troupe_id": troupe_id})
    assert response.status_code == 200, response.text
    url: str = response.json()["url"]
    assert url.startswith("http") and url.endswith(".ics")
    return url


def fetch(visitor: TestClient, url: str) -> Any:
    """What a calendar app gets from the link."""
    return visitor.get(url.split("/api", 1)[1])


def cycle(troupe: Troupe, name: str, *, opened: bool) -> dict[str, Any]:
    now = datetime.now(UTC)
    made = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/cycles",
        json={
            "name": name,
            "closes_at": (now + timedelta(days=7)).isoformat(),
            "grace_ends_at": (now + timedelta(days=10)).isoformat(),
        },
    )
    assert made.status_code == 201, made.text
    if opened:
        response = troupe.storyteller.client.post(f"/cycles/{made.json()['id']}/open")
        assert response.status_code == 200, response.text
    return made.json()


def test_members_say_whether_they_are_coming_and_staff_see_who(troupe: Troupe) -> None:
    member(troupe, troupe.player, "Agnes", "Brujah")
    member(troupe, troupe.player, "Beatrix", "Toreador")
    soon = game(troupe)
    later = game(troupe, timedelta(days=30))

    assert rsvp(troupe.player, troupe, soon, "coming").status_code == 200
    assert rsvp(troupe.narrator, troupe, soon, "maybe").status_code == 200
    assert rsvp(troupe.assistant, troupe, later, "not_coming").status_code == 200

    # The player sees how many said each, and their own answer, but not who.
    seen = games(troupe.player, troupe)
    assert seen.status_code == 200, seen.text
    first, second = seen.json()
    assert first["id"] == soon and second["id"] == later
    assert (first["my_answer"], first["coming"], first["maybe"], first["not_coming"]) == (
        "coming",
        1,
        1,
        0,
    )
    assert first["answers"] is None
    assert second["my_answer"] is None and second["not_coming"] == 1

    # Staff, narrators too, see who, coming first, with the characters they play here.
    answers = games(troupe.narrator, troupe).json()[0]["answers"]
    assert [(a["person"]["handle"], a["answer"], a["characters"]) for a in answers] == [
        (troupe.player.handle, "coming", ["Agnes", "Beatrix"]),
        (troupe.narrator.handle, "maybe", []),
    ]
    # Never an email.
    assert troupe.player.email not in games(troupe.lead, troupe).text

    # One answer per person: a new one takes its place, and it can be taken back.
    changed = rsvp(troupe.player, troupe, soon, "not_coming").json()
    assert (changed["my_answer"], changed["coming"], changed["not_coming"]) == ("not_coming", 0, 1)
    cleared = rsvp(troupe.player, troupe, soon, None).json()
    assert (cleared["my_answer"], cleared["not_coming"]) == (None, 0)


def test_only_members_answer_and_only_while_the_game_is_to_come(
    troupe: Troupe, session: Session
) -> None:
    soon = game(troupe)
    assert games(troupe.stranger, troupe).status_code == 403
    assert rsvp(troupe.stranger, troupe, soon, "coming").status_code == 403
    # The player has no character here yet.
    assert rsvp(troupe.player, troupe, soon, "coming").status_code == 403
    member(troupe, troupe.player, "Agnes", "Brujah")
    assert rsvp(troupe.player, troupe, soon, "perhaps").status_code == 422
    assert rsvp(troupe.player, troupe, str(uuid.uuid4()), "coming").status_code == 404

    # Once a game is over, its answers stand as they are.
    over = session.get_one(ScheduledGame, uuid.UUID(soon))
    over.starts_at = datetime.now(UTC) - timedelta(hours=6)
    over.ends_at = datetime.now(UTC) - timedelta(hours=1)
    session.flush()
    assert rsvp(troupe.player, troupe, soon, "coming").status_code == 422


def test_a_game_taken_off_the_schedule_takes_its_answers_with_it(troupe: Troupe) -> None:
    member(troupe, troupe.player, "Agnes", "Brujah")
    soon = game(troupe)
    assert rsvp(troupe.player, troupe, soon, "coming").status_code == 200
    removed = troupe.storyteller.client.delete(f"/troupes/{troupe.id}/games/{soon}")
    assert removed.status_code == 204, removed.text
    assert games(troupe.player, troupe).json() == []


def test_the_feed_is_icalendar_with_the_games_and_the_open_cycles_dates(
    troupe: Troupe, visitor: TestClient
) -> None:
    assert save(troupe).status_code == 200
    member(troupe, troupe.player, "Agnes", "Brujah")
    soon = game(troupe)
    cycle(troupe, "November nights", opened=True)
    cycle(troupe, "December plans", opened=False)

    links = troupe.player.client.get("/calendar/links", params={"troupe_id": troupe.id})
    assert links.json() == {"troupe": None, "personal": None}
    url = new_link(troupe.player, troupe.id)
    assert troupe.player.client.get("/calendar/links", params={"troupe_id": troupe.id}).json() == {
        "troupe": {"url": url},
        "personal": None,
    }

    response = fetch(visitor, url)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/calendar")
    text = response.text
    # Lines end CRLF and are folded to 75 octets.
    assert "\r\n" in text and all(len(line.encode()) <= 75 for line in text.split("\r\n"))
    parsed = Calendar.from_ical(text)
    assert str(parsed["X-WR-CALNAME"]) == "Lords of the Night"
    events = {str(e["SUMMARY"]): e for e in parsed.walk("VEVENT")}
    assert set(events) == {
        "Game: Lords of the Night",
        "Downtimes due: November nights (Lords of the Night)",
        "Late downtimes close: November nights (Lords of the Night)",
    }
    played = events["Game: Lords of the Night"]
    assert str(played["UID"]) == f"game-{soon}@horatio"
    assert played.decoded("DTSTART").tzinfo is not None
    assert played.decoded("DTEND") - played.decoded("DTSTART") == timedelta(hours=5)
    # Members may see the street address, as anyone signed in may.
    assert str(played["LOCATION"]) == "The Crypt, 12 Mill Lane, Leeds LS1 4AB, Leeds"
    assert f"/troupes/{troupe.id}" in str(played["URL"])
    due = events["Downtimes due: November nights (Lords of the Night)"]
    late = events["Late downtimes close: November nights (Lords of the Night)"]
    assert late.decoded("DTSTART") - due.decoded("DTSTART") == timedelta(days=3)
    # No one is named in it.
    for person in (troupe.player, troupe.lead, troupe.storyteller):
        assert person.email not in text and person.handle not in text
    assert "Agnes" not in text


def test_resetting_a_link_stops_the_old_one(troupe: Troupe, visitor: TestClient) -> None:
    member(troupe, troupe.player, "Agnes", "Brujah")
    old = new_link(troupe.player, troupe.id)
    new = new_link(troupe.player, troupe.id)
    assert new != old
    assert fetch(visitor, old).status_code == 404
    assert fetch(visitor, new).status_code == 200
    # Some calendar apps ask with HEAD first.
    assert visitor.head(new.split("/api", 1)[1]).status_code == 200
    # A made-up address opens nothing.
    assert fetch(visitor, new.replace(new[-20:-4], "x" * 16)).status_code == 404


def test_only_members_get_a_link_and_it_stops_when_they_leave(
    troupe: Troupe, visitor: TestClient, session: Session
) -> None:
    refused = troupe.stranger.client.post("/calendar/links", json={"troupe_id": troupe.id})
    assert refused.status_code == 403
    assert (
        troupe.stranger.client.get("/calendar/links", params={"troupe_id": troupe.id}).status_code
        == 403
    )
    agnes = member(troupe, troupe.player, "Agnes", "Brujah")
    url = new_link(troupe.player, troupe.id)
    assert fetch(visitor, url).status_code == 200
    membership = session.scalars(
        select(TroupeMembership).where(TroupeMembership.character_id == uuid.UUID(agnes))
    ).one()
    membership.left_at = datetime.now(UTC)
    session.flush()
    assert fetch(visitor, url).status_code == 404


def test_a_suspended_persons_link_stops(
    troupe: Troupe, visitor: TestClient, session: Session
) -> None:
    member(troupe, troupe.player, "Agnes", "Brujah")
    url = new_link(troupe.player, troupe.id)
    session.add(
        Suspension(
            user_id=uuid.UUID(troupe.player.id),
            reason="A break.",
            suspended_by_id=uuid.UUID(troupe.custodian.id),
        )
    )
    session.flush()
    assert fetch(visitor, url).status_code == 404


def test_the_personal_feed_has_every_troupe_the_person_is_in(
    troupe: Troupe, client_for: Callable[[], TestClient], visitor: TestClient
) -> None:
    member(troupe, troupe.player, "Agnes", "Brujah")
    game(troupe)
    # A second troupe, which the player is staff of, and a third they are not in.
    made = troupe.custodian.client.post(
        "/troupes", json={"name": "Ravens of York", "lead_handle": troupe.player.handle}
    )
    assert made.status_code == 201, made.text
    elsewhere = troupe.custodian.client.post(
        "/troupes", json={"name": "Others", "lead_handle": troupe.lead.handle}
    )
    for troupe_id in (made.json()["id"], elsewhere.json()["id"]):
        start = datetime.now(UTC) + timedelta(days=5)
        lead = troupe.player if troupe_id == made.json()["id"] else troupe.lead
        added = lead.client.post(
            f"/troupes/{troupe_id}/games",
            json={
                "starts_at": start.isoformat(),
                "ends_at": (start + timedelta(hours=4)).isoformat(),
            },
        )
        assert added.status_code == 201, added.text

    url = new_link(troupe.player, None)
    links = troupe.player.client.get("/calendar/links", params={"troupe_id": troupe.id}).json()
    assert links == {"troupe": None, "personal": {"url": url}}
    parsed = Calendar.from_ical(fetch(visitor, url).text)
    assert str(parsed["X-WR-CALNAME"]) == "Your troupes"
    assert sorted(str(e["SUMMARY"]) for e in parsed.walk("VEVENT")) == [
        "Game: Lords of the Night",
        "Game: Ravens of York",
    ]
    # Someone in no troupe has an empty calendar, still a valid one.
    loner = sign_up(client_for, "loner")
    empty = Calendar.from_ical(fetch(visitor, new_link(loner, None)).text)
    assert empty.walk("VEVENT") == []


def test_text_is_escaped_and_long_lines_folded_without_splitting_a_character() -> None:
    assert calendar_feed.escaped("a, b; c\\d\ne") == "a\\, b\\; c\\\\d\\ne"
    line = "SUMMARY:" + "é" * 60
    folded = calendar_feed.folded(line)
    parts = folded.split("\r\n")
    assert all(len(p.encode()) <= 75 for p in parts)
    assert parts[0] + "".join(p[1:] for p in parts[1:]) == line
