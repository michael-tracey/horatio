"""A character's sheet, purchases, XP history, and discipline dots waiting on the home troupe."""

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from horatio import sheets, titles, xp_range
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import (
    Approval,
    Character,
    RuleSet,
    TraitCategory,
    TraitDefinition,
    Troupe,
    User,
    XpEntry,
)
from horatio.permissions import (
    TroupeAction,
    allows,
    can_edit_character,
    require_troupe_action,
    troupe_role,
    visible_character,
)
from horatio.reconciliation import unbanked_xp

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
    # The lowest the player can take it: the rating the home troupe accepted.
    min_rating: int
    # Dots bought but waiting on the home troupe: the rating they were bought from.
    pending_from: int | None
    # Dots other traits give (negative if a flaw takes some away), and which traits.
    granted_rating: int
    granted_by: list[str]
    note: str


class XpSummary(BaseModel):
    balance: int
    earned: int
    spent: int
    # Creation XP that would be lost if a first home troupe accepted it now.
    unbanked: int = 0


class ApprovalOut(BaseModel):
    id: uuid.UUID
    character_id: uuid.UUID
    troupe_id: uuid.UUID
    kind: str
    status: str
    player_note: str
    staff_note: str


class ProblemOut(BaseModel):
    """A check the sheet breaks: one the troupe should look at (refuse), or a note."""

    category: str
    name: str
    strength: str
    message: str


class LimitOut(BaseModel):
    """Points held in a category with a limit: merits held, or flaws paying XP."""

    category: str
    name: str
    used: int
    limit: int


class SheetTroupeOut(BaseModel):
    """A troupe the character is in: its home troupe, or one it visits."""

    troupe_id: uuid.UUID
    troupe_name: str
    home: bool
    # A request to make this the home troupe is waiting.
    waiting: bool
    # Titles the character holds in this troupe.
    titles: list[str]


class PendingDisciplineOut(BaseModel):
    approval_id: uuid.UUID
    name: str
    detail: str
    from_rating: int
    to_rating: int
    cost: int


class ExceptionOut(BaseModel):
    """A trait held by exception (horatio.trait_exceptions)."""

    trait_id: uuid.UUID
    category: str
    name: str
    detail: str
    # The rating it was given at: raising it further is judged as normal.
    rating: int
    free: bool
    reason: str
    # The rules it sets aside for this trait.
    breaks: list[str]
    # Asked, and still "waiting" on the home troupe; "approved" by its staff; or
    # "given" by them.
    status: Literal["waiting", "approved", "given"]
    # Who approved or gave it, and when.
    by: str | None
    at: datetime | None


class PrimaryPathOut(BaseModel):
    discipline: str
    # The one the player named, else the clan's in-clan path; None until named.
    path: str | None
    # Whether that is the clan's in-clan path.
    native: bool
    # The clan's in-clan path of the discipline, if the character holds it.
    default: str | None
    # The paths held, highest first, to name one from.
    options: list[str]


class PrimaryPathChange(BaseModel):
    discipline: str
    # None un-names it.
    path: str | None


class SheetOut(BaseModel):
    character_id: uuid.UUID
    name: str
    status: str
    kind: str  # pc | npc
    home_troupe_id: uuid.UUID | None
    troupes: list[SheetTroupeOut]
    traits: list[SheetTraitOut]
    xp: XpSummary
    pending_approvals: list[ApprovalOut]
    pending_disciplines: list[PendingDisciplineOut]
    limits: list[LimitOut]
    problems: list[ProblemOut]
    # For each discipline learned as paths, which path is primary (MET: VTM p. 187).
    primary_paths: list[PrimaryPathOut] = []
    # Traits held by exception, oldest first.
    exceptions: list[ExceptionOut] = []


class TraitChange(BaseModel):
    category: str
    name: str
    detail: str = Field(default="", max_length=200)
    # Null for traits without a rating; 0 removes a rated trait.
    rating: int | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=1000)
    # For a discipline dot that waits on the home troupe: who teaches it.
    teacher: str = Field(default="", max_length=200)


class ChoiceChange(BaseModel):
    category: str
    from_name: str
    to_name: str


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
    # A correction: the award (or self-entered XP) it corrects.
    corrects_id: uuid.UUID | None = None
    # An award that has been corrected: what it gives now.
    corrected_to: int | None = None
    # An award the viewer may correct.
    correctable: bool = False


class XpAward(BaseModel):
    amount: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)


class XpCorrection(BaseModel):
    # What the award should give: 0 cancels it.
    amount: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=500)


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


def exceptions_out(db: DbSession, character: Character) -> list[ExceptionOut]:
    held = sheets.held_by_exception(db, character)
    people = {
        p.id: p.display_name
        for p in db.scalars(
            select(User).where(User.id.in_([e.given_by for _, e in held if e.given_by]))
        )
    }
    return [
        ExceptionOut(
            trait_id=row.trait.id,
            category=row.category.key,
            name=row.definition.name,
            detail=row.trait.detail,
            rating=e.rating,
            free=e.free,
            reason=e.reason,
            breaks=[c["message"] for c in e.checks],
            status="waiting"
            if e.given_at is None
            else "approved"
            if e.approval_id is not None
            else "given",
            by=people.get(e.given_by) if e.given_by else None,
            at=e.given_at,
        )
        for row, e in held
    ]


def sheet_out(db: DbSession, character: Character) -> SheetOut:
    floor = sheets.accepted_ratings(db, character)
    granting = sheets.sheet_effects(db, character).sources
    rows = sheets.sheet_rows(db, character)
    entries = [
        (kind, amount)
        for kind, amount in db.execute(
            select(XpEntry.kind, XpEntry.amount).where(XpEntry.character_id == character.id)
        )
    ]
    earned, spent = sheets.earned_and_spent(entries)
    pending = sheets.pending_approvals(db, character)
    held = sheets.pending_disciplines(db, character)
    held_from = {(d.trait_definition_id, d.detail): d.from_rating for _, d in held}
    joined = sheets.memberships(db, character)
    names = {
        troupe_id: name
        for troupe_id, name in db.execute(
            select(Troupe.id, Troupe.name).where(Troupe.id.in_([m.troupe_id for m in joined]))
        )
    }
    definitions = {
        d.id: d.name
        for d in db.scalars(
            select(TraitDefinition).where(
                TraitDefinition.id.in_([d.trait_definition_id for _, d in held])
            )
        )
    }
    return SheetOut(
        character_id=character.id,
        name=character.name,
        status=character.status,
        kind=character.kind,
        home_troupe_id=character.home_troupe_id,
        troupes=sorted(
            (
                SheetTroupeOut(
                    troupe_id=m.troupe_id,
                    troupe_name=names[m.troupe_id],
                    home=m.troupe_id == character.home_troupe_id,
                    waiting=any(
                        a.troupe_id == m.troupe_id and a.kind == "home_troupe_change"
                        for a in pending
                    ),
                    titles=titles.held(db, m.troupe_id, character.id),
                )
                for m in joined
            ),
            key=lambda t: (not t.home, t.troupe_name.lower()),
        ),
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
                # A flaw can be bought off whatever was accepted (at a price).
                min_rating=r.trait.free_rating
                if r.category.buy_off_factor
                else max(r.trait.free_rating, floor.get(r.key, 0)),
                pending_from=held_from.get((r.definition.id, r.trait.detail)),
                granted_rating=r.trait.granted_rating,
                granted_by=granting.get(r.key, []) if r.trait.granted_rating else [],
                note=r.trait.note,
            )
            for r in rows
        ],
        xp=XpSummary(
            balance=earned - spent,
            earned=earned,
            spent=spent,
            unbanked=unbanked_xp(db, character) if character.kind == "pc" else 0,
        ),
        pending_approvals=[approval_out(a) for a in pending],
        primary_paths=[
            PrimaryPathOut(
                discipline=p.discipline,
                path=p.path,
                native=p.native,
                default=p.default,
                options=p.options,
            )
            for p in sheets.primary_paths(db, character)
        ],
        exceptions=exceptions_out(db, character),
        problems=[
            ProblemOut(
                category=v.subject.category,
                name=v.subject.full_name,
                strength=v.check.strength,
                message=v.message,
            )
            for v in sheets.sheet_violations(db, character)
        ],
        limits=[
            LimitOut(
                category=c.key,
                name=c.name,
                used=sheets.held_points(db, character, c.key),
                limit=c.points_limit,
            )
            for c in db.scalars(
                select(TraitCategory)
                .join(RuleSet, TraitCategory.rule_set_id == RuleSet.id)
                .where(RuleSet.splat == character.splat, TraitCategory.points_limit.is_not(None))
                .order_by(TraitCategory.position)
            )
            if c.points_limit is not None
        ],
        pending_disciplines=[
            PendingDisciplineOut(
                approval_id=a.id,
                name=definitions[d.trait_definition_id],
                detail=d.detail,
                from_rating=d.from_rating,
                to_rating=d.to_rating,
                cost=d.cost,
            )
            for a, d in held
        ],
    )


def players_character(db: DbSession, user: User, character_id: uuid.UUID) -> Character:
    character = visible_character(db, user, character_id)
    if not can_edit_character(db, user, character):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the character's player can change it.")
    return sheets.lock_character(db, character.id)


@router.get("/sheet")
def read_sheet(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> SheetOut:
    return sheet_out(db, visible_character(db, user, character_id))


@router.post("/quote")
def quote(character_id: uuid.UUID, body: TraitChange, db: DbSession, user: CurrentUser) -> QuoteOut:
    """What a change would cost, without making it."""
    character = visible_character(db, user, character_id)
    result, current = sheets.quote_change(
        db, character, body.category, body.name, body.detail, body.rating
    )
    definition, category = sheets.find_definition(db, character, body.category, body.name)
    if (
        result is not None
        and category.points_limit is not None
        and body.rating is not None
        and current is not None
        and body.rating > current
    ):
        result = sheets.within_points_limit(
            db, character, category, definition, body.detail, body.rating, result
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
    with sheets.checked(db, character, user):
        change = sheets.set_trait(
            db,
            user,
            character,
            body.category,
            body.name,
            body.detail,
            body.rating,
            body.note,
            body.teacher,
        )
    db.commit()
    return ChangeOut(cost=change.quote.cost if change.quote else 0, sheet=sheet_out(db, character))


@router.put("/primary-path")
def name_primary_path(
    character_id: uuid.UUID, body: PrimaryPathChange, db: DbSession, user: CurrentUser
) -> SheetOut:
    """Name the primary path of a discipline, for a clan with no in-clan path."""
    character = players_character(db, user, character_id)
    sheets.name_primary_path(db, user, character, body.discipline, body.path)
    db.commit()
    return sheet_out(db, character)


@router.post("/traits/change")
def change_choice(
    character_id: uuid.UUID, body: ChoiceChange, db: DbSession, user: CurrentUser
) -> ChangeOut:
    """Swap a focus (or another swappable choice) for another, for its change cost."""
    character = players_character(db, user, character_id)
    with sheets.checked(db, character, user):
        cost = sheets.change_choice(
            db, user, character, body.category, body.from_name, body.to_name
        )
    db.commit()
    return ChangeOut(cost=cost, sheet=sheet_out(db, character))


@router.get("/unavailable")
def unavailable(
    character_id: uuid.UUID,
    category: str,
    db: DbSession,
    user: CurrentUser,
    as_if: Literal["sheet", "picks", "empty"] = "sheet",
    picks: Annotated[list[str] | None, Query()] = None,
) -> dict[str, str]:
    """Traits in `category` the character cannot take, and why: with the sheet as it
    is; as if the category's creation picks were `picks` (a wizard step not yet
    saved); or as if the category held nothing (what is barred whatever is chosen)."""
    character = visible_character(db, user, character_id)
    rules = sheets.rules_for(db, character)
    if category not in rules.rule_set.categories:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No category {category!r}.")
    return sheets.unavailable(db, character, category, as_if, picks or [])


def home_troupe_awarding(db: DbSession, user: User, character: Character) -> Troupe | None:
    """The character's home troupe, if `user` may award (and correct) its XP there."""
    if character.home_troupe_id is None:
        return None
    troupe = db.get_one(Troupe, character.home_troupe_id)
    if troupe.archived_at is not None and not user.is_custodian:
        return None
    role = troupe_role(db, user, troupe)
    return troupe if allows(role, TroupeAction.AWARD_XP, is_custodian=user.is_custodian) else None


@router.get("/xp")
def xp_history(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[XpEntryOut]:
    character = visible_character(db, user, character_id)
    rows = list(
        db.execute(
            select(XpEntry, TraitDefinition.name)
            .outerjoin(TraitDefinition, XpEntry.trait_definition_id == TraitDefinition.id)
            .where(XpEntry.character_id == character.id)
            .order_by(XpEntry.id)
        )
    )
    corrected: dict[uuid.UUID, int] = {}
    for e, _ in rows:
        if e.corrects_id is not None:
            corrected[e.corrects_id] = corrected.get(e.corrects_id, 0) + e.amount
    may_correct = home_troupe_awarding(db, user, character) is not None
    own = self_entering(db, user, character)
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
            corrects_id=e.corrects_id,
            corrected_to=e.amount + corrected[e.id] if e.id in corrected else None,
            correctable=(may_correct and e.kind in sheets.CORRECTABLE)
            or (own and e.kind == "self_entered"),
        )
        for e, trait_name in rows
    ]


@router.post("/xp/{entry_id}/correction", status_code=status.HTTP_201_CREATED)
def correct_xp(
    character_id: uuid.UUID,
    entry_id: uuid.UUID,
    body: XpCorrection,
    db: DbSession,
    user: CurrentUser,
) -> XpEntryOut:
    """Correct a mistaken award with a new entry; the award itself is left as written.
    Whoever may award the character XP may correct it, and a player their own
    self-entered XP while the character has no home troupe."""
    character = visible_character(db, user, character_id)
    award = db.get(XpEntry, entry_id)
    if award is None or award.character_id != character.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such entry.")
    own = award.kind == "self_entered" and self_entering(db, user, character)
    if not own and home_troupe_awarding(db, user, character) is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the home troupe's staff correct its experience."
        )
    if own:
        character = players_character(db, user, character_id)
        sheets.ensure_unlocked(db, character)
    entry = sheets.correct_xp(db, user, character, award, body.amount, body.reason)
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
        corrects_id=award.id,
    )


def self_entering(db: DbSession, user: User, character: Character) -> bool:
    """Whether `user` may add XP to the character themselves: its player, while it
    has no home troupe."""
    return (
        character.kind == "pc"
        and character.home_troupe_id is None
        and character.status == "active"
        and can_edit_character(db, user, character)
    )


@router.post("/xp/self-entered", status_code=status.HTTP_201_CREATED)
def add_self_entered_xp(
    character_id: uuid.UUID, body: XpAward, db: DbSession, user: CurrentUser
) -> XpEntryOut:
    """A player adds XP to their own character while it has no home troupe, such
    as for one played elsewhere. The troupe it asks to join accepts or removes it."""
    character = players_character(db, user, character_id)
    sheets.ensure_unlocked(db, character)
    entry = xp_range.add_self_entered(db, user, character, body.amount, body.reason.strip())
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


@router.delete("/disciplines/{approval_id}", status_code=status.HTTP_204_NO_CONTENT)
def withdraw_discipline(
    character_id: uuid.UUID, approval_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> None:
    """Take back discipline dots still waiting on the home troupe, and get the XP back."""
    character = players_character(db, user, character_id)
    waiting = next(
        (a for a, _ in sheets.pending_disciplines(db, character) if a.id == approval_id), None
    )
    if waiting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such discipline is waiting.")
    sheets.withdraw(db, user, waiting)
    db.commit()
