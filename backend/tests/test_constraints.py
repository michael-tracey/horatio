"""The rules the database itself enforces, so the application cannot break them."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from horatio.models import Character, Troupe, TroupeMembership, TroupeStaff, User


def make_user(session: Session, email: str = "player@example.com") -> User:
    user = User(email=email, display_name=email.split("@")[0])
    session.add(user)
    session.flush()
    return user


def make_troupe(session: Session, lead: User) -> Troupe:
    troupe = Troupe(name="Lords of the Night", lead_user_id=lead.id)
    session.add(troupe)
    session.flush()
    return troupe


def make_character(session: Session, player: User) -> Character:
    character = Character(player_id=player.id, splat="vampire", name="Agnes")
    session.add(character)
    session.flush()
    return character


def test_emails_are_unique_regardless_of_case(session: Session) -> None:
    make_user(session, "Player@Example.com")

    with pytest.raises(IntegrityError):
        make_user(session, "player@example.com")


def test_a_troupe_cannot_exist_without_a_lead_storyteller(session: Session) -> None:
    session.add(Troupe(name="Leaderless"))

    with pytest.raises(IntegrityError):
        session.flush()


def test_a_user_holds_one_staff_role_per_troupe(session: Session) -> None:
    lead = make_user(session, "lead@example.com")
    troupe = make_troupe(session, lead)
    staff = make_user(session, "staff@example.com")
    session.add(TroupeStaff(troupe_id=troupe.id, user_id=staff.id, role="narrator"))
    session.flush()

    session.add(TroupeStaff(troupe_id=troupe.id, user_id=staff.id, role="storyteller"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_staff_roles_are_limited_to_the_known_ones(session: Session) -> None:
    lead = make_user(session, "lead@example.com")
    troupe = make_troupe(session, lead)
    session.add(TroupeStaff(troupe_id=troupe.id, user_id=lead.id, role="lead_storyteller"))

    with pytest.raises(IntegrityError):
        session.flush()


def test_new_characters_start_as_drafts(session: Session) -> None:
    character = make_character(session, make_user(session))
    session.refresh(character)

    assert character.status == "draft"


def test_character_status_is_limited_to_the_known_ones(session: Session) -> None:
    character = make_character(session, make_user(session))
    character.status = "deleted"

    with pytest.raises(IntegrityError):
        session.flush()


def test_a_character_is_a_current_member_of_a_troupe_only_once(session: Session) -> None:
    player = make_user(session)
    troupe = make_troupe(session, player)
    character = make_character(session, player)
    session.add(TroupeMembership(troupe_id=troupe.id, character_id=character.id))
    session.flush()

    session.add(TroupeMembership(troupe_id=troupe.id, character_id=character.id))
    with pytest.raises(IntegrityError):
        session.flush()


def test_a_character_can_rejoin_a_troupe_it_left(session: Session) -> None:
    player = make_user(session)
    troupe = make_troupe(session, player)
    character = make_character(session, player)
    joined = datetime.now(UTC) - timedelta(days=30)
    session.add(
        TroupeMembership(
            troupe_id=troupe.id,
            character_id=character.id,
            joined_at=joined,
            left_at=joined + timedelta(days=1),
        )
    )
    session.add(TroupeMembership(troupe_id=troupe.id, character_id=character.id))

    session.flush()


def test_ids_are_generated_by_the_database_in_creation_order(session: Session) -> None:
    first = make_user(session, "first@example.com")
    second = make_user(session, "second@example.com")

    assert first.id.version == 7
    assert first.id < second.id
