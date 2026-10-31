"""Staff give a player's character a trait by exception: free, despite the rules, or
both. And a diablerie, which changes the sheet past the rules in the same way: staff
record one, or a player asks them to."""

import uuid
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from horatio import diablerie, sheets, trait_exceptions
from horatio.api.sheets import ApprovalOut, SheetOut, approval_out, sheet_out
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, Troupe, User
from horatio.permissions import (
    TroupeAction,
    allows,
    require_troupe_action,
    troupe_role,
    visible_character,
)

router = APIRouter(prefix="/characters/{character_id}", tags=["sheets"])


class GiveIn(BaseModel):
    category: str
    name: str
    detail: str = Field(default="", max_length=200)
    rating: int = Field(ge=1)
    # At no XP cost: its dots are free dots.
    free: bool = False
    # Give it even though it breaks the rules; a trial says which it breaks.
    despite: bool = False
    reason: str = Field(min_length=1, max_length=500)
    # Say what it would cost and break, saving nothing.
    trial: bool = False


class GiveOut(BaseModel):
    # Whether it was given: never on a trial, nor if refused.
    given: bool
    # XP it spends.
    cost: int
    # The rules it breaks, that it is (or would be) given despite.
    breaks: list[str]
    # Why it cannot be given (on a trial); refusals otherwise come as 409.
    refused: str | None
    sheet: SheetOut


@router.post("/give")
def give(character_id: uuid.UUID, body: GiveIn, db: DbSession, user: CurrentUser) -> GiveOut:
    """A storyteller or assistant storyteller of a player's character's home troupe
    gives it a trait, or raises one: free, despite the rules, or both, always with
    a reason. Nothing waits on approval; the player is told."""
    character = visible_character(db, user, character_id)
    if character.kind != "pc" or character.home_troupe_id is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Staff give traits only to a player's character in its home troupe.",
        )
    require_troupe_action(
        db, user, db.get_one(Troupe, character.home_troupe_id), TroupeAction.APPROVE_CHANGES
    )
    character = sheets.lock_character(db, character.id)
    given = trait_exceptions.give(
        db,
        user,
        character,
        (body.category, body.name, body.detail),
        body.rating,
        free=body.free,
        despite=body.despite,
        reason=body.reason.strip(),
        trial=body.trial,
    )
    if not body.trial:
        db.commit()
    return GiveOut(
        given=not body.trial,
        cost=given.cost,
        breaks=given.breaks,
        refused=given.refused,
        sheet=sheet_out(db, character),
    )


# --- Diablerie (MET: VTM p. 306) --------------------------------------------------------


class LossOut(BaseModel):
    """A technique lost to the new Generation, and the XP it gives back."""

    name: str
    detail: str
    rating: int
    refund: int


class FlawPlanOut(BaseModel):
    """A Lesser Generation or Thin Blooded flaw, and what the troupe's setting does."""

    name: str
    rating: int
    # leave | remove | keep_xp
    setting: str
    # The XP the flaw gave, and what is taken back of it.
    gave: int
    taken: int


class DiablerieEffectsOut(BaseModel):
    """What a diablerie does to the sheet: filled in before, or done."""

    from_generation: int
    to_generation: int
    techniques: list[LossOut]
    # Humanity, or the Path followed, and its rating.
    morality: str | None
    morality_rating: int
    on_path: bool
    # Humanity lowered, and Beast traits for the next game: what the form fills in.
    humanity_lowered: int
    beast_traits: int
    flaw: FlawPlanOut | None
    caitiff: bool


class DiablerieEffectsPlanOut(DiablerieEffectsOut):
    # Why it cannot be recorded, if it cannot.
    refused: str | None
    # What the troupe does about a Lesser Generation or Thin Blooded flaw.
    flaw_setting: str


class DiablerieIn(BaseModel):
    # The night it happened.
    committed_on: date
    # Who was diablerized: for staff only.
    victim: str = Field(default="", max_length=200)
    note: str = Field(default="", max_length=1000)
    # Adjust what the form filled in; none uses it.
    humanity_lowered: int | None = Field(default=None, ge=0, le=10)
    beast_traits: int | None = Field(default=None, ge=0, le=5)


class DiablerieAsk(BaseModel):
    committed_on: date
    note: str = Field(default="", max_length=1000)


class DiablerieOut(BaseModel):
    """A diablerie on the sheet."""

    id: uuid.UUID
    committed_on: date
    note: str
    # Staff only: who was diablerized.
    victim: str | None
    recorded_by: str | None
    recorded_at: datetime | None
    effects: DiablerieEffectsOut | None


class DiablerieListOut(BaseModel):
    entries: list[DiablerieOut]
    # The viewer is the home troupe's storyteller or assistant: they can record one.
    can_record: bool
    # The viewer is the player, and can say they committed one.
    can_ask: bool
    # One the player asked for is waiting on staff, and the night they said it was.
    waiting: ApprovalOut | None
    waiting_on: date | None = None


class DiablerieRecorded(BaseModel):
    effects: DiablerieEffectsOut
    sheet: SheetOut


def effects_out(effects: dict[str, Any]) -> DiablerieEffectsOut | None:
    return DiablerieEffectsOut.model_validate(effects) if effects else None


def plan_out(db: DbSession, character: Character, plan: diablerie.Plan) -> DiablerieEffectsPlanOut:
    troupe = db.get(Troupe, character.home_troupe_id) if character.home_troupe_id else None
    return DiablerieEffectsPlanOut(
        **plan.as_dict(),
        flaw_setting=troupe.diablerie_flaws if troupe else "leave",
    )


def recording_staff(db: DbSession, user: User, character: Character) -> None:
    """Refuse unless `user` is staff who can record a diablerie for the character:
    its home troupe's lead storyteller, storytellers and assistant storytellers."""
    refused = diablerie.can_have(character)
    if refused:
        raise HTTPException(status.HTTP_409_CONFLICT, refused)
    assert character.home_troupe_id is not None
    require_troupe_action(
        db, user, db.get_one(Troupe, character.home_troupe_id), TroupeAction.APPROVE_CHANGES
    )


def may_record(db: DbSession, user: User, character: Character) -> bool:
    troupe = db.get(Troupe, character.home_troupe_id) if character.home_troupe_id else None
    return (
        character.kind == "pc"
        and diablerie.can_have(character) is None
        and troupe is not None
        and (troupe.archived_at is None or user.is_custodian)
        and allows(
            troupe_role(db, user, troupe),
            TroupeAction.APPROVE_CHANGES,
            is_custodian=user.is_custodian,
        )
    )


@router.get("/diablerie")
def list_diablerie(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> DiablerieListOut:
    """The diablerie on the sheet. Who was diablerized shows to staff only."""
    character = visible_character(db, user, character_id)
    staff = may_record(db, user, character)
    mine = character.kind == "pc" and character.player_id == user.id
    waiting = sheets.pending_approvals(db, character, "diablerie")
    asked = diablerie.asked_for(db, waiting[0]) if waiting else None
    names = {
        u.id: u.display_name
        for u in db.scalars(
            select(User).where(
                User.id.in_(
                    [d.recorded_by for d in diablerie.recorded(db, character) if d.recorded_by]
                )
            )
        )
    }
    return DiablerieListOut(
        entries=[
            DiablerieOut(
                id=d.id,
                committed_on=d.committed_on,
                note=d.note,
                victim=d.victim if staff or user.is_custodian else None,
                recorded_by=names.get(d.recorded_by) if d.recorded_by else None,
                recorded_at=d.recorded_at,
                effects=effects_out(d.outcome),
            )
            for d in diablerie.recorded(db, character)
        ],
        can_record=staff,
        can_ask=(
            mine
            and diablerie.can_have(character) is None
            and character.status == "active"
            and not waiting
        ),
        waiting=approval_out(waiting[0]) if waiting else None,
        waiting_on=asked.committed_on if asked else None,
    )


@router.get("/diablerie/plan")
def diablerie_plan(
    character_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    humanity_lowered: int | None = None,
    beast_traits: int | None = None,
) -> DiablerieEffectsPlanOut:
    """What recording a diablerie would do to the sheet, for staff to see before they
    confirm: the Generation, the techniques lost, the Humanity or Beast traits it fills
    in, and what the troupe's setting does to a Lesser Generation or Thin Blooded flaw."""
    character = visible_character(db, user, character_id)
    recording_staff(db, user, character)
    character = sheets.lock_character(db, character.id)
    plan = diablerie.plan_for(db, character, diablerie.Adjust(None, humanity_lowered, beast_traits))
    return plan_out(db, character, plan)


@router.post("/diablerie")
def record_diablerie(
    character_id: uuid.UUID, body: DiablerieIn, db: DbSession, user: CurrentUser
) -> DiablerieRecorded:
    """A storyteller or assistant storyteller of the character's home troupe records a
    diablerie: Generation up one, free, and the rest of what p. 306 changes. The player
    is told."""
    character = visible_character(db, user, character_id)
    recording_staff(db, user, character)
    character = sheets.lock_character(db, character.id)
    plan = diablerie.start(
        db,
        user,
        character,
        body.committed_on,
        body.victim,
        body.note,
        diablerie.Adjust(None, body.humanity_lowered, body.beast_traits),
    )
    db.commit()
    return DiablerieRecorded(
        effects=DiablerieEffectsOut(**plan.as_outcome()), sheet=sheet_out(db, character)
    )


@router.post("/diablerie/ask", status_code=status.HTTP_201_CREATED)
def ask_diablerie(
    character_id: uuid.UUID, body: DiablerieAsk, db: DbSession, user: CurrentUser
) -> ApprovalOut:
    """The player says their character committed diablerie. It waits on the home
    troupe's storytellers; approving it does what recording one does."""
    character = visible_character(db, user, character_id)
    if character.kind != "pc" or character.player_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the character's player can ask.")
    character = sheets.lock_character(db, character.id)
    approval = diablerie.ask(db, user, character, body.committed_on, body.note)
    db.commit()
    return approval_out(approval)


@router.delete("/diablerie/ask", status_code=status.HTTP_204_NO_CONTENT)
def withdraw_diablerie(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Response:
    """The player takes back the diablerie they asked to record."""
    character = visible_character(db, user, character_id)
    if character.kind != "pc" or character.player_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the character's player can do that.")
    character = sheets.lock_character(db, character.id)
    waiting = sheets.pending_approvals(db, character, "diablerie")
    if not waiting:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No diablerie is waiting.")
    sheets.withdraw(db, user, waiting[0])
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
