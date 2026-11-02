"""Free changes for new characters (horatio.free_changes, issue #439): none (locked on
acceptance, the default), by date or by games played; refunds in full while open,
still judged by the checks and reviewed by the home troupe; the traits a troupe
excludes; and how they end."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from horatio import free_changes
from horatio.models import (
    AuditEvent,
    Character,
    CharacterTrait,
    GameAttendance,
    Notification,
    SheetVersion,
    TraitDefinition,
)
from horatio.models import Troupe as TroupeRecord
from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_checkin import check_in, game
from tests.test_api_merit_requests import balance, held, line, queue, rating, sheet, spend
from tests.test_api_owed_actions import member_with
from tests.test_api_quests import give, ok

pytestmark = pytest.mark.usefixtures("without_bank")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def set_free_changes(
    troupe: Troupe,
    kind: str,
    *,
    days: int = 30,
    games: int = 3,
    excluded: tuple[tuple[str, str], ...] = (),
    person: Person | None = None,
) -> Any:
    return (person or troupe.lead).client.put(
        f"/troupes/{troupe.id}/free-changes",
        json={
            "kind": kind,
            "days": days,
            "games": games,
            "excluded": [{"category": c, "name": n} for c, n in excluded],
        },
    )


def accepted(troupe: Troupe, name: str = "Agnes", *, brawl: int = 3) -> str:
    """A character that bought Brawl with XP while it was built, then accepted home."""
    character_id = new_character(troupe, troupe.player, name)
    ok(
        troupe.player.client.put(
            f"/characters/{character_id}/traits",
            json={"category": "skills", "name": "Brawl", "rating": brawl},
        )
    )
    asked = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    )
    assert asked.status_code == 201, asked.text
    ok(troupe.lead.client.post(f"/approvals/{asked.json()['id']}/approve", json={}))
    return character_id


def accepted_days_ago(troupe: Troupe, character_id: str, days: int) -> None:
    """Move the character's acceptance back, as if it had been `days` days ago, with the
    troupe's free changes on since then."""
    at = datetime.now(UTC) - timedelta(days=days)
    session = troupe.session
    session.execute(
        update(SheetVersion)
        .where(SheetVersion.character_id == uuid.UUID(character_id))
        .values(approved_at=at)
    )
    record = session.get_one(TroupeRecord, uuid.UUID(troupe.id))
    if record.free_changes_since is not None and record.free_changes_since > at:
        record.free_changes_since = at
    session.flush()
    session.expire_all()


def review_queue(person: Person, troupe: Troupe, state: str = "pending") -> list[dict[str, Any]]:
    return ok(
        person.client.get(
            f"/troupes/{troupe.id}/approvals", params={"state": state, "kind": "review"}
        )
    )


def messages(troupe: Troupe, person: Person) -> list[str]:
    return list(
        troupe.session.scalars(
            select(Notification.summary).where(
                Notification.user_id == uuid.UUID(person.id),
                Notification.kind == "character.free_changes_ended",
            )
        )
    )


def logged(troupe: Troupe, action: str) -> list[dict[str, Any]]:
    return [
        e.data
        for e in troupe.session.scalars(
            select(AuditEvent).where(AuditEvent.action == action).order_by(AuditEvent.id)
        )
    ]


def award(troupe: Troupe, character_id: str, amount: int) -> None:
    given = troupe.lead.client.post(
        f"/characters/{character_id}/xp", json={"amount": amount, "reason": "Game"}
    )
    assert given.status_code == 201, given.text


def lower(troupe: Troupe, character_id: str, to: int) -> dict[str, Any]:
    return line(spend(troupe.player, character_id, rating("skills", "Brawl", to)))


# --- None, the default -----------------------------------------------------------


def test_with_no_free_changes_a_character_is_locked_on_acceptance(troupe: Troupe) -> None:
    agnes = accepted(troupe)
    found = ok(troupe.storyteller.client.get(f"/troupes/{troupe.id}/free-changes"))
    assert (found["kind"], found["text"]) == ("none", free_changes.LOCKED_TEXT)

    refused = lower(troupe, agnes, 1)

    assert refused["refused"] == (
        "Brawl was accepted at 3. Only storytellers can take accepted dots away."
    )
    mine = sheet(troupe.player, agnes)
    assert mine["free_changes"] is None
    assert next(t for t in mine["traits"] if t["name"] == "Brawl")["min_rating"] == 3
    # The House rules tab says nothing of it.
    rules = ok(troupe.player.client.get(f"/troupes/{troupe.id}/house-rules"))
    assert "Free changes for new characters" not in [s["name"] for s in rules["other"]]


# --- By date ---------------------------------------------------------------------


def test_by_date_a_trait_lowered_refunds_its_full_xp_and_waits_for_review(
    troupe: Troupe,
) -> None:
    ok(set_free_changes(troupe, "date", days=30))
    agnes = accepted(troupe)
    mine = sheet(troupe.player, agnes)
    assert mine["free_changes"]["kind"] == "date"
    assert mine["free_changes"]["games_left"] is None
    ends = datetime.fromisoformat(mine["free_changes"]["ends_at"])
    assert timedelta(days=29) < ends - datetime.now(UTC) <= timedelta(days=30)
    # The sheet lets it go down to its free dots.
    assert next(t for t in mine["traits"] if t["name"] == "Brawl")["min_rating"] == 0
    start = balance(troupe.player, agnes)
    quoted = ok(
        troupe.player.client.post(
            f"/characters/{agnes}/quote",
            json={"category": "skills", "name": "Brawl", "rating": 0},
        )
    )

    removed = lower(troupe, agnes, 0)

    # Its full cost back, as during creation.
    assert removed["refused"] is None
    assert removed["cost"] == quoted["cost"] < 0
    assert removed["needs_approval"] is True
    assert removed["because"] == (
        f"A free change: {-quoted['cost']} XP back, which the home troupe reviews."
    )
    assert balance(troupe.player, agnes) == start - quoted["cost"]
    assert "Brawl" not in held(troupe.player, agnes)
    [waiting] = sheet(troupe.player, agnes)["pending_disciplines"]
    assert (waiting["kind"], waiting["free_change"], waiting["cost"]) == (
        "review",
        True,
        quoted["cost"],
    )
    # Staff see it in their queue and bell.
    [request] = review_queue(troupe.storyteller, troupe)
    assert request["discipline"]["free_change"] is True
    assert (request["discipline"]["from_rating"], request["discipline"]["to_rating"]) == (3, 0)
    assert request["player_note"] == free_changes.REVIEW_NOTE
    bell = ok(troupe.storyteller.client.get("/notifications"))
    summaries = [i["summary"] for i in (bell["items"] if isinstance(bell, dict) else bell)]
    assert f"Agnes lowered Brawl 3 → 0 as a free change ({-quoted['cost']} XP back)" in summaries
    [entry] = logged(troupe, "sheet.free_change")
    assert (entry["name"], entry["from_rating"], entry["to_rating"], entry["refund"]) == (
        "Brawl",
        3,
        0,
        -quoted["cost"],
    )

    ok(troupe.storyteller.client.post(f"/approvals/{request['id']}/approve", json={}))

    assert "Brawl" not in held(troupe.player, agnes)
    assert balance(troupe.player, agnes) == start - quoted["cost"]
    # Bought back later, it is an ordinary purchase from nothing.
    bought = lower(troupe, agnes, 1)
    assert (bought["refused"], bought["needs_approval"]) == (None, False)


def test_declining_a_free_change_puts_the_dots_and_the_xp_back(troupe: Troupe) -> None:
    ok(set_free_changes(troupe, "date", days=30))
    agnes = accepted(troupe)
    start = balance(troupe.player, agnes)
    lower(troupe, agnes, 1)
    [request] = review_queue(troupe.storyteller, troupe)

    ok(troupe.storyteller.client.post(f"/approvals/{request['id']}/decline", json={"note": "No"}))

    assert held(troupe.player, agnes)["Brawl"] == 3
    assert balance(troupe.player, agnes) == start

    # Removed altogether and withdrawn, it comes back too.
    lower(troupe, agnes, 0)
    [request] = review_queue(troupe.storyteller, troupe)
    withdrawn = troupe.player.client.delete(f"/characters/{agnes}/disciplines/{request['id']}")
    assert withdrawn.status_code == 204, withdrawn.text
    assert held(troupe.player, agnes)["Brawl"] == 3
    assert balance(troupe.player, agnes) == start


def test_a_date_window_closes_d_days_after_acceptance(troupe: Troupe) -> None:
    ok(set_free_changes(troupe, "date", days=14))
    agnes = accepted(troupe)
    accepted_days_ago(troupe, agnes, 13)
    assert sheet(troupe.player, agnes)["free_changes"] is not None
    # Nothing is due yet.
    assert free_changes.close_due(troupe.session) == 0

    accepted_days_ago(troupe, agnes, 15)

    # Shut at once, before anyone notices it has ended.
    assert sheet(troupe.player, agnes)["free_changes"] is None
    assert lower(troupe, agnes, 1)["refused"] == (
        "Brawl was accepted at 3. Only storytellers can take accepted dots away."
    )
    # The delivery worker notices, and tells the player once.
    assert free_changes.close_due(troupe.session) == 1
    assert free_changes.close_due(troupe.session) == 0
    assert messages(troupe, troupe.player) == [
        "Agnes's free changes have ended (14 days after acceptance): the troupe's normal"
        " rules for lowering and removing traits apply now"
    ]
    character = troupe.session.get_one(Character, uuid.UUID(agnes))
    assert character.free_changes_ended_at is not None
    [ended] = logged(troupe, "character.free_changes_ended")
    assert ended["why"] == "14 days after acceptance"


# --- By games played -------------------------------------------------------------


def test_a_games_window_closes_after_n_attended_games(troupe: Troupe) -> None:
    ok(set_free_changes(troupe, "games", games=2))
    agnes = accepted(troupe)
    assert sheet(troupe.player, agnes)["free_changes"] == {
        "kind": "games",
        "ends_at": None,
        "games_left": 2,
        "excluded": [],
    }

    ok(check_in(troupe.assistant, troupe, game(troupe), agnes))
    assert sheet(troupe.player, agnes)["free_changes"]["games_left"] == 1
    assert messages(troupe, troupe.player) == []

    ok(check_in(troupe.assistant, troupe, game(troupe, timedelta(hours=2)), agnes))

    assert sheet(troupe.player, agnes)["free_changes"] is None
    assert messages(troupe, troupe.player) == [
        "Agnes's free changes have ended (2 games attended): the troupe's normal rules for"
        " lowering and removing traits apply now"
    ]
    assert lower(troupe, agnes, 1)["refused"] is not None


def test_absentee_games_do_not_count_toward_a_games_window(troupe: Troupe) -> None:
    ok(set_free_changes(troupe, "games", games=1))
    agnes = accepted(troupe)
    missed = game(troupe)
    # A game missed and recorded as absentee (issue #438) is not one attended.
    troupe.session.add(
        GameAttendance(
            game_id=uuid.UUID(missed),
            character_id=uuid.UUID(agnes),
            checked_in_by=uuid.UUID(troupe.assistant.id),
            by_staff=True,
            kind="absentee",
        )
    )
    troupe.session.flush()

    assert sheet(troupe.player, agnes)["free_changes"]["games_left"] == 1
    assert lower(troupe, agnes, 2)["refused"] is None


# --- Changing the setting --------------------------------------------------------


def test_changing_the_setting_applies_to_open_windows_as_they_stand(troupe: Troupe) -> None:
    ok(set_free_changes(troupe, "date", days=30))
    agnes = accepted(troupe, "Agnes")
    accepted_days_ago(troupe, agnes, 10)
    bea = accepted(troupe, "Beatrix")
    ok(check_in(troupe.assistant, troupe, game(troupe), bea))

    # To games: worked out from attendance as it stands.
    ok(set_free_changes(troupe, "games", games=3))
    assert sheet(troupe.player, agnes)["free_changes"]["games_left"] == 3
    assert sheet(troupe.player, bea)["free_changes"]["games_left"] == 2

    # Back to fewer days than Agnes has had: hers end, and her player is told.
    found = ok(set_free_changes(troupe, "date", days=7))
    assert found["text"] == "For 7 days after the troupe accepts a character"
    assert sheet(troupe.player, agnes)["free_changes"] is None
    assert sheet(troupe.player, bea)["free_changes"]["kind"] == "date"
    assert messages(troupe, troupe.player) == [
        "Agnes's free changes have ended (the troupe changed them): the troupe's normal rules"
        " for lowering and removing traits apply now"
    ]
    # More days later don't bring hers back: they have ended.
    ok(set_free_changes(troupe, "date", days=60))
    assert sheet(troupe.player, agnes)["free_changes"] is None

    # Off: every open window ends.
    ok(set_free_changes(troupe, "none"))
    assert sheet(troupe.player, bea)["free_changes"] is None
    assert len(messages(troupe, troupe.player)) == 2
    assert [e["setting"] for e in logged(troupe, "house.free_changes")] == [
        "For 30 days after the troupe accepts a character",
        "Until a character has attended 3 games after the troupe accepts it",
        "For 7 days after the troupe accepts a character",
        "For 60 days after the troupe accepts a character",
        free_changes.LOCKED_TEXT,
    ]


def test_turning_free_changes_on_gives_none_to_characters_already_accepted(
    troupe: Troupe,
) -> None:
    agnes = accepted(troupe, "Agnes")
    accepted_days_ago(troupe, agnes, 1)

    ok(set_free_changes(troupe, "games", games=3))
    bea = accepted(troupe, "Beatrix")

    assert sheet(troupe.player, agnes)["free_changes"] is None
    assert sheet(troupe.player, bea)["free_changes"]["games_left"] == 3
    assert messages(troupe, troupe.player) == []


def test_only_storytellers_set_free_changes_and_only_catalogue_traits_are_excluded(
    troupe: Troupe,
) -> None:
    assert set_free_changes(troupe, "date", person=troupe.assistant).status_code == 403
    unknown = set_free_changes(troupe, "date", excluded=(("merits", "Nonesuch"),))
    assert unknown.status_code == 422
    assert set_free_changes(troupe, "date", days=0).status_code == 422


# --- Exclusions, merits and flaws ------------------------------------------------


def test_excluded_traits_follow_the_normal_rules_in_the_window(troupe: Troupe) -> None:
    ok(
        set_free_changes(
            troupe,
            "games",
            excluded=(("merits", "Efficient Learner"), ("merits", "Arcane")),
        )
    )
    agnes = member_with(troupe, "Agnes", "Toreador")
    ok(
        troupe.lead.client.post(f"/characters/{agnes}/xp", json={"amount": 20, "reason": "Game"}),
        201,
    )
    for merit in ("Efficient Learner", "Rugged"):
        spend(troupe.player, agnes, rating("merits", merit, 2 if merit != "Rugged" else 3))
    for request in queue(troupe.storyteller, troupe):
        ok(troupe.storyteller.client.post(f"/approvals/{request['id']}/approve", json={}))
    assert sheet(troupe.player, agnes)["free_changes"]["excluded"] == [
        "Arcane",
        "Efficient Learner",
    ]
    start = balance(troupe.player, agnes)

    kept = line(spend(troupe.player, agnes, rating("merits", "Efficient Learner", 0)))
    refunded = line(spend(troupe.player, agnes, rating("merits", "Rugged", 0)))

    # Excluded: asked as ever, with nothing back.
    assert kept["because"] == (
        "Asked of the home troupe: removing a merit gives no XP back (MET: VTM p. 236)."
    )
    # Not excluded: its full cost back once approved.
    assert (
        refunded["because"]
        == "Asked of the home troupe as a free change: 3 XP back once they approve."
    )
    for request in queue(troupe.storyteller, troupe):
        ok(troupe.storyteller.client.post(f"/approvals/{request['id']}/approve", json={}))
    assert {"Efficient Learner", "Rugged"}.isdisjoint(held(troupe.player, agnes))
    assert balance(troupe.player, agnes) == start + 3
    [entry] = logged(troupe, "sheet.free_change")
    assert (entry["name"], entry["refund"]) == ("Rugged", 3)


def test_a_flaw_is_bought_off_for_what_it_gave_in_the_window(troupe: Troupe) -> None:
    ok(set_free_changes(troupe, "date"))
    agnes = member_with(troupe, "Agnes", "Toreador", ("flaws", "Dark Fate", 4))
    ok(
        troupe.lead.client.post(f"/characters/{agnes}/xp", json={"amount": 20, "reason": "Game"}),
        201,
    )
    start = balance(troupe.player, agnes)

    points = held(troupe.player, agnes)["Dark Fate"]
    assert points

    asked = line(spend(troupe.player, agnes, rating("flaws", "Dark Fate", 0)))

    # Once what it gave, not twice (MET: VTM p. 236).
    assert asked["cost"] == points
    assert asked["because"] == (
        f"Asked of the home troupe as a free change: buying it off costs {points} XP, what it"
        " gave, held until they decide."
    )
    [request] = queue(troupe.storyteller, troupe)
    ok(troupe.storyteller.client.post(f"/approvals/{request['id']}/approve", json={}))
    assert "Dark Fate" not in held(troupe.player, agnes)
    assert balance(troupe.player, agnes) == start - points


# --- Still book-legal ------------------------------------------------------------


def test_free_changes_are_still_judged_by_the_checks(troupe: Troupe) -> None:
    ok(set_free_changes(troupe, "date"))
    agnes = accepted(troupe)
    brawl = troupe.session.scalars(
        select(CharacterTrait)
        .join(TraitDefinition, CharacterTrait.trait_definition_id == TraitDefinition.id)
        .where(CharacterTrait.character_id == uuid.UUID(agnes), TraitDefinition.name == "Brawl")
    ).one()
    brawl.free_rating = 1
    troupe.session.flush()

    # Free dots from creation stay: only XP comes back.
    row = next(t for t in sheet(troupe.player, agnes)["traits"] if t["name"] == "Brawl")
    assert row["min_rating"] == row["free_rating"] == 1
    assert lower(troupe, agnes, 0)["refused"] == "A rating cannot go below its free dots."
    # Traits chosen only during creation stay as they were accepted.
    generation = line(spend(troupe.player, agnes, rating("backgrounds", "Generation", 2)))
    assert (
        generation["refused"]
        == "Generation can't change once a home troupe has accepted the character."
    )
    # Merits that stand for the Embrace, clan or bloodline stay.
    give(troupe.session, agnes, "merits", "Inceptor", 2)
    gone = line(spend(troupe.player, agnes, rating("merits", "Inceptor", 0)))
    assert "can't be removed" in gone["refused"]
    assert review_queue(troupe.storyteller, troupe) == []


def test_the_house_rules_tab_describes_free_changes(troupe: Troupe) -> None:
    ok(set_free_changes(troupe, "games", games=3, excluded=(("merits", "Arcane"),)))

    rules = ok(troupe.player.client.get(f"/troupes/{troupe.id}/house-rules"))

    [found] = [s for s in rules["other"] if s["name"] == "Free changes for new characters"]
    assert found["text"] == (
        "Until a character has attended 3 games after the troupe accepts it, lowering or"
        " removing a trait refunds its full XP, as during creation, and the troupe reviews"
        " each change; never for Arcane"
    )
    assert found["book_text"] == free_changes.LOCKED_TEXT
    [entry] = logged(troupe, "house.free_changes")
    assert entry["excluded"] == "Arcane"
