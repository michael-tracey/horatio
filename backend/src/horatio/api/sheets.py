"""A character's sheet, purchases, XP history and approval requests."""

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from horatio import sheets, titles
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Approval, Character, TraitDefinition, Troupe, User, XpEntry
from horatio.permissions import (
    TroupeAction,
    can_edit_character,
    require_troupe_action,
    visible_character,
)

router = APIRouter(prefix="/characters/{character_id}", tags=["sheets"])


class SheetTraitOut(BaseModel):
    id: uuid.UUID
    category: str
    category_name: str
    group: str
    name: str
    detail: str
    rating: int | None
    free_rating: int
    approved_rating: int | None
    note: str


class XpSummary(BaseModel):
    balance: int
    earned: int
    spent: int


class PendingChange(BaseModel):
    category: str
    name: str
    detail: str
    approved_rating: int | None
    rating: int | None
    added: bool
    removed: bool


class ApprovalOut(BaseModel):
    id: uuid.UUID
    character_id: uuid.UUID
    troupe_id: uuid.UUID
    kind: str
    status: str
    player_note: str
    staff_note: str


class StandingOut(BaseModel):
    """CONTEXT.md: Troupe Standing. One per troupe the character is in."""

    troupe_id: uuid.UUID
    troupe_name: str
    standing: str  # draft | approved
    # Why the troupe sent it back to draft, if it did.
    note: str
    home: bool
    # The sheet differs from what this troupe approved, or it never has.
    needs_approval: bool
    waiting: bool
    # Titles the character holds in this troupe.
    titles: list[str]


class SheetOut(BaseModel):
    character_id: uuid.UUID
    name: str
    status: str
    kind: str  # pc | npc
    standings: list[StandingOut]
    # Whose approved sheet `approved_rating` and `pending_changes` compare against.
    viewing_troupe_id: uuid.UUID | None
    traits: list[SheetTraitOut]
    xp: XpSummary
    pending_changes: list[PendingChange]
    pending_approvals: list[ApprovalOut]


class TraitChange(BaseModel):
    category: str
    name: str
    detail: str = Field(default="", max_length=200)
    # Null for traits without a rating; 0 removes a rated trait.
    rating: int | None = Field(default=None, ge=0)
    note: str | None = None


class QuoteOut(BaseModel):
    cost: int
    from_rating: int | None
    to_rating: int | None
    basis: dict[str, Any] | None


class ChangeOut(BaseModel):
    cost: int
    sheet: SheetOut


class XpEntryOut(BaseModel):
    id: uuid.UUID
    kind: str
    amount: int
    reason: str
    entered_on: date
    trait: str | None
    detail: str | None
    from_rating: int | None
    to_rating: int | None


class XpAward(BaseModel):
    amount: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)


class ApprovalRequest(BaseModel):
    note: str = ""


def approval_out(approval: Approval) -> ApprovalOut:
    return ApprovalOut(
        id=approval.id,
        character_id=approval.character_id,
        troupe_id=approval.troupe_id,
        kind=approval.kind,
        status=approval.status,
        player_note=approval.player_note,
        staff_note=approval.staff_note,
    )


def viewing_troupe(
    db: DbSession, character: Character, asked: uuid.UUID | None
) -> uuid.UUID | None:
    """The troupe whose approved sheet to compare against: the one asked for, else
    the home troupe, else the first that approved it, else the first joined."""
    joined = sheets.memberships(db, character)
    ids = [m.troupe_id for m in joined]
    for choice in (
        asked,
        character.home_troupe_id,
        next((m.troupe_id for m in joined if m.standing == "approved"), None),
        ids[0] if ids else None,
    ):
        if choice in ids:
            return choice
    return None


def sheet_out(db: DbSession, character: Character, troupe_id: uuid.UUID | None = None) -> SheetOut:
    viewing = viewing_troupe(db, character, troupe_id)
    approved = sheets.approved_ratings(db, character, viewing)
    rows = sheets.sheet_rows(db, character)
    entries = list(db.scalars(select(XpEntry.amount).where(XpEntry.character_id == character.id)))
    pending = sheets.pending_approvals(db, character)
    joined = sheets.memberships(db, character)
    names = {
        troupe_id: name
        for troupe_id, name in db.execute(
            select(Troupe.id, Troupe.name).where(Troupe.id.in_([m.troupe_id for m in joined]))
        )
    }
    return SheetOut(
        character_id=character.id,
        name=character.name,
        status=character.status,
        kind=character.kind,
        standings=[
            StandingOut(
                troupe_id=m.troupe_id,
                troupe_name=names[m.troupe_id],
                standing=m.standing,
                note=m.standing_note,
                home=m.troupe_id == character.home_troupe_id,
                needs_approval=sheets.needs_approval(db, character, m),
                waiting=any(a.troupe_id == m.troupe_id for a in pending),
                titles=titles.held(db, m.troupe_id, character.id),
            )
            for m in joined
        ],
        viewing_troupe_id=viewing,
        traits=[
            SheetTraitOut(
                id=r.trait.id,
                category=r.category.key,
                category_name=r.category.name,
                group=r.category.group_name,
                name=r.definition.name,
                detail=r.trait.detail,
                rating=r.trait.rating,
                free_rating=r.trait.free_rating,
                approved_rating=approved.get(r.key),
                note=r.trait.note,
            )
            for r in rows
        ],
        xp=XpSummary(
            balance=sum(entries),
            earned=sum(a for a in entries if a > 0),
            spent=-sum(a for a in entries if a < 0),
        ),
        pending_changes=[
            PendingChange(**c) for c in sheets.pending_changes(db, character, viewing)
        ],
        pending_approvals=[approval_out(a) for a in pending],
    )


def players_character(db: DbSession, user: User, character_id: uuid.UUID) -> Character:
    character = visible_character(db, user, character_id)
    if not can_edit_character(db, user, character):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the character's player can change it.")
    return sheets.lock_character(db, character.id)


@router.get("/sheet")
def read_sheet(
    character_id: uuid.UUID, db: DbSession, user: CurrentUser, troupe_id: uuid.UUID | None = None
) -> SheetOut:
    """The sheet, compared against `troupe_id`'s approved sheet (by default the
    home troupe's)."""
    return sheet_out(db, visible_character(db, user, character_id), troupe_id)


@router.post("/quote")
def quote(character_id: uuid.UUID, body: TraitChange, db: DbSession, user: CurrentUser) -> QuoteOut:
    """What a change would cost, without making it."""
    character = visible_character(db, user, character_id)
    result, current = sheets.quote_change(
        db, character, body.category, body.name, body.detail, body.rating
    )
    return QuoteOut(
        cost=result.cost if result else 0,
        from_rating=current,
        to_rating=body.rating,
        basis=result.rule.describe() if result else None,
    )


@router.put("/traits")
def change_trait(
    character_id: uuid.UUID, body: TraitChange, db: DbSession, user: CurrentUser
) -> ChangeOut:
    character = players_character(db, user, character_id)
    change = sheets.set_trait(
        db, user, character, body.category, body.name, body.detail, body.rating, body.note
    )
    db.commit()
    return ChangeOut(cost=change.quote.cost if change.quote else 0, sheet=sheet_out(db, character))


@router.get("/xp")
def xp_history(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[XpEntryOut]:
    character = visible_character(db, user, character_id)
    rows = db.execute(
        select(XpEntry, TraitDefinition.name)
        .outerjoin(TraitDefinition, XpEntry.trait_definition_id == TraitDefinition.id)
        .where(XpEntry.character_id == character.id)
        .order_by(XpEntry.id)
    )
    return [
        XpEntryOut(
            id=e.id,
            kind=e.kind,
            amount=e.amount,
            reason=e.reason,
            entered_on=e.entered_on,
            trait=trait_name,
            detail=e.detail,
            from_rating=e.from_rating,
            to_rating=e.to_rating,
        )
        for e, trait_name in rows
    ]


@router.post("/xp", status_code=status.HTTP_201_CREATED)
def award_xp(
    character_id: uuid.UUID, body: XpAward, db: DbSession, user: CurrentUser
) -> XpEntryOut:
    """Storytellers and assistant storytellers of the character's home troupe award XP."""
    character = visible_character(db, user, character_id)
    if character.home_troupe_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a home troupe's staff award XP.")
    troupe = db.get_one(Troupe, character.home_troupe_id)
    require_troupe_action(db, user, troupe, TroupeAction.AWARD_XP)
    entry = sheets.award_xp(db, user, character, body.amount, body.reason)
    db.commit()
    return XpEntryOut(
        id=entry.id,
        kind=entry.kind,
        amount=entry.amount,
        reason=entry.reason,
        entered_on=date.today(),
        trait=None,
        detail=None,
        from_rating=None,
        to_rating=None,
    )


@router.post("/approval", status_code=status.HTTP_201_CREATED)
def request_approval(
    character_id: uuid.UUID, body: ApprovalRequest, db: DbSession, user: CurrentUser
) -> list[ApprovalOut]:
    """Put the sheet to every troupe the character is in that has not approved it as it stands."""
    character = players_character(db, user, character_id)
    approvals = sheets.request_approval(db, user, character, body.note)
    db.commit()
    return [approval_out(a) for a in approvals]


@router.delete("/approval", status_code=status.HTTP_204_NO_CONTENT)
def withdraw_approval(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    character = players_character(db, user, character_id)
    waiting = sheets.pending_approvals(db, character, "sheet_change")
    if not waiting:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nothing is waiting for approval.")
    for approval in waiting:
        sheets.withdraw(db, user, approval)
    db.commit()
