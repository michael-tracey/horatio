"""Location quests and what locations give (horatio.location_quests, issue #326):
players ask to acquire, add a quality to, undermine and repair locations; staff
build the quest from the location; its success changes the location; and a
location's qualities give its controller what they say, unless a negative switches
them off."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import InfluenceEntry, Notification
from tests.api_helpers import Person, Troupe, sign_up
from tests.test_api_downtimes import member_character, my_downtime, new_cycle, open_cycle
from tests.test_api_quests import give, member_character_of, ok, quests_on


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    found = Troupe(client_for, session)
    quests_on(found, per_cycle=5)
    return found


@pytest.fixture
def agnes(troupe: Troupe) -> str:
    return member_character(troupe, troupe.player, "Agnes")


@pytest.fixture
def second(troupe: Troupe) -> Person:
    return sign_up(troupe.client_for, "second")


@pytest.fixture
def bram(troupe: Troupe, second: Person) -> str:
    return member_character_of(troupe, second, "Bram")


def location(troupe: Troupe, **body: Any) -> Any:
    return ok(troupe.storyteller.client.post(f"/troupes/{troupe.id}/locations", json=body), 201)


def read(troupe: Troupe, location_id: str) -> Any:
    return ok(troupe.storyteller.client.get(f"/locations/{location_id}"))


def ask(person: Person, character_id: str, **body: Any) -> Any:
    return person.client.post(f"/characters/{character_id}/location-requests", json=body)


def plan(troupe: Troupe, location_id: str, change: dict[str, Any], **body: Any) -> Any:
    return ok(
        troupe.storyteller.client.post(
            f"/locations/{location_id}/quest-plan", json={"change": change, **body}
        )
    )


def build(troupe: Troupe, location_id: str, change: dict[str, Any], **body: Any) -> Any:
    found = plan(
        troupe,
        location_id,
        change,
        request_id=body.get("request_id"),
        leader_id=body.get("leader_id"),
    )
    return troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/location-quests",
        json={
            "location_id": location_id,
            "change": change,
            "category": found["category"],
            "difficulty": found["difficulty"],
            "requirements": [{"options": s["options"]} for s in found["suggestions"]],
            **body,
        },
    )


def complete(troupe: Troupe, quest: dict[str, Any]) -> Any:
    ok(troupe.storyteller.client.post(f"/quests/{quest['id']}/send"))
    found = quest
    for s in quest["scenarios"]:
        found = ok(
            troupe.storyteller.client.post(
                f"/quests/{quest['id']}/scenarios/{s['number']}/result", json={"result": "passed"}
            )
        )
    return found


def held(person: Person, character_id: str) -> Any:
    return ok(person.client.get(f"/characters/{character_id}/held-locations"))


def effects(person: Person, character_id: str) -> list[tuple[str, str, bool, str]]:
    return [
        (e["quality"], e["gives"], e["on"], e["off_because"])
        for loc in held(person, character_id)["locations"]
        for e in loc["effects"]
    ]


def queue(troupe: Troupe) -> list[Any]:
    return ok(troupe.storyteller.client.get(f"/troupes/{troupe.id}/quest-requests"))


def ruby(troupe: Troupe, agnes: str) -> dict[str, Any]:
    """Ruby's Bar: asked for by Agnes's player, made a standard 2 with a Hangout, and
    acquired with a Simple 2 quest."""
    ok(
        ask(
            troupe.player,
            agnes,
            kind="acquire",
            name="Ruby's Bar",
            address="12 Main St",
            reason="Somewhere of my own",
        ),
        201,
    )
    request = queue(troupe)[0]
    matched = ok(
        troupe.storyteller.client.put(
            f"/quest-requests/{request['id']}/location",
            json={"new": {"rating": 2, "qualities": [{"name": "Hangout", "detail": "Regulars"}]}},
        )
    )
    quest = ok(
        build(
            troupe,
            matched["location"]["id"],
            {"kind": "acquire"},
            name="Ruby's Bar",
            request_id=request["id"],
        ),
        201,
    )
    complete(troupe, quest)
    return read(troupe, matched["location"]["id"])


# --- acquiring ------------------------------------------------------------------------------


def test_a_player_acquires_a_new_location(troupe: Troupe, agnes: str) -> None:
    asked = ok(
        ask(troupe.player, agnes, kind="acquire", name="Ruby's Bar", address="12 Main St"), 201
    )
    assert (asked["kind"], asked["objective"]) == ("acquire", "Acquire Ruby's Bar, 12 Main St")
    request = queue(troupe)[0]
    assert request["details"]["address"] == "12 Main St"
    assert request["can_match"] is True

    # Matched to a new standard 2, made from the request.
    matched = ok(
        troupe.storyteller.client.put(
            f"/quest-requests/{request['id']}/location",
            json={"new": {"rating": 2, "qualities": [{"name": "Hangout", "detail": "Regulars"}]}},
        )
    )
    bar = read(troupe, matched["location"]["id"])
    assert (bar["name"], bar["kind"], bar["rating"], bar["address"]) == (
        "Ruby's Bar",
        "standard",
        2,
        "12 Main St",
    )
    assert bar["control"] == "none"

    # A Simple 2, with what its Hangout suggests at rating 2.
    found = plan(troupe, bar["id"], {"kind": "acquire"}, request_id=request["id"])
    assert (found["category"], found["difficulty"], found["refusal"]) == ("simple", 2, None)
    assert [m["reason"] for m in found["modifiers"]] == ["Rating 2"]
    assert [s["label"] for s in found["suggestions"]] == [
        "Empathy 2",
        "Contacts 2 or Influences: The Elite 2 or Influences: The Underworld 2 or Allies 2",
    ]
    assert found["change"] == "control passes to its leader"

    quest = ok(
        build(troupe, bar["id"], {"kind": "acquire"}, name="Ruby's Bar", request_id=request["id"]),
        201,
    )
    assert (quest["category"], quest["difficulty"]) == ("simple", 2)
    assert quest["leader"]["name"] == "Agnes"
    assert quest["location"]["name"] == "Ruby's Bar"
    assert len(quest["requirements"]) == 2

    done = complete(troupe, quest)
    assert done["status"] == "completed"
    assert any("Ruby's Bar: Agnes controls it now" in e["text"] for e in done["log"])
    bar = read(troupe, bar["id"])
    assert bar["controller"] == {"id": agnes, "name": "Agnes"}
    assert any("was completed for Ruby's Bar" in e["message"] for e in bar["log"])

    # Its player sees its name, and what its Hangout gives.
    mine = held(troupe.player, agnes)
    assert [loc["name"] for loc in mine["locations"]] == ["Ruby's Bar"]
    assert effects(troupe.player, agnes) == [("Hangout", "Contacts 1 (Regulars)", True, "")]


def test_a_request_is_matched_only_by_those_who_keep_locations(troupe: Troupe, agnes: str) -> None:
    ok(ask(troupe.player, agnes, kind="acquire", name="Ruby's Bar"), 201)
    request = queue(troupe)[0]
    ok(
        troupe.storyteller.client.put(
            f"/quest-requests/{request['id']}/assignment", json={"any_narrator": True}
        )
    )
    refused = troupe.narrator.client.put(
        f"/quest-requests/{request['id']}/location", json={"new": {"rating": 1}}
    )
    assert refused.status_code == 403
    seen = ok(troupe.narrator.client.get(f"/troupes/{troupe.id}/quest-requests"))[0]
    assert (seen["can_match"], seen["location"]) == (False, None)


# --- adding a quality -----------------------------------------------------------------------


def test_adding_profitable_raises_the_rating_and_gives_resources(
    troupe: Troupe, agnes: str
) -> None:
    bar = ruby(troupe, agnes)
    choices = held(troupe.player, agnes)["qualities"]
    assert "Profitable" in [q["name"] for q in choices]

    asked = ok(
        ask(troupe.player, agnes, kind="quality", location_id=bar["id"], quality="Profitable"), 201
    )
    assert asked["objective"] == "Add Profitable to Ruby's Bar"
    request = next(r for r in queue(troupe) if r["kind"] == "quality")
    assert request["location"]["name"] == "Ruby's Bar"

    change = {"kind": "quality", "quality": "Profitable"}
    found = plan(troupe, bar["id"], change, request_id=request["id"])
    assert (found["category"], found["difficulty"]) == ("simple", 2)
    assert "Leadership 2" in [s["label"] for s in found["suggestions"]]
    quest = ok(build(troupe, bar["id"], change, name="Profit", request_id=request["id"]), 201)
    complete(troupe, quest)

    bar = read(troupe, bar["id"])
    assert [q["name"] for q in bar["qualities"]] == ["Hangout", "Profitable"]
    assert bar["rating"] == 3
    assert ("Profitable", "Resources 1", True, "") in effects(troupe.player, agnes)


def test_a_quality_is_asked_only_for_the_characters_own_location(
    troupe: Troupe, agnes: str, bram: str, second: Person
) -> None:
    bar = ruby(troupe, agnes)
    refused = ask(second, bram, kind="quality", location_id=bar["id"], quality="Profitable")
    assert refused.status_code == 422
    assert refused.json()["detail"] == "Choose one of Bram's locations."


# --- undermining and repairing --------------------------------------------------------------


def test_insolvent_switches_profitable_off_and_a_repair_brings_it_back(
    troupe: Troupe, agnes: str, bram: str, second: Person, session: Session
) -> None:
    bar = ruby(troupe, agnes)
    ok(
        troupe.storyteller.client.patch(
            f"/locations/{bar['id']}",
            json={
                "qualities": [{"name": "Hangout", "detail": "Regulars"}, {"name": "Profitable"}],
                "rating": 3,
            },
        )
    )

    # Bram's player asks to make it Insolvent; staff match his request to the record.
    asked = ok(
        ask(
            second,
            bram,
            kind="undermine",
            name="Ruby's",
            address="12 Main St",
            negative="Insolvent",
        ),
        201,
    )
    assert asked["objective"] == "Undermine Ruby's, 12 Main St: Insolvent"
    request = next(r for r in queue(troupe) if r["kind"] == "undermine")
    ok(
        troupe.storyteller.client.put(
            f"/quest-requests/{request['id']}/location", json={"location_id": bar["id"]}
        )
    )
    change = {"kind": "negative", "negative": "Insolvent", "secret": True}
    found = plan(troupe, bar["id"], change, request_id=request["id"])
    assert (found["category"], found["difficulty"]) == ("simple", 3)
    quest = ok(build(troupe, bar["id"], change, name="Bad debts", request_id=request["id"]), 201)
    complete(troupe, quest)

    bar = read(troupe, bar["id"])
    assert [(n["name"], n["level"], n["secret"], n["by"]) for n in bar["negatives"]] == [
        ("Insolvent", 1, True, "Bram")
    ]
    # Agnes's player sees the Resources switched off, not why; staff see why.
    assert ("Profitable", "Resources 1", False, "") in effects(troupe.player, agnes)
    assert ("Profitable", "Resources 1", False, "Insolvent ×1") in effects(
        troupe.storyteller, agnes
    )

    # Her player asks to repair it; staff remove Insolvent for an Elite 3 action of hers.
    asked = ok(ask(troupe.player, agnes, kind="repair", location_id=bar["id"]), 201)
    assert asked["objective"] == "Repair Ruby's Bar"
    repair = next(r for r in queue(troupe) if r["kind"] == "repair")
    removing = {"name": "Insolvent", "character_id": agnes, "request_id": repair["id"]}
    short = troupe.storyteller.client.post(
        f"/locations/{bar['id']}/negatives/remove", json=removing
    )
    assert short.status_code == 409
    assert short.json()["detail"] == (
        "Removing Insolvent takes Expend Elite 3, which Agnes can't take."
    )
    give(session, agnes, "backgrounds", "Influences: The Elite", 3)
    bar = ok(
        troupe.storyteller.client.post(f"/locations/{bar['id']}/negatives/remove", json=removing)
    )
    assert bar["negatives"] == []
    assert any(
        "removed Insolvent ×1 from Ruby's Bar: Elite 3 from Agnes" in e["message"]
        for e in bar["log"]
    )
    entry = session.scalars(
        select(InfluenceEntry).where(InfluenceEntry.purpose.like("%Ruby's Bar%"))
    ).one()
    assert entry.purpose == "To remove Insolvent from Ruby's Bar"
    assert ("Profitable", "Resources 1", True, "") in effects(troupe.player, agnes)
    mine = ok(troupe.player.client.get(f"/characters/{agnes}/quests"))
    answered = next(r for r in mine["requests"] if r["kind"] == "repair")
    assert (answered["status"], answered["outcome"], answered["note"]) == (
        "answered",
        "done",
        "Ruby's Bar is repaired.",
    )


def test_an_infiltration_records_its_victory_and_guards_add_one(
    troupe: Troupe, agnes: str, bram: str, second: Person
) -> None:
    hall = location(troupe, name="Guild Hall", rating=3, qualities=[{"name": "Guards"}])
    asked = ok(
        ask(second, bram, kind="undermine", name="Guild Hall", victory="Steal the ledger"), 201
    )
    assert asked["objective"] == "Infiltrate Guild Hall: Steal the ledger"
    change = {"kind": "infiltrate", "victory": "Steal the ledger"}
    found = plan(troupe, hall["id"], change, leader_id=bram)
    assert found["difficulty"] == 4
    assert [m["reason"] for m in found["modifiers"]] == ["Rating 3", "Guards +1"]
    quest = ok(build(troupe, hall["id"], change, name="The ledger", leader_id=bram), 201)
    done = complete(troupe, quest)
    assert any("the party achieves its goal: Steal the ledger" in e["text"] for e in done["log"])


# --- difficulty and refusals ----------------------------------------------------------------


def test_historic_adds_one_to_taking_control(troupe: Troupe, agnes: str) -> None:
    hall = location(troupe, name="Old Courthouse", rating=2, qualities=[{"name": "Historic"}])
    found = plan(troupe, hall["id"], {"kind": "acquire"}, leader_id=agnes)
    assert found["difficulty"] == 3
    assert [(m["reason"], m["amount"]) for m in found["modifiers"]] == [
        ("Rating 2", 2),
        ("Historic +1", 1),
    ]
    # Only to taking control: not to adding a quality.
    assert plan(troupe, hall["id"], {"kind": "negative", "negative": "Damaged"})["difficulty"] == 2


def test_a_prestige_location_takes_a_complex_quest_and_an_iconic_one_epic(troupe: Troupe) -> None:
    prestige = location(troupe, name="Opera House", kind="prestige", rating=3)
    assert plan(troupe, prestige["id"], {"kind": "acquire"})["category"] == "complex"
    upgrade = plan(troupe, prestige["id"], {"kind": "upgrade"})
    assert (upgrade["category"], upgrade["category_note"]) == (
        "epic",
        "The book's Heroic quest is Epic here.",
    )
    iconic = location(troupe, name="Cathedral", kind="iconic", rating=3)
    assert plan(troupe, iconic["id"], {"kind": "upgrade"})["refusal"] == (
        "An iconic location can't be upgraded further (Vol. II Issue 1, p. 126)."
    )


def test_a_locked_location_cant_be_targeted(troupe: Troupe, agnes: str) -> None:
    vault = location(troupe, name="The Vault", rating=2, locked=True)
    assert plan(troupe, vault["id"], {"kind": "acquire"}, leader_id=agnes)["refusal"] == (
        "The Vault is locked: no quest may target it."
    )
    refused = build(troupe, vault["id"], {"kind": "acquire"}, name="Vault", leader_id=agnes)
    assert refused.status_code == 409
    assert refused.json()["detail"] == "The Vault is locked: no quest may target it."


def test_a_controlled_location_is_acquired_only_once_insolvent_three_times(
    troupe: Troupe, agnes: str, bram: str
) -> None:
    bar = ruby(troupe, agnes)
    found = plan(troupe, bar["id"], {"kind": "acquire"}, leader_id=bram)
    assert found["refusal"] == (
        "Ruby's Bar is controlled by Agnes: it must be undermined first (Vol. II Issue 1, p. "
        "121). Insolvent ×3 opens it to anyone, with a Complex quest (Vol. II Issue 1, p. 128)."
    )
    ok(
        troupe.storyteller.client.patch(
            f"/locations/{bar['id']}", json={"negatives": [{"name": "Insolvent", "level": 3}]}
        )
    )
    found = plan(troupe, bar["id"], {"kind": "acquire"}, leader_id=bram)
    assert (found["refusal"], found["category"]) == (None, "complex")
    assert found["category_note"].startswith("Insolvent ×3: anyone may take it")

    quest = ok(
        build(troupe, bar["id"], {"kind": "acquire"}, name="Foreclosure", leader_id=bram), 201
    )
    complete(troupe, quest)
    assert read(troupe, bar["id"])["controller"]["name"] == "Bram"
    # Agnes's player is told, without the record.
    told = ok(troupe.player.client.get("/notifications"))
    items = told["items"] if isinstance(told, dict) else told
    assert "Your character no longer controls Ruby's Bar." in [i["summary"] for i in items]
    assert held(troupe.player, agnes)["locations"] == []


# --- negatives acting on their own ----------------------------------------------------------


def test_out_of_code_gets_worse_after_two_games_and_staff_are_told(
    troupe: Troupe, agnes: str, session: Session
) -> None:
    bar = location(
        troupe,
        name="Ruby's Bar",
        rating=2,
        negatives=[{"name": "Out of Code", "level": 1}],
    )

    def game() -> None:
        ok(
            troupe.lead.client.post(
                f"/troupes/{troupe.id}/xp-awards",
                json={
                    "reason": "Game",
                    "awards": [{"character_id": agnes, "amount": 1}],
                    "game_xp": 1,
                },
            ),
            201,
        )

    game()
    found = read(troupe, bar["id"])
    assert [(n["level"], n["games"]) for n in found["negatives"]] == [(1, 1)]
    told = session.scalars(
        select(Notification.summary).where(Notification.kind == "location.out_of_code")
    ).all()
    assert "Out of Code on Ruby's Bar goes to ×2 after the next game unless it is removed." in told

    # Editing the location keeps the count.
    ok(troupe.storyteller.client.patch(f"/locations/{bar['id']}", json={"notes": "Watch it"}))
    game()
    found = read(troupe, bar["id"])
    assert [(n["level"], n["games"]) for n in found["negatives"]] == [(2, 0)]
    told = session.scalars(
        select(Notification.summary).where(Notification.kind == "location.out_of_code")
    ).all()
    assert "Out of Code on Ruby's Bar is now ×2: two games passed without it being removed." in told


def test_insolvent_twice_makes_it_forfeit_when_the_rating_is_above_resources(
    troupe: Troupe, agnes: str
) -> None:
    bar = ruby(troupe, agnes)
    found = ok(
        troupe.storyteller.client.patch(
            f"/locations/{bar['id']}", json={"negatives": [{"name": "Insolvent", "level": 2}]}
        )
    )
    assert found["forfeit"] == (
        "Insolvent ×2: Ruby's Bar's rating 2 is above Agnes's Resources 0, so it is forfeit "
        "(Vol. II Issue 1, p. 128)."
    )
    found = ok(troupe.storyteller.client.post(f"/locations/{bar['id']}/forfeit"))
    assert (found["control"], found["controller"], found["forfeit"]) == ("none", None, None)


def test_damaged_switches_off_what_staff_choose(troupe: Troupe, agnes: str) -> None:
    bar = location(
        troupe,
        name="Ruby's Bar",
        rating=2,
        qualities=[{"name": "Profitable"}, {"name": "Hangout", "detail": "Regulars"}],
        control="character",
        controller_id=agnes,
        negatives=[{"name": "Damaged", "level": 1}],
        damaged_off=["Hangout"],
    )
    assert bar["damaged_off"] == ["Hangout"]
    assert effects(troupe.storyteller, agnes) == [
        ("Profitable", "Resources 1", True, ""),
        ("Hangout", "Contacts 1 (Regulars)", False, "Damaged ×1"),
    ]


# --- Fancy in the allowance -----------------------------------------------------------------


def test_fancy_gives_an_elite_action_in_the_next_cycle(troupe: Troupe, agnes: str) -> None:
    location(
        troupe,
        name="The Gala",
        rating=4,
        qualities=[{"name": "Fancy"}],
        control="character",
        controller_id=agnes,
    )
    open_cycle(troupe, new_cycle(troupe))
    mine = my_downtime(troupe.player, agnes).json()
    assert mine["allowance"]["influence_elite"] == 1
    assert {
        "action_kind": "influence_elite",
        "source": "The Gala (Fancy)",
        "amount": 1,
        "note": "",
    } in mine["breakdown"]


def test_shunned_switches_fancy_off_for_the_cycle(troupe: Troupe, agnes: str) -> None:
    location(
        troupe,
        name="The Gala",
        rating=4,
        qualities=[{"name": "Fancy"}],
        control="character",
        controller_id=agnes,
        negatives=[{"name": "Shunned", "level": 1, "secret": True}],
    )
    open_cycle(troupe, new_cycle(troupe))
    mine = my_downtime(troupe.player, agnes).json()
    assert mine["allowance"]["influence_elite"] == 0
    assert {
        "action_kind": "influence_elite",
        "source": "The Gala (Fancy)",
        "amount": 0,
        "note": "Not available this cycle.",
    } in mine["breakdown"]


# --- the Resources shortcut and Contacts ----------------------------------------------------


def test_resources_over_the_difficulty_give_more_successes(
    troupe: Troupe, agnes: str, session: Session
) -> None:
    hall = location(troupe, name="Medical Centre", rating=3)
    quest = ok(
        build(
            troupe,
            hall["id"],
            {"kind": "acquire"},
            name="Clinic",
            leader_id=agnes,
            requirements=[{"options": [{"kind": "text", "text": "A willing seller"}]}],
        ),
        201,
    )
    ok(troupe.storyteller.client.post(f"/quests/{quest['id']}/send"))
    url = f"/quests/{quest['id']}/scenarios/1/resources"
    give(session, agnes, "backgrounds", "Resources", 5)
    short = troupe.storyteller.client.post(url, json={"character_id": agnes, "dots": 2})
    assert short.status_code == 422
    found = ok(troupe.storyteller.client.post(url, json={"character_id": agnes, "dots": 5}))
    assert found["scenarios"][0]["resources"] == [
        {"character_id": agnes, "name": "Agnes", "dots": 5, "successes": 3}
    ]


def test_contacts_learns_whose_locations_are_whose(
    troupe: Troupe, agnes: str, bram: str, second: Person, session: Session
) -> None:
    ruby(troupe, agnes)
    location(
        troupe,
        name="The Cellar",
        rating=1,
        qualities=[{"name": "Hole in the Wall"}],
        control="character",
        controller_id=agnes,
    )
    refused = ask(second, bram, kind="whose", target="Agnes")
    assert refused.status_code == 409
    give(session, bram, "backgrounds", "Contacts", 1)
    ok(ask(second, bram, kind="whose", target="Agnes"), 201)
    request = next(r for r in queue(troupe) if r["kind"] == "whose")
    assert request["whose"] == [
        {
            "name": "Agnes",
            "locations": [
                "Ruby's Bar",
                "The Cellar (Hole in the Wall: only if they have been there)",
            ],
        }
    ]
    answered = ok(
        troupe.storyteller.client.post(
            f"/quest-requests/{request['id']}/answer",
            json={"outcome": "done", "note": "Agnes controls Ruby's Bar."},
        )
    )
    assert answered["outcome"] == "done"
