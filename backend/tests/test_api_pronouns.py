"""Pronouns (issue #265, horatio.pronouns): a character's and a player's, who sets
them, where they show, and the troupe's choice to print a character's on badges."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, sign_up
from tests.test_api_sect_status import member, npc


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def say(person: Person, character_id: str, pronouns: str | None) -> Any:
    return person.client.put(f"/characters/{character_id}/pronouns", json={"pronouns": pronouns})


def profile(person: Person, **changes: Any) -> Any:
    return person.client.put(
        "/profile", json={"display_name": person.email.split("@")[0], **changes}
    )


def whos_who_entry(person: Person, troupe: Troupe, name: str) -> dict[str, Any]:
    found = person.client.get(f"/troupes/{troupe.id}/whos-who")
    assert found.status_code == 200, found.text
    return next(e for e in found.json()["entries"] if e["name"] == name)


def test_a_player_sets_their_characters_pronouns_and_no_one_else_does(troupe: Troupe) -> None:
    agnes = member(troupe)
    said = say(troupe.player, agnes, "  she/her ")
    assert said.status_code == 200, said.text
    assert said.json()["pronouns"] == "she/her"
    assert troupe.player.client.get(f"/characters/{agnes}").json()["pronouns"] == "she/her"

    # Staff approve; they don't edit a PC. Someone else can't see it at all.
    assert say(troupe.storyteller, agnes, "he/him").status_code == 403
    assert say(troupe.stranger, agnes, "he/him").status_code == 404
    assert say(troupe.player, agnes, "x" * 41).status_code == 422

    # Empty is none, not "unknown".
    cleared = say(troupe.player, agnes, "")
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["pronouns"] is None

    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert "player set Agnes's pronouns: she/her." in log
    assert "player set Agnes's pronouns: none." in log


def test_staff_set_an_npcs_pronouns(troupe: Troupe) -> None:
    hale = npc(troupe, "Sheriff Hale", "Camarilla")
    said = say(troupe.assistant, hale, "they/them")
    assert said.status_code == 200, said.text
    assert said.json()["pronouns"] == "they/them"
    # A narrator never sees an NPC.
    assert say(troupe.narrator, hale, "any").status_code == 404


def test_a_player_keeps_pronouns_on_their_profile(troupe: Troupe) -> None:
    saved = profile(troupe.player, pronouns="she/they")
    assert saved.status_code == 200, saved.text
    assert saved.json()["pronouns"] == "she/they"
    # Anyone signed in sees them beside the name.
    seen = troupe.stranger.client.get(f"/players/{troupe.player.id}").json()
    assert seen["pronouns"] == "she/they"
    # Leaving them out of a change keeps them; empty clears them.
    assert profile(troupe.player, bio="Hello").json()["pronouns"] == "she/they"
    assert profile(troupe.player, pronouns="x" * 41).status_code == 422
    assert profile(troupe.player, pronouns="").json()["pronouns"] is None


def test_both_show_on_the_whos_who_the_characters_tab_and_others_at_the_game(
    troupe: Troupe, client_for: Callable[[], TestClient]
) -> None:
    other = sign_up(client_for, "other")
    agnes = member(troupe)
    elena = member(troupe, "Elena", player=other)
    say(troupe.player, agnes, "she/her")
    profile(troupe.player, pronouns="they/them")

    found = whos_who_entry(other, troupe, "Agnes")
    assert (found["pronouns"], found["player_pronouns"]) == ("she/her", "they/them")
    nothing = whos_who_entry(other, troupe, "Elena")
    assert (nothing["pronouns"], nothing["player_pronouns"]) == (None, None)

    roster = troupe.storyteller.client.get(f"/troupes/{troupe.id}/characters").json()
    row = next(r for r in roster if r["character_name"] == "Agnes")
    assert (row["pronouns"], row["player_pronouns"]) == ("she/her", "they/them")

    others = other.client.get(f"/characters/{elena}/play/others")
    assert others.status_code == 200, others.text
    assert [(o["name"], o["pronouns"]) for o in others.json()] == [("Agnes", "she/her")]


def test_badges_print_the_characters_pronouns_only_if_the_troupe_says(troupe: Troupe) -> None:
    agnes = member(troupe)
    say(troupe.player, agnes, "she/her")
    profile(troupe.player, pronouns="they/them")

    def printed() -> tuple[bool, str | None]:
        found = troupe.lead.client.get(f"/troupes/{troupe.id}/badges").json()
        return found["print_pronouns"], found["badges"][0]["pronouns"]

    # Off unless the troupe chooses.
    assert troupe.lead.client.get(f"/troupes/{troupe.id}").json()["badge_pronouns"] is False
    assert printed() == (False, None)

    path = f"/troupes/{troupe.id}"
    assert troupe.assistant.client.patch(path, json={"badge_pronouns": True}).status_code == 403
    turned = troupe.storyteller.client.patch(path, json={"badge_pronouns": True})
    assert turned.status_code == 200, turned.text
    assert turned.json()["badge_pronouns"] is True
    # The character's, never the player's.
    assert printed() == (True, "she/her")
    badge = troupe.lead.client.get(f"/characters/{agnes}/badge").json()
    assert badge["badges"][0]["pronouns"] == "she/her"
    assert "they/them" not in troupe.lead.client.get(f"/troupes/{troupe.id}/badges").text

    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert "storyteller set badges to print character pronouns." in log
