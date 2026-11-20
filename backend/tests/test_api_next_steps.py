"""Next for this character (issue #1051): what needs the player, what waits on staff
and since when, and what is coming up, for each of a player's characters, each with
a link to where it is done; in a few queries for all of them."""

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from horatio import next_steps
from horatio.models import Approval, Character, User
from horatio.models import Troupe as TroupeRecord
from tests.api_helpers import Person, Troupe, finish, new_character
from tests.test_api_backstories import draft, save
from tests.test_api_bond_reports import Players
from tests.test_api_boon_reviews import hold, report
from tests.test_api_boons import Ledger
from tests.test_api_checkin import game
from tests.test_api_downtimes import member_character, new_cycle, open_cycle, question_id
from tests.test_api_downtimes import save as save_answers
from tests.test_api_free_changes import accepted, set_free_changes
from tests.test_api_quests import ask, quests_on
from tests.test_api_standing import buy

pytestmark = pytest.mark.usefixtures("without_bank")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def ok(response: Any, code: int = 200) -> Any:
    assert response.status_code == code, response.text
    return response.json()


def steps(person: Person, character_id: str) -> list[dict[str, Any]]:
    return ok(person.client.get(f"/characters/{character_id}/next"))["steps"]


def kinds(person: Person, character_id: str) -> list[tuple[str, str]]:
    return [(s["who"], s["kind"]) for s in steps(person, character_id)]


def step(person: Person, character_id: str, kind: str) -> dict[str, Any]:
    return next(s for s in steps(person, character_id) if s["kind"] == kind)


def build_for(troupe: Troupe, character_id: str) -> None:
    ok(
        troupe.player.client.put(
            f"/characters/{character_id}/building-troupe", json={"troupe_id": troupe.id}
        )
    )


def ask_home(troupe: Troupe, character_id: str) -> dict[str, Any]:
    return ok(
        troupe.player.client.post(
            f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
        ),
        201,
    )


def require_backstory(troupe: Troupe, required: bool = True) -> None:
    troupe.session.get_one(TroupeRecord, uuid.UUID(troupe.id)).backstory_required = required
    troupe.session.flush()


# --- built, joined, accepted ---------------------------------------------------------------


def test_a_new_character_is_finished_asks_its_troupe_and_waits_then_has_nothing_next(
    troupe: Troupe,
) -> None:
    agnes = new_character(troupe, troupe.player, finished=False)
    build_for(troupe, agnes)
    [made] = steps(troupe.player, agnes)
    assert made == {
        "kind": "finish_creation",
        "who": "player",
        "label": "Finish character creation",
        "link": f"/characters/{agnes}/create",
        "since": None,
        "at": None,
    }

    finish(troupe, agnes)
    [asking] = steps(troupe.player, agnes)
    assert (asking["kind"], asking["who"]) == ("ask_home", "player")
    assert asking["label"] == "Ask Lords of the Night to be its home"
    assert asking["link"] == f"/characters/{agnes}/troupes?home={troupe.id}"

    asked = ask_home(troupe, agnes)
    [waiting] = steps(troupe.player, agnes)
    assert (waiting["kind"], waiting["who"]) == ("approval_home", "staff")
    assert waiting["label"] == "Asked Lords of the Night to be its home"
    assert waiting["link"] == f"/characters/{agnes}/troupes"
    held = troupe.session.get_one(Approval, uuid.UUID(asked["id"]))
    assert datetime.fromisoformat(waiting["since"]) == held.created_at

    ok(troupe.lead.client.post(f"/approvals/{asked['id']}/approve", json={}))
    assert steps(troupe.player, agnes) == []
    # The Characters page leaves out a character with nothing next.
    assert ok(troupe.player.client.get("/characters/next")) == []


def test_with_no_troupe_chosen_any_troupe_is_asked(troupe: Troupe) -> None:
    agnes = new_character(troupe, troupe.player)

    [asking] = steps(troupe.player, agnes)
    assert (asking["label"], asking["link"]) == (
        "Ask a troupe to be its home",
        f"/characters/{agnes}/troupes",
    )


def test_the_backstory_a_troupe_needs_is_written_read_sent_back_and_revised(
    troupe: Troupe,
) -> None:
    require_backstory(troupe)
    agnes = new_character(troupe, troupe.player)
    build_for(troupe, agnes)
    assert kinds(troupe.player, agnes) == [("player", "backstory_write"), ("player", "ask_home")]
    assert step(troupe.player, agnes, "backstory_write")["label"] == (
        "Write the backstory Lords of the Night needs"
    )
    assert step(troupe.player, agnes, "backstory_write")["link"] == f"/characters/{agnes}/backstory"

    # A draft is said once, in place of writing it.
    ok(draft(troupe.player, agnes, "Born in", 0))
    assert kinds(troupe.player, agnes) == [("player", "backstory_draft"), ("player", "ask_home")]

    ok(save(troupe.player, agnes, "Born in 1890.", 0))
    ask_home(troupe, agnes)
    reading = step(troupe.player, agnes, "backstory_reading")
    assert (reading["who"], reading["label"]) == (
        "staff",
        "Backstory with Lords of the Night's storytellers",
    )
    assert reading["since"] is not None

    ok(
        troupe.storyteller.client.post(
            f"/characters/{agnes}/backstory/feedback", json={"body": "More about the sire"}
        )
    )
    assert kinds(troupe.player, agnes) == [
        ("player", "backstory_returned"),
        ("staff", "approval_home"),
    ]
    assert step(troupe.player, agnes, "backstory_returned")["label"] == (
        "Revise the backstory Lords of the Night sent back"
    )

    ok(save(troupe.player, agnes, "Born in 1890, sired by a cruel man.", 1))
    ok(
        troupe.player.client.post(
            f"/characters/{agnes}/backstory/resubmit", json={"note": "More on the sire."}
        )
    )
    assert ("staff", "backstory_reading") in kinds(troupe.player, agnes)


# --- downtimes -----------------------------------------------------------------------------


def test_a_downtime_is_due_then_waits_for_results_then_has_new_results(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    cycle = open_cycle(troupe, new_cycle(troupe))

    [due] = steps(troupe.player, agnes)
    assert (due["kind"], due["who"], due["link"]) == (
        "downtime_due",
        "player",
        f"/characters/{agnes}/downtime",
    )
    assert datetime.fromisoformat(due["at"]) == datetime.fromisoformat(cycle["closes_at"])

    form = ok(troupe.player.client.get(f"/characters/{agnes}/downtime"))
    general = question_id(form, "Downtime action")
    answer = [{"question_id": general, "slot": 1, "body": "Feed at the docks"}]
    ok(save_answers(troupe.player, agnes, answer))
    ok(troupe.player.client.post(f"/characters/{agnes}/downtime/submit"))
    [results] = steps(troupe.player, agnes)
    assert (results["kind"], results["who"], results["label"]) == (
        "downtime_results",
        "staff",
        "Results of October 2026",
    )
    assert results["since"] is not None

    lead = troupe.lead.client
    ok(lead.post(f"/cycles/{cycle['id']}/close", json={"add_to_ceiling": True}))
    [response] = ok(lead.get(f"/cycles/{cycle['id']}/responses"))
    ok(lead.put(f"/responses/{response['id']}", json={"body": "You feed well."}))
    ok(lead.post(f"/cycles/{cycle['id']}/deliver", json={"partial": True}))
    [new] = steps(troupe.player, agnes)
    assert (new["kind"], new["who"], new["link"]) == (
        "results",
        "player",
        f"/characters/{agnes}/results",
    )
    # When the newest came: the page judges whether its player has opened them.
    delivered = ok(troupe.player.client.get(f"/characters/{agnes}/downtime/waiting"))
    assert new["since"] == delivered["delivered"][0]


# --- approvals -----------------------------------------------------------------------------


def test_approvals_wait_on_staff_one_step_for_each_kind_since_the_oldest(
    troupe: Troupe, session: Session
) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    for discipline in ("Celerity", "Fortitude"):
        ok(buy(troupe.player, agnes, discipline, 1, "disciplines"))
    # An exception asked for, as the cart asks for one.
    player = session.get_one(User, uuid.UUID(troupe.player.id))
    session.add(
        Approval(
            character_id=uuid.UUID(agnes),
            troupe_id=uuid.UUID(troupe.id),
            kind="exception",
            requested_by=player.id,
        )
    )
    session.flush()

    found = steps(troupe.player, agnes)
    assert [(s["who"], s["kind"], s["label"]) for s in found] == [
        ("staff", "approval_discipline", "2 discipline purchases awaiting approval"),
        ("staff", "approval_exception", "Exception awaiting an answer"),
    ]
    assert all(s["link"] == f"/characters/{agnes}" and s["since"] for s in found)
    oldest = min(
        session.scalars(
            select(Approval.created_at).where(
                Approval.character_id == uuid.UUID(agnes), Approval.kind == "discipline"
            )
        )
    )
    assert datetime.fromisoformat(found[0]["since"]) == oldest


# --- boons, bonds and quests ---------------------------------------------------------------


@pytest.fixture
def ledger(client_for: Callable[[], TestClient], session: Session) -> Ledger:
    return Ledger(Troupe(client_for, session))


def test_a_boon_report_held_for_review_waits_on_staff(ledger: Ledger) -> None:
    t = ledger.troupe
    assert steps(t.player, ledger.agnes) == []
    ok(hold(ledger, True))
    report(ledger, ledger.agnes)
    report(ledger, ledger.agnes, reason="Safe passage")

    [waiting] = steps(t.player, ledger.agnes)
    assert (waiting["kind"], waiting["who"], waiting["label"]) == (
        "boon_reports",
        "staff",
        "2 boon reports awaiting approval",
    )
    assert waiting["link"] == f"/play/characters/{ledger.agnes}?tab=boons"
    # With the ledger off, nothing of it shows.
    ok(ledger.switch(False))
    assert steps(t.player, ledger.agnes) == []


@pytest.fixture
def players(client_for: Callable[[], TestClient], session: Session) -> Players:
    return Players(Troupe(client_for, session))


def test_a_drink_the_regnant_recorded_is_the_thralls_to_confirm(players: Players) -> None:
    p, t = players, players.troupe
    p.set("players_manage")
    assert p.reported(p.bram, p.other, "regnant", p.agnes) == "thrall"

    [confirm] = steps(t.player, p.agnes)
    assert (confirm["kind"], confirm["who"], confirm["label"], confirm["link"]) == (
        "drinks_to_confirm",
        "player",
        "A drink to confirm or decline",
        f"/characters/{p.agnes}",
    )
    # Nothing for the regnant's player, who recorded it.
    assert steps(p.other, p.bram) == []


def test_a_drink_reported_for_staff_to_approve_waits_on_them(players: Players) -> None:
    p, t = players, players.troupe
    p.set("players_report")
    made = p.report(p.agnes, t.player, "thrall", p.bram)
    assert made.status_code == 201, made.text

    assert kinds(t.player, p.agnes) == [("staff", "approval_bond_drink")]
    # Switched off, a drink reported is in no queue, and waits on no one.
    p.set("off")
    assert steps(t.player, p.agnes) == []


def test_a_quest_request_waits_for_an_answer(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    quests_on(troupe)
    ok(ask(troupe.player, agnes), 201)

    [waiting] = steps(troupe.player, agnes)
    assert (waiting["kind"], waiting["who"], waiting["label"], waiting["link"]) == (
        "quest_requests",
        "staff",
        "Quest request awaiting an answer",
        f"/characters/{agnes}/quests",
    )


# --- coming up -----------------------------------------------------------------------------


def test_the_next_game_and_free_changes_are_coming_up(troupe: Troupe) -> None:
    ok(set_free_changes(troupe, "date", days=30))
    agnes = accepted(troupe)
    soon = game(troupe, timedelta(days=2))
    game(troupe, timedelta(days=9))

    found = steps(troupe.player, agnes)
    assert [(s["who"], s["kind"]) for s in found] == [
        ("coming", "next_game"),
        ("coming", "free_changes"),
    ]
    games = ok(troupe.player.client.get(f"/troupes/{troupe.id}/games"))
    first = next(g for g in games if g["id"] == soon)
    assert found[0]["at"] == first["starts_at"]
    assert found[0]["link"] == f"/troupes/{troupe.id}"
    ends = datetime.fromisoformat(found[1]["at"])
    assert timedelta(days=29) < ends - datetime.now(UTC) <= timedelta(days=30)

    ok(set_free_changes(troupe, "games", games=3))
    assert step(troupe.player, agnes, "free_changes")["label"] == "Free changes for 3 more games"


# --- who sees it ---------------------------------------------------------------------------


def test_only_its_player_sees_what_is_next_and_never_for_npcs_or_retired_characters(
    troupe: Troupe,
) -> None:
    agnes = new_character(troupe, troupe.player)
    for person in (troupe.lead, troupe.stranger):
        assert person.client.get(f"/characters/{agnes}/next").status_code in (403, 404)

    npc = ok(troupe.lead.client.post(f"/troupes/{troupe.id}/npcs", json={"name": "Vidal"}), 201)
    assert ok(troupe.lead.client.get(f"/characters/{npc['id']}/next"))["steps"] == []

    retired = troupe.session.get_one(Character, uuid.UUID(agnes))
    retired.status = "retired"
    troupe.session.flush()
    assert steps(troupe.player, agnes) == []


def test_the_characters_page_has_each_characters_steps(troupe: Troupe) -> None:
    agnes = new_character(troupe, troupe.player, "Agnes", finished=False)
    bea = new_character(troupe, troupe.player, "Bea")
    member_character(troupe, troupe.player, "Cora")

    listed = ok(troupe.player.client.get("/characters/next"))
    assert {c["character_id"]: [s["kind"] for s in c["steps"]] for c in listed} == {
        agnes: ["finish_creation"],
        bea: ["ask_home"],
    }
    # Only the player's own.
    assert ok(troupe.lead.client.get("/characters/next")) == []


@pytest.fixture
def statements(session: Session) -> Iterator[list[str]]:
    sent: list[str] = []

    def keep(*args: Any) -> None:
        sent.append(args[2])

    connection = session.connection()
    event.listen(connection, "before_cursor_execute", keep)
    yield sent
    event.remove(connection, "before_cursor_execute", keep)


def test_many_characters_take_no_more_queries_than_one(
    troupe: Troupe, session: Session, statements: list[str]
) -> None:
    ok(set_free_changes(troupe, "games", games=3))
    quests_on(troupe)
    game(troupe, timedelta(days=2))
    ids = []
    for name in ("Agnes", "Bea", "Cora"):
        character_id = accepted(troupe, name)
        ok(buy(troupe.player, character_id, "Celerity", 1, "disciplines"))
        ok(ask(troupe.player, character_id), 201)
        ids.append(uuid.UUID(character_id))
    open_cycle(troupe, new_cycle(troupe))

    def asked(these: list[uuid.UUID]) -> int:
        session.expire_all()
        found = list(session.scalars(select(Character).where(Character.id.in_(these))))
        statements.clear()
        listed = next_steps.next_steps(session, found)
        expected = {
            "downtime_due",
            "approval_discipline",
            "quest_requests",
            "next_game",
            "free_changes",
        }
        assert all({s.kind for s in listed[c.id]} == expected for c in found)
        return len(statements)

    assert asked(ids) == asked(ids[:1])
