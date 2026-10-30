"""Sect status at a game, on the Play View's Status tab (horatio.play_status): choosing
the source of abiding status and a title's conditional status, locked for the game;
spending status, with Undo; adding status at the game; titles gained and lost during
a game; and fleeting status suppressed."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.models import HeldStatus
from tests.api_helpers import Person, Troupe
from tests.test_api_play import send, tap
from tests.test_api_sect_status import add, entitle, held, held_id, logged, member, put_trait


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def view(person: Person, character_id: str) -> dict[str, Any]:
    response = person.client.get(f"/characters/{character_id}/play")
    assert response.status_code == 200, response.text
    return response.json()


def choose(person: Person, character_id: str, **body: Any) -> Any:
    return person.client.put(f"/characters/{character_id}/play/status/choice", json=body)


def carried(state: dict[str, Any]) -> list[tuple[str, str]]:
    return [(c["name"], c["type"]) for c in state["status"]["carried"]]


def entry(state: dict[str, Any], name: str) -> dict[str, Any]:
    return next(c for c in state["status"]["carried"] if c["name"] == name)


def undo(of: str) -> dict[str, Any]:
    return {**tap(), "kind": "undo", "tracker": "", "amount": 0, "undoes": of}


def reset(person: Person, character_id: str) -> None:
    response = person.client.post(f"/characters/{character_id}/play/reset", json={})
    assert response.status_code == 200, response.text


def test_a_seneschal_elder_chooses_one_source_locked_for_the_game(troupe: Troupe) -> None:
    agnes = member(troupe)
    # Of its titles only the active one, the Seneschal, is a source; its social age
    # is another.
    entitle(troupe, agnes, "Seneschal", "Primogen")
    put_trait(troupe.session, agnes, "backgrounds", "Generation", 3)

    state = view(troupe.player, agnes)["status"]
    assert state["accepted"] == "Acknowledged"
    assert state["choosing"]
    assert [s["name"] for s in state["sources"]] == ["Seneschal", "Elder"]
    assert [(t["name"], t["active"]) for t in state["titles"]] == [
        ("Primogen", False),
        ("Seneschal", True),
    ]
    # Until the choice, no abiding status.
    assert state["carried"] == []

    chosen = choose(troupe.player, agnes, source="Seneschal")
    assert chosen.status_code == 200, chosen.text
    state = chosen.json()["status"]
    assert (state["source"], state["source_chosen"], state["choosing"]) == (
        "Seneschal",
        True,
        False,
    )
    assert carried(chosen.json()) == [("Noble", "Abiding")]
    [prince] = state["conditions"]
    assert (prince["kind"], prince["absent_title"], prince["options"]) == (
        "absent",
        "Prince",
        ["Authority"],
    )

    # The Prince is away tonight: the Seneschal gains Authority.
    away = choose(troupe.player, agnes, absent={"Prince": True})
    assert away.status_code == 200, away.text
    assert carried(away.json()) == [("Noble", "Abiding"), ("Authority", "Abiding")]

    # Locked for the game: the player cannot change it, and staff can.
    refused = choose(troupe.player, agnes, source="Elder")
    assert refused.status_code == 409
    assert "staff can change it" in refused.json()["detail"]
    assert choose(troupe.player, agnes, absent={"Prince": False}).status_code == 409
    # A title not active is no source.
    assert choose(troupe.storyteller, agnes, source="Primogen").status_code == 422
    changed = choose(troupe.storyteller, agnes, source="Elder")
    assert changed.status_code == 200, changed.text
    assert [n for n, _ in carried(changed.json())] == ["Confirmed", "Established", "Privileged"]
    assert [e["choice"] for e in logged(troupe.session, agnes, "play.status_chosen")] == [
        "Seneschal as its source of abiding status",
        "the Prince absent",
        "Elder as its source of abiding status",
    ]

    # The next game, the choice is to make again.
    send(troupe.player, agnes, tap("blood", -1))
    reset(troupe.player, agnes)
    assert view(troupe.player, agnes)["status"]["choosing"]


def test_a_bishop_chooses_blessed_or_enforcer(troupe: Troupe) -> None:
    rook = member(troupe, "Rook", sect="Sabbat", clan="Lasombra")
    entitle(troupe, rook, "Bishop")

    state = view(troupe.player, rook)["status"]
    assert state["source"] == "Bishop"
    choice = next(c for c in state["conditions"] if c["kind"] == "choose")
    assert choice["options"] == ["Blessed", "Enforcer"]
    assert carried(view(troupe.player, rook)) == []

    assert choose(troupe.player, rook, chosen={"Bishop": "Glorious"}).status_code == 422
    chosen = choose(troupe.player, rook, chosen={"Bishop": "Enforcer"})
    assert chosen.status_code == 200, chosen.text
    assert carried(chosen.json()) == [("Enforcer", "Abiding")]
    assert choose(troupe.player, rook, chosen={"Bishop": "Blessed"}).status_code == 409


def test_abiding_status_is_spent_for_the_game_and_undo_restores_it(troupe: Troupe) -> None:
    agnes = member(troupe)
    entitle(troupe, agnes, "Prince")

    spend = tap("status:Authority", -1)
    state = send(troupe.player, agnes, spend)
    assert entry(state, "Authority")["spent"]
    assert entry(state, "Authority")["spent_by"] == spend["id"]
    assert not entry(state, "Commander")["spent"]
    assert state["log"][0]["text"] == "Spent Authority"

    state = send(troupe.player, agnes, undo(spend["id"]))
    assert not entry(state, "Authority")["spent"]
    assert state["log"][0]["text"] == "Undid: Spent Authority"

    send(troupe.player, agnes, tap("status:Authority", -1))
    reset(troupe.player, agnes)
    assert not entry(view(troupe.player, agnes), "Authority")["spent"]


def test_fleeting_status_is_spent_for_good_and_undo_gives_it_back(troupe: Troupe) -> None:
    agnes = member(troupe)
    assert add(troupe.player, agnes, "Loyal", story="For holding the door").status_code == 200
    loyal = held_id(troupe.player, agnes, "Loyal")
    key = f"held:{loyal}"
    assert entry(view(troupe.player, agnes), "Loyal")["key"] == key

    spend = tap(key, -1, note="a crowbar, quickly")
    state = send(troupe.player, agnes, spend)
    assert held(troupe.player, agnes) == []
    spent = entry(state, "Loyal")
    assert (spent["spent"], spent["spent_by"], spent["source"]) == (
        True,
        spend["id"],
        "Prince Varga",
    )
    assert state["log"][0]["text"] == "Spent Loyal for good"
    assert logged(troupe.session, agnes, "status.spent")[0]["reason"] == "a crowbar, quickly"

    # Spent again from another device: nothing more happens.
    state = send(troupe.player, agnes, tap(key, -1))
    assert state["log"][0]["text"] == "Spent a fleeting status already gone"

    state = send(troupe.player, agnes, undo(spend["id"]))
    assert held(troupe.player, agnes) == ["Loyal"]
    row = troupe.session.get_one(HeldStatus, uuid.UUID(loyal))
    assert (row.story, row.patron_text) == ("For holding the door", "Prince Varga")
    assert not entry(state, "Loyal")["spent"]
    log = [e["message"] for e in troupe.player.client.get(f"/characters/{agnes}/log").json()]
    assert "player spent Agnes's Loyal (from Prince Varga) (a crowbar, quickly)." in log
    assert "player undid spending Agnes's Loyal (from Prince Varga): it is back." in log


def test_negative_status_is_never_spent(troupe: Troupe) -> None:
    agnes = member(troupe)
    assert add(troupe.player, agnes, "Warned").status_code == 200
    state = view(troupe.player, agnes)
    assert carried(state)[0] == ("Warned", "Negative")
    assert not entry(state, "Warned")["spendable"]
    assert entry(state, "Warned")["ending"]["games_left"] == 2

    response = troupe.player.client.post(
        f"/characters/{agnes}/play/taps",
        json={"taps": [tap(f"held:{held_id(troupe.player, agnes, 'Warned')}", -1)]},
    )
    assert response.status_code == 422
    assert held(troupe.player, agnes) == ["Warned"]


def test_a_player_adds_status_at_the_game_as_the_troupe_allows(troupe: Troupe) -> None:
    agnes = member(troupe)
    added = troupe.player.client.post(
        f"/characters/{agnes}/play/status",
        json={"name": "Courageous", "patron_text": "Prince Varga"},
    )
    assert added.status_code == 200, added.text
    assert carried(added.json()) == [("Courageous", "Fleeting")]
    game = added.json()["game"]["number"]
    log = [e["message"] for e in troupe.player.client.get(f"/characters/{agnes}/log").json()]
    assert (
        f"player gave Agnes the fleeting status Courageous, from Prince Varga at game {game}."
        in log
    )
    assert troupe.session.get_one(
        HeldStatus, uuid.UUID(held_id(troupe.player, agnes, "Courageous"))
    ).game_id

    set_to = troupe.storyteller.client.patch(f"/troupes/{troupe.id}", json={"status_by": "staff"})
    assert set_to.status_code == 200, set_to.text
    refused = troupe.player.client.post(
        f"/characters/{agnes}/play/status", json={"name": "Loyal", "patron_text": "Varga"}
    )
    assert refused.status_code == 409
    # Spending stays the holder's.
    loyal = held_id(troupe.player, agnes, "Courageous")
    send(troupe.player, agnes, tap(f"held:{loyal}", -1))
    assert held(troupe.player, agnes) == []
    by_staff = troupe.storyteller.client.post(
        f"/characters/{agnes}/play/status",
        json={"name": "Loyal", "patron_text": "Varga", "reason": "Held the door"},
    )
    assert by_staff.status_code == 200, by_staff.text


def test_a_title_given_during_a_game_gives_nothing_until_the_next(troupe: Troupe) -> None:
    agnes = member(troupe)
    send(troupe.player, agnes, tap("blood", -1))

    entitle(troupe, agnes, "Sheriff")
    state = view(troupe.player, agnes)
    sheriff = next(t for t in state["status"]["titles"] if t["name"] == "Sheriff")
    assert (sheriff["next_game"], sheriff["active"]) == (True, True)
    assert state["status"]["sources"] == []
    assert carried(state) == []

    reset(troupe.player, agnes)
    state = view(troupe.player, agnes)["status"]
    assert [s["name"] for s in state["sources"]] == ["Sheriff"]
    assert not any(t["next_game"] for t in state["titles"])


def test_a_title_taken_during_a_game_takes_its_unspent_status(troupe: Troupe) -> None:
    agnes = member(troupe)
    entitle(troupe, agnes, "Seneschal", "Primogen")
    assert choose(troupe.player, agnes, source="Seneschal").status_code == 200

    entitle(troupe, agnes, "Primogen")
    state = view(troupe.player, agnes)["status"]
    # The source chosen is gone: no other title stands in for it this game.
    assert (state["source"], state["choosing"]) == (None, False)
    assert state["carried"] == []


def test_staff_suppress_fleeting_status_and_it_comes_back(troupe: Troupe) -> None:
    agnes = member(troupe)
    assert add(troupe.player, agnes, "Loyal").status_code == 200
    path = f"/characters/{agnes}/status"

    assert (
        troupe.player.client.post(
            f"{path}/suppress", json={"kind": "commander", "reason": "Defied the Prince"}
        ).status_code
        == 409
    )
    suppressed = troupe.storyteller.client.post(
        f"{path}/suppress", json={"kind": "commander", "reason": "Defied the Prince"}
    )
    assert suppressed.status_code == 200, suppressed.text
    [why] = suppressed.json()["suppressed"]
    assert (why["kind"], why["ending"]["games_left"]) == ("commander", 2)

    state = view(troupe.player, agnes)
    loyal = entry(state, "Loyal")
    assert (loyal["suppressed"], loyal["spendable"]) == (True, False)
    assert state["status"]["suppressed"][0]["text"] == "for defying a Commander"
    # It gains none meanwhile.
    refused = add(troupe.player, agnes, "Courageous")
    assert refused.status_code == 409
    assert "suppressed" in refused.json()["detail"]

    lifted = troupe.storyteller.client.post(
        f"{path}/suppressions/{why['id']}/lift", json={"reason": "Pardoned"}
    )
    assert lifted.status_code == 200, lifted.text
    assert lifted.json()["suppressed"] == []
    assert not entry(view(troupe.player, agnes), "Loyal")["suppressed"]


def test_suppressed_for_the_game_comes_back_when_it_ends(troupe: Troupe) -> None:
    agnes = member(troupe)
    assert add(troupe.player, agnes, "Loyal").status_code == 200
    send(troupe.player, agnes, tap("blood", -1))
    suppressed = troupe.storyteller.client.post(
        f"/characters/{agnes}/status/suppress", json={"kind": "game", "reason": "Struck dumb"}
    )
    assert suppressed.status_code == 200, suppressed.text
    assert entry(view(troupe.player, agnes), "Loyal")["suppressed"]

    reset(troupe.player, agnes)
    assert not entry(view(troupe.player, agnes), "Loyal")["suppressed"]
    assert logged(troupe.session, agnes, "status.suppression_ended")


def test_holding_vulgar_suppresses_fleeting_status(troupe: Troupe) -> None:
    agnes = member(troupe)
    assert add(troupe.player, agnes, "Loyal").status_code == 200
    assert add(troupe.player, agnes, "Vulgar").status_code == 200

    state = view(troupe.player, agnes)
    assert entry(state, "Loyal")["suppressed"]
    assert state["status"]["suppressed"][0]["kind"] == "vulgar"
