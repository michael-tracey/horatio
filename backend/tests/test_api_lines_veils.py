"""A player's lines and veils (horatio.lines_veils): the player keeps their own;
staff of the troupes they play in always see them; other players there only if
they share them; and no one else, nor anything public or printed."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio.models import AuditEvent
from tests.api_helpers import Person, Troupe, sign_up
from tests.test_api_sect_status import member, npc
from tests.test_api_troupe_profiles import PROFILE

MINE = {"lines": ["Spiders", "harm to children"], "veils": ["Torture"]}


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def other(troupe: Troupe) -> Person:
    """Another player, with a character in the troupe."""
    person = sign_up(troupe.client_for, "other")
    member(troupe, "Bea", player=person)
    return person


def keep(person: Person, **body: Any) -> Any:
    return person.client.put("/profile/lines-veils", json=body)


def kept(person: Person, **body: Any) -> dict[str, Any]:
    response = keep(person, **body)
    assert response.status_code == 200, response.text
    return response.json()


def on_profile(viewer: Person, player: Person) -> Any:
    response = viewer.client.get(f"/players/{player.id}")
    assert response.status_code == 200, response.text
    return response.json()["lines_veils"]


def on_whos_who(viewer: Person, troupe: Troupe, name: str) -> Any:
    response = viewer.client.get(f"/troupes/{troupe.id}/whos-who")
    assert response.status_code == 200, response.text
    return next(e for e in response.json()["entries"] if e["name"] == name)["lines_veils"]


def test_a_player_keeps_their_own_tidied_and_unlogged(troupe: Troupe, session: Session) -> None:
    logged = session.scalar(select(func.count()).select_from(AuditEvent))
    found = kept(
        troupe.player,
        lines=["  Spiders ", "", "spiders", "harm   to children"],
        veils=["Torture"],
    )
    # Trimmed, without blanks or the same one twice; sharing is off unless they say.
    assert found == {
        "lines": ["Spiders", "harm to children"],
        "veils": ["Torture"],
        "shared": False,
    }
    assert on_profile(troupe.player, troupe.player) == found
    # Their private settings: not in any log.
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == logged

    assert keep(troupe.player, lines=["x" * 101]).status_code == 422
    assert keep(troupe.player, veils=[f"veil {n}" for n in range(21)]).status_code == 422
    assert on_profile(troupe.player, troupe.player) == found

    # Saving the rest of the profile leaves them be.
    profile = troupe.player.client.put("/profile", json={"display_name": "Player One"})
    assert profile.status_code == 200, profile.text
    assert profile.json()["lines_veils"] == found


def test_staff_always_see_them_and_other_players_only_once_shared(
    troupe: Troupe, other: Person, client_for: Callable[[], TestClient]
) -> None:
    agnes = member(troupe)
    kept(troupe.player, **MINE)
    staff = (troupe.lead, troupe.storyteller, troupe.assistant, troupe.narrator)
    elsewhere = sign_up(client_for, "elsewhere")
    lead_elsewhere = troupe.custodian.client.post(
        "/troupes", json={"name": "Barons of the Bay", "lead_handle": elsewhere.handle}
    )
    assert lead_elsewhere.status_code == 201, lead_elsewhere.text

    # Not shared: staff and the custodian see them; no other player does.
    for person in (*staff, troupe.custodian):
        assert on_profile(person, troupe.player)["lines"] == MINE["lines"]
        assert on_whos_who(person, troupe, "Agnes")["veils"] == MINE["veils"]
    for person in (other, troupe.stranger, elsewhere):
        assert on_profile(person, troupe.player) is None
    assert on_whos_who(other, troupe, "Agnes") is None
    # The player sees their own on the Who's Who.
    assert on_whos_who(troupe.player, troupe, "Agnes")["lines"] == MINE["lines"]

    # Shared: the other players in the troupe see them too, but no one outside it,
    # not even the lead storyteller of another troupe.
    kept(troupe.player, **MINE, shared=True)
    assert on_whos_who(other, troupe, "Agnes")["lines"] == MINE["lines"]
    assert on_profile(other, troupe.player)["veils"] == MINE["veils"]
    for person in (troupe.stranger, elsewhere):
        assert on_profile(person, troupe.player) is None
    assert troupe.stranger.client.get(f"/troupes/{troupe.id}/whos-who").status_code == 403

    # Sharing off again, they are the staff's only.
    kept(troupe.player, **MINE, shared=False)
    assert on_whos_who(other, troupe, "Agnes") is None
    assert on_profile(other, troupe.player) is None

    # Once the player has no active character there, its staff see them no more.
    assert troupe.player.client.post(f"/characters/{agnes}/retire").status_code == 200
    assert on_profile(troupe.storyteller, troupe.player) is None
    assert on_profile(troupe.custodian, troupe.player)["lines"] == MINE["lines"]


def test_staff_see_them_on_the_characters_tab_and_play_view(troupe: Troupe) -> None:
    agnes = member(troupe)
    thug = npc(troupe, "Nameless Thug", "Camarilla")
    kept(troupe.player, **MINE)

    roster = troupe.storyteller.client.get(f"/troupes/{troupe.id}/characters").json()
    by_name = {e["character_name"]: e["lines_veils"] for e in roster}
    assert by_name["Agnes"]["lines"] == MINE["lines"]
    assert by_name["Nameless Thug"] is None
    assert troupe.player.client.get(f"/troupes/{troupe.id}/characters").status_code == 403

    for person in (troupe.storyteller, troupe.assistant):
        found = person.client.get(f"/characters/{agnes}/play/reference").json()
        assert found["lines_veils"]["veils"] == MINE["veils"]
    # The player knows their own, and an NPC has none.
    assert (
        troupe.player.client.get(f"/characters/{agnes}/play/reference").json()["lines_veils"]
        is None
    )
    reference = troupe.storyteller.client.get(f"/characters/{thug}/play/reference").json()
    assert reference["lines_veils"] is None


def test_staff_see_the_whole_troupes_list_named_only_where_shared(
    troupe: Troupe, other: Person, client_for: Callable[[], TestClient]
) -> None:
    member(troupe)
    quiet = sign_up(client_for, "quiet")
    member(troupe, "Cass", player=quiet)
    kept(troupe.player, lines=["Spiders", "Fire"], veils=["Torture"])
    kept(other, lines=["spiders"], veils=["Needles"], shared=True)
    path = f"/troupes/{troupe.id}/lines-veils"

    for person in (troupe.player, other, troupe.stranger):
        assert person.client.get(path).status_code == 403
    for person in (troupe.storyteller, troupe.narrator, troupe.custodian):
        assert person.client.get(path).status_code == 200
    found = troupe.narrator.client.get(path).json()

    def shown(items: list[dict[str, Any]]) -> list[tuple[str, int, list[str]]]:
        return [
            (i["text"].lower(), i["count"], [p["display_name"] for p in i["shared_by"]])
            for i in items
        ]

    # The same words once, in any case, most given first; only a player who shares
    # is named.
    assert shown(found["lines"]) == [("spiders", 2, ["other"]), ("fire", 1, [])]
    assert shown(found["veils"]) == [("needles", 1, ["other"]), ("torture", 1, [])]
    # Everyone who gave any, to open; not those who gave none.
    assert [p["display_name"] for p in found["players"]] == ["other", "player"]


def test_never_public_nor_printed(troupe: Troupe, client_for: Callable[[], TestClient]) -> None:
    member(troupe)
    kept(troupe.player, lines=["Spiders"], veils=["Needles"], shared=True)
    public = troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/profile",
        json={**PROFILE, "public": True, "contact_id": troupe.storyteller.id},
    )
    assert public.status_code == 200, public.text

    responses = [
        client_for().get(f"/troupes/{troupe.id}/profile"),
        troupe.player.client.get(f"/troupes/{troupe.id}/profile"),
        troupe.lead.client.get(f"/troupes/{troupe.id}/badges"),
    ]
    for response in responses:
        assert response.status_code == 200, response.text
        assert "Spiders" not in response.text
        assert "Needles" not in response.text
    # Someone not signed in sees no profile at all.
    assert client_for().get(f"/players/{troupe.player.id}").status_code == 401
