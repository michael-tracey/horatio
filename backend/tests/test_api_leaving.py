"""Why a character left (horatio.leaving): a reason at retirement, in its log, and its
listing under "No longer with us" on the Who's Who (horatio.whos_who)."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe
from tests.test_api_renames import other_troupe, summaries, troupe_log, visit
from tests.test_api_sect_status import entitle, member, status


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def whos_who(person: Person, troupe: Troupe) -> dict[str, Any]:
    response = person.client.get(f"/troupes/{troupe.id}/whos-who")
    assert response.status_code == 200, response.text
    return response.json()


def names(found: dict[str, Any], ids: list[str]) -> list[str]:
    by_id = {e["character_id"]: e["name"] for e in found["entries"]}
    return [by_id[i] for i in ids]


def everywhere(found: dict[str, Any]) -> list[str]:
    """Every character in the court, the clans and Other."""
    ids = found["court"] + found["other"]
    for section in found["clans"]:
        ids += section["character_ids"]
    return names(found, ids)


def log(person: Person, character_id: str) -> list[str]:
    return [e["message"] for e in person.client.get(f"/characters/{character_id}/log").json()]


def retire(person: Person, character_id: str, **body: Any) -> dict[str, Any]:
    response = person.client.post(f"/characters/{character_id}/retire", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_a_character_retired_off_field_is_no_longer_with_us(troupe: Troupe) -> None:
    lena = member(troupe, "Lena", clan="Toreador")
    member(troupe, "Mara", clan="Toreador")
    entitle(troupe, lena, "Harpy")

    retired = retire(troupe.player, lena, reason="off_field", note="Gone to Chicago.", listed=True)

    assert (retired["status"], retired["left_reason"], retired["left_listed"]) == (
        "retired",
        "off_field",
        True,
    )
    found = whos_who(troupe.storyteller, troupe)
    # Listed with why it left, and in no other view, though it held a title.
    assert names(found, found["departed"]) == ["Lena"]
    assert everywhere(found) == ["Mara"]
    entry = next(e for e in found["entries"] if e["name"] == "Lena")
    assert (entry["left_reason"], entry["clan"], entry["player_name"]) == (
        "Off-field",
        "Toreador",
        "player",
    )
    assert entry["social_age"]
    assert entry["titles"] == []
    # The note goes in its log, which the troupe's staff see too.
    said = "player retired Lena: Off-field, listed under No longer with us. Gone to Chicago."
    assert said in log(troupe.player, lena)
    assert log(troupe.storyteller, lena).count(said) == 1


@pytest.mark.parametrize("reason", ["final_death", "off_field", "inactive"])
def test_retiring_gives_up_every_title_in_every_troupe(troupe: Troupe, reason: str) -> None:
    ursula = member(troupe, "Ursula")
    entitle(troupe, ursula, "Prince", "Harpy")
    elsewhere = other_troupe(troupe)
    visit(troupe.player, ursula, elsewhere)
    given = troupe.stranger.client.put(
        f"/troupes/{elsewhere}/characters/{ursula}/titles", json={"titles": ["Seneschal"]}
    )
    assert given.status_code == 200, given.text
    # Its active title in each troupe gives it status.
    assert {d["source"] for d in status(troupe.player, ursula)["derived"]} == {
        "Prince",
        "Seneschal",
    }
    # The retire dialog warns of them, by troupe.
    troupes = troupe.player.client.get(f"/characters/{ursula}/troupes").json()
    assert [(t["troupe_name"], t["titles"]) for t in troupes] == [
        ("Elsewhere", ["Seneschal"]),
        ("Lords of the Night", ["Harpy", "Prince"]),
    ]

    retire(troupe.player, ursula, reason=reason, listed=False)

    troupes = troupe.player.client.get(f"/characters/{ursula}/troupes").json()
    assert [t["titles"] for t in troupes] == [[], []]
    # Its active title went, and the status it gave.
    assert status(troupe.player, ursula)["derived"] == []
    # One entry in each troupe's log, and each troupe's storytellers are told.
    assert "Ursula (player) gave up Prince and Harpy on retiring." in troupe_log(
        troupe.lead, troupe.id
    )
    assert "Ursula (player) gave up Seneschal on retiring." in troupe_log(
        troupe.stranger, elsewhere
    )
    assert (
        "Ursula gave up Prince and Harpy on retiring: −Authority, −Commander, −Sovereign"
        in summaries(troupe.storyteller)
    )
    assert any(
        s.startswith("Ursula gave up Seneschal on retiring") for s in summaries(troupe.stranger)
    )
    assert not [s for s in summaries(troupe.player) if "on retiring" in s]
    # The titles leave the court: no one holds them, and staff can't give them back.
    held = troupe.storyteller.client.get(f"/troupes/{troupe.id}/titles").json()["titles"]
    assert [t["holders"] for t in held if t["name"] in ("Prince", "Harpy")] == [[], []]
    again = troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/characters/{ursula}/titles", json={"titles": ["Prince"]}
    )
    assert again.status_code == 409


def test_a_title_given_up_on_retiring_is_free_for_another(troupe: Troupe) -> None:
    ursula = member(troupe, "Ursula")
    vera = member(troupe, "Vera")
    entitle(troupe, ursula, "Prince")

    retire(troupe.player, ursula, reason="final_death", listed=True)

    chosen = troupe.player.client.post(f"/characters/{vera}/titles", json={"name": "Prince"})
    assert chosen.status_code < 300, chosen.text
    court = whos_who(troupe.storyteller, troupe)
    assert names(court, court["court"]) == ["Vera"]


def test_an_unlisted_character_is_nowhere_on_the_whos_who(troupe: Troupe) -> None:
    gone = member(troupe, "Quiet")
    member(troupe, "Mara")

    retire(troupe.player, gone, reason="inactive", listed=False)

    found = whos_who(troupe.storyteller, troupe)
    assert found["departed"] == []
    assert [e["name"] for e in found["entries"]] == ["Mara"]


def test_staff_or_the_player_give_an_older_retirement_a_reason(troupe: Troupe) -> None:
    old = member(troupe, "Olga")
    member(troupe, "Mara")
    # Retired before reasons were kept, or without one: not listed.
    assert troupe.player.client.post(f"/characters/{old}/retire").status_code == 200
    found = whos_who(troupe.storyteller, troupe)
    assert found["departed"] == []
    assert "player retired Olga: no reason given, not listed. No note." in log(troupe.player, old)

    # Its home troupe's running staff give one and list it.
    leaving = {"reason": "final_death", "note": "Staked at Elysium.", "listed": True}
    changed = troupe.storyteller.client.put(f"/characters/{old}/leaving", json=leaving)
    assert changed.status_code == 200, changed.text
    found = whos_who(troupe.player, troupe)
    assert names(found, found["departed"]) == ["Olga"]
    assert found["entries"][-1]["left_reason"] == "Final Death"
    assert (
        "storyteller changed why Olga (player) left: Final Death, listed under No longer"
        " with us. Staked at Elysium." in log(troupe.player, old)
    )

    # Its player unlists it.
    unlisted = troupe.player.client.put(
        f"/characters/{old}/leaving", json={"reason": "final_death", "listed": False}
    )
    assert unlisted.status_code == 200, unlisted.text
    assert whos_who(troupe.player, troupe)["departed"] == []

    # Narrators, and those who can't see it, can't.
    assert troupe.narrator.client.put(f"/characters/{old}/leaving", json=leaving).status_code in (
        403,
        404,
    )
    assert troupe.stranger.client.put(f"/characters/{old}/leaving", json=leaving).status_code == 404
    # Only once it is retired.
    mara = whos_who(troupe.storyteller, troupe)["entries"][0]["character_id"]
    assert troupe.player.client.put(f"/characters/{mara}/leaving", json=leaving).status_code == 409
    # A reason is one of the three.
    wrong = troupe.player.client.put(
        f"/characters/{old}/leaving", json={"reason": "eaten", "listed": True}
    )
    assert wrong.status_code == 422
