"""A character's backstory (issue #343).

**The text.** One per character, in Markdown, kept in its own table so that loading
the sheet or the Play View never loads it. It saves only when its writer presses
Save, naming the version they opened: if it has changed since, the save is refused
rather than overwriting the newer one. A save goes in the character's log, without
the text. A PC's player writes it; an NPC's troupe's storytellers and assistant
storytellers do.

**Who reads it** (horatio.permissions.can_read_backstory): its player, the custodian,
and the storytellers and assistant storytellers of its home troupe and of a troupe it
asks to make its home. Never narrators, a visiting troupe's staff or other players.

**The troupe's questions.** A troupe chooses in its house rules how backstories are
written (`Troupe.backstory_mode`): free text only, free text or its questions, or its
questions only. Its questions come in sets, in order, each question of a kind (long
or short answer, year, choice, a scale between two poles, or a heading only) and
shown only when its condition holds on the sheet: the character's social age, its
sect or a trait it holds. Answers are kept per question, saved as the player goes.

Building a set from its answers writes its sections into the backstory between two
marks, `<!-- questions:<set id> -->` and `<!-- /questions:<set id> -->`: `## <question>`
(or its short title) then the answer, for each answered question in order, and
`# <heading>` for a heading-only question with answered questions under it.
Building again replaces only what is between that set's marks, and keeps everything
the player wrote outside them; a set built for the first time, or whose marks the
player removed, goes at the end. What each set last built is kept, so the player is
asked before building again replaces edits they made between the marks.

**Approval.** The backstory is read by the troupe deciding the character's home troupe
change, or its home troupe once accepted (`review_troupe`). Its storytellers and
assistant storytellers send it back with feedback, overall or on one section, and the
player resubmits it with a reply; or they approve it. A troupe that requires it
(`Troupe.backstory_required`, on by default) accepts a PC only with its backstory
approved there, as it stands. A change after approval shows staff what changed.
"""

import difflib
import re
import tomllib
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio import audit, social_age
from horatio.models import (
    Approval,
    Backstory,
    BackstoryAnswer,
    BackstoryFeedback,
    BackstoryQuestion,
    BackstoryQuestionSet,
    Character,
    Troupe,
    User,
)
from horatio.notifications import approvers, notify
from horatio.permissions import (
    TroupeAction,
    allows,
    can_edit_character,
    can_read_backstory,
    troupe_role,
)
from horatio.sheets import conflict, sheet_rows, unprocessable

# About 80,000 words. Postgres `text` holds far more.
MAX_LENGTH = 500_000
MODES = ("free", "either", "wizard")
MODE_WORDS = {
    "free": "free text only",
    "either": "free text or the troupe's questions",
    "wizard": "the troupe's questions only",
}
AGES = social_age.AGES
TEMPLATE_FILE = Path(__file__).parent / "backstory_template.toml"
# The kinds that take an answer, and the scale's five points.
ANSWERED = ("long", "short", "year", "choice", "scale")
SCALE_POINTS = 5


def now() -> datetime:
    return datetime.now(UTC)


# --- who may do what -----------------------------------------------------------------------


def pending_troupe(db: Session, character: Character) -> Troupe | None:
    """The troupe the character asks to make its home, while that request waits."""
    return db.scalar(
        select(Troupe)
        .join(Approval, Approval.troupe_id == Troupe.id)
        .where(
            Approval.character_id == character.id,
            Approval.kind == "home_troupe_change",
            Approval.status == "pending",
        )
    )


def review_troupe(db: Session, character: Character) -> Troupe | None:
    """The troupe whose staff read and approve a PC's backstory: the one it asks to
    make its home, or its home troupe. None for an NPC, which needs no approval."""
    if character.kind != "pc":
        return None
    found = pending_troupe(db, character)
    if found is None and character.home_troupe_id is not None:
        found = db.get(Troupe, character.home_troupe_id)
    return found


def question_troupe(db: Session, character: Character) -> Troupe | None:
    """The troupe whose questions the character answers: an NPC's own troupe; a PC's
    troupe it asks to make home, its home troupe, or the troupe it is built for."""
    if character.kind == "npc":
        return db.get(Troupe, character.owner_troupe_id)
    found = review_troupe(db, character)
    if found is None and character.building_troupe_id is not None:
        found = db.get(Troupe, character.building_troupe_id)
    return found


@dataclass(frozen=True)
class Access:
    read: bool
    write: bool
    # Send it back with feedback, and approve it.
    review: bool


def access(db: Session, user: User, character: Character) -> Access:
    read = can_read_backstory(db, user, character)
    write = read and can_edit_character(db, user, character)
    troupe = review_troupe(db, character)
    review = (
        read
        and troupe is not None
        and character.player_id != user.id
        and (troupe.archived_at is None or user.is_custodian)
        and allows(
            troupe_role(db, user, troupe),
            TroupeAction.APPROVE_CHANGES,
            is_custodian=user.is_custodian,
        )
    )
    return Access(read=read, write=write, review=review)


def readable(db: Session, user: User, character: Character) -> Access:
    found = access(db, user, character)
    if not found.read:
        raise forbidden("Only the character's player and its storytellers read its backstory.")
    return found


def forbidden(message: str) -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, message)


# --- the text --------------------------------------------------------------------------------


def find(db: Session, character: Character, *, lock: bool = False) -> Backstory | None:
    query = select(Backstory).where(Backstory.character_id == character.id)
    if lock:
        query = query.with_for_update()
    return db.scalar(query)


def held(db: Session, character: Character) -> Backstory:
    """The character's backstory, locked for a change, made empty if it has none."""
    found = find(db, character, lock=True)
    if found is None:
        found = Backstory(character_id=character.id, text="", version=0, built={})
        db.add(found)
        db.flush()
    return found


def approved_for(backstory: Backstory | None, troupe: Troupe) -> bool:
    """Approved by `troupe`'s staff, and unchanged since."""
    return (
        backstory is not None
        and backstory.review == "approved"
        and backstory.review_troupe_id == troupe.id
        and backstory.approved_text == backstory.text
    )


def state_for(backstory: Backstory | None, troupe: Troupe | None) -> str:
    """Where `troupe`'s reading of the backstory stands: "none" if it has done
    nothing with it, else as kept."""
    if backstory is None or troupe is None or backstory.review_troupe_id != troupe.id:
        return "none"
    return backstory.review


def changed_since_approval(backstory: Backstory | None, troupe: Troupe | None) -> bool:
    return (
        state_for(backstory, troupe) == "approved"
        and backstory is not None
        and backstory.approved_text != backstory.text
    )


def write(
    db: Session, user: User, character: Character, backstory: Backstory, text: str, how: str
) -> None:
    """Put `text` in place, logged as `how` ("saved", "built"). Its staff are told when
    an approved backstory first changes."""
    if len(text) > MAX_LENGTH:
        raise unprocessable(f"A backstory can be at most {MAX_LENGTH:,} characters.")
    if text == backstory.text:
        return
    was_approved = backstory.review == "approved" and backstory.approved_text == backstory.text
    backstory.text = text
    backstory.version += 1
    backstory.changed_at = now()
    backstory.changed_by = user.id
    db.flush()
    audit.record(
        db,
        user,
        "backstory.changed",
        troupe_id=character.home_troupe_id or character.owner_troupe_id,
        character_id=character.id,
        kind=how,
    )
    troupe = review_troupe(db, character)
    if was_approved and troupe is not None and backstory.review_troupe_id == troupe.id:
        notify(
            db,
            [p for p in approvers(db, troupe) if p != user.id],
            "backstory.changed",
            f"{character.name}'s backstory has changed since it was approved",
            f"/characters/{character.id}/backstory",
            troupe_id=troupe.id,
            character_id=character.id,
        )


def save(db: Session, user: User, character: Character, text: str, version: int) -> Backstory:
    backstory = held(db, character)
    if version != backstory.version:
        raise conflict(
            "The backstory has changed since you opened it, perhaps on another device."
            " Copy your text somewhere safe, then load the newer version."
        )
    write(db, user, character, backstory, text, "saved")
    return backstory


# --- feedback and approval -------------------------------------------------------------------


def reviewing(db: Session, user: User, character: Character) -> Troupe:
    if not access(db, user, character).review:
        raise forbidden(
            "Only the storytellers and assistant storytellers deciding on the character"
            " review its backstory."
        )
    troupe = review_troupe(db, character)
    assert troupe is not None
    return troupe


def send_back(
    db: Session, staff: User, character: Character, body: str, section: str
) -> BackstoryFeedback:
    """Send the backstory back with feedback, overall or on one section, without
    declining the character."""
    troupe = reviewing(db, staff, character)
    body, section = body.strip(), section.strip()
    if not body:
        raise unprocessable("Say what you would like changed.")
    backstory = held(db, character)
    backstory.review = "returned"
    backstory.review_troupe_id = troupe.id
    entry = BackstoryFeedback(
        character_id=character.id,
        troupe_id=troupe.id,
        author_id=staff.id,
        kind="feedback",
        section=section,
        body=body,
    )
    db.add(entry)
    db.flush()
    audit.record(db, staff, "backstory.returned", troupe_id=troupe.id, character_id=character.id)
    on = f" (on “{section}”)" if section else ""
    notify(
        db,
        [character.player_id],
        "backstory.returned",
        f"{troupe.name} sent {character.name}'s backstory back{on}: {shorten(body)}",
        f"/characters/{character.id}/backstory",
        troupe_id=troupe.id,
        character_id=character.id,
    )
    return entry


def resubmit(db: Session, player: User, character: Character, note: str) -> None:
    """The player sends the backstory back to staff after revising it, with a reply."""
    troupe = review_troupe(db, character)
    backstory = held(db, character)
    if troupe is None or state_for(backstory, troupe) != "returned":
        raise conflict("Nothing has been sent back to resubmit.")
    backstory.review = "resubmitted"
    if note.strip():
        db.add(
            BackstoryFeedback(
                character_id=character.id,
                troupe_id=troupe.id,
                author_id=player.id,
                kind="reply",
                body=note.strip(),
            )
        )
    db.flush()
    audit.record(
        db, player, "backstory.resubmitted", troupe_id=troupe.id, character_id=character.id
    )
    notify(
        db,
        [p for p in approvers(db, troupe) if p != player.id],
        "backstory.resubmitted",
        f"{character.name}'s backstory is revised and back with you",
        f"/characters/{character.id}/backstory",
        troupe_id=troupe.id,
        character_id=character.id,
    )


def approve(db: Session, staff: User, character: Character, version: int, note: str) -> None:
    troupe = reviewing(db, staff, character)
    backstory = held(db, character)
    if not backstory.text.strip():
        raise conflict("There is no backstory to approve yet.")
    if version != backstory.version:
        raise conflict("The backstory has changed since you opened it. Read it again first.")
    backstory.review = "approved"
    backstory.review_troupe_id = troupe.id
    backstory.approved_text = backstory.text
    backstory.approved_at = now()
    backstory.approved_by = staff.id
    db.add(
        BackstoryFeedback(
            character_id=character.id,
            troupe_id=troupe.id,
            author_id=staff.id,
            kind="approved",
            body=note.strip(),
        )
    )
    db.flush()
    audit.record(db, staff, "backstory.approved", troupe_id=troupe.id, character_id=character.id)
    notify(
        db,
        [character.player_id],
        "backstory.approved",
        f"{troupe.name} approved {character.name}'s backstory",
        f"/characters/{character.id}/backstory",
        troupe_id=troupe.id,
        character_id=character.id,
    )


def ensure_approved(db: Session, character: Character, troupe: Troupe) -> None:
    """Accepting a PC into a troupe that requires it needs its backstory approved there."""
    if character.kind != "pc" or not troupe.backstory_required:
        return
    backstory = find(db, character)
    if approved_for(backstory, troupe):
        return
    if changed_since_approval(backstory, troupe):
        raise conflict(
            f"{character.name}'s backstory has changed since it was approved."
            " Approve it again before accepting the character."
        )
    raise conflict(
        f"{troupe.name} needs {character.name}'s backstory approved before accepting the character."
    )


def thread(db: Session, character: Character, troupe: Troupe | None) -> list[BackstoryFeedback]:
    """The feedback, replies and approvals between the player and `troupe`, oldest first."""
    if troupe is None:
        return []
    return list(
        db.scalars(
            select(BackstoryFeedback)
            .where(
                BackstoryFeedback.character_id == character.id,
                BackstoryFeedback.troupe_id == troupe.id,
            )
            .order_by(BackstoryFeedback.created_at, BackstoryFeedback.id)
        )
    )


def shorten(text: str, length: int = 80) -> str:
    text = " ".join(text.split())
    return text if len(text) <= length else text[: length - 1].rstrip() + "…"


@dataclass(frozen=True)
class Line:
    # "same", "added", "removed", or "skipped" for unchanged lines left out.
    change: str
    text: str
    # For "skipped": how many lines.
    count: int = 0


# Unchanged lines kept either side of a change; longer runs are skipped.
CONTEXT = 2


def differences(old: str, new: str) -> list[Line]:
    """What changed from `old` to `new`, line by line, with a little context."""
    before, after = old.split("\n"), new.split("\n")
    lines: list[Line] = []
    matcher = difflib.SequenceMatcher(None, before, after, autojunk=False)
    for op, b1, b2, a1, a2 in matcher.get_opcodes():
        if op == "equal":
            same = before[b1:b2]
            first, last = b1 == 0, b2 == len(before)
            keep_start = 0 if first else CONTEXT
            keep_end = 0 if last else CONTEXT
            if len(same) > keep_start + keep_end + 1:
                lines += [Line("same", t) for t in same[:keep_start]]
                lines.append(Line("skipped", "", len(same) - keep_start - keep_end))
                lines += [Line("same", t) for t in same[len(same) - keep_end :]]
            else:
                lines += [Line("same", t) for t in same]
            continue
        lines += [Line("removed", t) for t in before[b1:b2]]
        lines += [Line("added", t) for t in after[a1:a2]]
    return lines


# --- the troupe's questions ------------------------------------------------------------------


def set_settings(db: Session, user: User, troupe: Troupe, mode: str, required: bool) -> None:
    troupe.backstory_mode = mode
    troupe.backstory_required = required
    db.flush()
    audit.record(
        db,
        user,
        "house.backstories",
        troupe_id=troupe.id,
        mode=MODE_WORDS[mode],
        required="needed to join" if required else "not needed to join",
    )


def question_sets(
    db: Session, troupe: Troupe, *, archived: bool = True
) -> list[tuple[BackstoryQuestionSet, list[BackstoryQuestion]]]:
    """The troupe's sets in order, each with its questions in order."""
    query = select(BackstoryQuestionSet).where(BackstoryQuestionSet.troupe_id == troupe.id)
    if not archived:
        query = query.where(BackstoryQuestionSet.archived_at.is_(None))
    sets = list(db.scalars(query.order_by(BackstoryQuestionSet.position)))
    questions: dict[uuid.UUID, list[BackstoryQuestion]] = {s.id: [] for s in sets}
    found = select(BackstoryQuestion).where(BackstoryQuestion.set_id.in_(list(questions)))
    if not archived:
        found = found.where(BackstoryQuestion.archived_at.is_(None))
    for q in db.scalars(found.order_by(BackstoryQuestion.position)):
        questions[q.set_id].append(q)
    return [(s, questions[s.id]) for s in sets]


def next_position(db: Session, column: Any, *where: Any) -> int:
    return (db.scalar(select(func.max(column)).where(*where)) or 0) + 1


def add_set(db: Session, user: User, troupe: Troupe, name: str) -> BackstoryQuestionSet:
    found = BackstoryQuestionSet(
        troupe_id=troupe.id,
        name=name.strip(),
        position=next_position(
            db, BackstoryQuestionSet.position, BackstoryQuestionSet.troupe_id == troupe.id
        ),
    )
    db.add(found)
    db.flush()
    audit.record(
        db, user, "house.backstory_set", troupe_id=troupe.id, change="added", name=found.name
    )
    return found


def change_set(
    db: Session,
    user: User,
    question_set: BackstoryQuestionSet,
    name: str | None,
    archived: bool | None,
) -> None:
    """Rename a set, or archive it or bring it back. Its answers are kept either way."""
    changes: list[str] = []
    if name is not None and name.strip() and name.strip() != question_set.name:
        question_set.name = name.strip()
        changes.append("renamed")
    if archived is not None and archived != (question_set.archived_at is not None):
        question_set.archived_at = now() if archived else None
        changes.append("archived" if archived else "brought back")
    db.flush()
    for change in changes:
        audit.record(
            db,
            user,
            "house.backstory_set",
            troupe_id=question_set.troupe_id,
            change=change,
            name=question_set.name,
        )


@dataclass(frozen=True)
class QuestionData:
    kind: str
    text: str
    title: str = ""
    hint: str = ""
    optional: bool = False
    options: Sequence[str] = ()
    condition: Mapping[str, Any] | None = None


def checked(data: QuestionData) -> QuestionData:
    """Refuse a question whose options do not fit its kind; tidy what it says."""
    options = [o.strip() for o in data.options if o.strip()]
    if data.kind == "choice" and len(options) < 2:
        raise unprocessable("A choice needs at least two options.")
    if data.kind == "scale" and len(options) != 2:
        raise unprocessable("A scale needs its two poles, such as Action and Intrigue.")
    if data.kind not in ("choice", "scale"):
        options = []
    if not data.text.strip():
        raise unprocessable("A question needs its words.")
    return QuestionData(
        kind=data.kind,
        text=data.text.strip(),
        title=data.title.strip(),
        hint=data.hint.strip(),
        optional=data.optional and data.kind != "heading",
        options=options,
        condition=dict(data.condition) if data.condition else None,
    )


def add_question(
    db: Session, user: User, question_set: BackstoryQuestionSet, data: QuestionData
) -> BackstoryQuestion:
    data = checked(data)
    found = BackstoryQuestion(
        set_id=question_set.id,
        position=next_position(
            db, BackstoryQuestion.position, BackstoryQuestion.set_id == question_set.id
        ),
        kind=data.kind,
        text=data.text,
        title=data.title,
        hint=data.hint,
        optional=data.optional,
        options=list(data.options),
        condition=dict(data.condition) if data.condition else None,
    )
    db.add(found)
    db.flush()
    audit.record(
        db,
        user,
        "house.backstory_question",
        troupe_id=question_set.troupe_id,
        change="added",
        question=shorten(found.title or found.text, 60),
    )
    return found


def change_question(
    db: Session, user: User, question: BackstoryQuestion, data: QuestionData
) -> None:
    data = checked(data)
    question.kind = data.kind
    question.text = data.text
    question.title = data.title
    question.hint = data.hint
    question.optional = data.optional
    question.options = list(data.options)
    question.condition = dict(data.condition) if data.condition else None
    db.flush()
    troupe_id = db.get_one(BackstoryQuestionSet, question.set_id).troupe_id
    audit.record(
        db,
        user,
        "house.backstory_question",
        troupe_id=troupe_id,
        change="changed",
        question=shorten(question.title or question.text, 60),
    )


def archive_question(db: Session, user: User, question: BackstoryQuestion, archived: bool) -> None:
    """Archive a question, or bring it back. Its answers are kept either way."""
    question.archived_at = now() if archived else None
    db.flush()
    troupe_id = db.get_one(BackstoryQuestionSet, question.set_id).troupe_id
    audit.record(
        db,
        user,
        "house.backstory_question",
        troupe_id=troupe_id,
        change="archived" if archived else "brought back",
        question=shorten(question.title or question.text, 60),
    )


def move(db: Session, item: BackstoryQuestion | BackstoryQuestionSet, up: bool) -> None:
    """Swap a question with its neighbour in its set, or a set with its neighbour."""
    if isinstance(item, BackstoryQuestion):
        query = select(BackstoryQuestion).where(BackstoryQuestion.set_id == item.set_id)
        column: Any = BackstoryQuestion.position
    else:
        query = select(BackstoryQuestionSet).where(BackstoryQuestionSet.troupe_id == item.troupe_id)
        column = BackstoryQuestionSet.position
    query = (
        query.where(column < item.position).order_by(column.desc())
        if up
        else query.where(column > item.position).order_by(column)
    )
    neighbour = db.scalars(query.limit(1)).first()
    if neighbour is None:
        return
    item.position, neighbour.position = neighbour.position, item.position
    db.flush()


def load_template(db: Session, user: User, troupe: Troupe) -> list[BackstoryQuestionSet]:
    """Add the starting template's sets after the troupe's own, for it to edit."""
    with TEMPLATE_FILE.open("rb") as f:
        template = tomllib.load(f)
    made: list[BackstoryQuestionSet] = []
    for raw in template["sets"]:
        question_set = BackstoryQuestionSet(
            troupe_id=troupe.id,
            name=raw["name"],
            position=next_position(
                db, BackstoryQuestionSet.position, BackstoryQuestionSet.troupe_id == troupe.id
            ),
        )
        db.add(question_set)
        db.flush()
        for position, q in enumerate(raw["questions"], start=1):
            data = checked(
                QuestionData(
                    kind=q["kind"],
                    text=q["text"].replace("{troupe}", troupe.name),
                    title=q.get("title", ""),
                    hint=q.get("hint", ""),
                    optional=q.get("optional", False),
                    options=q.get("options", []),
                    condition=q.get("condition"),
                )
            )
            db.add(
                BackstoryQuestion(
                    set_id=question_set.id,
                    position=position,
                    kind=data.kind,
                    text=data.text,
                    title=data.title,
                    hint=data.hint,
                    optional=data.optional,
                    options=list(data.options),
                    condition=dict(data.condition) if data.condition else None,
                )
            )
        made.append(question_set)
    db.flush()
    audit.record(db, user, "house.backstory_template", troupe_id=troupe.id)
    return made


# --- answering them --------------------------------------------------------------------------


@dataclass(frozen=True)
class Facts:
    """What the sheet says that a question's condition can ask about."""

    age: str | None
    sect: str | None
    # (category, name), the name casefolded, for each trait held.
    traits: frozenset[tuple[str, str]]


def facts(db: Session, character: Character) -> Facts:
    rows = sheet_rows(db, character)
    sect = next((r.definition.name for r in rows if r.category.key == "sect"), None)
    age = social_age.standings(db, [character.id])[character.id].age
    return Facts(
        age=age if age in AGES else None,
        sect=sect,
        traits=frozenset(
            (r.category.key, r.definition.name.casefold())
            for r in rows
            if r.trait.rating is None or r.trait.rating > 0
        ),
    )


def shown(condition: Mapping[str, Any] | None, known: Facts) -> bool:
    """Whether a question with `condition` is shown for a character the sheet says
    `known` of."""
    if not condition:
        return True
    kind = condition.get("kind")
    if kind == "social_age":
        return known.age in condition.get("ages", [])
    if kind == "sect":
        return known.sect in condition.get("sects", [])
    if kind == "trait":
        return (condition.get("category"), str(condition.get("name", "")).casefold()) in (
            known.traits
        )
    return True


def answers(db: Session, character: Character) -> dict[uuid.UUID, str]:
    return {
        a.question_id: a.answer
        for a in db.scalars(
            select(BackstoryAnswer).where(BackstoryAnswer.character_id == character.id)
        )
    }


def mode_for(db: Session, character: Character) -> tuple[str, Troupe | None]:
    troupe = question_troupe(db, character)
    if troupe is None or troupe.archived_at is not None:
        return "free", None
    return troupe.backstory_mode, troupe


def answerable(
    db: Session, character: Character, question_id: uuid.UUID
) -> tuple[BackstoryQuestion, BackstoryQuestionSet]:
    """A question the character is asked now, or refused."""
    mode, troupe = mode_for(db, character)
    question = db.get(BackstoryQuestion, question_id)
    question_set = db.get(BackstoryQuestionSet, question.set_id) if question else None
    if (
        mode == "free"
        or troupe is None
        or question is None
        or question_set is None
        or question_set.troupe_id != troupe.id
        or question.archived_at is not None
        or question_set.archived_at is not None
        or not shown(question.condition, facts(db, character))
    ):
        raise unprocessable("That question isn't asked of this character.")
    return question, question_set


YEAR = re.compile(r"\d{1,4}")


def tidy_answer(question: BackstoryQuestion, answer: str) -> str:
    """The answer as kept, or refused if it does not fit the question's kind."""
    answer = answer.strip()
    if not answer:
        return ""
    if question.kind == "heading":
        raise unprocessable("A heading takes no answer.")
    if question.kind == "year" and not YEAR.fullmatch(answer):
        raise unprocessable("Give the year as digits, such as 1888.")
    if question.kind == "choice" and answer not in question.options:
        raise unprocessable("Choose one of the options.")
    if question.kind == "scale" and answer not in {str(n) for n in range(1, SCALE_POINTS + 1)}:
        raise unprocessable(f"Choose a point from 1 to {SCALE_POINTS}.")
    if question.kind == "short":
        answer = " ".join(answer.split())
    if len(answer) > MAX_LENGTH:
        raise unprocessable(f"An answer can be at most {MAX_LENGTH:,} characters.")
    return answer


def answer(db: Session, character: Character, question_id: uuid.UUID, text: str) -> str:
    question, _ = answerable(db, character, question_id)
    text = tidy_answer(question, text)
    found = db.scalar(
        select(BackstoryAnswer).where(
            BackstoryAnswer.character_id == character.id,
            BackstoryAnswer.question_id == question.id,
        )
    )
    if found is None:
        db.add(BackstoryAnswer(character_id=character.id, question_id=question.id, answer=text))
    else:
        found.answer = text
    db.flush()
    return text


def scale_label(value: str, poles: Sequence[str]) -> str:
    """A point on a scale in words: "More Action than Intrigue"."""
    a, b = (poles[0], poles[1]) if len(poles) == 2 else ("", "")
    return {
        "1": a,
        "2": f"More {a} than {b}",
        "3": f"Evenly {a} and {b}",
        "4": f"More {b} than {a}",
        "5": b,
    }.get(value, value)


def shown_answer(question: BackstoryQuestion, value: str) -> str:
    return scale_label(value, question.options) if question.kind == "scale" else value


def heading(question: BackstoryQuestion) -> str:
    return " ".join((question.title or question.text).split())


def marks(set_id: uuid.UUID) -> tuple[str, str]:
    return f"<!-- questions:{set_id} -->", f"<!-- /questions:{set_id} -->"


def built_sections(
    question_set: BackstoryQuestionSet,
    questions: Sequence[BackstoryQuestion],
    given: Mapping[uuid.UUID, str],
) -> str:
    """A set's sections, between its marks: each answered question in order as its
    own section, and each heading-only question with answered questions under it."""
    start, end = marks(question_set.id)
    parts: list[str] = [start]
    waiting: str | None = None
    for q in questions:
        if q.kind == "heading":
            waiting = f"# {heading(q)}"
            continue
        value = given.get(q.id, "").strip()
        if not value:
            continue
        if waiting is not None:
            parts.append(waiting)
            waiting = None
        # The answer may not end the set's sections early.
        body = "\n".join(line for line in shown_answer(q, value).split("\n") if line != end)
        parts.append(f"## {heading(q)}\n\n{body}")
    parts.append(end)
    return "\n\n".join(parts)


def between_marks(text: str, set_id: uuid.UUID) -> tuple[int, int] | None:
    """Where a set's sections are in `text`, marks and all, if its marks are there."""
    start, end = marks(set_id)
    at = text.find(start)
    if at < 0:
        return None
    until = text.find(end, at + len(start))
    if until < 0:
        return None
    return at, until + len(end)


def splice(text: str, set_id: uuid.UUID, sections: str) -> str:
    """`text` with the set's sections replaced by `sections`, or `sections` added at
    the end if its marks are not both there. Nothing outside the marks changes."""
    found = between_marks(text, set_id)
    if found is None:
        kept = text.rstrip()
        return f"{kept}\n\n{sections}\n" if kept else f"{sections}\n"
    return text[: found[0]] + sections + text[found[1] :]


def edited_sets(backstory: Backstory | None) -> list[str]:
    """The sets whose sections the player has changed since they were last built."""
    if backstory is None:
        return []
    found: list[str] = []
    for set_id, sections in backstory.built.items():
        at = between_marks(backstory.text, uuid.UUID(set_id))
        if at is not None and backstory.text[at[0] : at[1]] != sections:
            found.append(set_id)
    return found


def build(
    db: Session, user: User, character: Character, set_id: uuid.UUID, replace_edits: bool
) -> Backstory:
    """Write a set's answers into the backstory, as its sections."""
    mode, troupe = mode_for(db, character)
    question_set = db.get(BackstoryQuestionSet, set_id)
    if (
        mode == "free"
        or troupe is None
        or question_set is None
        or question_set.troupe_id != troupe.id
        or question_set.archived_at is not None
    ):
        raise unprocessable("Those questions aren't asked of this character.")
    known = facts(db, character)
    questions = [
        q
        for q in db.scalars(
            select(BackstoryQuestion)
            .where(BackstoryQuestion.set_id == question_set.id)
            .where(BackstoryQuestion.archived_at.is_(None))
            .order_by(BackstoryQuestion.position)
        )
        if shown(q.condition, known)
    ]
    given = answers(db, character)
    missing = [
        q
        for q in questions
        if q.kind in ANSWERED and not q.optional and not given.get(q.id, "").strip()
    ]
    if missing:
        raise unprocessable(
            "Answer every question that isn't optional first: "
            + "; ".join(shorten(heading(q), 60) for q in missing[:5])
            + ("…" if len(missing) > 5 else "")
        )
    backstory = held(db, character)
    if str(question_set.id) in edited_sets(backstory) and not replace_edits:
        raise conflict(
            f"You have changed the sections built from {question_set.name} since."
            " Building again replaces them; your writing outside them stays."
        )
    sections = built_sections(question_set, questions, given)
    write(
        db,
        user,
        character,
        backstory,
        splice(backstory.text, question_set.id, sections),
        "built",
    )
    backstory.built = {**backstory.built, str(question_set.id): sections}
    db.flush()
    return backstory
