"""Why a character left (horatio.leaving): a reason at retirement, in its log, and its
listing under "No longer with us" on the Who's Who (horatio.whos_who)."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe
from tests.test_api_sect_status import entitle, member


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
