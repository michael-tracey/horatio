"""Remembrances (#471): an optional troupe setting; opened by staff for a character
who leaves play, or asked for by its player; the right cycle asks the troupe for a
memory; reviewed and published with the Player Nominations, without names; kept with
the character and on the Who's Who, even after the setting is switched off."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio import downtimes
from tests.api_helpers import Person, Troupe, sign_up
from tests.test_api_downtimes import member_character, new_cycle, open_cycle


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def switch(troupe: Troupe, on: bool, by: Person | None = None) -> Any:
    return (by or troupe.storyteller).client.put(
        f"/troupes/{troupe.id}/remembrances", json={"on": on}
    )


def retire(person: Person, character: str, remembrances: bool = True) -> Any:
    response = person.client.post(
        f"/characters/{character}/retire",
        json={"reason": "final_death", "note": "", "listed": True, "remembrances": remembrances},
    )
    assert response.status_code == 200, response.text
    return response.json()


def standing(person: Person, character: str) -> Any:
    return person.client.get(f"/characters/{character}/remembrances")


def open_for(person: Person, character: str) -> Any:
    return person.client.post(f"/characters/{character}/remembrances/open")


def asked(person: Person, character: str) -> Any:
    return person.client.get(f"/characters/{character}/downtime/remembrances")


def remember(person: Person, character: str, remembrance: str, text: str) -> Any:
    return person.client.put(
        f"/characters/{character}/downtime/remembrances/{remembrance}", json={"text": text}
    )


def submit(person: Person, character: str) -> None:
    response = person.client.post(f"/characters/{character}/downtime/submit")
    assert response.status_code == 200, response.text


def review(troupe: Troupe, cycle: dict[str, Any], by: Person | None = None) -> Any:
    return (by or troupe.storyteller).client.get(f"/cycles/{cycle['id']}/nominations")


def publish(troupe: Troupe, cycle: dict[str, Any]) -> Any:
    return troupe.storyteller.client.post(f"/cycles/{cycle['id']}/nominations/publish")


def whos_who_entry(person: Person, troupe: Troupe, name: str) -> dict[str, Any]:
    found = person.client.get(f"/troupes/{troupe.id}/whos-who").json()["entries"]
    return next(e for e in found if e["name"] == name)


@pytest.fixture
def later(monkeypatch: pytest.MonkeyPatch) -> Callable[[int], None]:
    """Move the clock on by some days."""
    start = datetime.now(UTC)

    def by(days: int) -> None:
        monkeypatch.setattr(downtimes, "now", lambda: start + timedelta(days=days))

    return by


def the_troupe(troupe: Troupe) -> tuple[str, str, str]:
    """Agnes and Bram (the player's) and Corin (the stranger's) at home, with
    Remembrances on and Player Nominations off."""
    agnes = member_character(troupe, troupe.player, "Agnes")
    bram = member_character(troupe, troupe.player, "Bram")
    corin = member_character(troupe, troupe.stranger, "Corin")
    assert switch(troupe, True).status_code == 200
    return agnes, bram, corin


# --- the setting --------------------------------------------------------------------------


def test_with_the_setting_off_none_of_it_shows(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    corin = member_character(troupe, troupe.stranger, "Corin")
    cycle = open_cycle(troupe, new_cycle(troupe))
    assert troupe.player.client.get(f"/troupes/{troupe.id}").json()["remembrances"] is False
    # Asking for them while retiring does nothing.
    retire(troupe.player, agnes)
    got = standing(troupe.player, agnes).json()
    assert (got["on"], got["state"], got["can_open"], got["months"]) == (False, "none", False, [])
    assert standing(troupe.storyteller, agnes).json()["can_open"] is False
    assert open_for(troupe.storyteller, agnes).status_code == 409
    assert (
        troupe.stranger.client.get(f"/characters/{corin}/downtime").json()["remembrances"] is False
    )
    assert asked(troupe.stranger, corin).status_code == 409
    assert troupe.storyteller.client.get(f"/cycles/{cycle['id']}").json()["remembrances"] is False
    assert review(troupe, cycle).status_code == 409
    entry = whos_who_entry(troupe.lead, troupe, "Agnes")
    assert (entry["remembered"], entry["remembrances_openable"]) == (False, False)


def test_only_storytellers_switch_it_and_it_is_logged(troupe: Troupe) -> None:
    assert switch(troupe, True, troupe.assistant).status_code == 403
    assert switch(troupe, True).json() == {"on": True}
    assert troupe.player.client.get(f"/troupes/{troupe.id}").json()["remembrances"] is True
    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert "storyteller switched Remembrances on." in log


# --- opening them -------------------------------------------------------------------------


def test_a_player_asks_as_they_retire_and_staff_open_them_in_the_open_cycle(
    troupe: Troupe,
) -> None:
    agnes, _, _ = the_troupe(troupe)
    cycle = open_cycle(troupe, new_cycle(troupe))
    retire(troupe.player, agnes)
    got = standing(troupe.player, agnes).json()
    assert (got["state"], got["can_open"], got["cycle_name"]) == ("asked", False, "October 2026")
    # Running staff are told, and confirm by opening them.
    told = [
        i["summary"]
        for i in troupe.assistant.client.get("/notifications").json()["items"]
        if i["kind"] == "remembrance.asked"
    ]
    assert told == ["Agnes's player asks for remembrances of Agnes"]
    assert open_for(troupe.player, agnes).status_code == 403
    assert open_for(troupe.narrator, agnes).status_code in (403, 404)
    staff = standing(troupe.assistant, agnes).json()
    assert (staff["state"], staff["can_open"]) == ("asked", True)
    opened = open_for(troupe.assistant, agnes)
    assert opened.status_code == 200, opened.text
    assert (opened.json()["state"], opened.json()["cycle_name"]) == ("open", cycle["name"])
    assert open_for(troupe.assistant, agnes).status_code == 409
    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert any(m.startswith("assistant opened remembrances for Agnes") for m in log)


def test_another_player_never_sees_the_asking(troupe: Troupe) -> None:
    """Asking is between the player and staff: to the troupe's other players it would
    say the character has left play, which it may not tell them (#659)."""
    agnes, _, corin = the_troupe(troupe)
    open_cycle(troupe, new_cycle(troupe))
    response = troupe.player.client.post(
        f"/characters/{agnes}/retire",
        json={"reason": "final_death", "note": "", "listed": False, "remembrances": True},
    )
    assert response.status_code == 200, response.text
    assert standing(troupe.player, agnes).json()["state"] == "asked"
    assert standing(troupe.assistant, agnes).json()["state"] == "asked"
    # Corin's player, and a narrator, see what they would of an active character.
    for person in (troupe.stranger, troupe.narrator):
        got = standing(person, agnes).json()
        assert got == standing(person, corin).json() and got["state"] == "none"
    # Once staff open them, the troupe is asked, so everyone sees it.
    assert open_for(troupe.assistant, agnes).status_code == 200
    assert standing(troupe.stranger, agnes).json()["state"] == "open"


def test_staff_open_them_as_they_retire_one_and_an_active_one_has_none(troupe: Troupe) -> None:
    _, _, corin = the_troupe(troupe)
    # Only a character who has left play.
    assert open_for(troupe.storyteller, corin).status_code == 409
    # A storyteller retiring their own character opens them at once.
    own = member_character(troupe, troupe.storyteller, "Dorian")
    retire(troupe.storyteller, own)
    assert standing(troupe.storyteller, own).json()["state"] == "open"


def test_the_cycle_is_the_open_one_before_due_or_else_the_next_to_open(
    troupe: Troupe, later: Callable[[int], None]
) -> None:
    agnes, bram, corin = the_troupe(troupe)
    first = open_cycle(troupe, new_cycle(troupe))
    later(8)  # past the first cycle's Due
    retire(troupe.player, agnes, remembrances=False)
    assert standing(troupe.storyteller, agnes).json()["cycle_name"] is None
    assert open_for(troupe.storyteller, agnes).json()["cycle_name"] is None
    # The open cycle, past Due, doesn't ask.
    assert (
        troupe.stranger.client.get(f"/characters/{corin}/downtime").json()["remembrances"] is False
    )
    assert (
        troupe.storyteller.client.post(f"/cycles/{first['id']}/close", json={}).status_code == 200
    )

    # The next cycle to open does.
    second = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/cycles",
        json={
            "name": "November 2026",
            "closes_at": (datetime.now(UTC) + timedelta(days=20)).isoformat(),
            "grace_ends_at": (datetime.now(UTC) + timedelta(days=25)).isoformat(),
        },
    ).json()
    assert troupe.storyteller.client.post(f"/cycles/{second['id']}/open").status_code == 200
    assert standing(troupe.player, agnes).json()["cycle_name"] == "November 2026"
    assert (
        troupe.stranger.client.get(f"/characters/{corin}/downtime").json()["remembrances"] is True
    )
    [one] = asked(troupe.player, bram).json()["remembered"]
    assert (one["name"], one["reason"], one["text"]) == ("Agnes", "Final Death", None)


# --- writing, reviewing and publishing them -----------------------------------------------


def test_the_troupe_writes_one_memory_each_staff_review_and_publish_them(
    troupe: Troupe, later: Callable[[int], None]
) -> None:
    agnes, bram, corin = the_troupe(troupe)
    cycle = open_cycle(troupe, new_cycle(troupe))
    retire(troupe.player, agnes)
    assert open_for(troupe.storyteller, agnes).status_code == 200
    [one] = asked(troupe.stranger, corin).json()["remembered"]
    remembrance = one["remembrance_id"]

    # One each: writing again changes it.
    assert (
        remember(troupe.stranger, corin, remembrance, "She laughed at the Prince").status_code
        == 200
    )
    again = remember(troupe.stranger, corin, remembrance, "She laughed at the Prince, once")
    assert again.json()["remembered"][0]["text"] == "She laughed at the Prince, once"
    assert remember(troupe.stranger, corin, remembrance, "  ").status_code == 422
    # The retired character's own player can write one too, from another character.
    assert remember(troupe.player, bram, remembrance, "My sire, my friend").status_code == 200
    submit(troupe.stranger, corin)
    submit(troupe.player, bram)

    assert review(troupe, cycle, troupe.narrator).status_code == 403
    got = review(troupe, cycle).json()
    assert (got["player_nominations"], got["remembrances_on"], got["nominations"]) == (
        False,
        True,
        [],
    )
    [section] = got["remembrances"]
    assert (section["name"], section["reason"]) == ("Agnes", "Final Death")
    memories = {m["text"]: m for m in section["memories"]}
    assert memories["My sire, my friend"]["character_name"] == "Bram"
    laughed = memories["She laughed at the Prince, once"]["id"]
    # Not starred: stars are for nominations.
    assert (
        troupe.storyteller.client.put(
            f"/nominations/{laughed}/star", json={"starred": True}
        ).status_code
        == 409
    )
    edited = troupe.storyteller.client.put(
        f"/nominations/{laughed}/text", json={"text": "She laughed at the Prince once."}
    )
    assert edited.status_code == 200

    # Published with the cycle's one Publish, once past Due.
    assert publish(troupe, cycle).status_code == 409
    later(8)
    published = publish(troupe, cycle)
    assert published.status_code == 200, published.text
    assert published.json() == {"count": 2}
    # A memory published can't be changed by its writer.
    assert remember(troupe.stranger, corin, remembrance, "Changed").status_code == 409

    # The troupe's players are told, and Agnes's player has a notification of their own.
    def told(person: Person) -> list[tuple[str, str]]:
        items = person.client.get("/notifications").json()["items"]
        return sorted(
            (i["summary"], i["link"]) for i in items if i["kind"].startswith("remembrance.")
        )

    assert told(troupe.stranger) == [
        ("Remembrances for Agnes are up", f"/troupes/{troupe.id}/nominations")
    ]
    assert told(troupe.player) == [
        ("The troupe's remembrances of Agnes are up", f"/characters/{agnes}")
    ]
    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert any(m.startswith("storyteller edited a memory of Agnes in October 2026") for m in log)

    # On the month's page, beside the nominations, without names.
    [month] = troupe.stranger.client.get(f"/troupes/{troupe.id}/nominations").json()
    [remembered] = month["remembrances"]
    assert (remembered["name"], remembered["reason"]) == ("Agnes", "Final Death")
    assert {m["text"] for m in remembered["memories"]} == {
        "She laughed at the Prince once.",
        "My sire, my friend",
    }
    assert month["nominations"] == []
    assert "Bram" not in str(month) and "Corin" not in str(month)


# --- reading them -------------------------------------------------------------------------


def test_kept_with_the_character_and_the_whos_who_even_once_switched_off(
    troupe: Troupe, client_for: Callable[[], TestClient], later: Callable[[int], None]
) -> None:
    agnes, bram, corin = the_troupe(troupe)
    cycle = open_cycle(troupe, new_cycle(troupe))
    retire(troupe.player, agnes)
    assert open_for(troupe.storyteller, agnes).status_code == 200
    [one] = asked(troupe.stranger, corin).json()["remembered"]
    for person, character, text in (
        (troupe.stranger, corin, "Kind to the end"),
        (troupe.player, bram, "Taken out later"),
    ):
        assert remember(person, character, one["remembrance_id"], text).status_code == 200
        submit(person, character)
    later(8)
    assert publish(troupe, cycle).status_code == 200

    def memories(person: Person) -> list[str]:
        got = standing(person, agnes).json()
        return [m["text"] for month in got["months"] for m in month["memories"]]

    # Its player, the troupe's players and staff read them; no one else.
    for person in (troupe.player, troupe.stranger, troupe.narrator, troupe.lead):
        assert sorted(memories(person)) == ["Kind to the end", "Taken out later"]
    outsider = sign_up(client_for, "outsider")
    assert standing(outsider, agnes).status_code == 404
    assert "Corin" not in standing(troupe.player, agnes).text
    entry = whos_who_entry(troupe.stranger, troupe, "Agnes")
    assert (entry["remembered"], entry["remembrances_openable"]) == (True, False)

    # Removed after publishing, it goes everywhere.
    taken = next(
        m["id"]
        for m in review(troupe, cycle).json()["remembrances"][0]["memories"]
        if m["text"] == "Taken out later"
    )
    assert (
        troupe.storyteller.client.post(f"/nominations/{taken}/remove", json={}).status_code == 200
    )
    assert memories(troupe.stranger) == ["Kind to the end"]

    # Switched off: none can be opened or written, but those published stay.
    assert switch(troupe, False).status_code == 200
    got = standing(troupe.player, agnes).json()
    assert (got["on"], got["can_open"]) == (False, False)
    assert memories(troupe.player) == ["Kind to the end"]
    assert whos_who_entry(troupe.stranger, troupe, "Agnes")["remembered"] is True
    # Nothing else of them shows: the month's page is gone with both settings off.
    assert troupe.stranger.client.get(f"/troupes/{troupe.id}/nominations").status_code == 404
    assert review(troupe, cycle).status_code == 409


def test_staff_open_them_from_the_whos_who_and_nominations_are_independent(
    troupe: Troupe,
) -> None:
    agnes, _, corin = the_troupe(troupe)
    retire(troupe.player, agnes, remembrances=False)
    assert whos_who_entry(troupe.lead, troupe, "Agnes")["remembrances_openable"] is True
    assert whos_who_entry(troupe.stranger, troupe, "Agnes")["remembrances_openable"] is False
    assert open_for(troupe.lead, agnes).status_code == 200
    assert whos_who_entry(troupe.lead, troupe, "Agnes")["remembrances_openable"] is False
    # Player Nominations stay off: no nominations section, no footer.
    cycle = open_cycle(troupe, new_cycle(troupe))
    form = troupe.stranger.client.get(f"/characters/{corin}/downtime").json()
    assert (form["player_nominations"], form["remembrances"]) == (False, True)
    assert (
        troupe.stranger.client.get(f"/characters/{corin}/downtime/nominations").status_code == 409
    )
    assert troupe.stranger.client.get(f"/troupes/{troupe.id}/nominations/starred").json() == []
    assert troupe.storyteller.client.get(f"/cycles/{cycle['id']}").json()["remembrances"] is True
