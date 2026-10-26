"""A ghoul's Embrace (horatio.embrace), run by its home troupe's staff from the
ghoul's sheet, and XP debt (horatio.xp_debt), which they can add to or forgive."""

import uuid
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from horatio import domitors, embrace, sheets, xp_debt
from horatio.api.sheets import SheetOut, sheet_out
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, Embrace, Troupe, User
from horatio.permissions import (
    TroupeAction,
    allows,
    require_troupe_action,
    troupe_role,
    visible_character,
)

router = APIRouter(prefix="/characters/{character_id}", tags=["sheets"])


class SireIn(BaseModel):
    # A vampire PC or NPC in Horatio; or, without one, its name, clan and generation.
    character_id: uuid.UUID | None = None
    name: str = Field(default="", max_length=200)
    clan: str = Field(default="", max_length=200)
    # As a number: 10 for the 10th generation.
    generation: int | None = Field(default=None, ge=1, le=15)


class EmbraceNamedIn(BaseModel):
    category: Literal["merits", "flaws"]
    name: str
    detail: str = ""


class EmbraceDotsIn(BaseModel):
    name: str
    rating: int = Field(ge=1, le=10)


class EmbraceChoicesIn(BaseModel):
    sire: SireIn
    # Whether the sire was the ghoul's domitor; left out, worked out where both are in
    # Horatio, and otherwise by their names.
    sire_is_domitor: bool | None = None
    # The merits the sire's clan and rarity need in the setting; left out, suggested.
    clan_merits: list[str] | None = Field(default=None, max_length=10)
    # The in-clan discipline with 2 dots; left out, the first.
    two_dots: str | None = None
    # A Caitiff's three in-clan disciplines.
    caitiff_three: list[str] = Field(default_factory=list[str], max_length=3)
    # Merits and flaws to take off.
    remove: list[EmbraceNamedIn] = Field(default_factory=list[EmbraceNamedIn], max_length=50)
    # Lost disciplines bought back, each to a rating: 2 dots in all at most.
    buy_back: list[EmbraceDotsIn] = Field(default_factory=list[EmbraceDotsIn], max_length=2)
    # The Storyteller lets lost dots be bought back into XP debt, now or from the cart.
    buy_back_into_debt: bool = False
    # The clan weakness, as the player takes it: a Malkavian's derangement, say.
    weakness: str = Field(default="", max_length=1000)

    def to_choices(self) -> embrace.Choices:
        return embrace.Choices(
            sire=embrace.SireIn(
                self.sire.character_id, self.sire.name, self.sire.clan, self.sire.generation
            ),
            sire_is_domitor=self.sire_is_domitor,
            clan_merits=tuple(self.clan_merits) if self.clan_merits is not None else None,
            two_dots=self.two_dots,
            caitiff_three=tuple(self.caitiff_three),
            remove=tuple(embrace.Named(r.category, r.name, r.detail) for r in self.remove),
            buy_back=tuple(embrace.Dots(d.name, d.rating) for d in self.buy_back),
            buy_back_into_debt=self.buy_back_into_debt,
            weakness=self.weakness,
        )


class EmbraceIn(EmbraceChoicesIn):
    embraced_on: date
    note: str = Field(default="", max_length=2000)


class EmbraceDiedIn(BaseModel):
    embraced_on: date
    sire_name: str = Field(default="", max_length=200)
    note: str = Field(default="", max_length=2000)


class EmbraceLineOut(BaseModel):
    text: str
    # Positive for XP back, negative for XP spent or owed.
    xp: int


class EmbraceStepOut(BaseModel):
    key: str
    title: str
    lines: list[EmbraceLineOut]
    xp: int


class EmbraceRatedOut(BaseModel):
    name: str
    rating: int
    detail: str = ""


class EmbraceRemovableOut(BaseModel):
    category: str
    name: str
    detail: str
    rating: int
    # What taking it off gives back (negative: takes back).
    xp: int


class EmbracePlanOut(BaseModel):
    sire_id: uuid.UUID | None
    sire_name: str
    sire_clan: str
    sire_generation: int | None
    sire_is_domitor: bool
    generation: int | None
    generation_dots: int
    lesser_flaw: str | None
    title: str
    blood: int
    blood_per_turn: int
    attribute_bonus: int
    clan: str
    caitiff: bool
    in_clan: list[str]
    two_dots: str | None
    clan_merit_choices: list[str]
    clan_merits: list[str]
    merit_points: int
    merit_limit: int
    # It cannot come within the merit limit, and dies in the Embrace.
    dies: bool
    removable: list[EmbraceRemovableOut]
    lost: list[EmbraceRatedOut]
    disciplines: list[EmbraceRatedOut]
    bought_back: list[EmbraceRatedOut]
    buy_back_into_debt: bool
    weakness: str
    steps: list[EmbraceStepOut]
    balance_before: int
    balance_after: int
    debt: int
    # What the sheet then breaks without stopping the Embrace.
    notes: list[str]
    # Why it cannot be done as chosen, if it cannot.
    refused: str | None


class EmbraceOut(BaseModel):
    id: uuid.UUID
    result: str
    embraced_on: date
    sire_id: uuid.UUID | None
    sire_name: str
    sire_clan: str
    sire_generation: int | None
    note: str
    recorded_by: str | None
    # What each step did, and its XP; none for one that died.
    steps: list[EmbraceStepOut]
    debt: int


class EmbraceListOut(BaseModel):
    entries: list[EmbraceOut]
    # Whether this viewer runs an Embrace of this character now.
    can_embrace: bool


class SireChoiceOut(BaseModel):
    character_id: uuid.UUID
    name: str
    kind: str
    clan: str
    # As its sheet has it; none where it has no Generation to tell.
    generation: int | None


class EmbracedOut(BaseModel):
    plan: EmbracePlanOut
    sheet: SheetOut


class DebtOut(BaseModel):
    debt: int
    # Whether this viewer adds or forgives the character's debt.
    can_change: bool


class DebtIn(BaseModel):
    change: Literal["add", "forgive"]
    amount: int = Field(ge=1, le=1000)
    reason: str = Field(min_length=1, max_length=500)


def home_troupe(db: DbSession, character: Character) -> Troupe | None:
    return db.get(Troupe, character.home_troupe_id) if character.home_troupe_id else None


def running_staff(db: DbSession, user: User, character: Character, action: TroupeAction) -> bool:
    troupe = home_troupe(db, character)
    return (
        character.kind == "pc"
        and troupe is not None
        and (troupe.archived_at is None or user.is_custodian)
        and allows(troupe_role(db, user, troupe), action, is_custodian=user.is_custodian)
    )


def embracing_staff(db: DbSession, user: User, character_id: uuid.UUID) -> Character:
    """The character, locked, if `user` runs its Embrace: its home troupe's lead
    storyteller, storytellers and assistant storytellers."""
    character = visible_character(db, user, character_id)
    refused = embrace.can_embrace(db, character)
    if refused:
        raise HTTPException(status.HTTP_409_CONFLICT, refused)
    troupe = home_troupe(db, character)
    assert troupe is not None
    require_troupe_action(db, user, troupe, TroupeAction.APPROVE_CHANGES)
    return sheets.lock_character(db, character.id)


def checked_sire(db: DbSession, user: User, body: EmbraceChoicesIn) -> None:
    """A linked sire is one the staff member can see."""
    if body.sire.character_id is not None:
        visible_character(db, user, body.sire.character_id)


def plan_out(plan: embrace.Plan) -> EmbracePlanOut:
    return EmbracePlanOut.model_validate(plan.as_dict())


def steps_out(outcome: dict[str, Any]) -> list[EmbraceStepOut]:
    return [EmbraceStepOut.model_validate(s) for s in outcome.get("steps", [])]


def embrace_out(db: DbSession, record: Embrace) -> EmbraceOut:
    by = db.get(User, record.recorded_by)
    return EmbraceOut(
        id=record.id,
        result=record.result,
        embraced_on=record.embraced_on,
        sire_id=record.sire_id,
        sire_name=record.sire_name,
        sire_clan=record.sire_clan,
        sire_generation=record.sire_generation,
        note=record.note,
        recorded_by=by.display_name if by else None,
        steps=steps_out(record.outcome),
        debt=record.outcome.get("debt", 0),
    )


@router.get("/embrace")
def list_embraces(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> EmbraceListOut:
    """The character's Embrace, once it has been Embraced, and whether this viewer can
    run one now."""
    character = visible_character(db, user, character_id)
    return EmbraceListOut(
        entries=[embrace_out(db, e) for e in embrace.embraces(db, character)],
        can_embrace=embrace.can_embrace(db, character) is None
        and running_staff(db, user, character, TroupeAction.APPROVE_CHANGES),
    )


@router.get("/embrace/sires")
def sire_choices(
    character_id: uuid.UUID, db: DbSession, user: CurrentUser, q: str = ""
) -> list[SireChoiceOut]:
    """The vampires in Horatio the staff member can see, by name, that could be the
    sire: with their clan, and generation as their sheets have it."""
    character = embracing_staff(db, user, character_id)
    return [
        SireChoiceOut(
            character_id=c.character.id,
            name=c.character.name,
            kind=c.character.kind,
            clan=c.clan,
            generation=embrace.sire_generation(db, c.character),
        )
        for c in domitors.candidates(db, user, character, q)
    ]


@router.post("/embrace/plan")
def embrace_plan(
    character_id: uuid.UUID, body: EmbraceChoicesIn, db: DbSession, user: CurrentUser
) -> EmbracePlanOut:
    """What the Embrace would do with these choices, step by step with its XP, for
    staff to see before they confirm. Nothing is saved."""
    character = embracing_staff(db, user, character_id)
    checked_sire(db, user, body)
    return plan_out(embrace.plan_for(db, character, body.to_choices()))


@router.post("/embrace")
def embrace_ghoul(
    character_id: uuid.UUID, body: EmbraceIn, db: DbSession, user: CurrentUser
) -> EmbracedOut:
    """The ghoul becomes a vampire of its sire's clan, all its steps at once or none
    (MET: VTM pp. 297–299). Its player is told."""
    character = embracing_staff(db, user, character_id)
    checked_sire(db, user, body)
    plan = embrace.embrace(db, user, character, body.to_choices(), body.embraced_on, body.note)
    db.commit()
    return EmbracedOut(plan=plan_out(plan), sheet=sheet_out(db, character))


@router.post("/embrace/died")
def died_in_embrace(
    character_id: uuid.UUID, body: EmbraceDiedIn, db: DbSession, user: CurrentUser
) -> EmbraceOut:
    """The ghoul died in the attempted Embrace: it is retired, with a note in its log."""
    character = embracing_staff(db, user, character_id)
    record = embrace.died(db, user, character, body.embraced_on, body.sire_name, body.note)
    db.commit()
    return embrace_out(db, record)


@router.get("/xp/debt")
def xp_debt_of(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> DebtOut:
    character = visible_character(db, user, character_id)
    return DebtOut(
        debt=xp_debt.debt(db, character),
        can_change=character.status == "active"
        and running_staff(db, user, character, TroupeAction.AWARD_XP),
    )


@router.post("/xp/debt")
def change_xp_debt(
    character_id: uuid.UUID, body: DebtIn, db: DbSession, user: CurrentUser
) -> DebtOut:
    """The home troupe's staff add XP debt, or forgive some of it, with a reason."""
    character = visible_character(db, user, character_id)
    troupe = home_troupe(db, character)
    if character.kind != "pc" or troupe is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Only a home troupe's staff change a character's XP debt."
        )
    require_troupe_action(db, user, troupe, TroupeAction.AWARD_XP)
    character = sheets.lock_character(db, character.id)
    sheets.ensure_unlocked(db, character)
    amount = body.amount if body.change == "add" else -body.amount
    xp_debt.adjust(db, user, character, amount, body.reason)
    db.commit()
    return DebtOut(debt=xp_debt.debt(db, character), can_change=True)
