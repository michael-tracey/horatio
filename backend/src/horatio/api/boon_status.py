"""Status the book ties to boons, from the boon ledger (#694; horatio.boon_status): the
boon an apology owes for a slip under Warned or Disgraced, for staff to register;
and, for spending Praised, who isn't already in the character's debt."""

import uuid
from datetime import date

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from horatio import boon_status, boons
from horatio.api.boons import BoonOut, BoonPartyIn, choices, full_out, play_ledger, side
from horatio.api.influence_log import CharacterChoice
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, Troupe, User
from horatio.permissions import visible_character

router = APIRouter(tags=["boons"])


class ApologyChoicesOut(BaseModel):
    """Where an apology's boon goes: the troupe whose ledger the character's Play
    View shows, and its characters, to name whoever was wronged."""

    troupe_id: uuid.UUID
    troupe_name: str
    characters: list[CharacterChoice]


class ApologyBoonIn(BaseModel):
    # The Warned or Disgraced the slip was under.
    held_id: uuid.UUID
    # Whoever was wronged: a character in the troupe, or a name only.
    wronged: BoonPartyIn
    # The in-game night of the apology.
    made_on: date
    # Left empty: "An apology for a slip while Warned".
    reason: str = Field(default="", max_length=boons.LONGEST_TEXT)


class PraisedClaimsOut(BaseModel):
    troupe_id: uuid.UUID
    troupe_name: str
    # The sect that has Accepted the character; None if none has.
    sect: str | None
    # The troupe's characters in play Accepted by that sect who owe the character no
    # boon still standing.
    characters: list[CharacterChoice]


def apology_ledger(db: DbSession, user: User, character_id: uuid.UUID) -> tuple[Character, Troupe]:
    """The character, and the ledger an apology's boon goes in, for that troupe's
    running staff."""
    character = visible_character(db, user, character_id)
    troupe = boons.ledger_of(db, character)
    if troupe is None or not boons.can_manage(db, user, troupe):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No boon ledger here that you keep for this character."
        )
    return character, troupe


@router.get("/characters/{character_id}/apology-boon")
def apology_choices(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> ApologyChoicesOut:
    """For staff putting right a slip under Warned or Disgraced: the ledger its boon
    goes in, and who could have been wronged."""
    _, troupe = apology_ledger(db, user, character_id)
    return ApologyChoicesOut(
        troupe_id=troupe.id, troupe_name=troupe.name, characters=choices(db, troupe)
    )


@router.post("/characters/{character_id}/apology-boon", status_code=status.HTTP_201_CREATED)
def apology_boon(
    character_id: uuid.UUID, body: ApologyBoonIn, db: DbSession, user: CurrentUser
) -> BoonOut:
    """Register the boon an apology owes for a slip (p. 316): minor under Warned, major
    under Disgraced, owed by the character to whoever was wronged."""
    character, troupe = apology_ledger(db, user, character_id)
    row = boon_status.apology_status(db, character, body.held_id)
    wronged = side(db, troupe, body.wronged, "one wronged")
    made = boon_status.register_apology(
        db, user, troupe, character, row, wronged, body.made_on, body.reason
    )
    db.commit()
    return full_out(db, user, troupe, made)


@router.get("/characters/{character_id}/praised-claims")
def praised_claims(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> PraisedClaimsOut:
    """For spending Praised (p. 316): who in the troupe whose ledger the character's
    Play View shows is Accepted by its sect and not already in its debt. Its player
    sees player characters; staff see the troupe's NPCs too."""
    character, troupe = play_ledger(db, user, character_id)
    sect, found = boon_status.not_in_debt(
        db, troupe, character, players_only=not boons.can_manage(db, user, troupe)
    )
    return PraisedClaimsOut(
        troupe_id=troupe.id,
        troupe_name=troupe.name,
        sect=sect,
        characters=[
            CharacterChoice(id=c.id, name=c.name, kind=c.kind, in_troupe=True) for c in found
        ],
    )
