"""A character's plan of XP purchases to come (horatio.xp_plans): its player's own,
seen by staff only while shared."""

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from horatio import sheets, xp_plans
from horatio.api.cart import TeacherNeedOut, teacher_need_out
from horatio.api.sheets import players_character
from horatio.auth.deps import CurrentUser, DbSession
from horatio.auth.viewing import read_only
from horatio.models import Character, User
from horatio.permissions import visible_character

router = APIRouter(prefix="/characters/{character_id}", tags=["sheets"])


class XpPlanLineIn(BaseModel):
    category: str = Field(max_length=100)
    name: str = Field(max_length=200)
    detail: str = Field(default="", max_length=200)
    # The rating to take it to.
    rating: int = Field(ge=1, le=20)


class XpPlanIn(BaseModel):
    # In the order they are to be bought.
    lines: list[XpPlanLineIn] = Field(max_length=xp_plans.MAX_LINES)
    # The staff who see the sheet see the plan too.
    shared: bool = False


class XpPlanLineOut(BaseModel):
    category: str
    name: str
    detail: str
    rating: int
    # The rating it raises from: held now, or as the lines before it leave it.
    from_rating: int
    # XP it costs (negative: gives back), as the cart prices it; null if that can't be
    # told, or the plan isn't priced.
    cost: int | None
    # Why the cart would refuse it even with the XP for it; null if it wouldn't.
    refused: str | None
    # Already held at its rating or more.
    held: bool
    # What this line and those before it cost together.
    total: int
    # The XP unspent now pays for it and every line before it.
    affordable: bool
    # Roughly how many games of the usual award until it is affordable; null if
    # there is no usual award to tell by.
    games: int | None
    # It can go into the cart now: affordable, not refused, and the next step for its trait.
    buyable: bool
    # Waits on the home troupe once bought, like a discipline dot.
    needs_approval: bool
    # A power a merit opens past a check: "Hard as Steel: 20 XP".
    because: str | None
    # A troupe's teacher rule asks a teacher for it, chosen in the cart.
    teacher: TeacherNeedOut | None


class XpPlanAwardOut(BaseModel):
    # XP a game usually gives the character.
    per_game: int
    # Where that comes from: "the troupe's session XP".
    source: str


class XpPlanOut(BaseModel):
    shared: bool
    # The viewer is the character's player, who keeps the plan.
    mine: bool
    # XP unspent now.
    balance: int
    # The usual award for a game, to tell how far off a line is; null without a home troupe.
    award: XpPlanAwardOut | None
    # Whether the lines are priced: not while the custodian views as someone.
    priced: bool
    lines: list[XpPlanLineOut]


def plan_out(
    db: Session, user: User, character: Character, lines: list[xp_plans.Line], shared: bool
) -> XpPlanOut:
    balance = sheets.xp_balance(db, character)
    award = xp_plans.usual_award(db, character)
    priced = xp_plans.price(db, character, lines)
    held_now = {row.key: row.trait.rating or 0 for row in sheets.sheet_rows(db, character)}
    out: list[XpPlanLineOut] = []
    total = 0
    for p in priced:
        total += p.cost or 0
        affordable = not p.held and p.cost is not None and balance >= 0 and total <= balance
        out.append(
            XpPlanLineOut(
                category=p.line.category,
                name=p.line.name,
                detail=p.line.detail,
                rating=p.line.rating,
                from_rating=p.from_rating,
                cost=p.cost,
                refused=p.refused,
                held=p.held,
                total=total,
                affordable=affordable,
                games=None if p.held else xp_plans.games_away(total - balance, award),
                buyable=affordable
                and p.refused is None
                and held_now.get(p.line.key, 0) == p.from_rating,
                needs_approval=p.needs_approval,
                because=p.because,
                teacher=teacher_need_out(p.teacher),
            )
        )
    return XpPlanOut(
        shared=shared,
        mine=xp_plans.is_players(character, user),
        balance=balance,
        award=XpPlanAwardOut(per_game=award.per_game, source=award.source) if award else None,
        priced=not read_only(db),
        lines=out,
    )


@router.get("/xp-plan")
def read_plan(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> XpPlanOut:
    """The character's plan, each line priced as the cart would price it. Its player's
    own: anyone else who sees the sheet sees it only while it is shared."""
    character = visible_character(db, user, character_id)
    plan = xp_plans.find(db, character)
    if not xp_plans.visible_to(character, user, plan):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No plan is shared.")
    return plan_out(db, user, character, xp_plans.lines_of(plan), plan.shared if plan else False)


@router.put("/xp-plan")
def save_plan(
    character_id: uuid.UUID, body: XpPlanIn, db: DbSession, user: CurrentUser
) -> XpPlanOut:
    """Keep the plan's lines, in order, and whether it is shared. Its player's alone."""
    character = players_character(db, user, character_id)
    plan = xp_plans.save(
        db,
        character,
        [xp_plans.Line(x.category, x.name, x.detail, x.rating) for x in body.lines],
        shared=body.shared,
    )
    db.commit()
    return plan_out(db, user, character, xp_plans.lines_of(plan), plan.shared)
