"""Teacher rules (horatio.teaching): a troupe's storytellers make them in the Settings at
the top of Characters › Approvals; a player buying a trait one is about chooses a teacher; the
teacher's player confirms spending Willpower on it."""

import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from horatio import sheets, teaching
from horatio.api.downtimes import staff_troupe
from horatio.api.house_rules import house_splat
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, TeacherRule, Teaching, Troupe
from horatio.permissions import TroupeAction, visible_character
from horatio.rules.model import SheetTrait
from horatio.rules.teachers import TeacherRuleData, TeacherRuleProblem, check_rule, describe

router = APIRouter(tags=["house rules"])


class TeacherRuleIn(BaseModel):
    splat: str = "vampire"
    # Which traits: a category, and in it these traits (`names`) or the names
    # starting with `name_prefix`; neither for every trait of the category.
    category: str = Field(min_length=1, max_length=100)
    names: list[str] = Field(default_factory=list[str], max_length=50)
    name_prefix: str | None = Field(default=None, max_length=200)
    # For whom: a condition from the house checks' blocks; null for everyone.
    condition: dict[str, Any] | None = None
    # When: only once creation is finished (false), or always.
    always: bool = False
    # What the teacher holds: the trait at the rating bought ("same"), or at `rating`.
    holds: Literal["same", "rating"] = "same"
    rating: int | None = Field(default=None, ge=1, le=10)
    # Downtime actions learning takes.
    actions: int = Field(default=0, ge=0, le=5)
    # Willpower the teacher spends, and the games they attend before it returns.
    willpower: int = Field(default=0, ge=0, le=5)
    games: int = Field(default=0, ge=0, le=12)

    def to_data(self, rule_id: object = "draft") -> TeacherRuleData:
        return TeacherRuleData(
            id=str(rule_id),
            splat=self.splat,
            category=self.category,
            names=tuple(dict.fromkeys(n for n in self.names if n)),
            name_prefix=self.name_prefix or None,
            condition=self.condition or None,
            always=self.always,
            holds=self.holds,
            rating=self.rating if self.holds == "rating" else None,
            actions=self.actions,
            willpower=self.willpower,
            games=self.games if self.willpower else 0,
        )


class TeacherRuleOut(TeacherRuleIn):
    id: uuid.UUID
    # The rule in plain words.
    text: str
    # Why the rules cannot use it now (a trait the book has since lost), or None.
    problem: str | None


class TeacherRulePreviewOut(BaseModel):
    text: str
    # Why it cannot be saved as it is, or None.
    problem: str | None


def rule_out(db: DbSession, troupe: Troupe, row: TeacherRule) -> TeacherRuleOut:
    data = teaching.rule_data(row)
    problem = teaching.problem_of(db, troupe, data)
    return TeacherRuleOut(
        id=row.id,
        splat=row.splat,
        category=row.category,
        names=list(row.names),
        name_prefix=row.name_prefix,
        condition=row.condition,
        always=row.always,
        holds=data.holds,
        rating=row.rating,
        actions=row.actions,
        willpower=row.willpower,
        games=row.games,
        text=teaching.text_of(db, troupe, data) if problem is None else row.category,
        problem=problem,
    )


def troupe_rule(db: DbSession, troupe: Troupe, rule_id: uuid.UUID) -> TeacherRule:
    row = teaching.row_of(db, troupe, rule_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such rule.")
    return row


@router.get("/troupes/{troupe_id}/teacher-rules")
def list_teacher_rules(
    troupe_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> list[TeacherRuleOut]:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS)
    return [rule_out(db, troupe, r) for r in teaching.rule_rows(db, troupe.id)]


@router.post("/troupes/{troupe_id}/teacher-rules", status_code=status.HTTP_201_CREATED)
def add_teacher_rule(
    troupe_id: uuid.UUID, body: TeacherRuleIn, db: DbSession, user: CurrentUser
) -> TeacherRuleOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    house_splat(db, troupe.id, body.splat)
    row = teaching.create(db, user, troupe, body.to_data())
    db.commit()
    return rule_out(db, troupe, row)


@router.put("/troupes/{troupe_id}/teacher-rules/{rule_id}")
def change_teacher_rule(
    troupe_id: uuid.UUID, rule_id: uuid.UUID, body: TeacherRuleIn, db: DbSession, user: CurrentUser
) -> TeacherRuleOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    house_splat(db, troupe.id, body.splat)
    row = troupe_rule(db, troupe, rule_id)
    teaching.change(db, user, troupe, row, body.to_data(row.id))
    db.commit()
    return rule_out(db, troupe, row)


@router.delete(
    "/troupes/{troupe_id}/teacher-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_teacher_rule(
    troupe_id: uuid.UUID, rule_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> Response:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    teaching.delete(db, user, troupe, troupe_rule(db, troupe, rule_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/troupes/{troupe_id}/teacher-rules/preview")
def preview_teacher_rule(
    troupe_id: uuid.UUID, body: TeacherRuleIn, db: DbSession, user: CurrentUser
) -> TeacherRulePreviewOut:
    """The rule as it is being made, in plain words; or why it cannot be saved as it
    is. Nothing is saved."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    house_splat(db, troupe.id, body.splat)
    data = body.to_data()
    rule_set = teaching.rule_set_of(db, troupe, data.splat)
    try:
        check_rule(data, rule_set)
    except TeacherRuleProblem as problem:
        return TeacherRulePreviewOut(text="", problem=str(problem))
    return TeacherRulePreviewOut(text=describe(data, rule_set), problem=None)


# --- a character's purchases ---------------------------------------------------------


class TeacherRuleBriefOut(BaseModel):
    """A teacher rule that applies to the character now: what it is about."""

    id: uuid.UUID
    category: str
    names: list[str]
    name_prefix: str | None
    text: str


class TeacherChoiceOut(BaseModel):
    id: uuid.UUID
    name: str
    # pc | npc
    kind: str


class TeacherOptionsOut(BaseModel):
    """A purchase needs a teacher: the rule, and who in the troupe could teach it."""

    rule: str
    # The rating the teacher must hold.
    rating: int
    willpower: int
    games: int
    candidates: list[TeacherChoiceOut]


@router.get("/characters/{character_id}/teacher-rules")
def character_teacher_rules(
    character_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> list[TeacherRuleBriefOut]:
    """The troupe's teacher rules that apply to the character as its sheet stands
    (who it is, whether creation is finished), for the sheet to ask for a teacher
    before adding a trait one is about. The purchase itself is judged again."""
    character = visible_character(db, user, character_id)
    troupe_id = teaching.asks_teachers(character)
    if troupe_id is None:
        return []
    rows = teaching.rule_rows(db, troupe_id, character.splat)
    if not rows:
        return []
    troupe = db.get_one(Troupe, troupe_id)
    sheet = [r.as_rules_trait() for r in sheets.sheet_rows(db, character)]
    context = sheets.check_context(db, character, sheet)
    found: list[TeacherRuleBriefOut] = []
    for row in rows:
        data = teaching.rule_data(row)
        subject = SheetTrait(data.category, data.names[0] if data.names else "", 1)
        if teaching.problem_of(db, troupe, data) is None and data.applies(sheet, subject, context):
            found.append(
                TeacherRuleBriefOut(
                    id=row.id,
                    category=row.category,
                    names=list(row.names),
                    name_prefix=row.name_prefix,
                    text=teaching.text_of(db, troupe, data),
                )
            )
    return found


@router.get("/characters/{character_id}/teachers")
def teacher_options(
    character_id: uuid.UUID,
    category: str,
    name: str,
    db: DbSession,
    user: CurrentUser,
    rating: int = 1,
    detail: str = "",
    current: int = 0,
) -> TeacherOptionsOut | None:
    """Whether buying the trait from `current` to `rating` needs a teacher here, and
    the troupe's characters who qualify; null if it needs none."""
    character = visible_character(db, user, character_id)
    try:
        definition, _ = sheets.find_definition(db, character, category, name)
    except HTTPException:
        return None
    need = teaching.need_for(db, character, category, definition.name, detail, current, rating)
    if need is None:
        return None
    return TeacherOptionsOut(
        rule=need.text,
        rating=need.rating,
        willpower=need.rule.willpower,
        games=need.rule.games,
        candidates=[
            TeacherChoiceOut(id=c.id, name=c.name, kind=c.kind)
            for c in teaching.holders(db, character, category, definition.name, detail, need.rating)
        ],
    )


# --- the teacher -----------------------------------------------------------------------


class TeachingAskOut(BaseModel):
    """A purchase asking the character to teach it, at the cost of its Willpower."""

    id: uuid.UUID
    # "Teaching Firearms 2 to Elmer".
    what: str
    student: str
    willpower: int
    games: int


class TeachingOut(BaseModel):
    # Purchases waiting for the teacher's player to confirm.
    asked: list[TeachingAskOut]
    # Willpower out teaching, which rest does not bring back yet, in words; None for none.
    lent: str | None


def ask_out(db: DbSession, t: Teaching) -> TeachingAskOut:
    return TeachingAskOut(
        id=t.id,
        what=teaching.what_taught(db, t),
        student=db.get_one(Character, t.character_id).name,
        willpower=t.willpower,
        games=t.games,
    )


@router.get("/characters/{character_id}/teaching")
def character_teaching(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> TeachingOut:
    """What the character is asked to teach, and its Willpower out teaching."""
    character = visible_character(db, user, character_id)
    asked = [t for t in teaching.asked_of(db, character) if teaching.can_answer(db, user, t)]
    return TeachingOut(
        asked=[ask_out(db, t) for t in asked], lent=teaching.lent_text(db, character)
    )


def answerable(db: DbSession, teaching_id: uuid.UUID) -> Teaching:
    found = db.scalar(select(Teaching).where(Teaching.id == teaching_id).with_for_update())
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such teaching.")
    return found


@router.post("/teachings/{teaching_id}/confirm")
def confirm_teaching(teaching_id: uuid.UUID, db: DbSession, user: CurrentUser) -> TeachingOut:
    """The teacher's player agrees to teach: the Willpower is spent on the Play View."""
    found = teaching.answer(db, user, answerable(db, teaching_id), teach=True)
    db.commit()
    assert found.teacher_id is not None
    return character_teaching(found.teacher_id, db, user)


@router.post("/teachings/{teaching_id}/refuse")
def refuse_teaching(teaching_id: uuid.UUID, db: DbSession, user: CurrentUser) -> TeachingOut:
    """The teacher's player will not teach it; staff then decline the purchase."""
    found = teaching.answer(db, user, answerable(db, teaching_id), teach=False)
    db.commit()
    assert found.teacher_id is not None
    return character_teaching(found.teacher_id, db, user)
