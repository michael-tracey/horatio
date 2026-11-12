"""A troupe's sire lines, and each character's sire (horatio.sire_lines, issue #707)."""

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import sire_lines, social_age, whos_who
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, Troupe, TroupeMembership, User
from horatio.permissions import (
    TroupeAction,
    allows,
    can_edit_character,
    can_see_whos_who,
    troupe_role,
    visible_character,
)
from horatio.sheets import lock_character

router = APIRouter(tags=["sire lines"])


class SireLineNodeOut(BaseModel):
    # The character's id, or "named:…" for a sire known by name only.
    key: str
    character_id: uuid.UUID | None
    name: str
    clan: str | None
    generation: int | None
    # final_death, off_field or inactive for a retired character.
    left_reason: str | None
    retired: bool
    # "pc", "npc", "named" (a sire known by name only) or "elsewhere" (a sire outside
    # the troupe).
    kind: str
    sire_key: str | None


class SireLineClanCount(BaseModel):
    clan: str
    count: int


class SireLinesOut(BaseModel):
    troupe_id: uuid.UUID
    nodes: list[SireLineNodeOut]
    # How many of the tree's characters each clan has, for its colours.
    clans: list[SireLineClanCount]
    # The caller sees the troupe's every character, as its staff.
    staff: bool
    # The troupe shows its sire lines to its players.
    players_see: bool


class CharacterSireOut(BaseModel):
    character_id: uuid.UUID | None
    # The linked sire's name, or the name given.
    name: str
    clan: str
    secret: bool
    # Whether the caller may change it.
    can_change: bool


class CharacterSireIn(BaseModel):
    # A character in Horatio, or else a name with its clan; neither for none.
    character_id: uuid.UUID | None = None
    name: str = Field(default="", max_length=sire_lines.NAME_LENGTH)
    clan: str = Field(default="", max_length=sire_lines.NAME_LENGTH)
    secret: bool = False


class SireLineChoiceOut(BaseModel):
    character_id: uuid.UUID
    name: str
    clan: str | None


def is_running_staff(db: Session, user: User, troupe: Troupe | None) -> bool:
    return troupe is not None and allows(
        troupe_role(db, user, troupe),
        TroupeAction.VIEW_MEMBER_CHARACTERS,
        is_custodian=user.is_custodian,
    )


def home_of(db: Session, character: Character) -> Troupe | None:
    troupe_id = character.home_troupe_id or character.owner_troupe_id
    return db.get(Troupe, troupe_id) if troupe_id else None


def may_change(db: Session, user: User, character: Character) -> bool:
    """Its player while it is active, an NPC's troupe staff, or its home troupe's
    storytellers and assistant storytellers, at any time."""
    if character.splat != sire_lines.VAMPIRE:
        return False
    if user.is_custodian:
        return True
    if character.status == "active" and can_edit_character(db, user, character):
        return True
    home = home_of(db, character)
    return home is not None and allows(troupe_role(db, user, home), TroupeAction.APPROVE_CHANGES)


@router.get("/troupes/{troupe_id}/sire-lines")
def read_sire_lines(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> SireLinesOut:
    """Who sired whom: every vampire in the troupe for its staff; for its players, if
    the troupe shows them, those on its Who's Who with the sires it shows."""
    troupe = db.get(Troupe, troupe_id)
    if troupe is None or not can_see_whos_who(db, user, troupe):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    staff = is_running_staff(db, user, troupe)
    if not staff and not troupe.sire_lines_players:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "The troupe shows its sire lines to its staff only."
        )
    nodes = sire_lines.staff_forest(db, troupe) if staff else sire_lines.player_forest(db, troupe)
    counts = sire_lines.clan_counts(nodes)
    return SireLinesOut(
        troupe_id=troupe.id,
        nodes=[SireLineNodeOut(**n.__dict__) for n in nodes],
        clans=[SireLineClanCount(clan=c, count=n) for c, n in sorted(counts.items())],
        staff=staff,
        players_see=troupe.sire_lines_players,
    )


def sire_out(db: Session, user: User, character: Character) -> CharacterSireOut:
    """The sire, unless it is kept secret from the caller: one kept from players shows
    only to those who may change it and to the home troupe's staff."""
    can_change = may_change(db, user, character)
    if (
        character.sire_secret
        and not can_change
        and not is_running_staff(db, user, home_of(db, character))
    ):
        return CharacterSireOut(character_id=None, name="", clan="", secret=True, can_change=False)
    linked = db.get(Character, character.sire_id) if character.sire_id else None
    return CharacterSireOut(
        character_id=linked.id if linked else None,
        name=linked.name if linked else character.sire_name,
        clan=(social_age.standings(db, [linked.id])[linked.id].clan or "")
        if linked
        else character.sire_clan,
        secret=character.sire_secret,
        can_change=can_change,
    )


@router.get("/characters/{character_id}/sire")
def read_sire(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> CharacterSireOut:
    """The character's sire, as anyone who sees the character sees it."""
    return sire_out(db, user, visible_character(db, user, character_id))


@router.put("/characters/{character_id}/sire")
def set_sire(
    character_id: uuid.UUID, body: CharacterSireIn, db: DbSession, user: CurrentUser
) -> CharacterSireOut:
    """Give the character its sire: a character the caller can see, or a name and
    clan; and whether the troupe's players see it."""
    character = visible_character(db, user, character_id)
    if not may_change(db, user, character):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only the character's player, or its troupe's storytellers, give its sire.",
        )
    character = lock_character(db, character.id)
    sire = None
    if body.character_id is not None:
        sire = next((c for c in candidates(db, user, character) if c.id == body.character_id), None)
        if sire is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such character to be the sire.")
    home = home_of(db, character)
    by_staff = user.is_custodian or (
        home is not None and allows(troupe_role(db, user, home), TroupeAction.APPROVE_CHANGES)
    )
    sire_lines.set_sire(
        db,
        user,
        character,
        sire=sire,
        name=body.name,
        clan=body.clan,
        secret=body.secret,
        by_player=not by_staff,
    )
    db.commit()
    return sire_out(db, user, character)


def candidates(db: Session, user: User, character: Character) -> list[Character]:
    """The vampires that could be the character's sire: those on its home troupe's
    Who's Who, and for that troupe's staff every vampire in it."""
    home = home_of(db, character)
    if home is None:
        return []
    if is_running_staff(db, user, home):
        found = list(
            db.scalars(
                select(Character)
                .join(TroupeMembership, TroupeMembership.character_id == Character.id)
                .where(TroupeMembership.troupe_id == home.id, TroupeMembership.left_at.is_(None))
                .order_by(Character.name, Character.id)
            )
        )
    else:
        found = [e.character for e in whos_who.whos_who(db, home).entries]
    return [c for c in found if c.id != character.id and c.splat == sire_lines.VAMPIRE]


@router.get("/characters/{character_id}/sire/choices")
def sire_choices(
    character_id: uuid.UUID, db: DbSession, user: CurrentUser, q: str = ""
) -> list[SireLineChoiceOut]:
    """The vampires that could be the character's sire, by name (`candidates`)."""
    character = visible_character(db, user, character_id)
    if not may_change(db, user, character):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't give this character's sire.")
    wanted = q.strip().casefold()
    found = [
        c for c in candidates(db, user, character) if not wanted or wanted in c.name.casefold()
    ][:50]
    standing = social_age.standings(db, [c.id for c in found])
    return [
        SireLineChoiceOut(character_id=c.id, name=c.name, clan=standing[c.id].clan) for c in found
    ]
