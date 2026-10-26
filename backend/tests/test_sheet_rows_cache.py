"""A character's sheet rows are read once per session until something could
change them: then they are read afresh."""

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, event, select
from sqlalchemy.orm import ORMExecuteState, Session

from horatio import sheets
from horatio.models import Character, CharacterTrait, TraitCategory, TraitDefinition
from tests.api_helpers import Troupe, new_character


@pytest.fixture
def character(client_for: Callable[[], TestClient], session: Session) -> Character:
    troupe = Troupe(client_for, session)
    return session.get_one(Character, uuid.UUID(new_character(troupe, troupe.player)))


@pytest.fixture
def reads(session: Session) -> list[int]:
    """How many times the sheet's rows are asked of the database."""
    counted: list[int] = []

    def count(state: ORMExecuteState) -> None:
        if state.is_select and "character_traits" in str(state.statement):
            counted.append(1)

    event.listen(session, "do_orm_execute", count)
    return counted


def names(db: Session, character: Character) -> list[str]:
    return [r.definition.name for r in sheets.sheet_rows(db, character)]


def brawl(session: Session) -> TraitDefinition:
    return session.scalars(
        select(TraitDefinition)
        .join(TraitCategory)
        .where(TraitCategory.key == "skills", TraitDefinition.name == "Brawl")
    ).one()


def test_the_rows_are_read_once(session: Session, character: Character, reads: list[int]) -> None:
    first = names(session, character)
    assert names(session, character) == first
    assert len(reads) == 1


def test_a_trait_added_is_found(session: Session, character: Character, reads: list[int]) -> None:
    assert "Brawl" not in names(session, character)
    session.add(
        CharacterTrait(character_id=character.id, trait_definition_id=brawl(session).id, rating=1)
    )
    assert "Brawl" in names(session, character)
    assert "Brawl" in names(session, character)
    assert len(reads) == 2


def test_a_trait_deleted_by_a_statement_is_gone(session: Session, character: Character) -> None:
    session.add(
        CharacterTrait(character_id=character.id, trait_definition_id=brawl(session).id, rating=1)
    )
    assert "Brawl" in names(session, character)
    session.execute(
        delete(CharacterTrait).where(CharacterTrait.trait_definition_id == brawl(session).id)
    )
    assert "Brawl" not in names(session, character)


def test_a_trait_rolled_back_is_gone(session: Session, character: Character) -> None:
    savepoint = session.begin_nested()
    session.add(
        CharacterTrait(character_id=character.id, trait_definition_id=brawl(session).id, rating=1)
    )
    assert "Brawl" in names(session, character)
    savepoint.rollback()
    assert "Brawl" not in names(session, character)


def test_expired_rows_are_read_again(
    session: Session, character: Character, reads: list[int]
) -> None:
    names(session, character)
    session.expire_all()
    names(session, character)
    assert len(reads) == 2
