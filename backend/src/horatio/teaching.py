"""Teachers for more kinds of trait (issue #440): an optional troupe setting.

The book has a teacher for a discipline dot (core, p. 112), which waits on the home
troupe with the teacher the player names (horatio.sheets). A troupe can ask one for
other traits too, with teacher rules (horatio.rules.teachers) its storytellers make
under Customise › Rules › Teachers. With none, nothing changes.

When a player buys a trait a rule is about, for a character the rule applies to,
the purchase needs a teacher: a character of the troupe who holds the trait at the
rating the rule asks (the player picks one of those who qualify), or an NPC the
player names, whom staff approve. Once a home troupe has accepted the character the
purchase waits on it, as a discipline dot does, and declining takes it back. Before
then (a rule for "always", while building) the teacher is recorded and checked, and
the troupe sees it when it reviews the sheet.

A rule can ask downtime actions for the learning, owed when the purchase is made or
approved, and Willpower of the teacher. Then the teacher's player is asked to
confirm (a task in their bell); confirming spends the Willpower on their Play View,
and it does not come back with rest until they have attended the rule's number of
games since: each game they start before then starts that much lower. Staff cannot
approve the purchase until the teacher's player has confirmed; an NPC of the troupe
spends its Willpower when staff approve. If the purchase is declined or withdrawn,
the Willpower is given back.

Games attended are those the teacher checked in to (horatio.checkin) that have
ended. `games_attended` is the one place that says so.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from horatio import audit, play, sheets
from horatio.models import (
    Approval,
    Character,
    CharacterTrait,
    GameAttendance,
    PlayGame,
    ScheduledGame,
    TeacherRule,
    Teaching,
    TraitCategory,
    TraitDefinition,
    Troupe,
    User,
)
from horatio.permissions import TroupeAction, require_troupe_action
from horatio.rules.model import RuleSetData, SheetTrait
from horatio.rules.store import read_troupe_rules
from horatio.rules.teachers import (
    TeacherRuleData,
    TeacherRuleProblem,
    check_rule,
    describe,
    first_applying,
)
from horatio.sheets import conflict, unprocessable

# --- the rules ---------------------------------------------------------------------


def rule_data(row: TeacherRule) -> TeacherRuleData:
    return TeacherRuleData(
        id=str(row.id),
        splat=row.splat,
        category=row.category,
        names=tuple(row.names),
        name_prefix=row.name_prefix,
        condition=row.condition,
        always=row.always,
        holds="rating" if row.holds == "rating" else "same",
        rating=row.rating,
        actions=row.actions,
        willpower=row.willpower,
        games=row.games,
    )


def rule_rows(db: Session, troupe_id: uuid.UUID, splat: str | None = None) -> list[TeacherRule]:
    """A troupe's teacher rules, oldest first: of one splat, if given."""
    query = select(TeacherRule).where(TeacherRule.troupe_id == troupe_id)
    if splat is not None:
        query = query.where(TeacherRule.splat == splat)
    return list(db.scalars(query.order_by(TeacherRule.created_at, TeacherRule.id)))


def rules_of(db: Session, troupe_id: uuid.UUID, splat: str) -> list[TeacherRuleData]:
    return [rule_data(r) for r in rule_rows(db, troupe_id, splat)]


def rule_set_of(db: Session, troupe: Troupe, splat: str) -> RuleSetData:
    return read_troupe_rules(db, splat, troupe.id).rule_set


def problem_of(db: Session, troupe: Troupe, data: TeacherRuleData) -> str | None:
    """Why the troupe's rules cannot use a teacher rule now, or None if they can."""
    try:
        check_rule(data, rule_set_of(db, troupe, data.splat))
    except TeacherRuleProblem as problem:
        return str(problem)
    return None


def text_of(db: Session, troupe: Troupe, data: TeacherRuleData) -> str:
    return describe(data, rule_set_of(db, troupe, data.splat))


def checked(db: Session, troupe: Troupe, data: TeacherRuleData) -> None:
    """Refuse a teacher rule the troupe's rules cannot use (422), saying why."""
    problem = problem_of(db, troupe, data)
    if problem is not None:
        raise unprocessable(problem)


def stored(row: TeacherRule, data: TeacherRuleData) -> None:
    row.splat = data.splat
    row.category = data.category
    row.names = list(data.names)
    row.name_prefix = data.name_prefix or None
    row.condition = dict(data.condition) if data.condition is not None else None
    row.always = data.always
    row.holds = data.holds
    row.rating = data.rating if data.holds == "rating" else None
    row.actions = data.actions
    row.willpower = data.willpower
    row.games = data.games if data.willpower else 0


def create(db: Session, staff: User, troupe: Troupe, data: TeacherRuleData) -> TeacherRule:
    checked(db, troupe, data)
    row = TeacherRule(troupe_id=troupe.id)
    stored(row, data)
    db.add(row)
    db.flush()
    audit.record(
        db, staff, "house.teacher_added", troupe_id=troupe.id, text=text_of(db, troupe, data)
    )
    return row


def change(
    db: Session, staff: User, troupe: Troupe, row: TeacherRule, data: TeacherRuleData
) -> TeacherRule:
    checked(db, troupe, data)
    stored(row, data)
    db.flush()
    audit.record(
        db, staff, "house.teacher_changed", troupe_id=troupe.id, text=text_of(db, troupe, data)
    )
    return row


def delete(db: Session, staff: User, troupe: Troupe, row: TeacherRule) -> None:
    data = rule_data(row)
    try:
        text = text_of(db, troupe, data)
    except (KeyError, TypeError, ValueError):
        text = row.category
    db.delete(row)
    db.flush()
    audit.record(db, staff, "house.teacher_removed", troupe_id=troupe.id, text=text)


def row_of(db: Session, troupe: Troupe, rule_id: uuid.UUID) -> TeacherRule | None:
    row = db.get(TeacherRule, rule_id)
    return row if row is not None and row.troupe_id == troupe.id else None


# --- what a purchase needs ---------------------------------------------------------


@dataclass(frozen=True)
class Need:
    """A purchase needs a teacher: the rule, and the rating the teacher must hold."""

    rule: TeacherRuleData
    rating: int
    # The rule in plain words.
    text: str


def asks_teachers(character: Character) -> uuid.UUID | None:
    """The troupe whose teacher rules the character's purchases follow: a PC's home
    troupe, or the troupe it is being built for."""
    return sheets.rules_troupe(character) if character.kind == "pc" else None


def need_for(
    db: Session,
    character: Character,
    category: str,
    name: str,
    detail: str,
    current: int,
    rating: int | None,
) -> Need | None:
    """Whether buying `name` from `current` up to `rating` needs a teacher, and of
    what rating. Lowering, or a troupe with no teacher rules, needs none."""
    troupe_id = asks_teachers(character)
    if troupe_id is None or rating is None or rating <= current:
        return None
    rules = rules_of(db, troupe_id, character.splat)
    if not any(r.about(category, name) for r in rules):
        return None
    sheet = [r.as_rules_trait() for r in sheets.sheet_rows(db, character)]
    context = sheets.check_context(db, character, sheet)
    subject = SheetTrait(category, name, rating, detail=detail)
    rule = first_applying(rules, sheet, subject, context)
    if rule is None:
        return None
    troupe = db.get_one(Troupe, troupe_id)
    return Need(rule, rule.needed(rating), text_of(db, troupe, rule))


def labelled(name: str, detail: str) -> str:
    return f"{name}: {detail}" if detail else name


def holders(
    db: Session, character: Character, category: str, name: str, detail: str, rating: int
) -> list[Character]:
    """The characters of the troupe whose teacher rules the character follows who
    hold the trait at `rating` or more, and so could teach it: its PCs and NPCs of
    any splat (a domitor teaches its ghoul), active, other than the character, by
    name."""
    troupe_id = asks_teachers(character)
    if troupe_id is None:
        return []
    return list(
        db.scalars(
            select(Character)
            .join(CharacterTrait, CharacterTrait.character_id == Character.id)
            .join(TraitDefinition, CharacterTrait.trait_definition_id == TraitDefinition.id)
            .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
            .where(
                or_(
                    (Character.kind == "pc") & (Character.home_troupe_id == troupe_id),
                    (Character.kind == "npc") & (Character.owner_troupe_id == troupe_id),
                ),
                Character.status == "active",
                Character.id != character.id,
                TraitCategory.key == category,
                TraitDefinition.name == name,
                CharacterTrait.detail == detail,
                or_(CharacterTrait.rating.is_(None), CharacterTrait.rating >= rating),
            )
            .order_by(Character.name, Character.id)
        ).unique()
    )


@dataclass(frozen=True)
class Teacher:
    """Who teaches: a character of the troupe, or an NPC known only by name."""

    character: Character | None
    name: str


def chosen_teacher(
    db: Session,
    character: Character,
    need: Need,
    category: str,
    name: str,
    detail: str,
    teacher_id: uuid.UUID | None,
    teacher_name: str,
) -> Teacher:
    """The teacher the player chose, refused (422) if there is none or they do not
    qualify."""
    what = labelled(name, detail)
    if teacher_id is not None:
        found = next(
            (
                c
                for c in holders(db, character, category, name, detail, need.rating)
                if c.id == teacher_id
            ),
            None,
        )
        if found is None:
            teacher = db.get(Character, teacher_id)
            who = teacher.name if teacher is not None else "That character"
            raise unprocessable(
                f"{who} cannot teach {what}: a teacher here holds it at {need.rating} or more."
            )
        return Teacher(found, found.name)
    if teacher_name.strip():
        return Teacher(None, teacher_name.strip())
    raise unprocessable(
        f"{what} needs a teacher here: choose a character who holds it at {need.rating} "
        "or more, or name an NPC for staff to approve."
    )


def record(
    db: Session,
    player: User,
    character: Character,
    need: Need,
    teacher: Teacher,
    definition: TraitDefinition,
    detail: str,
    rating: int,
    approval: Approval | None,
) -> Teaching:
    """Keep who teaches a purchase. With no approval to wait on, the downtime actions
    are owed at once; otherwise when staff approve."""
    troupe_id = asks_teachers(character)
    assert troupe_id is not None
    asks_willpower = need.rule.willpower > 0 and teacher.character is not None
    teaching = Teaching(
        character_id=character.id,
        troupe_id=troupe_id,
        approval_id=approval.id if approval is not None else None,
        rule_id=uuid.UUID(need.rule.id),
        trait_definition_id=definition.id,
        detail=detail,
        rating=rating,
        teacher_id=teacher.character.id if teacher.character is not None else None,
        teacher_name=teacher.name,
        actions=need.rule.actions,
        willpower=need.rule.willpower if asks_willpower else 0,
        games=need.rule.games if asks_willpower else 0,
        status="asked" if asks_willpower else "not_needed",
    )
    db.add(teaching)
    db.flush()
    audit.record(
        db,
        player,
        "sheet.teacher",
        troupe_id=troupe_id,
        character_id=character.id,
        name=labelled(definition.name, detail),
        rating=rating,
        teacher=teacher.name,
    )
    if approval is None and teaching.actions:
        sheets.owe(
            db,
            player,
            character,
            teaching.actions,
            f"Learning {labelled(definition.name, detail)} {rating} from {teacher.name}",
        )
    return teaching


def of_approval(db: Session, approval: Approval) -> Teaching | None:
    return db.scalar(select(Teaching).where(Teaching.approval_id == approval.id))


# --- the teacher's Willpower -------------------------------------------------------


def now() -> datetime:
    return datetime.now(UTC)


def trait_name(db: Session, teaching: Teaching) -> str:
    definition = db.get_one(TraitDefinition, teaching.trait_definition_id)
    return labelled(definition.name, teaching.detail)


def what_taught(db: Session, teaching: Teaching, verb: str = "Teaching") -> str:
    """ "Teaching Firearms 2 to Elmer"."""
    student = db.get_one(Character, teaching.character_id)
    return f"{verb} {trait_name(db, teaching)} {teaching.rating} to {student.name}"


def can_answer(db: Session, user: User, teaching: Teaching) -> bool:
    """The teacher's player answers for a PC; staff who approve changes, for an NPC."""
    if teaching.teacher_id is None:
        return False
    teacher = db.get_one(Character, teaching.teacher_id)
    if teacher.kind == "pc":
        return teacher.player_id == user.id
    troupe = db.get_one(Troupe, teaching.troupe_id)
    try:
        require_troupe_action(db, user, troupe, TroupeAction.APPROVE_CHANGES)
    except HTTPException:
        return False
    return True


def spend(db: Session, actor: User, teaching: Teaching) -> None:
    """Spend the teacher's Willpower on their Play View, in the game they are in."""
    assert teaching.teacher_id is not None
    teacher = sheets.lock_character(db, teaching.teacher_id)
    tap = uuid.uuid4()
    at = now()
    play.record(
        db,
        teacher,
        actor,
        [
            play.Tap(
                id=tap,
                happened_at=at,
                kind="change",
                tracker="willpower",
                amount=-teaching.willpower,
                note=what_taught(db, teaching),
            )
        ],
    )
    game = play.current_game(db, teacher)
    teaching.status = "spent"
    teaching.spent_at = at
    teaching.spent_game_id = game.id if game is not None else None
    teaching.tap_id = tap
    db.flush()


def give_back(db: Session, actor: User, teaching: Teaching) -> None:
    """The purchase was not made: Willpower spent comes back (undone on the Play
    View if the teacher is still in that game), and none is asked any more."""
    if teaching.status == "spent" and teaching.teacher_id is not None:
        teacher = sheets.lock_character(db, teaching.teacher_id)
        game = play.current_game(db, teacher)
        if game is not None and game.id == teaching.spent_game_id and teaching.tap_id:
            undo = play.Tap(id=uuid.uuid4(), happened_at=now(), kind="undo", undoes=teaching.tap_id)
            play.record(db, teacher, actor, [undo])
    if teaching.status in ("asked", "spent"):
        teaching.status = "given_back"
    db.flush()


def answer(db: Session, user: User, teaching: Teaching, *, teach: bool) -> Teaching:
    """The teacher's player confirms teaching, which spends the Willpower, or says no."""
    if not can_answer(db, user, teaching):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such teaching.")
    if teaching.status != "asked":
        raise conflict("This has been answered already.")
    if teach:
        spend(db, user, teaching)
    else:
        teaching.status = "refused"
    teaching.answered_by = user.id
    db.flush()
    audit.record(
        db,
        user,
        "sheet.teacher_confirmed" if teach else "sheet.teacher_refused",
        troupe_id=teaching.troupe_id,
        character_id=teaching.teacher_id,
        what=what_taught(db, teaching),
    )
    return teaching


def asked_of(db: Session, teacher: Character) -> list[Teaching]:
    """What the teacher is asked to confirm, oldest first."""
    return list(
        db.scalars(
            select(Teaching)
            .where(Teaching.teacher_id == teacher.id, Teaching.status == "asked")
            .order_by(Teaching.created_at, Teaching.id)
        )
    )


# --- deciding the purchase ---------------------------------------------------------


def ready(db: Session, approval: Approval) -> None:
    """Refuse approving a purchase whose teacher's player has not confirmed (409)."""
    teaching = of_approval(db, approval)
    if teaching is None or teaching.teacher_id is None:
        return
    teacher = db.get_one(Character, teaching.teacher_id)
    if teaching.status == "refused":
        raise conflict(f"{teacher.name}'s player said no to teaching it: decline it instead.")
    if teaching.status == "asked" and teacher.kind == "pc":
        raise conflict(
            f"{teacher.name}'s player has not yet confirmed teaching it, "
            f"which spends {teaching.willpower} Willpower."
        )


def decided(db: Session, actor: User, approval: Approval, *, approve: bool) -> None:
    """A purchase that needed a teacher was approved (an NPC teacher spends its
    Willpower now, and the downtime actions are owed), or declined or withdrawn
    (Willpower spent comes back)."""
    teaching = of_approval(db, approval)
    if teaching is None:
        return
    if not approve:
        give_back(db, actor, teaching)
        return
    if teaching.status == "asked":
        spend(db, actor, teaching)
    if teaching.actions:
        character = db.get_one(Character, teaching.character_id)
        sheets.owe(
            db,
            actor,
            character,
            teaching.actions,
            f"Learning {trait_name(db, teaching)} {teaching.rating} from {teaching.teacher_name}",
        )


# --- the Willpower's return --------------------------------------------------------


def games_attended(db: Session, character: Character, since: datetime, before: datetime) -> int:
    """The games the character attended that started after `since` and ended by
    `before`: those it checked in to, or, where attendance has kinds, attended."""
    query = (
        select(func.count())
        .select_from(GameAttendance)
        .join(ScheduledGame, GameAttendance.game_id == ScheduledGame.id)
        .where(
            GameAttendance.character_id == character.id,
            ScheduledGame.starts_at > since,
            ScheduledGame.ends_at <= before,
        )
    )
    kind = getattr(GameAttendance, "kind", None)
    if kind is not None:
        query = query.where(kind == "attended")
    return db.scalar(query) or 0


def lending(db: Session, character: Character) -> list[Teaching]:
    """Willpower the character spent teaching, which may still be out."""
    return list(
        db.scalars(
            select(Teaching).where(
                Teaching.teacher_id == character.id,
                Teaching.status == "spent",
                Teaching.games > 0,
                Teaching.spent_at.is_not(None),
            )
        )
    )


def games_left(db: Session, character: Character, teaching: Teaching, at: datetime) -> int:
    assert teaching.spent_at is not None
    return max(0, teaching.games - games_attended(db, character, teaching.spent_at, at))


def lent(db: Session, character: Character, game: PlayGame | None) -> int:
    """Willpower out teaching as `game` starts (the next game, for None), which
    rest does not bring back: what was spent before it started, in an earlier game,
    until the teacher has attended the rule's games since."""
    found = lending(db, character)
    if not found:
        return 0
    start = game.started_at if game is not None else now()
    return sum(
        t.willpower
        for t in found
        if t.spent_at is not None
        and t.spent_at < start
        and (game is None or t.spent_game_id != game.id)
        and games_left(db, character, t, start) > 0
    )


def lent_text(db: Session, character: Character) -> str | None:
    """What is out teaching, for the Play View: "1 Willpower out teaching Firearms 2
    to Elmer: back after 2 more games"."""
    at = now()
    parts = []
    for t in lending(db, character):
        left = games_left(db, character, t, at)
        if left > 0:
            games = "1 more game" if left == 1 else f"{left} more games"
            parts.append(
                f"{t.willpower} Willpower out {what_taught(db, t, 'teaching')}: back after {games}"
            )
    return "; ".join(parts) or None


# --- the teacher's bell ------------------------------------------------------------


def waiting_for(db: Session, user: User) -> Sequence[tuple[Teaching, Character]]:
    """Teachings waiting on `user` as a PC teacher's player."""
    return [
        (t, c)
        for t, c in db.execute(
            select(Teaching, Character)
            .join(Character, Teaching.teacher_id == Character.id)
            .where(
                Teaching.status == "asked",
                Character.kind == "pc",
                Character.player_id == user.id,
            )
            .order_by(Teaching.created_at, Teaching.id)
        )
    ]
