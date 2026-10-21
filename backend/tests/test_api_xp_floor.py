"""A troupe's XP floor and ceiling, starting XP for new characters, self-entered
XP, and settling a joining character's XP against the floor and ceiling (issue #74)."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, finish, new_character
from tests.test_api_downtimes import member_character, new_cycle, open_cycle


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def xp_range(person: Person, troupe: Troupe) -> dict[str, Any]:
    response = person.client.get(f"/troupes/{troupe.id}/xp-range")
    assert response.status_code == 200, response.text
    return response.json()


def floor_and_ceiling(troupe: Troupe) -> tuple[int, int]:
    shown = troupe.player.client.get(f"/troupes/{troupe.id}").json()
    return shown["xp_floor"], shown["xp_ceiling"]


def set_by_hand(troupe: Troupe, **figures: Any) -> Any:
    return troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/xp-range", json={"reason": "Chronicle began in 2019", **figures}
    )


def history(person: Person, character_id: str) -> list[tuple[str, int, str]]:
    response = person.client.get(f"/characters/{character_id}/xp")
    assert response.status_code == 200, response.text
    return [(e["kind"], e["amount"], e["reason"]) for e in response.json()]


def balance(person: Person, character_id: str) -> int:
    return person.client.get(f"/characters/{character_id}/sheet").json()["xp"]["balance"]


def self_enter(
    person: Person, character_id: str, amount: int, reason: str = "Played at Con"
) -> Any:
    return person.client.post(
        f"/characters/{character_id}/xp/self-entered", json={"amount": amount, "reason": reason}
    )


def ask_home(
    troupe: Troupe, character_id: str, *, top_up: bool = True, player: Person | None = None
) -> dict[str, Any]:
    response = (player or troupe.player).client.post(
        f"/characters/{character_id}/home-troupe",
        json={"troupe_id": troupe.id, "top_up": top_up},
    )
    assert response.status_code == 201, response.text
    waiting = troupe.assistant.client.get(f"/troupes/{troupe.id}/approvals").json()
    return next(a for a in waiting if a["id"] == response.json()["id"])


def approve(troupe: Troupe, approval: dict[str, Any], **xp: Any) -> Any:
    return troupe.assistant.client.post(
        f"/approvals/{approval['id']}/approve", json={"xp": xp} if xp else {}
    )


def built_for(troupe: Troupe, name: str = "Agnes") -> str:
    response = troupe.player.client.post(
        "/characters", json={"splat": "vampire", "name": name, "building_troupe_id": troupe.id}
    )
    assert response.status_code == 201, response.text
    character_id: str = response.json()["id"]
    finish(troupe, character_id)
    return character_id


# --- the floor and ceiling ----------------------------------------------------------------


def test_a_new_troupe_starts_both_at_its_starting_xp(troupe: Troupe) -> None:
    assert floor_and_ceiling(troupe) == (30, 30)
    shown = xp_range(troupe.player, troupe)
    assert (shown["starting_xp"], shown["games"], shown["downtimes"]) == (30, 0, 0)

    assert (
        troupe.assistant.client.patch(f"/troupes/{troupe.id}", json={"starting_xp": 40}).status_code
        == 403
    )
    changed = troupe.storyteller.client.patch(f"/troupes/{troupe.id}", json={"starting_xp": 40})
    assert changed.status_code == 200, changed.text
    assert changed.json()["starting_xp"] == 40
    assert floor_and_ceiling(troupe) == (40, 40)


def test_a_games_xp_raises_both_when_asked(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    bram = member_character(troupe, troupe.player, "Bram")

    response = troupe.assistant.client.post(
        f"/troupes/{troupe.id}/xp-awards",
        json={
            "reason": "Game, 18 October",
            "awards": [{"character_id": agnes, "amount": 8}, {"character_id": bram, "amount": 9}],
            "game_xp": 8,
        },
    )
    assert response.status_code == 201, response.text
    assert floor_and_ceiling(troupe) == (38, 38)

    troupe.assistant.client.post(
        f"/troupes/{troupe.id}/xp-awards",
        json={"reason": "Bonus", "awards": [{"character_id": agnes, "amount": 2}]},
    )
    assert floor_and_ceiling(troupe) == (38, 38)
    shown = xp_range(troupe.player, troupe)
    assert (shown["games"], shown["game_xp"]) == (1, 8)
    assert [(e["kind"], e["floor_change"], e["reason"]) for e in shown["entries"]] == [
        ("game", 8, "Game, 18 October")
    ]


def test_closing_a_downtime_raises_only_the_ceiling(troupe: Troupe) -> None:
    member_character(troupe, troupe.player, "Agnes")
    cycle = open_cycle(troupe, new_cycle(troupe))
    closed = troupe.storyteller.client.post(f"/cycles/{cycle['id']}/close")
    assert closed.status_code == 200, closed.text
    assert floor_and_ceiling(troupe) == (30, 32)

    second = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/cycles",
        json={
            "name": "November 2026",
            "closes_at": cycle["closes_at"],
            "grace_ends_at": cycle["grace_ends_at"],
        },
    ).json()
    open_cycle(troupe, second)
    left_alone = troupe.storyteller.client.post(
        f"/cycles/{second['id']}/close", json={"add_to_ceiling": False}
    )
    assert left_alone.status_code == 200, left_alone.text
    assert floor_and_ceiling(troupe) == (30, 32)
    shown = xp_range(troupe.player, troupe)
    assert (shown["downtimes"], shown["downtime_xp"]) == (1, 2)


def test_storytellers_set_either_figure_by_hand(troupe: Troupe) -> None:
    assert set_by_hand(troupe, floor=120).status_code == 422  # above the ceiling
    assert (
        troupe.assistant.client.put(
            f"/troupes/{troupe.id}/xp-range", json={"ceiling": 150, "reason": "Old chronicle"}
        ).status_code
        == 403
    )
    response = set_by_hand(troupe, floor=120, ceiling=150)
    assert response.status_code == 200, response.text
    assert (response.json()["floor"], response.json()["ceiling"]) == (120, 150)
    assert (response.json()["set_floor"], response.json()["set_ceiling"]) == (90, 120)
    assert set_by_hand(troupe, floor=120).status_code == 422  # nothing changes

    # Later games still add to a figure set by hand.
    agnes = member_character(troupe, troupe.player, "Agnes")
    troupe.assistant.client.post(
        f"/troupes/{troupe.id}/xp-awards",
        json={"reason": "Game", "awards": [{"character_id": agnes, "amount": 8}], "game_xp": 8},
    )
    assert floor_and_ceiling(troupe) == (128, 158)


# --- starting XP --------------------------------------------------------------------------


def test_a_character_built_for_a_troupe_starts_at_its_floor(troupe: Troupe) -> None:
    set_by_hand(troupe, floor=96, ceiling=110)
    character_id = built_for(troupe)
    assert history(troupe.player, character_id) == [
        ("award", 96, "Starting experience: Lords of the Night's XP floor")
    ]

    vault = new_character(troupe, troupe.player, "Bram")
    assert history(troupe.player, vault) == [("award", 30, "Starting experience")]


# --- self-entered XP ----------------------------------------------------------------------


def test_a_player_adds_xp_in_the_vault(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    assert self_enter(troupe.stranger, character_id, 10).status_code == 404
    added = self_enter(troupe.player, character_id, 10)
    assert added.status_code == 201, added.text
    assert added.json()["kind"] == "self_entered"
    assert balance(troupe.player, character_id) == 40

    # They can put a mistake right themselves while it stays in the vault.
    entry = next(
        e
        for e in troupe.player.client.get(f"/characters/{character_id}/xp").json()
        if e["kind"] == "self_entered"
    )
    assert entry["correctable"]
    corrected = troupe.player.client.post(
        f"/characters/{character_id}/xp/{entry['id']}/correction",
        json={"amount": 6, "reason": "Miscounted"},
    )
    assert corrected.status_code == 201, corrected.text
    assert balance(troupe.player, character_id) == 36

    # Not other XP, and not once a troupe is its home.
    starting = history(troupe.player, character_id)[0]
    assert starting[0] == "award"
    approval = ask_home(troupe, character_id)
    assert approve(troupe, approval).status_code == 200
    assert self_enter(troupe.player, character_id, 5).status_code == 409


@pytest.mark.usefixtures("without_bank")
def test_staff_see_self_entered_xp_apart_and_may_remove_it(troupe: Troupe) -> None:
    set_by_hand(troupe, ceiling=60)
    character_id = new_character(troupe, troupe.player)
    self_enter(troupe.player, character_id, 20, "Returning from another troupe")
    self_enter(troupe.player, character_id, 5, "Convention")

    approval = ask_home(troupe, character_id)
    assert approval["xp"] == {
        "given": 55,
        "self_entered": 25,
        "floor": 30,
        "ceiling": 60,
        "top_up_asked": True,
        "self_entered_removed": None,
        "topped_up": None,
        "above_ceiling_removed": None,
        "extra": None,
    }
    response = approve(troupe, approval, self_entered="remove")
    assert response.status_code == 200, response.text

    corrections = [h for h in history(troupe.player, character_id) if h[0] == "correction"]
    assert corrections == [
        ("correction", -20, "Self-entered XP not accepted by Lords of the Night"),
        ("correction", -5, "Self-entered XP not accepted by Lords of the Night"),
    ]
    assert balance(troupe.player, character_id) == 30
    decided = troupe.assistant.client.get(
        f"/troupes/{troupe.id}/approvals", params={"state": "approved"}
    ).json()
    assert decided[0]["xp"]["self_entered_removed"] == 25


# --- below the floor ----------------------------------------------------------------------


@pytest.mark.usefixtures("without_bank")
def test_below_the_floor_a_character_is_topped_up_when_it_joins(troupe: Troupe) -> None:
    set_by_hand(troupe, floor=100, ceiling=120)
    character_id = new_character(troupe, troupe.player)

    preview = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe/xp-preview", json={"troupe_id": troupe.id}
    )
    assert preview.json() == {"given": 30, "self_entered": 0, "floor": 100, "ceiling": 120}

    approval = ask_home(troupe, character_id)
    assert approve(troupe, approval).status_code == 200
    assert history(troupe.player, character_id)[-1] == (
        "award",
        70,
        "Top-up to Lords of the Night's XP floor of 100",
    )
    assert balance(troupe.player, character_id) == 100


@pytest.mark.usefixtures("without_bank")
def test_the_player_may_decline_the_top_up_and_staff_may_change_it(troupe: Troupe) -> None:
    set_by_hand(troupe, floor=100, ceiling=120)
    declined = new_character(troupe, troupe.player, "Agnes")
    approve(troupe, ask_home(troupe, declined, top_up=False))
    assert balance(troupe.player, declined) == 30

    overridden = new_character(troupe, troupe.player, "Bram")
    approve(troupe, ask_home(troupe, overridden), top_up=False)
    assert balance(troupe.player, overridden) == 30


def test_the_top_up_comes_after_unspent_creation_xp_is_banked(troupe: Troupe) -> None:
    set_by_hand(troupe, floor=100, ceiling=120)
    character_id = new_character(troupe, troupe.player)
    approve(troupe, ask_home(troupe, character_id))
    # 25 of the 30 unspent creation XP is lost on acceptance; all 70 of the top-up stays.
    assert balance(troupe.player, character_id) == 5 + 70


# --- above the ceiling --------------------------------------------------------------------


@pytest.mark.usefixtures("without_bank")
def test_above_the_ceiling_is_kept_unless_staff_remove_it(troupe: Troupe) -> None:
    kept = new_character(troupe, troupe.player, "Agnes")
    self_enter(troupe.player, kept, 15)
    approval = ask_home(troupe, kept)
    assert (approval["xp"]["given"], approval["xp"]["ceiling"]) == (45, 30)
    assert approve(troupe, approval).status_code == 200
    assert balance(troupe.player, kept) == 45

    capped = new_character(troupe, troupe.player, "Bram")
    self_enter(troupe.player, capped, 15)
    response = approve(troupe, ask_home(troupe, capped), above_ceiling="remove")
    assert response.status_code == 200, response.text
    assert history(troupe.player, capped)[-1] == (
        "cap",
        -15,
        "XP above Lords of the Night's ceiling of 30",
    )
    sheet = troupe.player.client.get(f"/characters/{capped}/sheet").json()["xp"]
    assert (sheet["balance"], sheet["earned"], sheet["spent"]) == (30, 30, 0)


@pytest.mark.usefixtures("without_bank")
def test_xp_already_spent_cannot_be_taken_away(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    self_enter(troupe.player, character_id, 30)
    for skill in ("Academics", "Athletics", "Awareness"):
        bought = troupe.player.client.put(
            f"/characters/{character_id}/traits",
            json={"category": "skills", "name": skill, "rating": 5},
        )
        assert bought.status_code == 200, bought.text
    spent_down_to = balance(troupe.player, character_id)
    assert spent_down_to < 30

    response = approve(troupe, ask_home(troupe, character_id), above_ceiling="remove")
    assert response.status_code == 409
    assert "spent" in response.json()["detail"]


# --- extra XP -----------------------------------------------------------------------------


@pytest.mark.usefixtures("without_bank")
def test_staff_give_extra_xp_as_a_character_joins(troupe: Troupe) -> None:
    set_by_hand(troupe, floor=50, ceiling=60)
    character_id = built_for(troupe)
    response = approve(
        troupe, ask_home(troupe, character_id), extra=12, extra_reason="Returning player"
    )
    assert response.status_code == 200, response.text
    assert history(troupe.player, character_id)[-1] == (
        "award",
        12,
        "Extra XP on joining Lords of the Night: Returning player",
    )
    assert balance(troupe.player, character_id) == 62
