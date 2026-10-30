"""Quests (horatio.quests, issue #323): a troupe turns them on and limits requests;
players request, share and join; staff build, check, spend, send and close them."""

import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import delivery
from horatio.connectors import CONNECTORS
from horatio.models import (
    CharacterTrait,
    InfluenceEntry,
    Notification,
    OwedAction,
    RuleSet,
    TraitCategory,
    TraitDefinition,
)
from tests.api_helpers import Person, Troupe, new_character, sign_up
from tests.test_api_downtimes import member_character, new_cycle
from tests.test_delivery_connectors import START, FakeConnector


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def fake() -> Iterator[FakeConnector]:
    connector = FakeConnector()
    real = CONNECTORS.get("discord")
    CONNECTORS["discord"] = connector
    yield connector
    if real is not None:
        CONNECTORS["discord"] = real


def give(
    session: Session,
    character_id: str,
    category: str,
    name: str,
    rating: int | None,
    detail: str = "",
) -> None:
    """Put a trait straight on the sheet, as if bought long ago."""
    definition = session.scalars(
        select(TraitDefinition)
        .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
        .join(RuleSet, TraitCategory.rule_set_id == RuleSet.id)
        .where(
            RuleSet.splat == "vampire", TraitCategory.key == category, TraitDefinition.name == name
        )
    ).one()
    session.add(
        CharacterTrait(
            character_id=uuid.UUID(character_id),
            trait_definition_id=definition.id,
            rating=rating,
            detail=detail,
        )
    )
    session.flush()


def ok(response: Any, code: int = 200) -> Any:
    assert response.status_code == code, response.text
    return response.json()


def quests_on(troupe: Troupe, per_cycle: int = 1) -> None:
    ok(
        troupe.storyteller.client.put(
            f"/troupes/{troupe.id}/quest-settings",
            json={"enabled": True, "requests_per_cycle": per_cycle},
        )
    )


def ask(person: Person, character_id: str, objective: str = "Find Miles' journal") -> Any:
    return person.client.post(
        f"/characters/{character_id}/quest-requests",
        json={"objective": objective, "reason": "To learn who sired him", "companions": "Bram"},
    )


def mine(person: Person, character_id: str) -> Any:
    return ok(person.client.get(f"/characters/{character_id}/quests"))


def queue(person: Person, troupe: Troupe, show: str = "open") -> Any:
    return ok(person.client.get(f"/troupes/{troupe.id}/quest-requests", params={"show": show}))


def tasks(person: Person) -> list[str]:
    found = ok(person.client.get("/notifications"))
    items = found["items"] if isinstance(found, dict) else found
    return [i["summary"] for i in items if i["task"] and i["kind"] == "quest_request"]


def build(troupe: Troupe, **body: Any) -> Any:
    return ok(troupe.storyteller.client.post(f"/troupes/{troupe.id}/quests", json=body), 201)


def requirement(troupe: Troupe, quest_id: str, *options: dict[str, Any]) -> Any:
    return ok(
        troupe.storyteller.client.post(
            f"/quests/{quest_id}/requirements", json={"options": list(options)}
        ),
        201,
    )


MEDICINE = {"kind": "trait", "category": "skills", "name": "Medicine", "rating": 3}
SCIENCE = {
    "kind": "trait",
    "category": "skills",
    "name": "Science",
    "rating": 1,
    "specialization": "Biology",
}
ELITE_6 = {"kind": "influence", "type": "elite", "level": 6, "area": "High Society"}


@pytest.fixture
def agnes(troupe: Troupe) -> str:
    return member_character(troupe, troupe.player, "Agnes")


# --- the troupe's settings ----------------------------------------------------------------


def test_storytellers_turn_quests_on_and_set_the_limit(troupe: Troupe) -> None:
    url = f"/troupes/{troupe.id}/quest-settings"
    body = {"enabled": True, "requests_per_cycle": 2}
    assert troupe.assistant.client.put(url, json=body).status_code == 403
    assert troupe.player.client.put(url, json=body).status_code == 403

    found = ok(troupe.storyteller.client.put(url, json=body))

    assert (found["quests_enabled"], found["quest_requests_per_cycle"]) == (True, 2)
    log = ok(troupe.lead.client.get(f"/troupes/{troupe.id}/log"))
    assert log[0]["message"] == "storyteller turned quests on (2 requests a cycle)."


def test_with_quests_off_players_see_nothing_and_cannot_ask(troupe: Troupe, agnes: str) -> None:
    found = mine(troupe.player, agnes)

    assert (found["enabled"], found["requests"], found["quests"]) == (False, [], [])
    refused = ask(troupe.player, agnes)
    assert refused.status_code == 409
    assert "does not run quests" in refused.json()["detail"]


# --- requests -----------------------------------------------------------------------------


def test_a_second_request_in_the_cycle_is_refused_with_the_reason(
    troupe: Troupe, agnes: str
) -> None:
    quests_on(troupe)
    new_cycle(troupe)

    made = ok(ask(troupe.player, agnes), 201)
    refused = ask(troupe.player, agnes, "Something else")

    assert made["status"] == "waiting"
    assert refused.status_code == 409
    assert refused.json()["detail"] == "Agnes has made 1 of 1 quest request in October 2026."
    found = mine(troupe.player, agnes)
    assert (found["used"], found["limit"], found["cycle_name"]) == (1, 1, "October 2026")
    assert found["refusal"] == refused.json()["detail"]


def test_only_a_characters_player_asks(troupe: Troupe, agnes: str) -> None:
    quests_on(troupe)

    assert ask(troupe.stranger, agnes).status_code == 404
    assert ask(troupe.storyteller, agnes).status_code == 404


def test_a_request_waits_in_the_queue_and_as_a_task_for_storytellers_and_assistants(
    troupe: Troupe, agnes: str
) -> None:
    quests_on(troupe)
    ok(ask(troupe.player, agnes), 201)

    [row] = queue(troupe.assistant, troupe, "new")
    assert (row["character_name"], row["player_name"], row["objective"]) == (
        "Agnes",
        "player",
        "Find Miles' journal",
    )
    assert row["assigned_to_name"] is None
    for person in (troupe.lead, troupe.storyteller, troupe.assistant):
        assert tasks(person) == ["Agnes asks for a quest: Find Miles' journal"]
    assert tasks(troupe.narrator) == []
    assert troupe.player.client.get(f"/troupes/{troupe.id}/quest-requests").status_code == 403
    # The narrator sees nothing until it is theirs.
    assert queue(troupe.narrator, troupe) == []


def test_assigning_a_request_shows_the_player_it_is_being_worked_on(
    troupe: Troupe, agnes: str
) -> None:
    quests_on(troupe)
    request = ok(ask(troupe.player, agnes), 201)
    url = f"/quest-requests/{request['id']}"

    ok(troupe.storyteller.client.put(f"{url}/assignment", json={"user_id": troupe.narrator.id}))

    [shown] = mine(troupe.player, agnes)["requests"]
    assert (shown["status"], shown["can_withdraw"]) == ("working", False)
    assert troupe.player.client.post(f"{url}/withdraw").status_code == 409
    [row] = queue(troupe.narrator, troupe, "mine")
    assert row["assigned_to_name"] == "narrator"
    assert tasks(troupe.narrator) == ["Agnes asks for a quest: Find Miles' journal"]
    # A narrator does not assign.
    assert troupe.narrator.client.put(f"{url}/assignment", json={}).status_code == 403


def test_a_narrator_accepts_a_request_for_any_narrator(troupe: Troupe, agnes: str) -> None:
    quests_on(troupe)
    request = ok(ask(troupe.player, agnes), 201)
    url = f"/quest-requests/{request['id']}"
    ok(troupe.assistant.client.put(f"{url}/assignment", json={"any_narrator": True}))

    [row] = queue(troupe.narrator, troupe, "any_narrator")
    accepted = ok(troupe.narrator.client.post(f"{url}/accept"))

    assert row["id"] == request["id"]
    assert (accepted["assigned_to_name"], accepted["can_work"]) == ("narrator", True)


def test_not_needed_gives_the_slot_back_and_withdrawing_does_too(
    troupe: Troupe, agnes: str
) -> None:
    quests_on(troupe)
    first = ok(ask(troupe.player, agnes), 201)
    url = f"/quest-requests/{first['id']}/answer"
    assert (
        troupe.storyteller.client.post(url, json={"outcome": "not_needed", "note": " "}).status_code
        == 422
    )

    ok(
        troupe.storyteller.client.post(
            url, json={"outcome": "not_needed", "note": "You already know the ritual."}
        )
    )

    [answered] = mine(troupe.player, agnes)["requests"]
    assert (answered["status"], answered["outcome"]) == ("answered", "not_needed")
    assert answered["note"] == "You already know the ritual."
    second = ok(ask(troupe.player, agnes, "Another"), 201)
    ok(troupe.player.client.post(f"/quest-requests/{second['id']}/withdraw"))
    ok(ask(troupe.player, agnes, "A third"), 201)
    assert mine(troupe.player, agnes)["used"] == 1
    assert queue(troupe.storyteller, troupe, "answered")[0]["outcome"] == "not_needed"


# --- building, checking and sending -------------------------------------------------------


@pytest.fixture
def second(troupe: Troupe) -> Person:
    """Another player in the troupe."""
    return sign_up(troupe.client_for, "second")


@pytest.fixture
def bram(troupe: Troupe, second: Person, session: Session) -> str:
    """Another of the troupe, with Elite 5 and High Society: enough for Elite 6."""
    character_id = member_character_of(troupe, second, "Bram")
    give(session, character_id, "backgrounds", "Influences: The Elite", 5)
    give(session, character_id, "influence_elite_specializations", "High Society", 1)
    return character_id


def member_character_of(troupe: Troupe, player: Person, name: str) -> str:
    character_id = new_character(troupe, player, name)
    requested = player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    )
    assert requested.status_code == 201, requested.text
    ok(troupe.lead.client.post(f"/approvals/{requested.json()['id']}/approve", json={}))
    return character_id


def test_the_whole_quest(
    troupe: Troupe, agnes: str, bram: str, second: Person, session: Session, fake: FakeConnector
) -> None:
    """Request, build as Complex 2, send, share, join, meet, two results, the tale."""
    quests_on(troupe)
    new_cycle(troupe)
    give(session, agnes, "skills", "Medicine", 3)
    ok(
        troupe.storyteller.client.put(
            f"/troupes/{troupe.id}/connectors/discord",
            json={"enabled": True, "mode": "full", "settings": {"test_target": "#st-test"}},
        )
    )
    request = ok(ask(troupe.player, agnes), 201)
    ok(
        troupe.storyteller.client.put(
            f"/quest-requests/{request['id']}/assignment", json={"user_id": troupe.assistant.id}
        )
    )

    # Built from the request: Agnes leads, its words are the objective.
    quest = ok(
        troupe.assistant.client.post(
            f"/troupes/{troupe.id}/quests",
            json={
                "name": "The Lost Journal",
                "category": "complex",
                "difficulty": 2,
                "request_id": request["id"],
            },
        ),
        201,
    )
    qid = quest["id"]
    assert (quest["leader"]["name"], quest["objective"]) == ("Agnes", "Find Miles' journal")
    assert quest["guidance"] == {"requirements": 4, "scenarios": 2}
    assert [s["number"] for s in quest["scenarios"]] == [1, 2]
    assert quest["assigned_to_name"] == "assistant"
    assert [r["status"] for r in queue(troupe.storyteller, troupe, "to_send")] == ["working"]

    requirement(troupe, qid, MEDICINE, SCIENCE)
    requirement(troupe, qid, ELITE_6)
    requirement(troupe, qid, {"kind": "aspect", "aspect": "sect", "name": "Anarch"})
    quest = requirement(troupe, qid, {"kind": "text", "text": "Access to Miles' journal"})
    labels = [r["label"] for r in quest["requirements"]]
    assert labels == [
        "Medicine 3 or Science (Biology)",
        "Expend Elite 6 (High Society)",
        "Anarch (sect)",
        "Access to Miles' journal",
    ]
    # The party's sheets: Agnes has Medicine 3, not Elite.
    medicine, elite, _, words = quest["requirements"]
    assert medicine["checks"] == [{"character_id": agnes, "name": "Agnes", "meets": [True, False]}]
    assert elite["checks"][0]["meets"] == [False]
    assert words["checks"][0]["meets"] == [None]

    # Sent: Agnes's player is told, and Discord posts to her channel.
    sent = ok(troupe.storyteller.client.post(f"/quests/{qid}/send"))
    assert sent["status"] == "active"
    assert sent["request"]["status"] == "answered"
    assert delivery.send_due(session, START) == 1
    [(target, message)] = fake.sent
    assert target == "#agnes"
    assert "Expend Elite 6 (High Society)" in message.text
    assert message.link.endswith(f"/characters/{agnes}/quests/{qid}")
    summaries = [
        n.summary
        for n in session.scalars(
            select(Notification).where(Notification.user_id == uuid.UUID(troupe.player.id))
        )
    ]
    assert "The quest The Lost Journal for Agnes: its requirements are here" in summaries
    [shown] = mine(troupe.player, agnes)["quests"]
    assert (shown["role"], shown["can_share"]) == ("leader", True)
    assert [r["label"] for r in shown["requirements"]][1] == "Expend Elite 6 (High Society)"
    [answered] = mine(troupe.player, agnes)["requests"]
    assert (answered["status"], answered["quest_id"]) == ("answered", qid)
    assert tasks(troupe.storyteller) == []

    # Agnes's player shares it with Bram, who joins.
    choices = ok(troupe.player.client.get(f"/characters/{agnes}/quests/{qid}/share-choices"))
    assert bram in [c["id"] for c in choices]
    assert mine(second, bram)["quests"] == []
    ok(
        troupe.player.client.post(
            f"/characters/{agnes}/quests/{qid}/share", json={"character_ids": [bram]}
        )
    )
    [offered] = mine(second, bram)["quests"]
    assert (offered["role"], offered["can_join"], offered["results"]) == ("invited", True, [])
    joined = ok(second.client.post(f"/characters/{bram}/quests/{qid}/join"))
    assert (joined["role"], joined["party"]) == ("joined", ["Agnes", "Bram"])

    # Bram meets Expend Elite 6: it goes in the influence log for the cycle.
    quest = ok(troupe.storyteller.client.get(f"/quests/{qid}"))
    elite_id = quest["requirements"][1]["id"]
    assert quest["requirements"][1]["checks"][1] == {
        "character_id": bram,
        "name": "Bram",
        "meets": [True],
    }
    quest = ok(
        troupe.storyteller.client.post(
            f"/quests/{qid}/requirements/{elite_id}/met", json={"character_id": bram, "option": 0}
        )
    )
    met = quest["requirements"][1]
    assert (met["met"], met["met_by_name"], met["spent"], met["met_patron"]) == (
        True,
        "Bram",
        "logged as E1",
        False,
    )
    entry = session.scalars(select(InfluenceEntry)).one()
    assert (entry.name, entry.source, entry.specialization) == ("Bram", "quest", "High Society")
    assert entry.purpose == "For the quest The Lost Journal"
    assert entry.cycle_id is not None
    history = ok(second.client.get(f"/characters/{bram}/influence"))
    assert [e["source"] for e in history["entries"]] == ["quest"]

    # Scenario 1, then 2: completed, with the date and the party.
    fake.sent.clear()
    url = f"/quests/{qid}/scenarios"
    ok(
        troupe.storyteller.client.post(
            f"{url}/1/result", json={"result": "passed", "text": "You find the cellar."}
        )
    )
    assert (
        troupe.storyteller.client.post(f"{url}/1/result", json={"result": "passed"}).status_code
        == 409
    )
    done = ok(
        troupe.storyteller.client.post(
            f"{url}/2/result", json={"result": "passed", "text": "The journal is yours."}
        )
    )
    assert (done["status"], done["finished_by"]) == ("completed", ["Agnes", "Bram"])
    assert done["ended_on"] is not None
    assert delivery.send_due(session, START) == 4
    assert sorted(t for t, _ in fake.sent) == ["#agnes", "#agnes", "#bram", "#bram"]
    seen = ok(second.client.get(f"/characters/{bram}/quests/{qid}"))
    assert [(r["number"], r["result"], r["text"]) for r in seen["results"]] == [
        (1, "passed", "You find the cellar."),
        (2, "passed", "The journal is yours."),
    ]

    # The leader tells the tale; staff approve it, and then it is theirs to change.
    tale_url = f"/characters/{agnes}/quests/{qid}/tale"
    assert (
        second.client.put(f"/characters/{bram}/quests/{qid}/tale", json={"tale": "x"}).status_code
        == 403
    )
    told = ok(troupe.player.client.put(tale_url, json={"tale": "We went by night."}))
    assert (told["tale"], told["can_write_tale"]) == ("We went by night.", True)
    approved = ok(
        troupe.storyteller.client.put(
            f"/quests/{qid}/tale",
            json={"tale": "We went by night, and Bram paid.", "approve": True},
        )
    )
    assert approved["tale_approved"] is True
    assert troupe.player.client.put(tale_url, json={"tale": "No"}).status_code == 409
    assert ok(second.client.get(f"/characters/{bram}/quests/{qid}"))["tale"].endswith("Bram paid.")


def test_a_narrator_builds_what_is_theirs_but_cannot_send_or_see_sheets(
    troupe: Troupe, agnes: str
) -> None:
    quests_on(troupe)
    request = ok(ask(troupe.player, agnes), 201)
    body = {"name": "Night Errand", "request_id": request["id"]}
    url = f"/troupes/{troupe.id}/quests"
    assert troupe.narrator.client.post(url, json=body).status_code == 403
    ok(
        troupe.storyteller.client.put(
            f"/quest-requests/{request['id']}/assignment", json={"user_id": troupe.narrator.id}
        )
    )

    quest = ok(troupe.narrator.client.post(url, json=body), 201)
    quest = ok(
        troupe.narrator.client.post(
            f"/quests/{quest['id']}/requirements", json={"options": [MEDICINE]}
        ),
        201,
    )

    assert (quest["can_edit"], quest["can_send"], quest["can_check"]) == (True, False, False)
    assert quest["requirements"][0]["checks"] == []
    assert troupe.narrator.client.post(f"/quests/{quest['id']}/send").status_code == 403
    ok(troupe.storyteller.client.post(f"/quests/{quest['id']}/read"))
    marked = ok(troupe.assistant.client.post(f"/quests/{quest['id']}/read"))
    assert marked["read_by"] == ["storyteller", "assistant"]


def test_meeting_spends_willpower_a_status_and_an_action_and_unmarking_gives_them_back(
    troupe: Troupe, agnes: str, session: Session
) -> None:
    quests_on(troupe)
    quest = build(troupe, name="Hard Road", leader_id=agnes)
    qid = quest["id"]
    requirement(troupe, qid, {"kind": "pool", "pool": "willpower", "amount": 2})
    quest = requirement(troupe, qid, {"kind": "action"})
    willpower, action = (r["id"] for r in quest["requirements"])
    before = ok(troupe.player.client.get(f"/characters/{agnes}/play"))["willpower"]["value"]

    def met(requirement_id: str) -> Any:
        return troupe.storyteller.client.post(
            f"/quests/{qid}/requirements/{requirement_id}/met",
            json={"character_id": agnes, "option": 0},
        )

    ok(met(willpower))
    ok(met(action))

    assert (
        ok(troupe.player.client.get(f"/characters/{agnes}/play"))["willpower"]["value"]
        == before - 2
    )
    assert [d.reason for d in session.scalars(select(OwedAction))] == ["For the quest Hard Road"]
    assert met(willpower).status_code == 409

    ok(troupe.storyteller.client.delete(f"/quests/{qid}/requirements/{willpower}/met"))
    ok(troupe.storyteller.client.delete(f"/quests/{qid}/requirements/{action}/met"))

    assert ok(troupe.player.client.get(f"/characters/{agnes}/play"))["willpower"]["value"] == before
    assert session.scalars(select(OwedAction)).all() == []


def test_a_patron_meets_a_requirement_from_outside_the_party(
    troupe: Troupe, agnes: str, bram: str
) -> None:
    quests_on(troupe)
    quest = build(troupe, name="Favours", leader_id=agnes)
    quest = requirement(troupe, quest["id"], {"kind": "text", "text": "A word with the Prince"})

    quest = ok(
        troupe.storyteller.client.post(
            f"/quests/{quest['id']}/requirements/{quest['requirements'][0]['id']}/met",
            json={"character_id": bram},
        )
    )

    assert (quest["requirements"][0]["met_by_name"], quest["requirements"][0]["met_patron"]) == (
        "Bram",
        True,
    )


def test_a_quest_posted_to_the_troupe_shows_to_everyone_and_the_first_to_join_leads(
    troupe: Troupe, agnes: str, bram: str, second: Person
) -> None:
    quests_on(troupe)
    quest = build(troupe, name="Patrol the Docks", offer="troupe")
    requirement(troupe, quest["id"], MEDICINE)
    assert mine(troupe.player, agnes)["quests"] == []

    ok(troupe.storyteller.client.post(f"/quests/{quest['id']}/send"))

    for person, character in ((troupe.player, agnes), (second, bram)):
        [shown] = mine(person, character)["quests"]
        assert (shown["role"], shown["can_join"]) == ("offered", True)
    joined = ok(second.client.post(f"/characters/{bram}/quests/{quest['id']}/join"))
    assert (joined["role"], joined["leader_name"]) == ("leader", "Bram")
    ok(troupe.player.client.post(f"/characters/{agnes}/quests/{quest['id']}/join"))
    assert (
        ok(troupe.storyteller.client.get(f"/quests/{quest['id']}"))["members"][0]["status"]
        == "joined"
    )


def test_a_quest_unlocked_by_another_quests_scenario(
    troupe: Troupe, agnes: str, bram: str, second: Person
) -> None:
    quests_on(troupe)
    trail = build(troupe, name="Maria's Trail", leader_id=agnes, category="complex", difficulty=2)
    requirement(troupe, trail["id"], MEDICINE)
    ok(troupe.storyteller.client.post(f"/quests/{trail['id']}/send"))
    after = build(
        troupe,
        name="The Bell Tower",
        offer="unlocked",
        unlock_quest_id=trail["id"],
        unlock_scenario=2,
    )
    requirement(troupe, after["id"], MEDICINE)
    ok(troupe.storyteller.client.post(f"/quests/{after['id']}/send"))
    url = f"/quests/{trail['id']}/scenarios"
    ok(troupe.storyteller.client.post(f"{url}/1/result", json={"result": "passed"}))
    assert [q["name"] for q in mine(troupe.player, agnes)["quests"]] == ["Maria's Trail"]

    ok(troupe.storyteller.client.post(f"{url}/2/result", json={"result": "passed"}))

    assert [q["name"] for q in mine(troupe.player, agnes)["quests"]] == [
        "The Bell Tower",
        "Maria's Trail",
    ]
    assert mine(second, bram)["quests"] == []


def test_closing_a_quest_tells_its_characters_why_and_stops_it(troupe: Troupe, agnes: str) -> None:
    quests_on(troupe)
    quest = build(troupe, name="Old Business", leader_id=agnes)
    requirement(troupe, quest["id"], MEDICINE)
    ok(troupe.storyteller.client.post(f"/quests/{quest['id']}/send"))
    url = f"/quests/{quest['id']}/close"
    assert troupe.narrator.client.post(url, json={"note": "x"}).status_code == 404

    closed = ok(troupe.storyteller.client.post(url, json={"note": "No longer relevant"}))

    assert (closed["status"], closed["close_note"]) == ("closed", "No longer relevant")
    [shown] = mine(troupe.player, agnes)["quests"]
    assert (shown["status"], shown["close_note"], shown["can_share"]) == (
        "closed",
        "No longer relevant",
        False,
    )
    result = troupe.storyteller.client.post(
        f"/quests/{quest['id']}/scenarios/1/result", json={"result": "passed"}
    )
    assert result.status_code == 409


def test_a_failed_scenario_is_tried_again_or_ends_the_quest(troupe: Troupe, agnes: str) -> None:
    quests_on(troupe)
    quest = build(troupe, name="The Long Night", leader_id=agnes)
    requirement(troupe, quest["id"], MEDICINE)
    ok(troupe.storyteller.client.post(f"/quests/{quest['id']}/send"))
    url = f"/quests/{quest['id']}/scenarios/1/result"

    again = ok(troupe.storyteller.client.post(url, json={"result": "failed", "text": "Not yet."}))
    ended = ok(troupe.storyteller.client.post(url, json={"result": "failed", "ends": True}))

    assert again["status"] == "active"
    assert (ended["status"], ended["finished_by"]) == ("failed", ["Agnes"])


def test_a_draft_quest_shows_nothing_to_players(troupe: Troupe, agnes: str) -> None:
    quests_on(troupe)
    quest = build(troupe, name="Secret Plans", leader_id=agnes)

    assert mine(troupe.player, agnes)["quests"] == []
    assert troupe.player.client.get(f"/characters/{agnes}/quests/{quest['id']}").status_code == 404
    assert troupe.storyteller.client.post(f"/quests/{quest['id']}/send").status_code == 422


def test_turning_quests_off_hides_them_again(troupe: Troupe, agnes: str) -> None:
    quests_on(troupe)
    quest = build(troupe, name="Errand", leader_id=agnes)
    requirement(troupe, quest["id"], MEDICINE)
    ok(troupe.storyteller.client.post(f"/quests/{quest['id']}/send"))
    ok(
        troupe.storyteller.client.put(
            f"/troupes/{troupe.id}/quest-settings", json={"enabled": False, "requests_per_cycle": 1}
        )
    )

    found = mine(troupe.player, agnes)

    assert (found["enabled"], found["quests"]) == (False, [])
    assert troupe.player.client.get(f"/characters/{agnes}/quests/{quest['id']}").status_code == 404


def test_sheets_are_checked_for_specialisations_powers_and_aspects(
    troupe: Troupe, agnes: str, session: Session
) -> None:
    quests_on(troupe)
    give(session, agnes, "skills", "Science", 1, "Biology")
    give(session, agnes, "skills", "Lore", 2)
    give(session, agnes, "lore_specializations", "Assamite", 1)
    give(session, agnes, "disciplines", "Auspex", 2)
    give(session, agnes, "clan", "Tremere: Telyav", None)
    give(session, agnes, "sect", "Anarch", None)
    quest = build(troupe, name="Every Kind", leader_id=agnes)
    needs = [
        (SCIENCE, True),
        (
            {"kind": "trait", "category": "skills", "name": "Science", "specialization": "Physics"},
            False,
        ),
        (
            {"kind": "trait", "category": "skills", "name": "Lore", "specialization": "Assamite"},
            True,
        ),
        ({"kind": "trait", "category": "skills", "name": "Lore", "rating": 3}, False),
        ({"kind": "trait", "category": "power", "name": "Heightened Senses"}, True),
        ({"kind": "trait", "category": "power", "name": "Psychic Projection"}, False),
        ({"kind": "aspect", "aspect": "clan", "name": "Tremere"}, True),
        ({"kind": "aspect", "aspect": "bloodline", "name": "Telyav"}, True),
        ({"kind": "aspect", "aspect": "sect", "name": "Camarilla"}, False),
        ({"kind": "status", "name": ""}, False),
        ({"kind": "background", "name": "Resources", "dots": 5}, False),
    ]
    for option, _ in needs:
        quest = requirement(troupe, quest["id"], option)

    found = [r["checks"][0]["meets"][0] for r in quest["requirements"]]

    assert found == [expected for _, expected in needs]
    assert [r["label"] for r in quest["requirements"]][-3:] == [
        "Camarilla (sect)",
        "Expend a status trait",
        "Expend Resources 5",
    ]
