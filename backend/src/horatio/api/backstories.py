"""A character's backstory, its feedback and approval, and a troupe's backstory
questions (horatio.backstories). The backstory comes only from here: never with the
sheet or the Play View."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from horatio import backstories, titles
from horatio.api.downtimes import staff_troupe
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import (
    Backstory,
    BackstoryQuestion,
    BackstoryQuestionSet,
    Character,
    Troupe,
    User,
)
from horatio.permissions import (
    TroupeAction,
    allows,
    require_troupe_action,
    troupe_role,
    visible_character,
)

router = APIRouter(tags=["backstories"])

Mode = Literal["free", "either", "wizard"]
Kind = Literal["long", "short", "year", "choice", "scale", "heading"]
Age = Literal["Neonate", "Ancilla", "Elder"]


class AgeCondition(BaseModel):
    """Shown for characters of these social ages."""

    kind: Literal["social_age"]
    ages: list[Age] = Field(min_length=1)


class SectCondition(BaseModel):
    """Shown for characters of these sects."""

    kind: Literal["sect"]
    sects: list[str] = Field(min_length=1)


class TraitCondition(BaseModel):
    """Shown for characters holding this background, merit or flaw."""

    kind: Literal["trait"]
    category: Literal["backgrounds", "merits", "flaws"]
    name: str = Field(min_length=1, max_length=200)


Condition = Annotated[AgeCondition | SectCondition | TraitCondition, Field(discriminator="kind")]
conditions: TypeAdapter[Condition] = TypeAdapter(Condition)


def condition_out(raw: dict[str, Any] | None) -> Condition | None:
    if not raw:
        return None
    try:
        return conditions.validate_python(raw)
    except ValidationError:
        return None


# --- the backstory ---------------------------------------------------------------------------


class BackstoryStandingOut(BaseModel):
    """What the person asking may do with a character's backstory, and where it
    stands, without its text."""

    read: bool
    write: bool
    # Send it back with feedback, and approve it.
    review: bool
    # Anything is written.
    written: bool = False
    length: int = 0
    changed_at: datetime | None = None
    # The troupe reading it: the one it asks to make home, or its home troupe.
    troupe_id: uuid.UUID | None = None
    troupe_name: str | None = None
    # That troupe needs it approved before accepting the character.
    required: bool = False
    # That troupe's reading: none, returned, resubmitted or approved.
    state: Literal["none", "returned", "resubmitted", "approved"] = "none"
    # Approved there, as it stands.
    approved: bool = False
    changed_since_approval: bool = False
    # How its troupe has backstories written: free text, either, or its questions.
    mode: Mode = "free"


class BackstoryThreadEntryOut(BaseModel):
    id: uuid.UUID
    kind: Literal["feedback", "reply", "approved"]
    author_name: str
    # Its player wrote it, rather than staff.
    by_player: bool
    section: str
    body: str
    at: datetime


class BackstoryLineOut(BaseModel):
    change: Literal["same", "added", "removed", "skipped"]
    text: str
    count: int = 0


class BackstoryDraftOut(BaseModel):
    """Its writer's draft, saved as they type and not yet submitted."""

    text: str
    # The version it was started from.
    based_on: int
    saved_at: datetime
    # A newer version was submitted since it was started.
    behind: bool
    # Once behind: how the draft differs from the newer version, line by line.
    differences: list[BackstoryLineOut] | None = None


class BackstoryDraftSavedOut(BaseModel):
    # The latest version: newer than the draft's when one was submitted elsewhere.
    version: int
    # None once the draft says the same as the latest version.
    draft: BackstoryDraftOut | None


class BackstoryOut(BackstoryStandingOut):
    text: str = ""
    # Name it when saving: a save over a newer version is refused.
    version: int = 0
    changed_by_name: str | None = None
    approved_at: datetime | None = None
    approved_by_name: str | None = None
    # Feedback, replies and approvals with the troupe reading it, oldest first.
    thread: list[BackstoryThreadEntryOut] = []
    # For staff, once it has changed since they approved it: what changed.
    differences: list[BackstoryLineOut] | None = None
    # For its writer: the question sets whose built sections they have since edited.
    edited_sets: list[uuid.UUID] = []
    # For its writer: their draft, if they have one. Never for staff reading it.
    draft: BackstoryDraftOut | None = None


class BackstoryIn(BaseModel):
    text: str = Field(max_length=backstories.MAX_LENGTH)
    # The version it was started from.
    version: int


class BackstoryDraftIn(BaseModel):
    text: str = Field(max_length=backstories.MAX_LENGTH)
    # The version it was started from.
    based_on: int


class BackstoryFeedbackIn(BaseModel):
    body: str = Field(min_length=1, max_length=20_000)
    # The heading of the section it is about; empty for the whole backstory.
    section: str = Field(default="", max_length=500)


class BackstoryResubmitIn(BaseModel):
    note: str = Field(default="", max_length=20_000)


class BackstoryApproveIn(BaseModel):
    # The version staff read.
    version: int
    note: str = Field(default="", max_length=20_000)


def name_of(db: DbSession, user_id: uuid.UUID | None) -> str | None:
    if user_id is None:
        return None
    found = db.get(User, user_id)
    return found.display_name if found else None


def standing(db: DbSession, user: User, character: Character) -> BackstoryStandingOut:
    allowed = backstories.access(db, user, character)
    if not allowed.read:
        return BackstoryStandingOut(read=False, write=False, review=False)
    backstory = backstories.find(db, character)
    troupe = backstories.review_troupe(db, character)
    mode, _ = backstories.mode_for(db, character)
    return BackstoryStandingOut(
        read=True,
        write=allowed.write,
        review=allowed.review,
        written=bool(backstory and backstory.text.strip()),
        length=len(backstory.text) if backstory else 0,
        changed_at=backstory.changed_at if backstory else None,
        troupe_id=troupe.id if troupe else None,
        troupe_name=troupe.name if troupe else None,
        required=bool(troupe and troupe.backstory_required),
        state=backstories.state_for(backstory, troupe),  # type: ignore[arg-type]
        approved=bool(troupe and backstories.approved_for(backstory, troupe)),
        changed_since_approval=backstories.changed_since_approval(backstory, troupe),
        mode=mode,  # type: ignore[arg-type]
    )


def lines_out(old: str, new: str) -> list[BackstoryLineOut]:
    return [
        BackstoryLineOut(change=line.change, text=line.text, count=line.count)  # type: ignore[arg-type]
        for line in backstories.differences(old, new)
    ]


def draft_out(backstory: Backstory) -> BackstoryDraftOut | None:
    if backstory.draft_text is None or backstory.draft_at is None:
        return None
    based_on = backstory.draft_version or 0
    behind = based_on != backstory.version
    return BackstoryDraftOut(
        text=backstory.draft_text,
        based_on=based_on,
        saved_at=backstory.draft_at,
        behind=behind,
        differences=lines_out(backstory.text, backstory.draft_text) if behind else None,
    )


def backstory_out(db: DbSession, user: User, character: Character) -> BackstoryOut:
    found = standing(db, user, character)
    backstory = backstories.find(db, character)
    if backstory is None:
        return BackstoryOut(**found.model_dump())
    troupe = backstories.review_troupe(db, character)
    differences = None
    if found.review and found.changed_since_approval and backstory.approved_text is not None:
        differences = lines_out(backstory.approved_text, backstory.text)
    return BackstoryOut(
        **found.model_dump(),
        text=backstory.text,
        version=backstory.version,
        changed_by_name=name_of(db, backstory.changed_by),
        approved_at=backstory.approved_at if found.state == "approved" else None,
        approved_by_name=name_of(db, backstory.approved_by) if found.state == "approved" else None,
        thread=[
            BackstoryThreadEntryOut(
                id=e.id,
                kind=e.kind,  # type: ignore[arg-type]
                author_name=name_of(db, e.author_id) or "Someone",
                by_player=e.kind == "reply",
                section=e.section,
                body=e.body,
                at=e.created_at,
            )
            for e in backstories.thread(db, character, troupe)
        ],
        differences=differences,
        edited_sets=[uuid.UUID(s) for s in backstories.edited_sets(backstory)]
        if found.write
        else [],
        draft=draft_out(backstory) if found.write else None,
    )


def written_character(db: DbSession, user: User, character_id: uuid.UUID) -> Character:
    character = visible_character(db, user, character_id)
    if not backstories.access(db, user, character).write:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the character's player writes its backstory."
        )
    if character.status == "retired":
        raise HTTPException(status.HTTP_409_CONFLICT, "This character is retired.")
    return character


@router.get("/characters/{character_id}/backstory/standing")
def backstory_standing(
    character_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> BackstoryStandingOut:
    """Whether the person may read the backstory, and where it stands, without its text."""
    return standing(db, user, visible_character(db, user, character_id))


@router.get("/characters/{character_id}/backstory")
def get_backstory(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> BackstoryOut:
    character = visible_character(db, user, character_id)
    backstories.readable(db, user, character)
    return backstory_out(db, user, character)


@router.put("/characters/{character_id}/backstory")
def save_backstory(
    character_id: uuid.UUID, body: BackstoryIn, db: DbSession, user: CurrentUser
) -> BackstoryOut:
    """Submit the backstory as its next version, started from `version`: refused if a
    newer one was submitted since. The draft goes."""
    character = written_character(db, user, character_id)
    backstories.save(db, user, character, body.text, body.version)
    db.commit()
    return backstory_out(db, user, character)


@router.put("/characters/{character_id}/backstory/draft")
def save_draft(
    character_id: uuid.UUID, body: BackstoryDraftIn, db: DbSession, user: CurrentUser
) -> BackstoryDraftSavedOut:
    """Keep the writer's draft as they type, without making a version."""
    character = written_character(db, user, character_id)
    backstory = backstories.save_draft(db, character, body.text, body.based_on)
    db.commit()
    return BackstoryDraftSavedOut(version=backstory.version, draft=draft_out(backstory))


@router.delete("/characters/{character_id}/backstory/draft")
def discard_draft(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> BackstoryOut:
    """Throw the draft away, keeping the latest version."""
    character = written_character(db, user, character_id)
    backstories.discard_draft(db, character)
    db.commit()
    return backstory_out(db, user, character)


@router.post("/characters/{character_id}/backstory/feedback")
def send_back(
    character_id: uuid.UUID, body: BackstoryFeedbackIn, db: DbSession, user: CurrentUser
) -> BackstoryOut:
    """Send the backstory back to its player with feedback, without declining the
    character."""
    character = visible_character(db, user, character_id)
    backstories.send_back(db, user, character, body.body, body.section)
    db.commit()
    return backstory_out(db, user, character)


@router.post("/characters/{character_id}/backstory/resubmit")
def resubmit(
    character_id: uuid.UUID, body: BackstoryResubmitIn, db: DbSession, user: CurrentUser
) -> BackstoryOut:
    character = written_character(db, user, character_id)
    backstories.resubmit(db, user, character, body.note)
    db.commit()
    return backstory_out(db, user, character)


@router.post("/characters/{character_id}/backstory/approve")
def approve(
    character_id: uuid.UUID, body: BackstoryApproveIn, db: DbSession, user: CurrentUser
) -> BackstoryOut:
    character = visible_character(db, user, character_id)
    backstories.approve(db, user, character, body.version, body.note)
    db.commit()
    return backstory_out(db, user, character)


# --- the troupe's questions, as a character answers them -------------------------------------


class AnsweredQuestionOut(BaseModel):
    id: uuid.UUID
    kind: Kind
    text: str
    title: str
    hint: str
    optional: bool
    options: list[str]
    answer: str
    # The answer in words: a scale's point as "More Action than Intrigue".
    answer_text: str
    # Archived since it was answered: staff still read the answer.
    archived: bool


class AnsweredSetOut(BaseModel):
    id: uuid.UUID
    name: str
    # Its sections are in the backstory.
    built: bool
    questions: list[AnsweredQuestionOut]


class CharacterQuestionsOut(BaseModel):
    mode: Mode
    troupe_name: str | None
    sets: list[AnsweredSetOut]


class BackstoryAnswerIn(BaseModel):
    answer: str = Field(max_length=backstories.MAX_LENGTH)


class BackstoryAnswerOut(BaseModel):
    question_id: uuid.UUID
    answer: str


class BackstoryBuildIn(BaseModel):
    # Build again over sections the player has edited since they were built.
    replace_edits: bool = False


@router.get("/characters/{character_id}/backstory/questions")
def character_questions(
    character_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> CharacterQuestionsOut:
    """For its writer, the questions the character is asked, with its answers. For
    staff reading it, the questions answered, as question and answer, including any
    archived since."""
    character = visible_character(db, user, character_id)
    allowed = backstories.readable(db, user, character)
    mode, troupe = backstories.mode_for(db, character)
    if troupe is None:
        return CharacterQuestionsOut(mode="free", troupe_name=None, sets=[])
    if mode == "free" and allowed.write:
        # Under free text only, the questions aren't offered.
        return CharacterQuestionsOut(mode="free", troupe_name=troupe.name, sets=[])
    known = backstories.facts(db, character)
    given = backstories.answers(db, character)
    backstory = backstories.find(db, character)
    built = set(backstory.built) if backstory else set()
    sets: list[AnsweredSetOut] = []
    for question_set, questions in backstories.question_sets(db, troupe):
        if allowed.write:
            asked = [
                q
                for q in questions
                if question_set.archived_at is None
                and q.archived_at is None
                and backstories.shown(q.condition, known)
            ]
        else:
            asked = [q for q in questions if q.kind == "heading" or given.get(q.id)]
        if not any(q.kind != "heading" for q in asked):
            continue
        sets.append(
            AnsweredSetOut(
                id=question_set.id,
                name=question_set.name,
                built=str(question_set.id) in built,
                questions=[
                    AnsweredQuestionOut(
                        id=q.id,
                        kind=q.kind,  # type: ignore[arg-type]
                        text=q.text,
                        title=q.title,
                        hint=q.hint,
                        optional=q.optional,
                        options=q.options,
                        answer=given.get(q.id, ""),
                        answer_text=backstories.shown_answer(q, given.get(q.id, "")),
                        archived=q.archived_at is not None,
                    )
                    for q in asked
                ],
            )
        )
    return CharacterQuestionsOut(
        mode=mode,  # type: ignore[arg-type]
        troupe_name=troupe.name,
        sets=sets,
    )


@router.put("/characters/{character_id}/backstory/answers/{question_id}")
def answer_question(
    character_id: uuid.UUID,
    question_id: uuid.UUID,
    body: BackstoryAnswerIn,
    db: DbSession,
    user: CurrentUser,
) -> BackstoryAnswerOut:
    """Save one answer, as the player goes."""
    character = written_character(db, user, character_id)
    kept = backstories.answer(db, character, question_id, body.answer)
    db.commit()
    return BackstoryAnswerOut(question_id=question_id, answer=kept)


@router.post("/characters/{character_id}/backstory/sets/{set_id}/build")
def build(
    character_id: uuid.UUID,
    set_id: uuid.UUID,
    body: BackstoryBuildIn,
    db: DbSession,
    user: CurrentUser,
) -> BackstoryOut:
    """Write a set's answers into the backstory as its sections, replacing only those
    it built before."""
    character = written_character(db, user, character_id)
    backstories.build(db, user, character, set_id, body.replace_edits)
    db.commit()
    return backstory_out(db, user, character)


# --- the troupe's questions, as its storytellers keep them -----------------------------------


class BackstoryQuestionOut(BaseModel):
    id: uuid.UUID
    kind: Kind
    text: str
    title: str
    hint: str
    optional: bool
    options: list[str]
    condition: Condition | None
    archived: bool


class BackstoryQuestionSetOut(BaseModel):
    id: uuid.UUID
    name: str
    archived: bool
    questions: list[BackstoryQuestionOut]


class BackstorySettingsOut(BaseModel):
    mode: Mode
    required: bool
    # The person may change them: the troupe's storytellers.
    can_edit: bool
    sets: list[BackstoryQuestionSetOut]
    # Every sect, for a question shown only to some.
    sects: list[str]


class BackstorySettingsIn(BaseModel):
    mode: Mode
    required: bool


class BackstoryQuestionSetIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class BackstoryQuestionSetChange(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    archived: bool | None = None
    move: Literal["up", "down"] | None = None


class BackstoryQuestionIn(BaseModel):
    kind: Kind
    text: str = Field(min_length=1, max_length=5_000)
    title: str = Field(default="", max_length=200)
    hint: str = Field(default="", max_length=5_000)
    optional: bool = False
    options: list[Annotated[str, Field(max_length=200)]] = Field(default=[], max_length=30)
    condition: Condition | None = None


class BackstoryQuestionChange(BaseModel):
    """Change a question's words and the rest, archive it or bring it back, or move it."""

    question: BackstoryQuestionIn | None = None
    archived: bool | None = None
    move: Literal["up", "down"] | None = None


def settings_out(db: DbSession, user: User, troupe: Troupe) -> BackstorySettingsOut:
    return BackstorySettingsOut(
        mode=troupe.backstory_mode,  # type: ignore[arg-type]
        required=troupe.backstory_required,
        can_edit=allows(
            troupe_role(db, user, troupe),
            TroupeAction.MANAGE_HOUSE_RULES,
            is_custodian=user.is_custodian,
        ),
        sets=[
            BackstoryQuestionSetOut(
                id=s.id,
                name=s.name,
                archived=s.archived_at is not None,
                questions=[
                    BackstoryQuestionOut(
                        id=q.id,
                        kind=q.kind,  # type: ignore[arg-type]
                        text=q.text,
                        title=q.title,
                        hint=q.hint,
                        optional=q.optional,
                        options=q.options,
                        condition=condition_out(q.condition),
                        archived=q.archived_at is not None,
                    )
                    for q in questions
                ],
            )
            for s, questions in backstories.question_sets(db, troupe)
        ],
        sects=titles.sect_names(db),
    )


def question_data(body: BackstoryQuestionIn) -> backstories.QuestionData:
    return backstories.QuestionData(
        kind=body.kind,
        text=body.text,
        title=body.title,
        hint=body.hint,
        optional=body.optional,
        options=body.options,
        condition=body.condition.model_dump() if body.condition else None,
    )


def kept_set(db: DbSession, user: User, set_id: uuid.UUID) -> BackstoryQuestionSet:
    found = db.get(BackstoryQuestionSet, set_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such question set.")
    require_troupe_action(
        db, user, db.get_one(Troupe, found.troupe_id), TroupeAction.MANAGE_HOUSE_RULES
    )
    return found


@router.get("/troupes/{troupe_id}/backstory-settings")
def backstory_settings(
    troupe_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> BackstorySettingsOut:
    """How the troupe's backstories are written, whether one must be approved before a
    character is accepted, and its questions. For its staff."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.VIEW_STAFF)
    return settings_out(db, user, troupe)


@router.put("/troupes/{troupe_id}/backstory-settings")
def set_backstory_settings(
    troupe_id: uuid.UUID, body: BackstorySettingsIn, db: DbSession, user: CurrentUser
) -> BackstorySettingsOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    backstories.set_settings(db, user, troupe, body.mode, body.required)
    db.commit()
    return settings_out(db, user, troupe)


@router.post("/troupes/{troupe_id}/backstory-template")
def load_template(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> BackstorySettingsOut:
    """Add the starting template's question sets, for the troupe to edit."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    backstories.load_template(db, user, troupe)
    db.commit()
    return settings_out(db, user, troupe)


@router.post("/troupes/{troupe_id}/backstory-sets", status_code=status.HTTP_201_CREATED)
def add_set(
    troupe_id: uuid.UUID, body: BackstoryQuestionSetIn, db: DbSession, user: CurrentUser
) -> BackstorySettingsOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    backstories.add_set(db, user, troupe, body.name)
    db.commit()
    return settings_out(db, user, troupe)


@router.patch("/backstory-sets/{set_id}")
def change_set(
    set_id: uuid.UUID, body: BackstoryQuestionSetChange, db: DbSession, user: CurrentUser
) -> BackstorySettingsOut:
    question_set = kept_set(db, user, set_id)
    backstories.change_set(db, user, question_set, body.name, body.archived)
    if body.move:
        backstories.move(db, question_set, body.move == "up")
    db.commit()
    return settings_out(db, user, db.get_one(Troupe, question_set.troupe_id))


@router.post("/backstory-sets/{set_id}/questions", status_code=status.HTTP_201_CREATED)
def add_question(
    set_id: uuid.UUID, body: BackstoryQuestionIn, db: DbSession, user: CurrentUser
) -> BackstorySettingsOut:
    question_set = kept_set(db, user, set_id)
    backstories.add_question(db, user, question_set, question_data(body))
    db.commit()
    return settings_out(db, user, db.get_one(Troupe, question_set.troupe_id))


@router.patch("/backstory-questions/{question_id}")
def change_question(
    question_id: uuid.UUID, body: BackstoryQuestionChange, db: DbSession, user: CurrentUser
) -> BackstorySettingsOut:
    question = db.get(BackstoryQuestion, question_id)
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such question.")
    question_set = kept_set(db, user, question.set_id)
    if body.question is not None:
        backstories.change_question(db, user, question, question_data(body.question))
    if body.archived is not None:
        backstories.archive_question(db, user, question, body.archived)
    if body.move:
        backstories.move(db, question, body.move == "up")
    db.commit()
    return settings_out(db, user, db.get_one(Troupe, question_set.troupe_id))
