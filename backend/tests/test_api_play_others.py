"""Others at the game, on the Play View's Status tab (horatio.play_others): a member of
the same sect sees another's status names, learns a fleeting status's details with a
Leadership use, and sees negative status in full; another sect sees only the name and
sect; and nothing more leaks."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, new_character, sign_up
from tests.test_api_play import send, tap
from tests.test_api_play_status import reset, undo, view
from tests.test_api_sect_status import add, entitle, held, member, npc, put_trait


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def other(client_for: Callable[[], TestClient]) -> Person:
    return sign_up(client_for, "other")


def others(person: Person, character_id: str) -> Any:
    return person.client.get(f"/characters/{character_id}/play/others")


def look(person: Person, character_id: str, other_id: str) -> Any:
    return person.client.get(f"/characters/{character_id}/play/others/{other_id}")


def learn(person: Person, character_id: str, other_id: str, key: str) -> Any:
    return person.client.post(
        f"/characters/{character_id}/play/others/{other_id}/learn",
        json={"id": str(uuid.uuid4()), "key": key},
    )


def seen(response: Any, name: str) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    return next(s for s in response.json()["status"] if s["name"] == name)


def leadership(person: Person, character_id: str) -> tuple[int, int]:
    found = next(e for e in view(person, character_id)["expendables"] if e["name"] == "Leadership")
    return found["left"], found["uses"]


def court(troupe: Troupe, other: Person) -> tuple[str, str]:
    """Agnes, the troupe player's Camarilla PC with Leadership 2, and Elena, another
    player's: Prince, with Loyal, Courageous and Honorable, and Warned."""
    agnes = member(troupe)
    put_trait(troupe.session, agnes, "skills", "Leadership", 2)
    elena = member(troupe, "Elena", player=other)
    entitle(troupe, elena, "Prince")
    for name, story in (
        ("Loyal", "For holding the door"),
        ("Courageous", "For facing the Sheriff"),
        ("Honorable", "For keeping her word"),
    ):
        given = add(other, elena, name, patron_text="Prince Varga", place="Elysium", story=story)
        assert given.status_code == 200, given.text
    warned = add(other, elena, "Warned", patron_text="Sheriff Hale", story="For the brawl")
    assert warned.status_code == 200, warned.text
    return agnes, elena


def test_leadership_2_learns_about_two_status_and_a_third_is_refused(
    troupe: Troupe, other: Person
) -> None:
    agnes, elena = court(troupe, other)

    listed = others(troupe.player, agnes)
    assert listed.status_code == 200, listed.text
    [found] = listed.json()
    assert (found["name"], found["sect"], found["same_sect"], found["accepted"]) == (
        "Elena",
        "Camarilla",
        True,
        "Acknowledged",
    )
    assert found["titles"] == ["Prince"]

    # Her status names, as carried into her game; the patrons and stories stay hidden.
    looked = look(troupe.player, agnes, elena)
    assert looked.status_code == 200, looked.text
    assert [(s["name"], s["type"]) for s in looked.json()["status"]] == [
        ("Warned", "Negative"),
        ("Authority", "Abiding"),
        ("Commander", "Abiding"),
        ("Sovereign", "Abiding"),
        ("Loyal", "Fleeting"),
        ("Courageous", "Fleeting"),
        ("Honorable", "Fleeting"),
    ]
    for text in ("Prince Varga", "Elysium", "For holding the door", "For facing the Sheriff"):
        assert text not in looked.text
    loyal = seen(looked, "Loyal")
    assert (loyal["known"], loyal["learnable"], loyal["patron"], loyal["story"]) == (
        False,
        True,
        None,
        None,
    )
    assert not seen(looked, "Authority")["learnable"]

    # Negative status is public, its patron and all.
    warned = seen(looked, "Warned")
    assert (warned["known"], warned["patron"], warned["story"]) == (
        True,
        "Sheriff Hale",
        "For the brawl",
    )
    assert warned["ending"]["games_left"] == 2
    assert learn(troupe.player, agnes, elena, warned["key"]).status_code == 409

    # Two Leadership uses: two status learned about.
    assert leadership(troupe.player, agnes) == (2, 2)
    first = learn(troupe.player, agnes, elena, loyal["key"])
    loyal = seen(first, "Loyal")
    assert (loyal["known"], loyal["patron"], loyal["place"], loyal["story"]) == (
        True,
        "Prince Varga",
        "Elysium",
        "For holding the door",
    )
    assert "For facing the Sheriff" not in first.text
    assert leadership(troupe.player, agnes) == (1, 2)
    second = learn(troupe.player, agnes, elena, seen(first, "Courageous")["key"])
    assert seen(second, "Courageous")["story"] == "For facing the Sheriff"
    assert leadership(troupe.player, agnes) == (0, 2)

    # A third is refused, and learns nothing.
    third = learn(troupe.player, agnes, elena, seen(second, "Honorable")["key"])
    assert third.status_code == 409
    assert "used up" in third.json()["detail"]
    assert "For keeping her word" not in look(troupe.player, agnes, elena).text
    # Nor is the same one learned twice.
    assert learn(troupe.player, agnes, elena, loyal["key"]).status_code == 409

    state = view(troupe.player, agnes)
    assert [e["text"] for e in state["log"][:2]] == [
        "Learned about Elena's Courageous: Leadership 1 → 0",
        "Learned about Elena's Loyal: Leadership 2 → 1",
    ]

    # Undo gives the use back, and forgets what it learned.
    send(troupe.player, agnes, undo(loyal["learned_by"]))
    assert leadership(troupe.player, agnes) == (1, 2)
    again = look(troupe.player, agnes, elena)
    assert not seen(again, "Loyal")["known"]
    assert "For holding the door" not in again.text
    assert seen(again, "Courageous")["known"]

    # What was learned stays known at the next game, and Leadership is back.
    reset(troupe.player, agnes)
    assert leadership(troupe.player, agnes) == (2, 2)
    assert seen(look(troupe.player, agnes, elena), "Courageous")["known"]


def test_another_sect_sees_only_the_name_and_sect(troupe: Troupe, other: Person) -> None:
    _, elena = court(troupe, other)
    rook = member(troupe, "Rook", sect="Sabbat", clan="Lasombra")
    put_trait(troupe.session, rook, "skills", "Leadership", 2)

    listed = next(o for o in others(troupe.player, rook).json() if o["name"] == "Elena")
    assert (listed["sect"], listed["same_sect"], listed["accepted"], listed["titles"]) == (
        "Camarilla",
        False,
        None,
        [],
    )
    looked = look(troupe.player, rook, elena)
    assert looked.status_code == 200, looked.text
    assert looked.json()["status"] is None
    for text in ("Warned", "Loyal", "Authority", "Prince", "Sheriff Hale"):
        assert text not in looked.text
    assert learn(troupe.player, rook, elena, "status:Authority").status_code == 404


def test_only_the_troupes_characters_to_an_accepted_viewer(troupe: Troupe, other: Person) -> None:
    agnes, elena = court(troupe, other)
    prince = npc(troupe, "Prince Varga", "Camarilla")
    entitle(troupe, prince, "Prince")
    npc(troupe, "Udo the Quiet", "Camarilla")
    assert [o["name"] for o in others(troupe.player, agnes).json()] == ["Elena", "Prince Varga"]

    # Someone who cannot see Agnes cannot look through her.
    assert others(troupe.stranger, agnes).status_code == 404
    assert look(other, agnes, elena).status_code == 404

    # A character outside the troupe is not at its game.
    outside = new_character(troupe, other, "Outsider")
    assert look(troupe.player, agnes, outside).status_code == 404
    assert look(troupe.player, agnes, str(uuid.uuid4())).status_code == 404

    # A character of no sect is not Accepted, and sees no one's status.
    loner = member(troupe, "Loner", sect="Independent Alliance")
    refused = others(troupe.player, loner)
    assert refused.status_code == 409
    assert look(troupe.player, loner, elena).status_code == 409

    # Without Leadership, nothing is learned; abiding status has no patron to learn.
    plain = member(troupe, "Plain")
    loyal = seen(look(troupe.player, plain, elena), "Loyal")
    assert "has none" in learn(troupe.player, plain, elena, loyal["key"]).json()["detail"]
    assert learn(troupe.player, agnes, elena, "status:Authority").status_code == 422
    assert learn(troupe.player, agnes, elena, "held:nothing").status_code == 404


def test_spent_status_is_marked_spent(troupe: Troupe, other: Person) -> None:
    agnes, elena = court(troupe, other)
    loyal = seen(look(troupe.player, agnes, elena), "Loyal")["key"]
    send(other, elena, tap("status:Authority", -1))
    send(other, elena, tap(loyal, -1))
    assert "Loyal" not in held(other, elena)

    looked = look(troupe.player, agnes, elena)
    assert seen(looked, "Authority")["spent"]
    assert not seen(looked, "Commander")["spent"]
    spent = seen(looked, "Loyal")
    assert (spent["spent"], spent["known"]) == (True, False)
    # Still learned about from the tap's record.
    learned = seen(learn(troupe.player, agnes, elena, loyal), "Loyal")
    assert (learned["patron"], learned["story"]) == ("Prince Varga", "For holding the door")


def test_the_patrons_player_removes_the_negative_status_they_gave(
    troupe: Troupe, other: Person, client_for: Callable[[], TestClient]
) -> None:
    agnes, elena = court(troupe, other)
    given = add(other, elena, "Warned", patron_id=agnes, patron_text="")
    assert given.status_code == 200, given.text
    third = sign_up(client_for, "third")
    bram = member(troupe, "Bram", player=third)

    looked = look(troupe.player, agnes, elena)
    warnings = [s for s in looked.json()["status"] if s["name"] == "Warned"]
    mine = next(s for s in warnings if s["patron"] == "Agnes")
    hales = next(s for s in warnings if s["patron"] == "Sheriff Hale")
    assert (mine["removable"], hales["removable"]) == (True, False)

    # Bram's player gave neither, and cannot remove them.
    for s in warnings:
        url = f"/characters/{bram}/play/others/{elena}/status/{s['held_id']}/remove"
        assert third.client.post(url).status_code == 409
    url = f"/characters/{agnes}/play/others/{elena}/status/{hales['held_id']}/remove"
    assert troupe.player.client.post(url).status_code == 409

    url = f"/characters/{agnes}/play/others/{elena}/status/{mine['held_id']}/remove"
    removed = troupe.player.client.post(url)
    assert removed.status_code == 200, removed.text
    assert [s["patron"] for s in removed.json()["status"] if s["name"] == "Warned"] == [
        "Sheriff Hale"
    ]
    assert held(other, elena).count("Warned") == 1
