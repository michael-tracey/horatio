"""A power used on another character of the home troupe (issue #823): its effect
reaches their Play View at once, they acknowledge or dispute it, and whoever used it
or staff end it. A use that heals changes their own trackers."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import reference
from horatio.models import AuditEvent, Character, Notification, PlayEffect
from tests.api_helpers import Person, Troupe, new_character, sign_up
from tests.test_api_play import send, tap, view
from tests.test_api_play_powers import give, on
from tests.test_api_sheets import make_home_troupe_member

RESHAPED = "Reshaped by Fleshcraft"


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def second(client_for: Callable[[], TestClient]) -> Person:
    return sign_up(client_for, "second")


@pytest.fixture
def velya(troupe: Troupe, session: Session) -> str:
    """A fleshcrafter with Vicissitude 2 (Fleshcraft), at home in the troupe."""
    character_id = new_character(troupe, troupe.player, "Velya")
    give(session, character_id, "disciplines", "Vicissitude", 2)
    make_home_troupe_member(session, troupe, character_id)
    return character_id


@pytest.fixture
def bram(troupe: Troupe, second: Person, session: Session) -> str:
    """Another player's character, at home in the troupe."""
    character_id = new_character(troupe, second, "Bram")
    make_home_troupe_member(session, troupe, character_id)
    return character_id


def used_on(
    character_id: str, *, switch: str | None = None, use: str | None = None, power: str, **more: Any
) -> dict[str, Any]:
    """The note tap that uses a power on another character."""
    return {
        **tap("blood", 0, at=more.pop("at", 0)),
        "kind": "note",
        "tracker": "",
        "amount": 0,
        "note": f"{power} on someone",
        "on_other": {
            "character_id": character_id,
            "power": power,
            "switch": switch,
            "use": use,
            "options": more.pop("options", []),
        },
    }


def reshape(bram: str, *options: str, at: int = 0) -> dict[str, Any]:
    return used_on(bram, switch=RESHAPED, power="Fleshcraft", options=list(options), at=at)


def told(session: Session, kind: str) -> list[str]:
    return list(
        session.scalars(
            select(Notification.summary)
            .where(Notification.kind == kind)
            .order_by(Notification.created_at, Notification.id)
        )
    )


def test_the_switch_is_for_others_only_and_says_so(troupe: Troupe, velya: str) -> None:
    [found] = [p for p in view(troupe.player, velya)["powers"] if p["key"] == RESHAPED]
    assert found["target"] == "other" and found["kept"] and found["normal_form_only"]
    assert found["name"] == "Fleshcraft: reshaped"
    assert [o["name"] for o in found["picks"]["options"]] == ["Ordinary change", "Alien beauty"]
    [corpore] = reference.switch_for(RESHAPED)[:1]
    assert corpore.target == "other"


def test_only_the_home_troupe_can_be_picked(
    troupe: Troupe, velya: str, bram: str, second: Person, session: Session
) -> None:
    stray = new_character(troupe, second, "Stray")  # in no troupe
    response = troupe.player.client.get(f"/characters/{velya}/play/targets")
    assert response.status_code == 200, response.text
    assert [t["name"] for t in response.json()] == ["Bram"]

    state = send(troupe.player, velya, used_on(stray, switch=RESHAPED, power="Fleshcraft"))
    assert state["log"][0]["text"].startswith("Couldn't use Fleshcraft on Stray: Only a character")
    assert session.scalars(select(PlayEffect)).all() == []


def test_a_power_used_on_another_counts_on_their_play_view_at_once(
    troupe: Troupe, velya: str, bram: str, second: Person, session: Session
) -> None:
    state = send(troupe.player, velya, tap("blood", -1), reshape(bram, "Alien beauty", at=1))
    assert state["log"][0]["text"] == "Used Fleshcraft: reshaped (Alien beauty) on Bram"
    [made] = state["effects_made"]
    assert (made["character_name"], made["name"], made["options"]) == (
        "Bram",
        "Fleshcraft: reshaped",
        ["Alien beauty"],
    )
    # Velya's own switch is not on: it was used on Bram.
    assert RESHAPED not in on(state)

    theirs = view(second, bram)
    assert on(theirs) == {RESHAPED}
    [shown] = [p for p in theirs["powers"] if p["key"] == RESHAPED]
    assert shown["foreign"] and shown["picked"] == ["Alien beauty"]
    [effect] = theirs["effects"]
    assert effect["source_character_name"] == "Velya"
    assert effect["options"] == ["Alien beauty"]
    assert effect["acknowledged_at"] is None
    assert told(session, "play.effect_on_you") == [
        "Velya used Fleshcraft: reshaped (Alien beauty) on Bram."
    ]


def test_picks_must_fit_the_power(troupe: Troupe, velya: str, bram: str, session: Session) -> None:
    state = send(troupe.player, velya, reshape(bram))
    assert "Pick one of what it does" in state["log"][0]["text"]
    state = send(troupe.player, velya, reshape(bram, "Ordinary change", "Alien beauty", at=1))
    assert "Pick one of what it does" in state["log"][0]["text"]
    state = send(troupe.player, velya, reshape(bram, "Bone spurs", at=2))
    assert "can't be picked" in state["log"][0]["text"]
    assert session.scalars(select(PlayEffect)).all() == []


def test_it_lasts_through_their_reset_and_they_cant_turn_it_off(
    troupe: Troupe, velya: str, bram: str, second: Person
) -> None:
    send(troupe.player, velya, reshape(bram, "Ordinary change"))
    send(second, bram, tap(f"power:{RESHAPED}", -1))
    assert RESHAPED in on(view(second, bram))
    response = second.client.post(f"/characters/{bram}/play/reset", json={})
    assert response.status_code == 200, response.text
    assert RESHAPED in on(response.json())


def test_they_acknowledge_or_dispute_it_to_staff(
    troupe: Troupe, velya: str, bram: str, second: Person, session: Session
) -> None:
    send(troupe.player, velya, reshape(bram, "Alien beauty"))
    [effect] = view(second, bram)["effects"]
    response = second.client.post(f"/characters/{bram}/play/effects/{effect['id']}/acknowledge")
    assert response.status_code == 200, response.text
    assert response.json()["effects"][0]["acknowledged_at"] is not None
    assert told(session, "play.effect_acknowledged") == [
        "Bram acknowledged Fleshcraft: reshaped (Alien beauty), used on them by Velya."
    ]

    response = second.client.post(
        f"/characters/{bram}/play/effects/{effect['id']}/dispute",
        json={"note": "We never agreed to this."},
    )
    assert response.status_code == 200, response.text
    [disputed] = response.json()["effects"]
    assert disputed["dispute_note"] == "We never agreed to this."
    summaries = told(session, "play.effect_disputed")
    # The lead and every staff member, and the one who used it.
    assert len(summaries) >= 2
    assert summaries[0] == (
        "Bram disputed Fleshcraft: reshaped (Alien beauty), used on them by Velya: "
        "We never agreed to this."
    )
    made = view(troupe.player, velya)["effects_made"][0]
    assert made["dispute_note"] == "We never agreed to this."
    # It stays on until whoever used it, or staff, end it.
    assert RESHAPED in on(view(second, bram))

    # Another player can't answer for Bram.
    response = troupe.stranger.client.post(
        f"/characters/{bram}/play/effects/{effect['id']}/acknowledge"
    )
    assert response.status_code in (403, 404)


def test_whoever_used_it_ends_it(
    troupe: Troupe, velya: str, bram: str, second: Person, session: Session
) -> None:
    send(troupe.player, velya, reshape(bram, "Alien beauty"))
    made = view(troupe.player, velya)["effects_made"][0]
    # Bram can't end it as if it were Velya's.
    response = second.client.post(f"/characters/{bram}/play/effects-made/{made['id']}/end")
    assert response.status_code == 404
    response = troupe.player.client.post(f"/characters/{velya}/play/effects-made/{made['id']}/end")
    assert response.status_code == 200, response.text
    assert response.json()["effects_made"] == []
    assert RESHAPED not in on(view(second, bram))
    [ended] = session.scalars(select(PlayEffect)).all()
    assert ended.ended_how == "source"
    assert told(session, "play.effect_ended_on_you") == [
        "Velya ended Fleshcraft: reshaped (Alien beauty) on Bram."
    ]


def test_undo_takes_it_back_and_brings_back_the_one_it_replaced(
    troupe: Troupe, velya: str, bram: str, second: Person, session: Session
) -> None:
    first, again = reshape(bram, "Ordinary change"), reshape(bram, "Alien beauty", at=1)
    send(troupe.player, velya, first, again)
    assert view(second, bram)["effects"][0]["options"] == ["Alien beauty"]
    send(troupe.player, velya, {**tap("blood", 0, at=2), "kind": "undo", "undoes": again["id"]})
    [effect] = view(second, bram)["effects"]
    assert effect["options"] == ["Ordinary change"]
    send(troupe.player, velya, {**tap("blood", 0, at=3), "kind": "undo", "undoes": first["id"]})
    assert view(second, bram)["effects"] == []


def test_staff_end_it_and_the_target_hears(
    troupe: Troupe, velya: str, bram: str, second: Person, session: Session
) -> None:
    send(troupe.player, velya, reshape(bram, "Alien beauty"))
    [effect] = view(second, bram)["effects"]
    response = troupe.storyteller.client.post(f"/characters/{bram}/play/effects/{effect['id']}/end")
    assert response.status_code == 200, response.text
    assert response.json()["effects"] == []
    assert told(session, "play.effect_ended_on_you") == [
        "Staff ended Fleshcraft: reshaped on Bram."
    ]


def test_a_tap_sent_twice_uses_it_once(
    troupe: Troupe, velya: str, bram: str, session: Session
) -> None:
    once = reshape(bram, "Ordinary change")
    send(troupe.player, velya, once)
    send(troupe.player, velya, once)
    assert len(session.scalars(select(PlayEffect)).all()) == 1


def test_corpore_sano_heals_another_and_undo_takes_it_back(
    troupe: Troupe, bram: str, second: Person, session: Session
) -> None:
    healer = new_character(troupe, troupe.player, "Ivo")
    give(session, healer, "disciplines", "Obeah", 3)
    make_home_troupe_member(session, troupe, healer)
    send(second, bram, tap("health", 2, damage="normal"))

    heal = used_on(bram, use="Heal 1 normal", power="Corpore Sano", at=1)
    state = send(troupe.player, healer, tap("blood", -1, at=1), heal)
    assert state["log"][0]["text"] == "Used Corpore Sano on Bram: healed 1 normal"
    theirs = view(second, bram)
    assert theirs["health"]["marks"] == ["normal"]
    assert theirs["log"][0]["actor_name"] == "player"
    assert told(session, "play.used_on_you") == ["Ivo used Corpore Sano on Bram: healed 1 normal."]

    send(troupe.player, healer, {**tap("blood", 0, at=2), "kind": "undo", "undoes": heal["id"]})
    assert view(second, bram)["health"]["marks"] == ["normal", "normal"]

    # Nothing to heal: refused, and Bram's game is untouched.
    send(second, bram, tap("health", -2, at=3, damage="normal"))
    state = send(
        troupe.player, healer, used_on(bram, use="Heal 1 normal", power="Corpore Sano", at=4)
    )
    assert state["log"][0]["text"] == (
        "Couldn't use Corpore Sano on Bram: Bram has no damage it heals."
    )
    actions = session.scalars(
        select(AuditEvent.action).where(AuditEvent.action == "play.used_on_other")
    ).all()
    assert actions == ["play.used_on_other"]


def test_a_power_the_user_hasnt_cant_be_used(troupe: Troupe, bram: str, session: Session) -> None:
    plain = new_character(troupe, troupe.player, "Plain")
    make_home_troupe_member(session, troupe, plain)
    state = send(troupe.player, plain, used_on(bram, switch=RESHAPED, power="Fleshcraft"))
    assert "Plain can't use that on another character" in state["log"][0]["text"]
    state = send(troupe.player, plain, used_on(bram, use="Heal 1 normal", power="Corpore Sano"))
    assert "Plain can't use that on another character" in state["log"][0]["text"]
    character = session.get_one(Character, uuid.UUID(bram))
    assert (
        session.scalars(select(PlayEffect).where(PlayEffect.character_id == character.id)).all()
        == []
    )
