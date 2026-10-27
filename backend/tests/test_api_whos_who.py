"""A troupe's Who's Who (horatio.whos_who): the court in rank order, the seated clans,
Other, what each entry shows, and who may see it."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, new_character, sign_up
from tests.test_api_sect_status import add, entitle, member, npc


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def read(person: Person, troupe: Troupe) -> Any:
    return person.client.get(f"/troupes/{troupe.id}/whos-who")


def seen(person: Person, troupe: Troupe) -> dict[str, Any]:
    response = read(person, troupe)
    assert response.status_code == 200, response.text
    return response.json()


def names(found: dict[str, Any], ids: list[str]) -> list[str]:
    by_id = {e["character_id"]: e["name"] for e in found["entries"]}
    return [by_id[i] for i in ids]


def entry(found: dict[str, Any], name: str) -> dict[str, Any]:
    return next(e for e in found["entries"] if e["name"] == name)


def test_the_court_is_in_rank_order_with_the_troupes_own_titles_after(troupe: Troupe) -> None:
    st = troupe.storyteller.client
    for title in ("Master of Revels", "Hound"):
        assert st.post(f"/troupes/{troupe.id}/titles", json={"name": title}).status_code == 201
    harpy = member(troupe, "Hetty")
    hound = member(troupe, "Hugo")
    revels = member(troupe, "Rosa")
    roth = member(troupe, "Roth", clan="Brujah")
    varga = member(troupe, "Varga")
    member(troupe, "Untitled")
    entitle(troupe, harpy, "Harpy")
    entitle(troupe, hound, "Hound")
    entitle(troupe, revels, "Master of Revels")
    entitle(troupe, roth, "Primogen", "Seneschal")
    entitle(troupe, varga, "Prince")

    found = seen(troupe.player, troupe)
    # The rule sets' titles highest first, then the troupe's own in the order added.
    assert names(found, found["court"]) == ["Varga", "Roth", "Hetty", "Rosa", "Hugo"]
    # Several titles, once, highest first.
    assert entry(found, "Roth")["titles"] == ["Seneschal", "Primogen"]

    # The troupe sets the order of its own.
    order = st.put(
        f"/troupes/{troupe.id}/court-order", json={"titles": ["Hound", "Master of Revels"]}
    )
    assert order.status_code == 200, order.text
    assert order.json()["court_order"] == ["Hound", "Master of Revels"]
    found = seen(troupe.player, troupe)
    assert names(found, found["court"]) == ["Varga", "Roth", "Hetty", "Hugo", "Rosa"]
    # Each of its own titles, once.
    assert (
        st.put(f"/troupes/{troupe.id}/court-order", json={"titles": ["Hound"]}).status_code == 422
    )
    assert (
        troupe.player.client.put(
            f"/troupes/{troupe.id}/court-order", json={"titles": ["Hound", "Master of Revels"]}
        ).status_code
        == 403
    )


def test_clans_with_a_primogen_are_seated_and_the_rest_are_other(troupe: Troupe) -> None:
    ventrue = member(troupe, "Victor")
    brujah = member(troupe, "Bruno", clan="Brujah: True Brujah")
    member(troupe, "Gwen", clan="Gangrel")
    member(troupe, "Ada", clan="Brujah")

    # No one holds Primogen: every clan has a section.
    found = seen(troupe.player, troupe)
    assert found["seated"] is None
    assert [c["clan"] for c in found["clans"]] == ["Brujah", "Gangrel", "Ventrue"]
    assert found["other"] == []

    entitle(troupe, ventrue, "Primogen")
    entitle(troupe, brujah, "Primogen")
    found = seen(troupe.player, troupe)
    assert found["seated"] == ["Brujah", "Ventrue"]
    # A bloodline sits with its clan, by name.
    assert [(c["clan"], names(found, c["character_ids"])) for c in found["clans"]] == [
        ("Brujah", ["Ada", "Bruno"]),
        ("Ventrue", ["Victor"]),
    ]
    assert names(found, found["other"]) == ["Gwen"]
    gwen = entry(found, "Gwen")
    # Nobody speaks for the Gangrel yet (#267), and the Camarilla bans their status.
    assert gwen["represented_by"] is None
    assert any(
        b.startswith("Lesser status ban: Not Embraced into a pillar clan") for b in gwen["bans"]
    )
    assert entry(found, "Bruno")["clan"] == "Brujah: True Brujah"


def test_each_entry_says_who_plays_it_and_what_others_see(troupe: Troupe) -> None:
    agnes = member(troupe)
    note = troupe.storyteller.client.put(
        f"/characters/{agnes}/visible-note", json={"note": "Smells of lilies"}
    )
    assert note.status_code == 200, note.text
    assert add(troupe.player, agnes, "Warned").status_code == 200

    found = entry(seen(troupe.player, troupe), "Agnes")
    assert (found["player_name"], found["player_id"]) == ("player", troupe.player.id)
    assert (found["clan"], found["social_age"], found["sect"]) == (
        "Ventrue",
        "Neonate",
        "Camarilla",
    )
    assert found["visible"] == ["Smells of lilies"]
    assert (found["visiting"], found["visiting_from"]) == (False, None)
    # Sect status is not shown, until the troupe adds negative status.
    assert found["negative"] == []
    assert (
        troupe.player.client.patch(
            f"/troupes/{troupe.id}", json={"whos_who_negative": True}
        ).status_code
        == 403
    )
    shown = troupe.storyteller.client.patch(
        f"/troupes/{troupe.id}", json={"whos_who_negative": True}
    )
    assert shown.status_code == 200, shown.text
    found = seen(troupe.player, troupe)
    assert found["shows_negative"]
    assert entry(found, "Agnes")["negative"] == ["Warned"]

    # A player who prefers it is shown by their handle.
    kept = troupe.player.client.patch("/preferences", json={"whos_who_handle": True})
    assert kept.status_code == 200, kept.text
    assert entry(seen(troupe.player, troupe), "Agnes")["player_name"] == f"@{troupe.player.handle}"


def test_npcs_are_listed_when_titled_or_marked_by_staff(troupe: Troupe) -> None:
    member(troupe)
    prince = npc(troupe, "Prince Varga", "Camarilla")
    ghoul = npc(troupe, "Renfield", "Camarilla")
    npc(troupe, "Nameless Thug", "Camarilla")
    entitle(troupe, prince, "Prince")
    path = f"/troupes/{troupe.id}/npcs/{ghoul}/whos-who"
    assert troupe.player.client.put(path, json={"listed": True}).status_code == 403
    listed = troupe.storyteller.client.put(path, json={"listed": True})
    assert listed.status_code == 200, listed.text

    found = seen(troupe.player, troupe)
    assert sorted(e["name"] for e in found["entries"]) == ["Agnes", "Prince Varga", "Renfield"]
    assert (entry(found, "Prince Varga")["kind"], entry(found, "Prince Varga")["player_name"]) == (
        "npc",
        None,
    )
    npcs = troupe.storyteller.client.get(f"/troupes/{troupe.id}/npcs").json()
    assert {n["name"]: n["on_whos_who"] for n in npcs} == {
        "Nameless Thug": False,
        "Prince Varga": False,
        "Renfield": True,
    }


def test_only_staff_and_players_of_active_characters_see_it(
    troupe: Troupe, client_for: Callable[[], TestClient]
) -> None:
    member(troupe)
    # A player whose character only visits sees it, and the character is marked so.
    visitor = sign_up(client_for, "visitor")
    elsewhere = troupe.custodian.client.post(
        "/troupes", json={"name": "Barons of the Bay", "lead_handle": troupe.lead.handle}
    ).json()["id"]
    guest = new_character(troupe, visitor, "Guest", clan="Toreador")
    asked = visitor.client.post(f"/characters/{guest}/home-troupe", json={"troupe_id": elsewhere})
    assert asked.status_code == 201, asked.text
    approved = troupe.lead.client.post(f"/approvals/{asked.json()['id']}/approve", json={})
    assert approved.status_code == 200, approved.text
    joined = visitor.client.post(f"/characters/{guest}/troupes", json={"troupe_id": troupe.id})
    assert joined.status_code == 201, joined.text

    found = entry(seen(visitor, troupe), "Guest")
    assert (found["visiting"], found["visiting_from"]) == (True, "Barons of the Bay")
    for person in (troupe.narrator, troupe.storyteller, troupe.custodian):
        assert read(person, troupe).status_code == 200
    assert read(troupe.stranger, troupe).status_code == 403
    assert not troupe.stranger.client.get(f"/troupes/{troupe.id}").json()["whos_who"]
    assert visitor.client.get(f"/troupes/{troupe.id}").json()["whos_who"]

    # A retired character, or one that has left, opens it no more.
    assert visitor.client.post(f"/characters/{guest}/retire").status_code == 200
    assert read(visitor, troupe).status_code == 403
    assert "Guest" not in [e["name"] for e in seen(troupe.player, troupe)["entries"]]
