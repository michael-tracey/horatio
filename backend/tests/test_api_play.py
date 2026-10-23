"""The Play View: blood, Willpower, health and limited uses spent tap by tap at a
game, in the order the taps happened, and reset for the next game (issue #71)."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio import play
from horatio.rules.files import DATA_DIR, load_rule_set
from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_sheets import buy, make_home_troupe_member

T0 = datetime(2026, 10, 17, 20, 0, tzinfo=UTC)


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def agnes(troupe: Troupe, session: Session) -> str:
    """A character at home in the troupe, with Herd 2."""
    character_id = new_character(troupe, troupe.player)
    assert buy(troupe.player, character_id, "backgrounds", "Herd", 2).status_code == 200
    make_home_troupe_member(session, troupe, character_id)
    return character_id


def view(person: Person, character_id: str) -> dict[str, Any]:
    response = person.client.get(f"/characters/{character_id}/play")
    assert response.status_code == 200, response.text
    return response.json()


def tap(tracker: str = "blood", amount: int = -1, *, at: int = 0, **extra: Any) -> dict[str, Any]:
    """A change made `at` minutes into the game."""
    return {
        "id": str(uuid.uuid4()),
        "happened_at": (T0 + timedelta(minutes=at)).isoformat(),
        "kind": "change",
        "tracker": tracker,
        "amount": amount,
        **extra,
    }


def send(person: Person, character_id: str, *taps: dict[str, Any]) -> dict[str, Any]:
    response = person.client.post(f"/characters/{character_id}/play/taps", json={"taps": taps})
    assert response.status_code == 200, response.text
    return response.json()


def texts(state: dict[str, Any]) -> list[str]:
    return [e["text"] for e in state["log"]]


def test_a_new_game_starts_where_the_sheet_does(troupe: Troupe, agnes: str) -> None:
    state = view(troupe.player, agnes)

    # No Generation dots count as Generation 1: 10 blood, 1 a turn.
    assert state["blood"] == {"value": 10, "most": 10, "start": 10}
    assert state["blood_per_turn"] == 1
    # Herd 2: feeding at a game takes 5 minutes for 2 blood.
    assert state["herd"] == 2
    assert state["willpower"] == {"value": 6, "most": 6, "start": 6}
    assert [(h["name"], h["boxes"]) for h in state["health"]["levels"]] == [
        ("Healthy", 3),
        ("Injured", 3),
        ("Incapacitated", 3),
    ]
    assert state["health"]["marks"] == []
    assert state["morality"] == {"name": "Humanity", "value": 5, "rating": 5}
    assert state["beast"] == {"value": 0, "most": 5, "start": 0}
    assert [(e["name"], e["uses"], e["left"]) for e in state["expendables"]] == [("Herd", 2, 2)]
    assert state["game"] is None
    assert state["log"] == []
    # The sheet and pools come from /play/reference, loaded once.
    assert "pools" not in state


def test_each_tap_is_logged_with_its_time_and_who_made_it(troupe: Troupe, agnes: str) -> None:
    send(troupe.player, agnes, tap("blood", -1, at=1))
    state = send(troupe.storyteller, agnes, tap("willpower", -1, at=2, note="resisted Dominate"))

    assert state["blood"]["value"] == 9
    assert state["willpower"]["value"] == 5
    assert state["game"]["number"] == 1
    newest, oldest = state["log"]
    assert oldest["text"] == "Blood 10 → 9"
    assert oldest["actor_name"] == "player"
    assert not oldest["by_staff"]
    assert oldest["happened_at"] == (T0 + timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
    assert newest["text"] == "Willpower 6 → 5"
    assert newest["note"] == "resisted Dominate"
    assert newest["by_staff"]


def test_taps_sent_late_take_their_place_by_when_they_happened(troupe: Troupe, agnes: str) -> None:
    # The storyteller's screen restores a point of Willpower at minute 5, while the
    # player's phone, offline, spent one at minute 3; its tap arrives afterwards.
    first = send(troupe.storyteller, agnes, tap("willpower", 1, at=5))
    assert first["willpower"]["value"] == 6  # already full, so nothing to restore yet

    state = send(troupe.player, agnes, tap("willpower", -1, at=3))

    assert texts(state) == ["Willpower 5 → 6", "Willpower 6 → 5"]
    assert state["willpower"]["value"] == 6


def test_a_tap_sent_twice_is_recorded_once(troupe: Troupe, agnes: str, session: Session) -> None:
    spent = tap("blood", -2)
    send(troupe.player, agnes, spent)
    state = send(troupe.player, agnes, spent, tap("blood", -1, at=1))

    assert texts(state) == ["Blood 8 → 7", "Blood 10 → 8"]

    other = new_character(troupe, troupe.player, "Mara")
    response = troupe.player.client.post(f"/characters/{other}/play/taps", json={"taps": [spent]})
    assert response.status_code == 409


def test_undo_the_latest_tap(troupe: Troupe, agnes: str) -> None:
    spent = tap("blood", -1, at=1)
    send(troupe.player, agnes, tap("blood", -1), spent)
    undo = {
        "id": str(uuid.uuid4()),
        "happened_at": (T0 + timedelta(minutes=2)).isoformat(),
        "kind": "undo",
        "undoes": spent["id"],
    }
    state = send(troupe.player, agnes, undo)

    assert state["blood"]["value"] == 9
    assert texts(state) == ["Undid: Blood 9 → 8", "Blood 9 → 8", "Blood 10 → 9"]
    assert [e["undone"] for e in state["log"]] == [False, True, False]
    assert state["log"][0]["undoes"] == spent["id"]

    # Undoing it again changes nothing.
    again = send(troupe.player, agnes, {**undo, "id": str(uuid.uuid4())})
    assert len(again["log"]) == 3
    assert again["blood"]["value"] == 9


def test_health_marks_normal_and_aggravated_damage(troupe: Troupe, agnes: str) -> None:
    state = send(
        troupe.player,
        agnes,
        tap("health", 2, damage="normal"),
        tap("health", 1, at=1, damage="aggravated"),
        tap("health", -1, at=2, damage="normal"),
    )
    assert state["health"]["marks"] == ["normal", "aggravated"]
    assert state["log"][0]["text"] == "Health: healed 1 normal (3 → 2 marked)"

    # No more boxes than the sheet has.
    state = send(troupe.player, agnes, tap("health", 20, at=3, damage="aggravated"))
    assert len(state["health"]["marks"]) == 9

    response = troupe.player.client.post(
        f"/characters/{agnes}/play/taps", json={"taps": [tap("health", 1)]}
    )
    assert response.status_code == 422  # normal or aggravated?


def test_limited_uses_with_quick_notes(troupe: Troupe, agnes: str) -> None:
    herd = play.trait_key("backgrounds", "Herd", "")
    state = send(
        troupe.player,
        agnes,
        tap(herd, -1, note="fed at the club"),
        {
            "id": str(uuid.uuid4()),
            "happened_at": (T0 + timedelta(minutes=1)).isoformat(),
            "kind": "note",
            "note": "the Prince's itinerary is in the safe",
        },
    )

    assert state["expendables"][0]["left"] == 1
    assert [(e["text"], e["note"]) for e in state["log"]] == [
        ("Note", "the Prince's itinerary is in the safe"),
        ("Herd 2 → 1", "fed at the club"),
    ]
    assert state["game"]["notes"] == 2


def test_custom_counters_reset_with_the_rest(troupe: Troupe, agnes: str) -> None:
    response = troupe.player.client.post(
        f"/characters/{agnes}/play/counters", json={"name": "Fetish charges", "uses": 3}
    )
    assert response.status_code == 200, response.text
    counter = next(e for e in response.json()["expendables"] if e["name"] == "Fetish charges")
    assert (counter["group"], counter["uses"], counter["left"]) == ("Counters", 3, 3)

    state = send(troupe.player, agnes, tap(counter["key"], -2))
    assert texts(state) == ["Fetish charges 3 → 1"]
    reset = troupe.player.client.post(f"/characters/{agnes}/play/reset", json={})
    fresh = next(e for e in reset.json()["expendables"] if e["name"] == "Fetish charges")
    assert fresh["left"] == 3

    # Staff can remove it; the old game's log still names it.
    removed = troupe.storyteller.client.delete(
        f"/characters/{agnes}/play/counters/{counter['counter_id']}"
    )
    assert removed.status_code == 200, removed.text
    assert [e["name"] for e in removed.json()["expendables"]] == ["Herd"]
    past = troupe.player.client.get(f"/characters/{agnes}/play/games").json()
    log = troupe.player.client.get(f"/characters/{agnes}/play/games/{past[0]['id']}").json()
    assert texts(log) == ["Fetish charges 3 → 1"]


def test_reset_keeps_the_game_and_starts_the_next(troupe: Troupe, agnes: str) -> None:
    played = send(
        troupe.player,
        agnes,
        tap("blood", -4),
        tap("willpower", -2, at=1),
        tap("health", 3, at=2, damage="normal"),
        tap("beast", 2, at=3),
        tap("morality", -1, at=4),
    )
    game_one = played["game"]["id"]

    state = troupe.player.client.post(
        f"/characters/{agnes}/play/reset", json={"game_id": game_one}
    ).json()

    assert state["game"]["number"] == 2
    assert state["log"] == []
    assert state["blood"]["value"] == 10
    assert state["willpower"]["value"] == 6
    assert state["health"]["marks"] == []
    assert state["beast"]["value"] == 0
    assert state["morality"]["value"] == 5
    past = troupe.player.client.get(f"/characters/{agnes}/play/games").json()
    assert [(g["number"], g["taps"], g["ended_by"]) for g in past] == [(1, 5, "player")]
    assert past[0]["ended_at"] is not None

    # A second device resetting the same game does not end the new one.
    send(troupe.player, agnes, tap("blood", -1, at=10))
    again = troupe.storyteller.client.post(
        f"/characters/{agnes}/play/reset", json={"game_id": game_one}
    ).json()
    assert again["game"]["number"] == 2
    assert again["blood"]["value"] == 9


def test_a_tap_made_before_the_reset_lands_in_its_own_game(troupe: Troupe, agnes: str) -> None:
    game_one = send(troupe.player, agnes, tap("blood", -1))["game"]["id"]
    troupe.storyteller.client.post(f"/characters/{agnes}/play/reset", json={})

    # The phone was offline at the end of the game; its last tap arrives now.
    state = send(troupe.player, agnes, tap("blood", -1, at=50, game_id=game_one))

    assert state["blood"]["value"] == 10
    log = troupe.player.client.get(f"/characters/{agnes}/play/games/{game_one}").json()
    assert texts(log) == ["Blood 9 → 8", "Blood 10 → 9"]


def test_resetting_a_game_with_no_taps_changes_nothing(troupe: Troupe, agnes: str) -> None:
    state = troupe.player.client.post(f"/characters/{agnes}/play/reset", json={}).json()

    assert state["game"] is None
    assert troupe.player.client.get(f"/characters/{agnes}/play/games").json() == []


def test_a_troupe_house_rule_sets_the_starting_blood(troupe: Troupe, agnes: str) -> None:
    assert (
        troupe.assistant.client.put(
            f"/troupes/{troupe.id}/starting-blood", json={"blood": 5}
        ).status_code
        == 403
    )
    response = troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/starting-blood", json={"blood": 5}
    )
    assert response.status_code == 200, response.text
    assert response.json()["starting_blood"] == 5

    state = view(troupe.player, agnes)
    assert state["blood"] == {"value": 5, "most": 10, "start": 5}
    send(troupe.player, agnes, tap("blood", 3))  # fed
    state = troupe.player.client.post(f"/characters/{agnes}/play/reset", json={}).json()
    assert state["blood"]["value"] == 5

    # Never more than the generation's most; and back to full.
    troupe.storyteller.client.put(f"/troupes/{troupe.id}/starting-blood", json={"blood": 20})
    assert view(troupe.player, agnes)["blood"]["value"] == 10
    troupe.storyteller.client.put(f"/troupes/{troupe.id}/starting-blood", json={"blood": None})
    assert troupe.lead.client.get(f"/troupes/{troupe.id}").json()["starting_blood"] is None


def test_who_can_use_the_play_view(troupe: Troupe, agnes: str) -> None:
    for person in (troupe.storyteller, troupe.assistant, troupe.lead, troupe.custodian):
        assert person.client.get(f"/characters/{agnes}/play").status_code == 200
    for person in (troupe.narrator, troupe.stranger):
        assert person.client.get(f"/characters/{agnes}/play").status_code == 404
        response = person.client.post(f"/characters/{agnes}/play/taps", json={"taps": [tap()]})
        assert response.status_code == 404
        assert person.client.post(f"/characters/{agnes}/play/reset", json={}).status_code == 404


def test_staff_reset_the_whole_troupe_and_read_each_log(
    troupe: Troupe, agnes: str, session: Session
) -> None:
    mara = new_character(troupe, troupe.player, "Mara")
    make_home_troupe_member(session, troupe, mara)
    idle = new_character(troupe, troupe.player, "Idle")
    make_home_troupe_member(session, troupe, idle)
    send(troupe.player, agnes, tap("blood", -3))
    send(troupe.player, mara, tap("willpower", -1))

    overview = troupe.assistant.client.get(f"/troupes/{troupe.id}/play").json()
    by_name = {e["character_name"]: e for e in overview}
    assert by_name["Agnes"]["blood"]["value"] == 7
    assert by_name["Agnes"]["taps"] == 1
    assert by_name["Idle"]["game_number"] is None

    for person in (troupe.player, troupe.narrator):
        assert person.client.post(f"/troupes/{troupe.id}/play/reset").status_code == 403
    response = troupe.assistant.client.post(f"/troupes/{troupe.id}/play/reset")
    assert response.status_code == 200, response.text
    assert response.json() == {"reset": 2}

    assert view(troupe.player, agnes)["blood"]["value"] == 10
    past = troupe.storyteller.client.get(f"/characters/{mara}/play/games").json()
    log = troupe.storyteller.client.get(f"/characters/{mara}/play/games/{past[0]['id']}").json()
    assert texts(log) == ["Willpower 6 → 5"]
    events = troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()
    assert any("reset 2 characters for the next game" in e["message"] for e in events)


def test_uses_a_game_come_from_the_rules() -> None:
    rules = load_rule_set(DATA_DIR / "bns_met_vampire.toml")

    def uses(category: str, name: str) -> Any:
        return rules.trait_properties(category, name).get("uses_per_game")

    for background in ("Herd", "Influences: The Elite", "Influences: The Underworld", "Allies"):
        assert uses("backgrounds", background) == "rating"
    assert uses("merits", "Regal Bearing") == 1
    assert uses("backgrounds", "Haven") is None
    spec = uses("merits", "Whispers from Beyond")
    assert play.uses_per_game(spec, 1, {("skills", "Occult"): 3}) == 3
    assert play.uses_per_game("rating", 4, {}) == 4
    assert play.uses_per_game(2, None, {}) == 2


def test_npcs_are_at_game_and_reset_with_everyone(troupe: Troupe, agnes: str) -> None:
    """People → At game lists the troupe's NPCs, and Reset everyone resets them (#91)."""
    made = troupe.storyteller.client.post(f"/troupes/{troupe.id}/npcs", json={"name": "Lucien"})
    lucien = made.json()["id"]
    send(troupe.storyteller, lucien, tap("willpower", -1))
    send(troupe.player, agnes, tap("blood", -1))

    overview = troupe.lead.client.get(f"/troupes/{troupe.id}/play").json()
    by_name = {e["character_name"]: e for e in overview}
    assert (by_name["Lucien"]["kind"], by_name["Lucien"]["player_name"]) == ("npc", "NPC")
    assert by_name["Lucien"]["taps"] == 1

    reset = troupe.lead.client.post(f"/troupes/{troupe.id}/play/reset")
    assert reset.json() == {"reset": 2}
    assert view(troupe.storyteller, lucien)["game"]["number"] == 2


def test_feeding_at_a_game_is_a_blood_tap_with_a_note(troupe: Troupe, agnes: str) -> None:
    """Feed on the Play View (#153) records its blood as an ordinary tap, capped at
    the most; a character without Herd has a Herd of 0."""
    send(troupe.player, agnes, tap("blood", -3, at=1))
    state = send(troupe.storyteller, agnes, tap("blood", 2, at=20, note="Fed (Herd 2)"))
    assert state["blood"]["value"] == 9
    assert state["log"][0]["text"] == "Blood 7 → 9"
    assert state["log"][0]["note"] == "Fed (Herd 2)"
    state = send(troupe.player, agnes, tap("blood", 2, at=30, note="Fed (Herd 2)"))
    assert state["log"][0]["text"] == "Blood 9 → 10"

    no_herd = new_character(troupe, troupe.player, "Mara")
    assert view(troupe.player, no_herd)["herd"] == 0
