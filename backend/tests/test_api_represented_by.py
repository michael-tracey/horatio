"""Seats at court and Represented by (horatio.whos_who, #267): which clans have a seat
at a troupe's court, and who speaks there for a character of a clan without one."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, sign_up
from tests.test_api_sect_status import entitle, member


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def seen(person: Person, troupe: Troupe) -> dict[str, Any]:
    response = person.client.get(f"/troupes/{troupe.id}/whos-who")
    assert response.status_code == 200, response.text
    return response.json()


def names(found: dict[str, Any], ids: list[str]) -> list[str]:
    by_id = {e["character_id"]: e["name"] for e in found["entries"]}
    return [by_id[i] for i in ids]


def entry(found: dict[str, Any], name: str) -> dict[str, Any]:
    return next(e for e in found["entries"] if e["name"] == name)


def seat(person: Person, troupe: Troupe, clans: list[str] | None) -> Any:
    return person.client.put(f"/troupes/{troupe.id}/seats", json={"clans": clans})


def represent(person: Person, troupe: Troupe, character_id: str, words: str | None) -> Any:
    return person.client.put(
        f"/troupes/{troupe.id}/characters/{character_id}/represented-by",
        json={"represented_by": words},
    )


def test_staff_choose_the_clans_with_a_seat(troupe: Troupe) -> None:
    brujah = member(troupe, "Bruno", clan="Brujah")
    member(troupe, "Ravi", clan="Ravnos")
    member(troupe, "Gwen", clan="Gangrel")
    entitle(troupe, brujah, "Primogen")

    # Until staff choose, the clans whose Primogen is held here have a seat.
    seats = troupe.assistant.client.get(f"/troupes/{troupe.id}/seats").json()
    assert (seats["seated"], seats["chosen"], seats["primogen"]) == (["Brujah"], False, ["Brujah"])
    assert {"Brujah", "Gangrel", "Ravnos", "Ventrue"} <= set(seats["clans"])
    found = seen(troupe.player, troupe)
    assert [c["clan"] for c in found["clans"]] == ["Brujah"]
    assert names(found, found["other"]) == ["Gwen", "Ravi"]

    # Seating the Ravnos moves them into their own section.
    chosen = seat(troupe.assistant, troupe, ["Ravnos", "Brujah"])
    assert chosen.status_code == 200, chosen.text
    assert (chosen.json()["seated"], chosen.json()["chosen"]) == (["Brujah", "Ravnos"], True)
    found = seen(troupe.player, troupe)
    assert found["seated"] == ["Brujah", "Ravnos"]
    assert [(c["clan"], names(found, c["character_ids"])) for c in found["clans"]] == [
        ("Brujah", ["Bruno"]),
        ("Ravnos", ["Ravi"]),
    ]
    assert names(found, found["other"]) == ["Gwen"]
    # Who holds Primogen no longer decides it.
    entitle(troupe, brujah)
    assert seen(troupe.player, troupe)["seated"] == ["Brujah", "Ravnos"]

    # Only the troupe's clans, and at least one.
    assert seat(troupe.storyteller, troupe, ["Ravnos", "Lasombra Antitribu"]).status_code == 422
    assert seat(troupe.storyteller, troupe, []).status_code == 422
    for person in (troupe.player, troupe.narrator):
        assert seat(person, troupe, ["Ravnos"]).status_code == 403
        assert person.client.get(f"/troupes/{troupe.id}/seats").status_code == 403

    # Back to the default: no one holds Primogen now, so every clan has a seat.
    back = seat(troupe.storyteller, troupe, None)
    assert back.status_code == 200, back.text
    assert (back.json()["seated"], back.json()["chosen"]) == (None, False)
    assert seen(troupe.player, troupe)["other"] == []
    log = troupe.storyteller.client.get(f"/troupes/{troupe.id}/log").json()
    assert "storyteller gave seats at court to those whose Primogen is held here." in [
        e["message"] for e in log
    ]


def test_a_player_says_who_represents_a_character_of_a_clan_without_a_seat(
    troupe: Troupe, client_for: Callable[[], TestClient]
) -> None:
    brujah = member(troupe, "Bruno", clan="Brujah")
    ravi = member(troupe, "Ravi", clan="Ravnos")
    other_player = sign_up(client_for, "otherplayer")
    gwen = member(troupe, "Gwen", clan="Gangrel", player=other_player)
    entitle(troupe, brujah, "Primogen")

    found = seen(troupe.player, troupe)
    # A player may set their own character's; nobody speaks for it yet.
    assert names(found, found["can_represent"]) == ["Ravi"]
    assert entry(found, "Ravi")["represented_by"] is None

    chosen = represent(troupe.player, troupe, ravi, "Brujah")
    assert chosen.status_code == 200, chosen.text
    assert chosen.json() == {"represented_by": "Brujah"}
    found = seen(troupe.player, troupe)
    assert names(found, found["other"]) == ["Gwen", "Ravi"]
    assert entry(found, "Ravi")["represented_by"] == "Brujah"

    # Or a group, in their own words; blank is nobody yet.
    assert represent(troupe.player, troupe, ravi, "  Anarch ").json()["represented_by"] == "Anarch"
    assert represent(troupe.player, troupe, ravi, " ").json()["represented_by"] is None
    assert represent(troupe.player, troupe, ravi, "x" * 61).status_code == 422

    # Not for another player's character, nor for a clan with a seat.
    assert represent(troupe.player, troupe, gwen, "Brujah").status_code == 403
    assert represent(troupe.player, troupe, brujah, "Ventrue").status_code == 409
    assert represent(troupe.narrator, troupe, gwen, "Brujah").status_code == 403

    # Staff who give titles can change anyone's.
    assert names(
        seen(troupe.assistant, troupe), seen(troupe.assistant, troupe)["can_represent"]
    ) == [
        "Gwen",
        "Ravi",
    ]
    changed = represent(troupe.assistant, troupe, gwen, "Independent")
    assert changed.status_code == 200, changed.text
    assert entry(seen(other_player, troupe), "Gwen")["represented_by"] == "Independent"
    log = troupe.storyteller.client.get(f"/troupes/{troupe.id}/log").json()
    assert "assistant set who represents Gwen (otherplayer) at court: Independent." in [
        e["message"] for e in log
    ]

    # The Characters tab shows it for a character of a clan without a seat.
    roster = troupe.storyteller.client.get(f"/troupes/{troupe.id}/characters").json()
    assert {e["character_name"]: (e["seated"], e["represented_by"]) for e in roster} == {
        "Bruno": (True, None),
        "Gwen": (False, "Independent"),
        "Ravi": (False, None),
    }

    # Seated, it hides; unseated again, it is back.
    assert seat(troupe.storyteller, troupe, ["Brujah", "Gangrel"]).status_code == 200
    assert entry(seen(troupe.player, troupe), "Gwen")["represented_by"] is None
    assert seat(troupe.storyteller, troupe, None).status_code == 200
    assert entry(seen(troupe.player, troupe), "Gwen")["represented_by"] == "Independent"


def test_it_goes_when_the_character_leaves_the_troupe(troupe: Troupe) -> None:
    brujah = member(troupe, "Bruno", clan="Brujah")
    ravi = member(troupe, "Ravi", clan="Ravnos")
    entitle(troupe, brujah, "Primogen")
    assert represent(troupe.player, troupe, ravi, "Brujah").status_code == 200

    left = troupe.player.client.delete(f"/characters/{ravi}/troupes/{troupe.id}")
    assert left.status_code == 204, left.text
    assert represent(troupe.player, troupe, ravi, "Brujah").status_code == 409
    back = troupe.player.client.post(f"/characters/{ravi}/troupes", json={"troupe_id": troupe.id})
    assert back.status_code == 201, back.text
    assert entry(seen(troupe.player, troupe), "Ravi")["represented_by"] is None
