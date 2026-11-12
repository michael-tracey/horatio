"""Lesser Harpies, or talons (horatio.boon_talons, #689): the troupe's setting, and who
the Harpy gives access to the boon ledger, with what each may do. The Harpy gives,
changes and takes away access as their character, from the Play View; the troupe's
running staff see who has what, and may take it away."""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from horatio import boon_talons, boons
from horatio.api.downtimes import staff_troupe
from horatio.api.troupes import TroupeOut, troupe_out
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, Troupe, User
from horatio.permissions import TroupeAction

router = APIRouter(tags=["boons"])

TalonWord = Literal["Lesser Harpies", "Talons"]


class BoonTalonsSettingIn(BaseModel):
    # The Harpy may give others access to the ledger.
    on: bool
    # What the troupe calls them.
    word: TalonWord = "Lesser Harpies"


class TalonIn(BaseModel):
    can_add: bool = False
    can_edit: bool = False
    can_audit: bool = False


class TalonOut(BaseModel):
    character_id: uuid.UUID
    name: str
    can_add: bool
    can_edit: bool
    can_audit: bool
    # The Harpy who gave it, by their character's name; empty when staff did.
    given_by: str
    given_at: datetime
    # In play in the troupe now: retired, or gone from the troupe, they have no access.
    in_play: bool


class TalonChoice(BaseModel):
    id: uuid.UUID
    name: str
    # Holds the Lesser Harpy title in the troupe.
    lesser_harpy: bool


class BoonTalonsOut(BaseModel):
    troupe_id: uuid.UUID
    # The Harpy may give others access now (the setting is on, and the Harpy has the
    # full ledger).
    enabled: bool
    # What the troupe calls them: "Lesser Harpies" or "Talons".
    word: TalonWord
    # "harpy" (gives, changes and takes away access) or "staff" (sees, takes away).
    role: Literal["harpy", "staff"]
    talons: list[TalonOut]
    # Who the Harpy may give access: Lesser Harpy title holders first.
    choices: list[TalonChoice]


def manager(db: DbSession, user: User, troupe_id: uuid.UUID) -> tuple[Troupe, Character | None]:
    """The troupe, and who manages its Lesser Harpies: its running staff (None), or
    the user's Harpy in it while the Harpy may give access. Refused as staff's pages
    refuse anyone else."""
    troupe = db.get(Troupe, troupe_id)
    if troupe is not None and boons.can_manage(db, user, troupe):
        if not boons.tracked(troupe):
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "This troupe doesn't keep a boon ledger."
            )
        return troupe, None
    harpy = boon_talons.giver(db, user, troupe) if troupe is not None else None
    if troupe is None or harpy is None:
        staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_BOONS)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    return troupe, harpy


def talons_out(db: DbSession, troupe: Troupe, harpy: Character | None) -> BoonTalonsOut:
    return BoonTalonsOut(
        troupe_id=troupe.id,
        enabled=boon_talons.enabled(troupe),
        word=troupe.boon_talon_word,  # type: ignore[arg-type]  # checked by the database
        role="staff" if harpy is None else "harpy",
        talons=[
            TalonOut(
                character_id=t.character.id,
                name=t.character.name,
                can_add=t.talon.can_add,
                can_edit=t.talon.can_edit,
                can_audit=t.talon.can_audit,
                given_by=t.given_by,
                given_at=t.talon.created_at,
                in_play=t.in_play,
            )
            for t in boon_talons.listed(db, troupe)
        ],
        choices=[
            TalonChoice(id=c.id, name=c.name, lesser_harpy=lesser)
            for c, lesser in boon_talons.candidates(db, troupe)
        ]
        if harpy is not None
        else [],
    )


@router.put("/troupes/{troupe_id}/boon-talons-setting")
def set_boon_talons(
    troupe_id: uuid.UUID, body: BoonTalonsSettingIn, db: DbSession, user: CurrentUser
) -> TroupeOut:
    """Whether the troupe's Harpy may give others access to its boon ledger (#689),
    and what it calls them. Only used while the Harpy has the full ledger."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    boon_talons.set_setting(db, user, troupe, body.on, body.word)
    db.commit()
    return troupe_out(db, user, troupe)


@router.get("/troupes/{troupe_id}/boon-talons")
def boon_talons_list(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> BoonTalonsOut:
    """Who has access to the ledger as a Lesser Harpy, with what each may do: for the
    Harpy, who gives it, and for the troupe's running staff."""
    troupe, harpy = manager(db, user, troupe_id)
    return talons_out(db, troupe, harpy)


@router.put("/troupes/{troupe_id}/boon-talons/{character_id}")
def give_talon(
    troupe_id: uuid.UUID, character_id: uuid.UUID, body: TalonIn, db: DbSession, user: CurrentUser
) -> BoonTalonsOut:
    """The Harpy gives a character access to the ledger, or changes what it allows,
    as their character. Logged."""
    troupe, harpy = manager(db, user, troupe_id)
    if harpy is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "The Harpy gives access to the ledger; staff can take it away.",
        )
    character = db.get(Character, character_id)
    if character is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such character.")
    boon_talons.give(
        db,
        user,
        troupe,
        character,
        add=body.can_add,
        edit=body.can_edit,
        audits=body.can_audit,
        by=harpy,
    )
    db.commit()
    return talons_out(db, troupe, harpy)


@router.delete("/troupes/{troupe_id}/boon-talons/{character_id}")
def take_talon(
    troupe_id: uuid.UUID, character_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> BoonTalonsOut:
    """Take a character's access to the ledger away: the Harpy, as their character, or
    the troupe's running staff. Logged."""
    troupe, harpy = manager(db, user, troupe_id)
    boon_talons.take_away(db, user, troupe, character_id, harpy)
    db.commit()
    return talons_out(db, troupe, harpy)
