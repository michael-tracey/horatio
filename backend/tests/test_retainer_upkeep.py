"""Retainer upkeep and growth (issue #442): house rules, each off unless the troupe
switches it on. Upkeep is taken as a night begins, a game or a month, or charged at a
downtime's close; a Retainer the character can't pay for is neglected and staff are
told; growth gives XP as a cycle closes; a lost Retainer pays and gains nothing."""

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import AuditEvent, Character, RetainerGrowth
from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_checkin import check_in, game, open_checkin, send, tap, view
from tests.test_api_downtimes import new_cycle, open_cycle
from tests.test_api_retainers import give_retainers, make_npc, put, with_both


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


MARTA = "Marta, the driver"
GAME = {"amount": 1, "pool": "blood", "per": "game"}


def set_rules(troupe: Troupe, **body: Any) -> dict[str, Any]:
    response = troupe.storyteller.client.put(f"/troupes/{troupe.id}/retainer-rules", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def listed(person: Person, character_id: str) -> dict[str, dict[str, Any]]:
    response = person.client.get(f"/characters/{character_id}/retainers")
    assert response.status_code == 200, response.text
    return {r["name"]: r for r in response.json()["retainers"]}


def save(person: Person, character_id: str, **changes: dict[str, Any]) -> None:
    """Keep the list as it is, with these changes to each Retainer by name."""
    rows = [
        {
            "id": r["id"],
            "name": r["name"],
            "dots": r["dots"],
            "ghoul": r["ghoul"],
            "npc_id": r["npc_id"],
            "lost": r["lost"],
            "lost_on": r["lost_on"],
        }
        | changes.get(r["name"], {})
        for r in listed(person, character_id).values()
    ]
    response = put(person, character_id, rows)
    assert response.status_code == 200, response.text


def tonight(troupe: Troupe, character_id: str) -> None:
    """Check the character in at tonight's game, which begins its night."""
    game_id = game(troupe)
    open_checkin(troupe, game_id)
    response = check_in(troupe.player, troupe, game_id, character_id)
    assert response.status_code == 200, response.text


def upkeep_lines(person: Person, character_id: str) -> list[str]:
    return [e["text"] for e in view(person, character_id)["log"] if e["upkeep"]]


def next_night(troupe: Troupe, character_id: str) -> None:
    """End the night and begin the next with a tap of Willpower."""
    played = view(troupe.player, character_id)
    reset = troupe.player.client.post(
        f"/characters/{character_id}/play/reset", json={"game_id": played["game"]["id"]}
    )
    assert reset.status_code == 200, reset.text
    send(troupe.player, character_id, tap("willpower", -1, datetime.now(UTC)))


def close(troupe: Troupe, cycle: dict[str, Any]) -> None:
    response = troupe.storyteller.client.post(f"/cycles/{cycle['id']}/close")
    assert response.status_code == 200, response.text


def actions(session: Session, troupe: Troupe) -> list[str]:
    return list(
        session.scalars(
            select(AuditEvent.action)
            .where(AuditEvent.troupe_id == uuid.UUID(troupe.id))
            .order_by(AuditEvent.created_at, AuditEvent.id)
        )
    )


def test_with_both_rules_off_nothing_changes(troupe: Troupe, session: Session) -> None:
    character_id = with_both(troupe)
    start = view(troupe.player, character_id)["blood"]["start"]

    tonight(troupe, character_id)
    close(troupe, open_cycle(troupe, new_cycle(troupe)))

    played = view(troupe.player, character_id)
    assert played["log"] == []
    assert played["blood"]["value"] == start
    shown = listed(troupe.player, character_id)
    assert [(r["upkeep"], r["neglected_on"], r["banked_xp"]) for r in shown.values()] == [
        (None, None, 0),
        (None, None, 0),
    ]
    assert session.scalars(select(RetainerGrowth)).all() == []
    rules = troupe.player.client.get(f"/troupes/{troupe.id}/retainer-rules").json()
    assert (rules["upkeep"], rules["growth"]) == (None, None)


def test_a_games_upkeep_is_taken_as_the_night_starts_at_check_in(
    troupe: Troupe, session: Session
) -> None:
    character_id = with_both(troupe)
    start = view(troupe.player, character_id)["blood"]["start"]
    rules = set_rules(troupe, upkeep=GAME)
    assert rules["upkeep_text"] == "1 Blood for each Retainer a game, taken as the night starts"

    tonight(troupe, character_id)

    played = view(troupe.player, character_id)
    assert upkeep_lines(troupe.player, character_id) == [
        f"Retainer upkeep: −2 Blood ({MARTA}, Pike)"
    ]
    assert played["blood"]["value"] == start - 2
    assert [r["upkeep"] for r in listed(troupe.player, character_id).values()] == [
        "1 Blood a game",
        "1 Blood a game",
    ]
    # Each night takes it again.
    next_night(troupe, character_id)
    assert upkeep_lines(troupe.player, character_id) == [
        f"Retainer upkeep: −2 Blood ({MARTA}, Pike)"
    ]
    assert view(troupe.player, character_id)["game"]["number"] == 2
    # The House rules tab shows it, and the troupe's log has the change.
    house = troupe.player.client.get(f"/troupes/{troupe.id}/house-rules").json()["other"]
    assert {
        "name": "Retainer upkeep",
        "text": rules["upkeep_text"],
        "book_text": "No upkeep",
        "table": None,
    } in (house)
    assert "house.retainer_rules" in actions(session, troupe)


def test_a_games_upkeep_is_taken_at_the_first_tap_without_check_in(troupe: Troupe) -> None:
    character_id = with_both(troupe)
    start = view(troupe.player, character_id)["blood"]["start"]
    set_rules(troupe, upkeep=GAME)

    send(troupe.player, character_id, tap("blood", -1, datetime.now(UTC)))
    send(troupe.player, character_id, tap("blood", -1, datetime.now(UTC)))

    played = view(troupe.player, character_id)
    # Before the night's first tap, and only once.
    assert [e["text"] for e in played["log"]] == [
        f"Blood {start - 3} → {start - 4}",
        f"Blood {start - 2} → {start - 3}",
        f"Retainer upkeep: −2 Blood ({MARTA}, Pike)",
    ]
    assert played["blood"]["value"] == start - 4


def test_a_night_begun_before_upkeep_was_switched_on_takes_none(troupe: Troupe) -> None:
    character_id = with_both(troupe)
    send(troupe.player, character_id, tap("blood", -1, datetime.now(UTC)))

    set_rules(troupe, upkeep=GAME)
    send(troupe.player, character_id, tap("blood", -1, datetime.now(UTC)))

    assert upkeep_lines(troupe.player, character_id) == []


def test_only_ghoul_retainers_pay_when_the_troupe_says_so(troupe: Troupe) -> None:
    character_id = with_both(troupe)
    save(troupe.player, character_id, **{MARTA: {"ghoul": True}})
    set_rules(troupe, upkeep=GAME | {"ghouls_only": True, "amount": 2})

    tonight(troupe, character_id)

    assert upkeep_lines(troupe.player, character_id) == [f"Retainer upkeep: −2 Blood ({MARTA})"]
    shown = listed(troupe.player, character_id)
    assert (shown[MARTA]["upkeep"], shown["Pike"]["upkeep"]) == ("2 Blood a game", None)


def test_a_lost_retainer_pays_no_upkeep_and_gains_nothing(troupe: Troupe) -> None:
    character_id = with_both(troupe)
    save(troupe.player, character_id, Pike={"lost": "released", "lost_on": str(date.today())})
    set_rules(troupe, upkeep=GAME, growth=4)

    tonight(troupe, character_id)
    close(troupe, open_cycle(troupe, new_cycle(troupe)))

    assert upkeep_lines(troupe.player, character_id) == [f"Retainer upkeep: −1 Blood ({MARTA})"]
    shown = listed(troupe.player, character_id)
    assert (shown[MARTA]["banked_xp"], shown["Pike"]["banked_xp"]) == (4, 0)
    assert shown["Pike"]["upkeep"] is None


def test_a_retainer_the_character_cant_pay_for_is_neglected_and_staff_are_told(
    troupe: Troupe, session: Session
) -> None:
    character_id = with_both(troupe)
    # Characters start the game with 1 Blood here.
    response = troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/starting-blood", json={"blood": 1}
    )
    assert response.status_code == 200, response.text
    set_rules(troupe, upkeep=GAME)

    tonight(troupe, character_id)

    played = view(troupe.player, character_id)
    assert [e["text"] for e in played["log"]] == [
        "Retainer upkeep not paid: Pike neglected",
        f"Retainer upkeep: −1 Blood ({MARTA})",
    ]
    assert played["blood"]["value"] == 0
    shown = listed(troupe.player, character_id)
    assert shown["Pike"]["neglected_on"] == str(date.today())
    assert shown[MARTA]["neglected_on"] is None
    # Nothing is lost by itself.
    assert shown["Pike"]["lost"] is None
    told = troupe.lead.client.get("/notifications").json()["items"]
    name = played["character_name"]
    assert [n["summary"] for n in told if n["kind"] == "retainer.neglected"] == [
        f"{name} couldn't pay 1 Blood upkeep for Pike: neglected"
    ]
    assert "retainer.neglected" in actions(session, troupe)

    # Staff alone clear the mark.
    pike = shown["Pike"]["id"]
    path = f"/characters/{character_id}/retainers/{pike}/neglected"
    assert troupe.player.client.delete(path).status_code == 403
    cleared = troupe.storyteller.client.delete(path)
    assert cleared.status_code == 200, cleared.text
    assert listed(troupe.player, character_id)["Pike"]["neglected_on"] is None


def test_willpower_upkeep_the_character_cant_meet_neglects_each_retainer(troupe: Troupe) -> None:
    character_id = with_both(troupe)
    willpower = view(troupe.player, character_id)["willpower"]["start"]
    set_rules(troupe, upkeep={"amount": willpower, "pool": "willpower"})

    tonight(troupe, character_id)

    assert upkeep_lines(troupe.player, character_id) == [
        "Retainer upkeep not paid: Pike neglected",
        f"Retainer upkeep: −{willpower} Willpower ({MARTA})",
    ]
    assert view(troupe.player, character_id)["willpower"]["value"] == 0


def test_a_months_upkeep_is_taken_at_the_months_first_game_only(troupe: Troupe) -> None:
    character_id = with_both(troupe)
    set_rules(troupe, upkeep={"amount": 1, "pool": "willpower", "per": "month"})

    tonight(troupe, character_id)
    assert upkeep_lines(troupe.player, character_id) == [
        f"Retainer upkeep: −2 Willpower ({MARTA}, Pike)"
    ]

    next_night(troupe, character_id)
    assert upkeep_lines(troupe.player, character_id) == []


def test_a_months_upkeep_as_a_downtime_cost_is_charged_at_the_close_and_taken_next_game(
    troupe: Troupe, session: Session
) -> None:
    character_id = with_both(troupe)
    start = view(troupe.player, character_id)["blood"]["start"]
    rules = set_rules(
        troupe, upkeep={"amount": 1, "pool": "blood", "per": "month", "month_at": "downtime"}
    )
    assert rules["upkeep_text"] == (
        "1 Blood for each Retainer a month, charged as a downtime cycle closes and taken"
        " at the next game"
    )

    close(troupe, open_cycle(troupe, new_cycle(troupe)))
    assert "retainer.upkeep_charged" in actions(session, troupe)
    assert view(troupe.player, character_id)["log"] == []

    tonight(troupe, character_id)
    assert upkeep_lines(troupe.player, character_id) == [
        f"Retainer upkeep: −2 Blood ({MARTA}, Pike)"
    ]
    assert view(troupe.player, character_id)["blood"]["value"] == start - 2
    # Taken once.
    next_night(troupe, character_id)
    assert upkeep_lines(troupe.player, character_id) == []


def test_growth_goes_to_the_linked_npc_or_is_banked_once_a_month(
    troupe: Troupe, session: Session
) -> None:
    character_id = with_both(troupe)
    npc_id = make_npc(troupe)
    save(troupe.storyteller, character_id, **{MARTA: {"npc_id": npc_id}})
    rules = set_rules(troupe, growth=4)
    assert rules["growth_text"] == (
        "4 XP a month for each Retainer, given as a downtime cycle closes"
    )

    close(troupe, open_cycle(troupe, new_cycle(troupe)))

    shown = listed(troupe.storyteller, character_id)
    assert (shown[MARTA]["banked_xp"], shown["Pike"]["banked_xp"]) == (0, 4)
    assert shown[MARTA]["npc_xp"] == 4
    npc_xp = troupe.storyteller.client.get(f"/characters/{npc_id}/xp").json()
    assert [(e["reason"], e["amount"]) for e in npc_xp if e["kind"] == "award"] == [
        ("Retainer growth: October 2026", 4)
    ]
    assert actions(session, troupe).count("retainer.grew") == 2
    # Another cycle closing in the same month gives nothing more.
    close(troupe, open_cycle(troupe, new_cycle(troupe, closes_in=timedelta(days=8))))
    assert listed(troupe.storyteller, character_id)["Pike"]["banked_xp"] == 4
    assert len(session.scalars(select(RetainerGrowth)).all()) == 2


def test_a_character_removed_from_the_cycle_pays_no_upkeep_and_gains_nothing(
    troupe: Troupe, session: Session
) -> None:
    taking_part = with_both(troupe)
    removed = new_character(troupe, troupe.player, "Bertha")
    request = troupe.player.client.post(
        f"/characters/{removed}/home-troupe", json={"troupe_id": troupe.id}
    ).json()
    troupe.lead.client.post(f"/approvals/{request['id']}/approve", json={})
    give_retainers(troupe, removed, 2, "Old Tom")
    set_rules(
        troupe,
        upkeep={"amount": 1, "pool": "blood", "per": "month", "month_at": "downtime"},
        growth=4,
    )
    cycle = open_cycle(troupe, new_cycle(troupe))
    participants = troupe.storyteller.client.get(f"/cycles/{cycle['id']}/participants").json()
    [participant] = [p for p in participants if p["character_id"] == removed]
    taken_out = troupe.storyteller.client.delete(
        f"/cycles/{cycle['id']}/participants/{participant['id']}"
    )
    assert taken_out.status_code == 204, taken_out.text

    close(troupe, cycle)

    def kept(character_id: str) -> Any:
        return session.scalar(
            select(Character.upkeep_next_game).where(Character.id == uuid.UUID(character_id))
        )

    assert kept(taking_part) == {
        "charges": [{"pool": "blood", "amount": 2, "retainers": [MARTA, "Pike"]}]
    }
    assert kept(removed) is None
    assert actions(session, troupe).count("retainer.upkeep_charged") == 1
    assert listed(troupe.storyteller, taking_part)["Pike"]["banked_xp"] == 4
    assert listed(troupe.storyteller, removed)["Old Tom"]["banked_xp"] == 0
    assert actions(session, troupe).count("retainer.grew") == 2
    assert len(session.scalars(select(RetainerGrowth)).all()) == 2


def test_only_staff_set_the_rules_and_they_are_checked(troupe: Troupe) -> None:
    path = f"/troupes/{troupe.id}/retainer-rules"
    assert troupe.player.client.put(path, json={"growth": 4}).status_code == 403
    assert troupe.storyteller.client.put(path, json={"growth": 0}).status_code == 422
    refused = troupe.storyteller.client.put(path, json={"upkeep": {"amount": 1, "pool": "rage"}})
    assert refused.status_code == 422
    # A game's upkeep keeps no "month" choice.
    kept = set_rules(troupe, upkeep=GAME | {"month_at": "downtime"})
    assert kept["upkeep"]["month_at"] == "game"
