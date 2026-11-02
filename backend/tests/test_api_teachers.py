"""Teachers for more kinds of trait (#440): a troupe's storytellers add teacher rules,
and a purchase one is about needs a teacher who qualifies and waits on the home
troupe. A rule can cost the teacher Willpower, which their player confirms and which
comes back only after games they attend. With no rules, nothing changes. Each of the
issue's three examples can be built."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import play, teaching
from horatio.models import (
    AuditEvent,
    Character,
    GameAttendance,
    OwedAction,
    ScheduledGame,
    Teaching,
    User,
)
from tests.api_helpers import Person, Troupe, new_character, sign_up

pytestmark = pytest.mark.usefixtures("without_bank")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def other(client_for: Callable[[], TestClient]) -> Person:
    """A second player in the troupe, whose character teaches."""
    return sign_up(client_for, "teacherplayer")


def add(troupe: Troupe, rule: dict[str, Any], person: Person | None = None) -> Any:
    return (person or troupe.storyteller).client.post(
        f"/troupes/{troupe.id}/teacher-rules", json=rule
    )


def added(troupe: Troupe, rule: dict[str, Any]) -> dict[str, Any]:
    response = add(troupe, rule)
    assert response.status_code == 201, response.text
    return response.json()


def take(
    person: Person, character_id: str, category: str, name: str, rating: int, **more: Any
) -> Any:
    return person.client.put(
        f"/characters/{character_id}/traits",
        json={"category": category, "name": name, "rating": rating, **more},
    )


def bought(person: Person, character_id: str, category: str, name: str, rating: int) -> None:
    response = take(person, character_id, category, name, rating)
    assert response.status_code == 200, response.text


def award(troupe: Troupe, character_id: str, amount: int = 30) -> None:
    response = troupe.assistant.client.post(
        f"/characters/{character_id}/xp", json={"amount": amount, "reason": "Games"}
    )
    assert response.status_code == 201, response.text


def queue(troupe: Troupe) -> list[dict[str, Any]]:
    return troupe.lead.client.get(f"/troupes/{troupe.id}/approvals").json()


def owed(session: Session, character_id: str) -> list[str]:
    return [
        o.reason
        for o in session.scalars(
            select(OwedAction).where(OwedAction.character_id == uuid.UUID(character_id))
        )
    ]


# The issue's three examples.
LORE_SPECIALISATIONS = {"category": "lore_specializations", "actions": 1}
LORE_DOTS = {"category": "skills", "names": ["Lore"], "always": True}
ELDERS_MODERN_SKILLS = {
    "category": "skills",
    "names": ["Computer", "Drive", "Firearms"],
    "condition": {"generation": {"gte": 3}},
    "willpower": 1,
    "games": 2,
}


@pytest.fixture
def lore_teacher(troupe: Troupe, other: Person) -> str:
    """Brother Ansel, of the troupe, with Lore 3 and the Camarilla and Sabbat subjects."""
    ansel = new_character(troupe, other, "Brother Ansel")
    bought(other, ansel, "skills", "Lore", 3)
    bought(other, ansel, "lore_specializations", "Camarilla", 1)
    bought(other, ansel, "lore_specializations", "Sabbat", 1)
    return member_character_of(troupe, other, ansel)


def member_character_of(troupe: Troupe, player: Person, character_id: str) -> str:
    requested = player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    )
    assert requested.status_code == 201, requested.text
    approved = troupe.lead.client.post(f"/approvals/{requested.json()['id']}/approve", json={})
    assert approved.status_code == 200, approved.text
    return character_id


@pytest.fixture
def student(troupe: Troupe) -> str:
    """Agnes, accepted in the troupe, with Lore 1 and XP to spend."""
    agnes = new_character(troupe, troupe.player, "Agnes")
    bought(troupe.player, agnes, "skills", "Lore", 1)
    member_character_of(troupe, troupe.player, agnes)
    award(troupe, agnes)
    return agnes


# --- with no rules ---------------------------------------------------------------------


def test_with_no_rules_nothing_changes(troupe: Troupe, student: str, lore_teacher: str) -> None:
    assert troupe.storyteller.client.get(f"/troupes/{troupe.id}/teacher-rules").json() == []

    response = take(troupe.player, student, "lore_specializations", "Camarilla", 1)
    raised = take(troupe.player, student, "skills", "Lore", 2)

    assert response.status_code == 200, response.text
    assert raised.status_code == 200, raised.text
    assert queue(troupe) == []
    assert troupe.player.client.get(f"/characters/{student}/teacher-rules").json() == []
    options = troupe.player.client.get(
        f"/characters/{student}/teachers",
        params={"category": "skills", "name": "Firearms", "rating": 1},
    )
    assert options.json() is None


# --- the rules -------------------------------------------------------------------------


def test_storytellers_add_change_and_remove_rules_in_the_log(troupe: Troupe) -> None:
    for person in (troupe.assistant, troupe.narrator, troupe.player):
        assert add(troupe, LORE_SPECIALISATIONS, person).status_code == 403

    rule = added(troupe, LORE_SPECIALISATIONS)
    assert rule["text"] == (
        "Lore Specialisations need a teacher who holds it at the rating learned and "
        "1 downtime action, once creation is finished."
    )
    changed = troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/teacher-rules/{rule['id']}",
        json={**LORE_SPECIALISATIONS, "holds": "rating", "rating": 2},
    )
    assert changed.status_code == 200, changed.text
    assert "holds it at 2 or more" in changed.json()["text"]
    removed = troupe.storyteller.client.delete(f"/troupes/{troupe.id}/teacher-rules/{rule['id']}")
    assert removed.status_code == 204

    actions = [
        e.action
        for e in troupe.session.scalars(
            select(AuditEvent)
            .where(AuditEvent.troupe_id == uuid.UUID(troupe.id))
            .order_by(AuditEvent.created_at)
        )
        if e.action.startswith("house.teacher")
    ]
    assert actions == ["house.teacher_added", "house.teacher_changed", "house.teacher_removed"]


@pytest.mark.parametrize(
    ("rule", "problem"),
    [
        ({"category": "merits"}, "Merits and flaws"),
        ({"category": "clan"}, "bought in dots"),
        ({"category": "skills", "names": ["Basket Weaving"]}, "not one of the skills"),
        ({"category": "skills", "holds": "rating"}, "teacher's rating"),
        ({"category": "skills", "willpower": 1}, "returns after"),
        ({"category": "skills", "condition": {"npc": True}}, "cannot use 'npc'"),
    ],
)
def test_a_rule_the_rules_cannot_use_is_refused(
    troupe: Troupe, rule: dict[str, Any], problem: str
) -> None:
    response = add(troupe, rule)

    assert response.status_code == 422
    assert problem in response.json()["detail"]


def test_the_house_rules_tab_lists_the_rules(troupe: Troupe) -> None:
    added(troupe, ELDERS_MODERN_SKILLS)

    rules = troupe.player.client.get(f"/troupes/{troupe.id}/house-rules")

    assert rules.status_code == 200, rules.text
    assert rules.json()["teachers"] == [
        "Computer, Drive or Firearms need a teacher who holds it at the rating learned and "
        "1 of the teacher's Willpower, back after 2 games, once creation is finished, "
        "if Generation 3 or more."
    ]


# --- example 1: Lore specialisations after creation, with a downtime -----------------


def test_a_lore_specialisation_needs_a_teacher_who_holds_it(
    troupe: Troupe, student: str, lore_teacher: str
) -> None:
    added(troupe, LORE_SPECIALISATIONS)
    applying = troupe.player.client.get(f"/characters/{student}/teacher-rules").json()
    assert [r["category"] for r in applying] == ["lore_specializations"]

    without = take(troupe.player, student, "lore_specializations", "Camarilla", 1)
    assert without.status_code == 422
    assert "Camarilla needs a teacher here" in without.json()["detail"]

    options = troupe.player.client.get(
        f"/characters/{student}/teachers",
        params={"category": "lore_specializations", "name": "Camarilla", "rating": 1},
    ).json()
    assert options["rating"] == 1
    assert [c["name"] for c in options["candidates"]] == ["Brother Ansel"]
    nobody = troupe.player.client.get(
        f"/characters/{student}/teachers",
        params={"category": "lore_specializations", "name": "Giovanni", "rating": 1},
    ).json()
    assert nobody["candidates"] == []

    refused = take(
        troupe.player, student, "lore_specializations", "Giovanni", 1, teacher_id=lore_teacher
    )
    assert refused.status_code == 422
    assert "Brother Ansel cannot teach Giovanni" in refused.json()["detail"]

    taught = take(
        troupe.player, student, "lore_specializations", "Camarilla", 1, teacher_id=lore_teacher
    )
    assert taught.status_code == 200, taught.text
    [waiting] = queue(troupe)
    assert waiting["kind"] == "discipline"
    assert waiting["discipline"]["name"] == "Camarilla"
    assert waiting["discipline"]["teacher"] == "Brother Ansel"
    assert waiting["discipline"]["teaching"]["in_troupe"] is True
    assert waiting["discipline"]["teaching"]["actions"] == 1

    approved = troupe.lead.client.post(f"/approvals/{waiting['id']}/approve", json={})
    assert approved.status_code == 200, approved.text
    assert "Learning Camarilla 1 from Brother Ansel" in owed(troupe.session, student)


def test_an_npc_named_in_text_teaches_and_staff_decline_it(troupe: Troupe, student: str) -> None:
    added(troupe, LORE_SPECIALISATIONS)

    taught = take(
        troupe.player,
        student,
        "lore_specializations",
        "Giovanni",
        1,
        teacher="Old Mother Grey (NPC)",
    )

    assert taught.status_code == 200, taught.text
    [waiting] = queue(troupe)
    assert waiting["discipline"]["teacher"] == "Old Mother Grey (NPC)"
    assert waiting["discipline"]["teaching"]["in_troupe"] is False
    declined = troupe.lead.client.post(f"/approvals/{waiting['id']}/decline", json={})
    assert declined.status_code == 200, declined.text
    sheet = troupe.player.client.get(f"/characters/{student}/sheet").json()
    assert not any(t["name"] == "Giovanni" for t in sheet["traits"])
    assert owed(troupe.session, student) == []


def test_during_creation_the_rule_does_not_ask(troupe: Troupe) -> None:
    added(troupe, LORE_SPECIALISATIONS)
    draft = new_character(troupe, troupe.player, "Bettina")
    troupe.session.get_one(Character, uuid.UUID(draft)).building_troupe_id = uuid.UUID(troupe.id)
    troupe.session.flush()
    bought(troupe.player, draft, "skills", "Lore", 1)
    troupe.session.get_one(Character, uuid.UUID(draft)).creation_completed_at = None
    troupe.session.flush()

    assert take(troupe.player, draft, "lore_specializations", "Camarilla", 1).status_code == 200


# --- example 2: Lore dots, from a teacher with at least the rating ------------------


def test_lore_dots_need_a_teacher_with_the_rating_learned(
    troupe: Troupe, student: str, lore_teacher: str
) -> None:
    added(troupe, LORE_DOTS)

    options = troupe.player.client.get(
        f"/characters/{student}/teachers",
        params={"category": "skills", "name": "Lore", "rating": 4, "current": 1},
    ).json()
    assert options["rating"] == 4
    assert options["candidates"] == []
    too_far = take(troupe.player, student, "skills", "Lore", 4, teacher_id=lore_teacher)
    assert too_far.status_code == 422
    assert "holds it at 4 or more" in too_far.json()["detail"]

    raised = take(troupe.player, student, "skills", "Lore", 3, teacher_id=lore_teacher)

    assert raised.status_code == 200, raised.text
    [waiting] = queue(troupe)
    assert (waiting["discipline"]["name"], waiting["discipline"]["to_rating"]) == ("Lore", 3)
    withdrawn = troupe.player.client.delete(f"/characters/{student}/disciplines/{waiting['id']}")
    assert withdrawn.status_code == 204, withdrawn.text
    # Lowering needs none.
    lowering = troupe.player.client.get(
        f"/characters/{student}/teachers",
        params={"category": "skills", "name": "Lore", "rating": 1, "current": 3},
    )
    assert lowering.json() is None


def test_an_always_rule_asks_while_building_and_waits_on_nobody(
    troupe: Troupe, lore_teacher: str
) -> None:
    added(troupe, LORE_DOTS)
    draft = new_character(troupe, troupe.player, "Bettina")
    troupe.session.get_one(Character, uuid.UUID(draft)).building_troupe_id = uuid.UUID(troupe.id)
    troupe.session.flush()

    assert take(troupe.player, draft, "skills", "Lore", 2).status_code == 422
    taught = take(troupe.player, draft, "skills", "Lore", 2, teacher_id=lore_teacher)

    assert taught.status_code == 200, taught.text
    assert queue(troupe) == []
    [kept] = troupe.session.scalars(
        select(Teaching).where(Teaching.character_id == uuid.UUID(draft))
    )
    assert kept.teacher_name == "Brother Ansel"
    assert kept.approval_id is None


def test_the_cart_says_which_line_needs_a_teacher(
    troupe: Troupe, student: str, lore_teacher: str
) -> None:
    added(troupe, LORE_DOTS)

    def cart(**teacher: Any) -> dict[str, Any]:
        change = {"kind": "set", "category": "skills", "name": "Lore", "rating": 2, **teacher}
        response = troupe.player.client.post(
            f"/characters/{student}/cart", json={"changes": [change], "dry_run": True}
        )
        assert response.status_code == 200, response.text
        return response.json()["lines"][0]

    line = cart()
    assert line["refused"] is not None
    assert line["teacher"]["rating"] == 2
    assert "Lore need a teacher" in line["teacher"]["rule"]
    taught = cart(teacher_id=lore_teacher)
    assert taught["refused"] is None
    assert taught["needs_approval"] is True


# --- example 3: elders' modern skills, with the teacher's Willpower ------------------


@pytest.fixture
def elder(troupe: Troupe) -> str:
    """Konrad, an elder of Generation 3, accepted in the troupe."""
    konrad = new_character(troupe, troupe.player, "Konrad")
    bought(troupe.player, konrad, "backgrounds", "Generation", 3)
    member_character_of(troupe, troupe.player, konrad)
    award(troupe, konrad)
    return konrad


@pytest.fixture
def gunman(troupe: Troupe, other: Person) -> str:
    """Rook, of the troupe, with Firearms 2."""
    rook = new_character(troupe, other, "Rook")
    bought(other, rook, "skills", "Firearms", 2)
    return member_character_of(troupe, other, rook)


def willpower(person: Person, character_id: str) -> dict[str, Any]:
    view = person.client.get(f"/characters/{character_id}/play")
    assert view.status_code == 200, view.text
    return view.json()


def test_only_elders_need_a_teacher_for_modern_skills(
    troupe: Troupe, elder: str, student: str
) -> None:
    added(troupe, ELDERS_MODERN_SKILLS)

    assert take(troupe.player, student, "skills", "Firearms", 1).status_code == 200
    assert take(troupe.player, elder, "skills", "Firearms", 1).status_code == 422
    assert take(troupe.player, elder, "skills", "Brawl", 1).status_code == 200
    rules = troupe.player.client.get(f"/characters/{elder}/teacher-rules").json()
    assert [r["names"] for r in rules] == [["Computer", "Drive", "Firearms"]]
    assert troupe.player.client.get(f"/characters/{student}/teacher-rules").json() == []


def test_the_teachers_willpower_is_confirmed_spent_and_returns_after_two_games(
    troupe: Troupe, other: Person, elder: str, gunman: str, session: Session
) -> None:
    added(troupe, ELDERS_MODERN_SKILLS)
    full = willpower(other, gunman)["willpower"]["value"]

    taught = take(troupe.player, elder, "skills", "Firearms", 2, teacher_id=gunman)
    assert taught.status_code == 200, taught.text
    [waiting] = queue(troupe)
    assert waiting["discipline"]["teaching"]["status"] == "asked"
    assert waiting["discipline"]["teaching"]["willpower"] == 1

    # Staff wait for the teacher's player.
    early = troupe.lead.client.post(f"/approvals/{waiting['id']}/approve", json={})
    assert early.status_code == 409
    assert "Rook's player has not yet confirmed" in early.json()["detail"]

    # The teacher's player is asked, in their bell and on the Play View.
    bell = other.client.get("/notifications").json()
    task = next(i for i in bell["items"] if i["kind"] == "teaching")
    assert "Teaching Firearms 2 to Konrad" in task["summary"]
    asked = other.client.get(f"/characters/{gunman}/teaching").json()["asked"]
    assert [a["what"] for a in asked] == ["Teaching Firearms 2 to Konrad"]
    assert troupe.player.client.post(f"/teachings/{asked[0]['id']}/confirm").status_code == 404

    confirmed = other.client.post(f"/teachings/{asked[0]['id']}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["asked"] == []
    assert confirmed.json()["lent"] == (
        "1 Willpower out teaching Firearms 2 to Konrad: back after 2 more games"
    )
    view = willpower(other, gunman)
    assert view["willpower"]["value"] == full - 1
    assert "back after 2 more games" in view["willpower_lent"]
    assert not any(
        i["kind"] == "teaching" for i in other.client.get("/notifications").json()["items"]
    )

    approved = troupe.lead.client.post(f"/approvals/{waiting['id']}/approve", json={})
    assert approved.status_code == 200, approved.text

    # Rest does not bring it back until Rook has attended two games since.
    rook = session.get_one(Character, uuid.UUID(gunman))
    [spent] = session.scalars(select(Teaching).where(Teaching.teacher_id == rook.id))
    spent.spent_at = datetime.now(UTC) - timedelta(days=30)
    session.flush()
    assert play.limits(session, rook).starting_willpower() == full - 1
    attend(session, troupe, rook, days_ago=20)
    assert play.limits(session, rook).starting_willpower() == full - 1
    assert teaching.lent_text(session, rook) == (
        "1 Willpower out teaching Firearms 2 to Konrad: back after 1 more game"
    )
    attend(session, troupe, rook, days_ago=10)
    assert play.limits(session, rook).starting_willpower() == full
    assert teaching.lent_text(session, rook) is None


def attend(session: Session, troupe: Troupe, character: Character, days_ago: int) -> None:
    """The character checked in to a game, now over."""
    start = datetime.now(UTC) - timedelta(days=days_ago)
    game = ScheduledGame(
        troupe_id=uuid.UUID(troupe.id), starts_at=start, ends_at=start + timedelta(hours=5)
    )
    session.add(game)
    session.flush()
    lead = session.scalars(select(User).where(User.email == troupe.lead.email)).one()
    session.add(GameAttendance(game_id=game.id, character_id=character.id, checked_in_by=lead.id))
    session.flush()


def test_games_not_attended_do_not_count(troupe: Troupe, gunman: str, session: Session) -> None:
    rook = session.get_one(Character, uuid.UUID(gunman))
    since = datetime.now(UTC) - timedelta(days=40)
    attend(session, troupe, rook, days_ago=30)
    attend(session, troupe, rook, days_ago=50)  # before the spend
    start = datetime.now(UTC) - timedelta(days=5)
    session.add(
        ScheduledGame(
            troupe_id=uuid.UUID(troupe.id), starts_at=start, ends_at=start + timedelta(hours=5)
        )
    )
    session.flush()

    assert teaching.games_attended(session, rook, since, datetime.now(UTC)) == 1


def test_the_teacher_says_no_and_staff_decline(
    troupe: Troupe, other: Person, elder: str, gunman: str
) -> None:
    added(troupe, ELDERS_MODERN_SKILLS)
    full = willpower(other, gunman)["willpower"]["value"]
    take(troupe.player, elder, "skills", "Firearms", 1, teacher_id=gunman)
    [waiting] = queue(troupe)
    [asked] = other.client.get(f"/characters/{gunman}/teaching").json()["asked"]

    assert other.client.post(f"/teachings/{asked['id']}/refuse").status_code == 200

    refused = troupe.lead.client.post(f"/approvals/{waiting['id']}/approve", json={})
    assert refused.status_code == 409
    assert "said no" in refused.json()["detail"]
    assert (
        troupe.lead.client.post(f"/approvals/{waiting['id']}/decline", json={}).status_code == 200
    )
    assert willpower(other, gunman)["willpower"]["value"] == full


def test_willpower_spent_comes_back_if_the_purchase_is_withdrawn(
    troupe: Troupe, other: Person, elder: str, gunman: str
) -> None:
    added(troupe, ELDERS_MODERN_SKILLS)
    full = willpower(other, gunman)["willpower"]["value"]
    take(troupe.player, elder, "skills", "Firearms", 1, teacher_id=gunman)
    [waiting] = queue(troupe)
    [asked] = other.client.get(f"/characters/{gunman}/teaching").json()["asked"]
    other.client.post(f"/teachings/{asked['id']}/confirm")
    assert willpower(other, gunman)["willpower"]["value"] == full - 1

    withdrawn = troupe.player.client.delete(f"/characters/{elder}/disciplines/{waiting['id']}")

    assert withdrawn.status_code == 204, withdrawn.text
    assert willpower(other, gunman)["willpower"]["value"] == full
    assert other.client.get(f"/characters/{gunman}/teaching").json()["lent"] is None


def test_an_npc_teacher_of_the_troupe_spends_its_willpower_when_approved(
    troupe: Troupe, elder: str, session: Session
) -> None:
    added(troupe, ELDERS_MODERN_SKILLS)
    made = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/npcs", json={"name": "Sergeant Hale", "splat": "vampire"}
    )
    assert made.status_code == 201, made.text
    hale = made.json()["id"]
    given = troupe.storyteller.client.put(
        f"/characters/{hale}/npc/ratings",
        json={"category": "skills", "name": "Firearms", "rating": 3},
    )
    assert given.status_code == 200, given.text
    full = willpower(troupe.storyteller, hale)["willpower"]["value"]

    taught = take(troupe.player, elder, "skills", "Firearms", 1, teacher_id=hale)
    assert taught.status_code == 200, taught.text
    [waiting] = queue(troupe)
    approved = troupe.lead.client.post(f"/approvals/{waiting['id']}/approve", json={})

    assert approved.status_code == 200, approved.text
    assert willpower(troupe.storyteller, hale)["willpower"]["value"] == full - 1
