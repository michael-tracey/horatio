"""A power's effect that lasts until undone (issue #822): kept through Reset until it
is turned off, one application at a time, and paused in a transformed form for one
that changes the normal form only."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import play, reference
from horatio.models import AuditEvent, Character, PlayEffect
from tests.api_helpers import Troupe, new_character
from tests.test_api_play import send, tap, view
from tests.test_api_play_powers import give, on
from tests.test_api_sheets import make_home_troupe_member

HEART = "power:Heart removed"


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def setne(troupe: Troupe, session: Session) -> str:
    """A Follower of Set with Serpentis 5 (Heart of Darkness), at home in the troupe."""
    character_id = new_character(troupe, troupe.player, "Setne")
    give(session, character_id, "disciplines", "Serpentis", 5)
    make_home_troupe_member(session, troupe, character_id)
    return character_id


def undo(tap_id: str, *, at: int = 0) -> dict[str, Any]:
    found = tap("blood", 0, at=at)
    return {**found, "kind": "undo", "undoes": tap_id}


def effects(session: Session, character_id: str) -> list[PlayEffect]:
    return list(
        session.scalars(
            select(PlayEffect)
            .where(PlayEffect.character_id == uuid.UUID(character_id))
            .order_by(PlayEffect.started_at, PlayEffect.id)
        )
    )


def reset(troupe: Troupe, character_id: str) -> dict[str, Any]:
    response = troupe.player.client.post(f"/characters/{character_id}/play/reset", json={})
    assert response.status_code == 200, response.text
    return response.json()


def test_heart_of_darkness_is_kept_and_says_what_it_does(troupe: Troupe, setne: str) -> None:
    heart = next(p for p in view(troupe.player, setne)["powers"] if p["key"] == "Heart removed")
    assert heart["kept"] and not heart["normal_form_only"] and not heart["form"]
    assert heart["name"] == "Heart of Darkness: heart removed"
    assert heart["page"] == "p. 161"
    assert "Frenzy resisted as if with 1 Beast trait fewer" in heart["changes"]
    assert "You can't be staked." in heart["notes"]


def test_a_kept_effect_lasts_through_reset_until_it_is_turned_off(
    troupe: Troupe, setne: str, session: Session
) -> None:
    state = send(troupe.player, setne, tap("blood", -1), tap(HEART, 1, at=1))
    assert on(state) == {"Heart removed"}
    assert [e["name"] for e in state["effects"]] == ["Heart of Darkness: heart removed"]
    assert state["effects"][0]["started_by"] == "player"
    heart = next(p for p in state["powers"] if p["key"] == "Heart removed")
    assert heart["since"] is not None
    assert "Heart of Darkness: heart removed on" in state["log"][0]["text"]

    # Reset turns the game's switches off, but not the heart.
    state = reset(troupe, setne)
    assert state["game"]["number"] == 2
    assert on(state) == {"Heart removed"}
    state = reset(troupe, setne)  # A game with no taps stays as it is.
    assert on(state) == {"Heart removed"}

    state = send(troupe.player, setne, tap(HEART, -1, at=5))
    assert on(state) == set()
    assert state["effects"] == []
    [ended] = effects(session, setne)
    assert (ended.state, ended.ended_how) == ("ended", "off")
    state = send(troupe.player, setne, tap("blood", -1, at=6))
    assert reset(troupe, setne)["effects"] == []

    actions = session.scalars(
        select(AuditEvent.action)
        .where(AuditEvent.action.startswith("play.effect"))
        .order_by(AuditEvent.created_at, AuditEvent.id)
    ).all()
    assert actions == ["play.effect_started", "play.effect_ended"]


def test_a_tap_sent_twice_starts_one_effect(troupe: Troupe, setne: str, session: Session) -> None:
    once = tap(HEART, 1)
    send(troupe.player, setne, once)
    state = send(troupe.player, setne, once)
    assert on(state) == {"Heart removed"}
    assert len(effects(session, setne)) == 1


def test_using_it_again_replaces_the_one_on_and_undo_brings_it_back(
    troupe: Troupe, setne: str, session: Session
) -> None:
    first, second = tap(HEART, 1), tap(HEART, 1, at=1)
    state = send(troupe.player, setne, first, second)
    assert len(state["effects"]) == 1
    old, new = effects(session, setne)
    assert (old.state, old.ended_how) == ("ended", "replaced")
    assert (new.state, new.replaced_id) == ("active", old.id)

    state = send(troupe.player, setne, undo(second["id"], at=2))
    assert on(state) == {"Heart removed"}
    session.expire_all()
    old, new = effects(session, setne)
    assert (old.state, new.state, new.ended_how) == ("active", "ended", "undone")
    assert state["effects"][0]["id"] == str(old.id)


def test_undo_ends_the_effect_a_tap_started_or_brings_back_one_it_ended(
    troupe: Troupe, setne: str, session: Session
) -> None:
    started = tap(HEART, 1)
    state = send(troupe.player, setne, started, undo(started["id"], at=1))
    assert on(state) == set()

    again, off = tap(HEART, 1, at=2), tap(HEART, -1, at=3)
    assert on(send(troupe.player, setne, again, off)) == set()
    state = send(troupe.player, setne, undo(off["id"], at=4))
    assert on(state) == {"Heart removed"}
    # Kept through Reset, as before it was turned off.
    assert on(reset(troupe, setne)) == {"Heart removed"}


def test_a_character_without_the_power_starts_nothing(troupe: Troupe, session: Session) -> None:
    character_id = new_character(troupe, troupe.player, "Plain")
    state = send(troupe.player, character_id, tap(HEART, 1))
    assert on(state) == set()
    assert effects(session, character_id) == []


def test_staff_can_see_and_end_an_effect(troupe: Troupe, setne: str, session: Session) -> None:
    send(troupe.player, setne, tap(HEART, 1))
    listed = troupe.storyteller.client.get(f"/troupes/{troupe.id}/play").json()
    [entry] = [e for e in listed if e["character_id"] == setne]
    assert entry["effects"] == ["Heart of Darkness: heart removed"]

    [effect] = view(troupe.storyteller, setne)["effects"]
    # Another player can't reach it.
    other = troupe.stranger.client.post(f"/characters/{setne}/play/effects/{effect['id']}/end")
    assert other.status_code == 404
    response = troupe.storyteller.client.post(
        f"/characters/{setne}/play/effects/{effect['id']}/end"
    )
    assert response.status_code == 200, response.text
    assert on(response.json()) == set()
    [ended] = effects(session, setne)
    assert ended.ended_how == "staff"
    again = troupe.storyteller.client.post(f"/characters/{setne}/play/effects/{effect['id']}/end")
    assert again.status_code == 409


def test_deleting_a_character_takes_its_effects_and_leaves_those_it_used_on_others(
    troupe: Troupe, setne: str, session: Session
) -> None:
    # One with an effect of its own, deleted: its effect goes with it.
    loner = new_character(troupe, troupe.player, "Loner")
    give(session, loner, "disciplines", "Serpentis", 5)
    send(troupe.player, loner, tap(HEART, 1))
    assert troupe.player.client.delete(f"/characters/{loner}").status_code == 204
    assert effects(session, loner) == []

    # One that used a power on another (issue #823), deleted: the effect stays, with its name.
    healer = new_character(troupe, troupe.player, "Healer")
    player_id = session.get_one(Character, uuid.UUID(healer)).player_id
    session.add(
        PlayEffect(
            character_id=uuid.UUID(setne),
            source_character_id=uuid.UUID(healer),
            key="Heart removed",
            client_id=uuid.uuid4(),
            started_at=datetime.now(UTC),
            started_by_id=player_id,
        )
    )
    session.flush()
    assert view(troupe.player, setne)["effects"][0]["source_character_name"] == "Healer"
    assert troupe.player.client.delete(f"/characters/{healer}").status_code == 204
    session.expire_all()
    [kept] = effects(session, setne)
    assert (kept.source_character_id, kept.source_name) == (None, "Healer")
    assert view(troupe.player, setne)["effects"][0]["source_character_name"] == "Healer"


def test_resisting_frenzy_counts_one_fewer_beast_trait_while_the_heart_is_out(
    troupe: Troupe, setne: str
) -> None:
    frenzy = troupe.player.client.get(f"/characters/{setne}/play/reference").json()["frenzy"]
    assert frenzy["beast"] == []
    assert frenzy["switched_beast"] == [
        {
            "switch": "Heart removed",
            "label": "Heart of Darkness",
            "value": -1,
            "attribute": None,
            "most": None,
        }
    ]


def switch(key: str, **fields: Any) -> reference.Switch:
    return reference.Switch(key=key, name=key, origin=key, page="p. 1", **fields)


def limits(*switches: reference.Switch, forms: int = 1) -> play.Limits:
    return play.Limits(
        generation=0,
        blood=10,
        blood_per_turn=1,
        starting_blood=10,
        willpower=5,
        health=(("Healthy", 3),),
        morality=5,
        morality_name="Humanity",
        switches=switches,
        forms=forms,
    )


def test_a_normal_form_only_effect_is_paused_while_a_form_is_on() -> None:
    tough = switch(
        "Tough",
        kept=True,
        normal_form_only=True,
        health=[reference.SwitchLevel(level="Healthy", boxes=2)],
    )
    stomach = switch("Stomach", kept=True, blood_per_turn=1)
    wolf = switch("wolf", form=True)
    found = limits(tough, stomach, wolf)
    assert len(found.boxes(["Tough", "Stomach"])) == 5
    assert found.paused(["Tough", "Stomach"]) == set()
    # In a form, Tough's levels go until the form ends; Stomach's Blood stays.
    assert found.paused(["Tough", "Stomach", "wolf"]) == {"Tough"}
    assert len(found.boxes(["Tough", "Stomach", "wolf"])) == 3
    assert found.blood_per_turn_now(["Tough", "Stomach", "wolf"]) == 2


def test_a_kept_effect_that_counts_as_a_form_takes_one_of_ravenous_conglomerations_two() -> None:
    bone = switch("Bone", kept=True, counts_as_form=True)
    found = limits(bone, switch("wolf", form=True), switch("bat", form=True), forms=2)
    assert found.forms_now([]) == 2
    assert found.forms_now(["Bone"]) == 1
    # One form at most anyway: it takes nothing from a character without the merit.
    assert limits(bone, forms=1).forms_now(["Bone"]) == 1
