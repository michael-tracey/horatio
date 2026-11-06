"""Player Nominations (#470): an optional troupe setting; written in downtimes,
reviewed by running staff with their authors, published once the cycle is past Due
without names, starred into the footer, and read about one's own character."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio import downtimes
from tests.api_helpers import Person, Troupe, backstory_optional, new_character, sign_up
from tests.test_api_downtimes import member_character, new_cycle, open_cycle


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def switch(troupe: Troupe, on: bool, by: Person | None = None) -> Any:
    return (by or troupe.storyteller).client.put(
        f"/troupes/{troupe.id}/player-nominations", json={"on": on}
    )


def write(person: Person, character: str, text: str, **about: str) -> Any:
    return person.client.post(
        f"/characters/{character}/downtime/nominations", json={"text": text, **about}
    )


def submit(person: Person, character: str) -> None:
    response = person.client.post(f"/characters/{character}/downtime/submit")
    assert response.status_code == 200, response.text


def review(troupe: Troupe, cycle: dict[str, Any], by: Person | None = None) -> Any:
    return (by or troupe.storyteller).client.get(f"/cycles/{cycle['id']}/nominations")


def entry(troupe: Troupe, cycle: dict[str, Any], text: str) -> dict[str, Any]:
    found = review(troupe, cycle).json()["nominations"]
    return next(n for n in found if n["text"] == text)


def publish(troupe: Troupe, cycle: dict[str, Any], by: Person | None = None) -> Any:
    return (by or troupe.storyteller).client.post(f"/cycles/{cycle['id']}/nominations/publish")


def months(person: Person, troupe: Troupe) -> Any:
    return person.client.get(f"/troupes/{troupe.id}/nominations")


def texts(month: dict[str, Any]) -> set[str]:
    return {n["text"] for n in month["nominations"]}


@pytest.fixture
def past_due(monkeypatch: pytest.MonkeyPatch) -> Callable[[], None]:
    """Move the clock past the cycle's Due (a week away), within its grace period."""

    def later() -> None:
        then = datetime.now(UTC) + timedelta(days=8)
        monkeypatch.setattr(downtimes, "now", lambda: then)

    return later


def the_month(troupe: Troupe) -> tuple[str, str, dict[str, Any]]:
    """Agnes (the player's) and Corin (the stranger's) at home, an open cycle, and
    Player Nominations on."""
    agnes = member_character(troupe, troupe.player, "Agnes")
    corin = member_character(troupe, troupe.stranger, "Corin")
    assert switch(troupe, True).status_code == 200
    return agnes, corin, open_cycle(troupe, new_cycle(troupe))


# --- the setting ----------------------------------------------------------------------------------


def test_with_the_setting_off_nothing_of_them_shows(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    cycle = open_cycle(troupe, new_cycle(troupe))

    assert troupe.player.client.get(f"/troupes/{troupe.id}").json()["player_nominations"] is False
    assert troupe.player.client.get(f"/troupes/{troupe.id}").json()["nominations"] is False
    assert (
        troupe.storyteller.client.get(f"/cycles/{cycle['id']}").json()["player_nominations"]
        is False
    )
    assert (
        troupe.player.client.get(f"/characters/{agnes}/downtime").json()["player_nominations"]
        is False
    )
    assert troupe.player.client.get(f"/characters/{agnes}/downtime/nominations").status_code == 409
    assert write(troupe.player, agnes, "Lovely scene").status_code == 409
    assert review(troupe, cycle).status_code == 409
    assert publish(troupe, cycle).status_code == 409
    assert months(troupe.player, troupe).status_code == 404
    assert months(troupe.lead, troupe).status_code == 404
    assert troupe.player.client.get(f"/troupes/{troupe.id}/nominations/starred").json() == []
    assert troupe.player.client.get(f"/characters/{agnes}/nominations").json() == []


def test_only_storytellers_switch_it_and_it_is_logged(troupe: Troupe) -> None:
    assert switch(troupe, True, troupe.assistant).status_code == 403
    assert switch(troupe, True, troupe.player).status_code == 403
    switched = switch(troupe, True)
    assert switched.status_code == 200, switched.text
    assert switched.json() == {"on": True}
    assert troupe.lead.client.get(f"/troupes/{troupe.id}").json()["player_nominations"] is True
    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert "storyteller switched Player Nominations on." in log


def test_switching_it_off_hides_what_was_published(
    troupe: Troupe, past_due: Callable[[], None]
) -> None:
    agnes, corin, cycle = the_month(troupe)
    assert (
        write(
            troupe.player, agnes, "Corin's toast was perfect", about_character_id=corin
        ).status_code
        == 201
    )
    submit(troupe.player, agnes)
    past_due()
    assert publish(troupe, cycle).status_code == 200
    assert entry(troupe, cycle, "Corin's toast was perfect")
    starred = entry(troupe, cycle, "Corin's toast was perfect")["id"]
    assert (
        troupe.storyteller.client.put(
            f"/nominations/{starred}/star", json={"starred": True}
        ).status_code
        == 200
    )

    assert switch(troupe, False).status_code == 200
    assert months(troupe.stranger, troupe).status_code == 404
    assert troupe.stranger.client.get(f"/troupes/{troupe.id}/nominations/starred").json() == []
    assert troupe.stranger.client.get(f"/characters/{corin}/nominations").json() == []
    # On again, it is all there as it was.
    assert switch(troupe, True).status_code == 200
    assert [texts(m) for m in months(troupe.stranger, troupe).json()] == [
        {"Corin's toast was perfect"}
    ]


# --- writing them --------------------------------------------------------------------------


def test_players_write_them_in_their_downtime_with_an_optional_link(troupe: Troupe) -> None:
    agnes, corin, _ = the_month(troupe)
    assert (
        troupe.player.client.get(f"/characters/{agnes}/downtime").json()["player_nominations"]
        is True
    )

    mine = troupe.player.client.get(f"/characters/{agnes}/downtime/nominations").json()
    names = {(a["name"], a["character_id"] is not None) for a in mine["choices"]}
    # The troupe's characters and its staff, by name.
    assert {("Agnes", True), ("Corin", True), ("lead", False), ("narrator", False)} <= names
    assert mine["nominations"] == [] and mine["submitted"] is False and mine["most"] == 1000

    lead_id = next(a["user_id"] for a in mine["choices"] if a["name"] == "lead")
    written = write(
        troupe.player, agnes, "  The court scene was magnificent  ", about_character_id=corin
    )
    assert written.status_code == 201, written.text
    assert (
        write(troupe.player, agnes, "Thank you for the ball", about_user_id=lead_id).status_code
        == 201
    )
    assert write(troupe.player, agnes, "Everyone, for a kind night").status_code == 201
    found = written.json()["nominations"][0]
    assert found["text"] == "The court scene was magnificent"
    assert found["about"] == {"character_id": corin, "user_id": None, "name": "Corin"}

    # Nothing empty, nothing too long, and only someone in the troupe.
    assert write(troupe.player, agnes, "   ").status_code == 422
    assert write(troupe.player, agnes, "x" * 1001).status_code == 422
    assert write(troupe.player, agnes, "Hi", about_user_id=troupe.stranger.id).status_code == 422
    both = write(troupe.player, agnes, "Hi", about_user_id=lead_id, about_character_id=corin)
    assert both.status_code == 422

    # Changed and taken out while the downtime can be.
    changed = troupe.player.client.put(
        f"/characters/{agnes}/downtime/nominations/{found['id']}",
        json={"text": "The court scene was wonderful", "about_character_id": None},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["nominations"][0]["about"] is None
    last = changed.json()["nominations"][2]["id"]
    gone = troupe.player.client.delete(f"/characters/{agnes}/downtime/nominations/{last}")
    assert [n["text"] for n in gone.json()["nominations"]] == [
        "The court scene was wonderful",
        "Thank you for the ball",
    ]
    # Another player can't touch them, from Agnes or from their own character.
    assert troupe.stranger.client.delete(
        f"/characters/{agnes}/downtime/nominations/{found['id']}"
    ).status_code in (403, 404)
    assert (
        troupe.stranger.client.delete(
            f"/characters/{corin}/downtime/nominations/{found['id']}"
        ).status_code
        == 422
    )


def test_staff_read_them_only_once_the_downtime_is_submitted(troupe: Troupe) -> None:
    agnes, _, cycle = the_month(troupe)
    assert write(troupe.player, agnes, "A fine duel").status_code == 201
    assert review(troupe, cycle).json()["nominations"] == []
    submit(troupe.player, agnes)
    assert [n["text"] for n in review(troupe, cycle).json()["nominations"]] == ["A fine duel"]
    # They don't count against the actions.
    assert (
        troupe.player.client.get(f"/characters/{agnes}/downtime/nominations").json()["submitted"]
        is True
    )


# --- reviewing them -------------------------------------------------------------------------------


def test_running_staff_review_them_with_their_authors(troupe: Troupe) -> None:
    agnes, corin, cycle = the_month(troupe)
    assert (
        write(troupe.player, agnes, "Corin made me laugh", about_character_id=corin).status_code
        == 201
    )
    assert write(troupe.player, agnes, "Bob from work was great").status_code == 201
    submit(troupe.player, agnes)

    for person in (troupe.narrator, troupe.player, troupe.stranger):
        assert review(troupe, cycle, person).status_code == 403
    got = review(troupe, cycle, troupe.assistant).json()
    found = {n["text"]: n for n in got["nominations"]}
    laugh = found["Corin made me laugh"]
    assert (laugh["character_name"], laugh["player_handle"]) == ("Agnes", troupe.player.handle)
    assert laugh["about"]["name"] == "Corin"
    assert (got["written"], got["removed"], got["starred"], got["waiting"]) == (2, 0, 0, 2)

    # Remove with a reason for staff, star, and lightly edit.
    bob = found["Bob from work was great"]["id"]
    removed = troupe.assistant.client.post(
        f"/nominations/{bob}/remove", json={"reason": "Real name"}
    )
    assert removed.status_code == 200, removed.text
    starred = troupe.assistant.client.put(
        f"/nominations/{laugh['id']}/star", json={"starred": True}
    )
    assert starred.status_code == 200
    edited = troupe.assistant.client.put(
        f"/nominations/{laugh['id']}/text", json={"text": "Corin made me laugh so much"}
    )
    assert edited.status_code == 200
    got = edited.json()
    found = {n["id"]: n for n in got["nominations"]}
    assert (found[bob]["removed"], found[bob]["removed_reason"]) == (True, "Real name")
    assert (found[laugh["id"]]["starred"], found[laugh["id"]]["edited"]) == (True, True)
    assert found[laugh["id"]]["text"] == "Corin made me laugh so much"
    assert (got["written"], got["removed"], got["starred"], got["waiting"]) == (2, 1, 1, 1)
    assert troupe.narrator.client.post(f"/nominations/{bob}/restore").status_code == 403
    restored = troupe.assistant.client.post(f"/nominations/{bob}/restore")
    assert restored.json()["removed"] == 0

    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert (
        "assistant removed a Player Nomination from October 2026 (Real name):"
        ' "Bob from work was great"' in log
    )
    assert 'assistant starred a Player Nomination from October 2026: "Corin made me laugh"' in log
    assert any(m.startswith("assistant edited a Player Nomination in October 2026") for m in log)
    assert (
        'assistant put back a Player Nomination in October 2026: "Bob from work was great"' in log
    )


# --- publishing them ------------------------------------------------------------------------------


def test_publish_only_once_past_due_then_late_ones_wait_for_publish_more(
    troupe: Troupe, past_due: Callable[[], None]
) -> None:
    agnes, corin, cycle = the_month(troupe)
    assert write(troupe.player, agnes, "First light").status_code == 201
    submit(troupe.player, agnes)

    refused = publish(troupe, cycle)
    assert refused.status_code == 409
    assert "past Due" in refused.json()["detail"]
    assert review(troupe, cycle).json()["past_due"] is False
    past_due()
    assert review(troupe, cycle).json()["past_due"] is True
    assert publish(troupe, cycle, troupe.narrator).status_code == 403
    published = publish(troupe, cycle)
    assert published.status_code == 200, published.text
    assert published.json() == {"count": 1}
    got = review(troupe, cycle).json()
    assert got["published_at"] is not None and got["waiting"] == 0
    # Once only: nothing new, nothing to publish.
    assert publish(troupe, cycle).status_code == 409

    # Corin's player writes during the grace period: it waits on the tab.
    assert write(troupe.stranger, corin, "Second light").status_code == 201
    submit(troupe.stranger, corin)
    assert review(troupe, cycle).json()["waiting"] == 1
    assert [texts(m) for m in months(troupe.player, troupe).json()] == [{"First light"}]
    assert publish(troupe, cycle).json() == {"count": 1}
    [month] = months(troupe.player, troupe).json()
    assert texts(month) == {"First light", "Second light"}
    # A published one can't be changed by its writer.
    first = entry(troupe, cycle, "First light")["id"]
    assert (
        troupe.player.client.put(
            f"/characters/{agnes}/downtime/nominations/{first}", json={"text": "Changed"}
        ).status_code
        == 409
    )
    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert "storyteller published October 2026's Player Nominations (1)." in log
    assert "storyteller published 1 more of October 2026's Player Nominations." in log


def test_the_published_page_is_shuffled_once_and_names_no_one(
    troupe: Troupe, past_due: Callable[[], None]
) -> None:
    agnes, corin, cycle = the_month(troupe)
    for n in range(12):
        assert (
            write(troupe.player, agnes, f"Kind word {n}", about_character_id=corin).status_code
            == 201
        )
    submit(troupe.player, agnes)
    past_due()
    assert publish(troupe, cycle).status_code == 200

    response = months(troupe.stranger, troupe)
    assert response.status_code == 200, response.text
    [month] = response.json()
    assert month["name"] == "October 2026"
    order = [n["text"] for n in month["nominations"]]
    assert set(order) == {f"Kind word {n}" for n in range(12)}
    # Shuffled, and kept: the same order on every visit.
    assert order != [f"Kind word {n}" for n in range(12)]
    assert [n["text"] for n in months(troupe.player, troupe).json()[0]["nominations"]] == order
    assert [n["order"] for n in month["nominations"]] == sorted(
        n["order"] for n in month["nominations"]
    )
    # No author anywhere in it; the link shows as plain text.
    assert set(month["nominations"][0]) == {"id", "text", "about", "starred", "edited", "order"}
    assert month["nominations"][0]["about"] == "Corin"
    assert "Agnes" not in response.text and troupe.player.handle not in response.text


def test_staff_remove_one_after_publishing_and_it_goes(
    troupe: Troupe, past_due: Callable[[], None]
) -> None:
    agnes, _, cycle = the_month(troupe)
    assert write(troupe.player, agnes, "Keep me").status_code == 201
    assert write(troupe.player, agnes, "Not me").status_code == 201
    submit(troupe.player, agnes)
    past_due()
    assert publish(troupe, cycle).status_code == 200
    gone = entry(troupe, cycle, "Not me")["id"]
    assert (
        troupe.storyteller.client.put(
            f"/nominations/{gone}/star", json={"starred": True}
        ).status_code
        == 200
    )
    assert troupe.storyteller.client.post(f"/nominations/{gone}/remove", json={}).status_code == 200
    assert [texts(m) for m in months(troupe.stranger, troupe).json()] == [{"Keep me"}]
    assert troupe.stranger.client.get(f"/troupes/{troupe.id}/nominations/starred").json() == []
    # Restored, it is back.
    assert troupe.storyteller.client.post(f"/nominations/{gone}/restore").status_code == 200
    assert [texts(m) for m in months(troupe.stranger, troupe).json()] == [{"Keep me", "Not me"}]


# --- reading them ---------------------------------------------------------------------------------


def test_the_troupes_players_and_staff_read_them_but_not_visitors(
    troupe: Troupe, client_for: Callable[[], TestClient], past_due: Callable[[], None]
) -> None:
    agnes, _, cycle = the_month(troupe)
    # A player whose character only visits.
    visitor = sign_up(client_for, "visitor")
    elsewhere = troupe.custodian.client.post(
        "/troupes", json={"name": "Barons of the Bay", "lead_handle": troupe.lead.handle}
    ).json()["id"]
    backstory_optional(troupe.session, elsewhere)
    guest = new_character(troupe, visitor, "Guest")
    asked = visitor.client.post(f"/characters/{guest}/home-troupe", json={"troupe_id": elsewhere})
    assert (
        troupe.lead.client.post(f"/approvals/{asked.json()['id']}/approve", json={}).status_code
        == 200
    )
    assert (
        visitor.client.post(
            f"/characters/{guest}/troupes", json={"troupe_id": troupe.id}
        ).status_code
        == 201
    )

    assert write(troupe.player, agnes, "Lovely").status_code == 201
    submit(troupe.player, agnes)
    past_due()
    assert publish(troupe, cycle).status_code == 200

    for person in (troupe.player, troupe.stranger, troupe.narrator, troupe.lead, troupe.custodian):
        assert months(person, troupe).status_code == 200
        assert person.client.get(f"/troupes/{troupe.id}").json()["nominations"] is True
    outsider = sign_up(client_for, "outsider")
    for person in (visitor, outsider):
        assert months(person, troupe).status_code == 404
        assert person.client.get(f"/troupes/{troupe.id}/nominations/starred").json() == []
    assert visitor.client.get(f"/troupes/{troupe.id}").json()["nominations"] is False
    # The visitor's character can still be named in one.
    assert any(
        a["name"] == "Guest"
        for a in troupe.player.client.get(f"/characters/{agnes}/downtime/nominations").json()[
            "choices"
        ]
    )


def test_a_linked_characters_player_reads_those_about_it_and_is_told(
    troupe: Troupe, past_due: Callable[[], None]
) -> None:
    agnes, corin, cycle = the_month(troupe)
    assert (
        write(troupe.player, agnes, "Corin's speech moved me", about_character_id=corin).status_code
        == 201
    )
    assert write(troupe.player, agnes, "Removed one", about_character_id=corin).status_code == 201
    assert write(troupe.player, agnes, "About no one").status_code == 201
    submit(troupe.player, agnes)
    removed = entry(troupe, cycle, "Removed one")["id"]
    assert (
        troupe.storyteller.client.post(f"/nominations/{removed}/remove", json={}).status_code == 200
    )
    # Nothing before it is published.
    assert troupe.stranger.client.get(f"/characters/{corin}/nominations").json() == []
    past_due()
    assert publish(troupe, cycle).status_code == 200

    about = troupe.stranger.client.get(f"/characters/{corin}/nominations")
    assert about.status_code == 200
    assert [(n["text"], n["month"], n["troupe_name"]) for n in about.json()] == [
        ("Corin's speech moved me", "October 2026", "Lords of the Night")
    ]
    assert "Agnes" not in about.text
    # Only its player reads them there.
    assert troupe.player.client.get(f"/characters/{corin}/nominations").status_code in (403, 404)

    def told(person: Person) -> list[tuple[str, str]]:
        items = person.client.get("/notifications").json()["items"]
        return sorted(
            (i["summary"], i["link"]) for i in items if i["kind"].startswith("nominations.")
        )

    assert told(troupe.stranger) == [
        ("Corin is named in October 2026's Player Nominations", f"/characters/{corin}"),
        ("October 2026's Player Nominations are up", f"/troupes/{troupe.id}/nominations"),
    ]
    assert told(troupe.player) == [
        ("October 2026's Player Nominations are up", f"/troupes/{troupe.id}/nominations")
    ]


def test_every_starred_one_from_every_month_is_in_the_footer(
    troupe: Troupe, monkeypatch: pytest.MonkeyPatch
) -> None:
    agnes, corin, first = the_month(troupe)
    start = datetime.now(UTC)
    assert write(troupe.player, agnes, "October star").status_code == 201
    assert write(troupe.player, agnes, "October plain").status_code == 201
    submit(troupe.player, agnes)
    starred = entry(troupe, first, "October star")["id"]
    assert (
        troupe.storyteller.client.put(
            f"/nominations/{starred}/star", json={"starred": True}
        ).status_code
        == 200
    )
    # Starred but not yet published: not in the footer.
    assert troupe.player.client.get(f"/troupes/{troupe.id}/nominations/starred").json() == []
    monkeypatch.setattr(downtimes, "now", lambda: start + timedelta(days=8))
    assert publish(troupe, first).status_code == 200
    assert (
        troupe.storyteller.client.post(f"/cycles/{first['id']}/close", json={}).status_code == 200
    )

    second = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/cycles",
        json={
            "name": "November 2026",
            "closes_at": (start + timedelta(days=20)).isoformat(),
            "grace_ends_at": (start + timedelta(days=25)).isoformat(),
        },
    ).json()
    assert troupe.storyteller.client.post(f"/cycles/{second['id']}/open").status_code == 200
    assert write(troupe.stranger, corin, "November star").status_code == 201
    submit(troupe.stranger, corin)
    november = entry(troupe, second, "November star")["id"]
    assert (
        troupe.storyteller.client.put(
            f"/nominations/{november}/star", json={"starred": True}
        ).status_code
        == 200
    )
    monkeypatch.setattr(downtimes, "now", lambda: start + timedelta(days=21))
    assert publish(troupe, second).status_code == 200

    footer = troupe.player.client.get(f"/troupes/{troupe.id}/nominations/starred").json()
    assert sorted((n["text"], n["month"]) for n in footer) == [
        ("November star", "November 2026"),
        ("October star", "October 2026"),
    ]
    assert set(footer[0]) == {"id", "text", "month"}
    # Newest month first on the page.
    assert [m["name"] for m in months(troupe.player, troupe).json()] == [
        "November 2026",
        "October 2026",
    ]
    # Unstarred, it leaves the rotation.
    assert (
        troupe.lead.client.put(f"/nominations/{starred}/star", json={"starred": False}).status_code
        == 200
    )
    footer = troupe.player.client.get(f"/troupes/{troupe.id}/nominations/starred").json()
    assert [n["text"] for n in footer] == ["November star"]
