"""Diablerie: a vampire who drains another of better Generation gains one (MET: VTM
p. 306), and the sheet changes with it.

The home troupe's lead storyteller, storytellers and assistant storytellers record
one from the character's page; its player can instead ask them to, which waits as
an approval of the kind "diablerie" and, approved, does the same. Declining
changes nothing. Recording one:

- marks the date on the sheet, so later XP spending can be followed;
- raises Generation by one, free (CONTEXT.md: Free Rating), past the lock that
  holds it once a home troupe has accepted the character and past Caitiff's two
  dots (p. 69), up to the most there is;
- takes away the techniques the new Generation cannot learn, refunding the XP each
  cost on a line of its own (p. 101 sets who can learn them);
- leaves earlier buys at what they cost: nothing is repriced, and later buys are
  priced at the new Generation without anything further;
- lowers Humanity by one, free and with no XP back, or for a character on a Path
  gives 4 Beast traits at its next Play View game (pp. 290, 306). Staff can change
  either before confirming;
- deals with a Lesser Generation or Thin Blooded flaw as the troupe's setting says:
  leave it, remove it with the XP it gave, or remove it and keep that XP.

Its pieces are the same ones an exception uses (horatio.trait_exceptions): a free
raise made "by exception", and an exception on the Caitiff clan to set that check
aside.
"""

import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio import audit, notifications, play, sheets
from horatio.models import (
    Approval,
    Character,
    Diablerie,
    TraitException,
    Troupe,
    User,
    XpEntry,
)
from horatio.rules.checks import Violation
from horatio.sheets import conflict
from horatio.trait_exceptions import checks_of

GENERATION = ("backgrounds", "Generation")
# The most dots of Generation there are (MET: VTM p. 100).
GENERATION_MOST = 5
# What a diablerie costs a character on a Path, in place of a dot of Humanity (p. 306).
BEAST_ON_A_PATH = 4
# The flaws that make a character a lesser Generation than its blood says (p. 264).
LESSER_FLAWS = ("Lesser Generation 1", "Lesser Generation 2", "Thin Blooded")
# What a troupe can do about them when a holder commits diablerie.
FLAW_SETTINGS = ("leave", "remove", "keep_xp")
SETTING_TEXT = {
    "leave": "leaves the flaw",
    "remove": "removes the flaw and the XP it gave",
    "keep_xp": "removes the flaw and keeps the XP it gave",
}


@dataclass(frozen=True)
class Loss:
    """A technique the new Generation cannot hold, and the XP it gives back."""

    name: str
    detail: str
    rating: int
    refund: int


@dataclass(frozen=True)
class FlawPlan:
    """A Lesser Generation or Thin Blooded flaw, and what the troupe's setting does."""

    name: str
    rating: int
    setting: str
    # The XP it gave (from purchases in the XP history; 0 if taken at creation).
    gave: int
    # The XP taken back: what it gave, no more than the character has unspent.
    taken: int


@dataclass
class Plan:
    """What recording a diablerie would do to a character, or did."""

    from_generation: int
    to_generation: int
    techniques: list[Loss] = field(default_factory=list[Loss])
    # Humanity, or the Path the character follows, and its rating now.
    morality: str | None = None
    morality_rating: int = 0
    on_path: bool = False
    # What the form fills in, and what is (or would be) done.
    humanity_lowered: int = 0
    beast_traits: int = 0
    flaw: FlawPlan | None = None
    # Caitiff with more than 2 dots: allowed by this.
    caitiff: bool = False
    # Why it cannot be recorded, if it cannot.
    refused: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_outcome(self) -> dict[str, Any]:
        """What is kept on the diablerie once recorded."""
        found = self.as_dict()
        del found["refused"]
        return found


@dataclass(frozen=True)
class Adjust:
    """What staff change from the form's fill-in before confirming; None leaves it."""

    victim: str | None = None
    humanity_lowered: int | None = None
    beast_traits: int | None = None


def when(day: date) -> str:
    return f"{day.day} {day:%b %Y}"


def generation_of(db: Session, character: Character) -> int:
    row = next((r for r in sheets.sheet_rows(db, character) if r.key[:2] == GENERATION), None)
    return (row.trait.rating or 0) if row else 0


def morality_row(db: Session, character: Character) -> sheets.SheetRow | None:
    """The Morality the character follows: Humanity, or its Path."""
    return next(
        (
            r
            for r in sheets.sheet_rows(db, character)
            if r.category.key == "paths" and (r.trait.rating or 0) > 0
        ),
        None,
    )


def net_spent(db: Session, character: Character, definition_id: uuid.UUID, detail: str) -> int:
    """The XP spent on a trait, net of what came back: negative for a flaw that paid."""
    return -(
        db.scalar(
            select(func.coalesce(func.sum(XpEntry.amount), 0)).where(
                XpEntry.character_id == character.id,
                XpEntry.trait_definition_id == definition_id,
                func.coalesce(XpEntry.detail, "") == detail,
                XpEntry.kind.in_(("purchase", "reprice")),
            )
        )
        or 0
    )


def can_have(character: Character) -> str | None:
    """Why a diablerie cannot be on this character's sheet, if it cannot."""
    if character.kind != "pc":
        return "An NPC is its staff's to build as they like; set its Generation directly."
    if character.home_troupe_id is None:
        return "A diablerie goes on the sheet of a character a home troupe has accepted."
    return None


def plan_for(db: Session, character: Character, adjust: Adjust | None = None) -> Plan:
    """The changes a diablerie fills in for the character, before anything is saved.
    The techniques and flaw are as they would be recorded now."""
    adjust = adjust or Adjust()
    refused = can_have(character)
    generation = generation_of(db, character)
    if refused is None and generation == 0:
        refused = "The character has no Generation to improve."
    elif refused is None and generation >= GENERATION_MOST:
        refused = f"Generation is already at its most, {GENERATION_MOST}."
    plan = Plan(from_generation=generation, to_generation=generation + 1, refused=refused)
    row = morality_row(db, character)
    if row is not None:
        plan.morality = row.definition.name
        plan.morality_rating = row.trait.rating or 0
        plan.on_path = row.definition.name != "Humanity"
    plan.humanity_lowered = 0 if plan.on_path or row is None else min(1, plan.morality_rating)
    plan.beast_traits = BEAST_ON_A_PATH if plan.on_path else 0
    if adjust.humanity_lowered is not None:
        plan.humanity_lowered = adjust.humanity_lowered
    if adjust.beast_traits is not None:
        plan.beast_traits = adjust.beast_traits
    if plan.refused is None and not 0 <= plan.humanity_lowered <= plan.morality_rating:
        plan.refused = f"Humanity can go down by 0 to {plan.morality_rating}."
    if plan.refused is None and not 0 <= plan.beast_traits <= play.BEAST_TRAITS:
        plan.refused = f"A diablerie can add 0 to {play.BEAST_TRAITS} Beast traits."
    if plan.refused is None:
        trial(db, character, plan)
    return plan


def trial(db: Session, character: Character, plan: Plan) -> None:
    """Fill in what the sheet would lose and how the flaw would be handled, by
    making the change and taking it back."""
    savepoint = db.begin_nested()
    try:
        change(db, None, character, plan)
    except HTTPException as error:
        plan.refused = str(error.detail)
    finally:
        savepoint.rollback()
        db.expire_all()


def lost_techniques(
    db: Session, character: Character, found: list[Violation]
) -> list[tuple[sheets.SheetRow, int]]:
    """The techniques the sheet now breaks a check on, with the XP each cost."""
    keys = {
        (v.subject.category, v.subject.name, v.subject.detail)
        for v in found
        if v.subject.category == "techniques"
    }
    rows = [r for r in sheets.sheet_rows(db, character) if r.key in keys]
    return [(r, max(0, net_spent(db, character, r.definition.id, r.trait.detail))) for r in rows]


def change(db: Session, staff: User | None, character: Character, plan: Plan) -> None:
    """Make the sheet's changes, filling `plan` in with what was done. `staff` is
    None for a trial, which writes no history. The caller holds the character's
    lock and takes the changes back if this raises."""
    before = sheets.sheet_state(db, character)
    actor = staff or db.get_one(User, character.player_id)
    sheets.set_trait(
        db,
        actor,
        character,
        "backgrounds",
        "Generation",
        "",
        plan.to_generation,
        free=f"diablerie, {plan.from_generation} → {plan.to_generation}",
        by_exception="given",
    )
    sheets.apply_grants(db, actor, character)
    db.expire_all()

    # Techniques the new Generation cannot learn go, with their XP.
    plan.techniques = []
    found = [v for v in sheets.sheet_violations(db, character) if v.key not in before.broken]
    for row, refund in lost_techniques(db, character, found):
        rating = row.trait.rating or 0
        plan.techniques.append(Loss(row.definition.name, row.trait.detail, rating, refund))
        if refund:
            db.add(
                XpEntry(
                    character_id=character.id,
                    kind="purchase",
                    amount=refund,
                    reason=f"{row.definition.name} {rating} → 0 (lost to diablerie)",
                    entered_by=actor.id,
                    trait_definition_id=row.definition.id,
                    detail=row.trait.detail or None,
                    from_rating=rating,
                    to_rating=0,
                    cost_basis={"refund": "diablerie"},
                )
            )
        db.delete(row.trait)
    db.flush()
    if plan.techniques:
        sheets.apply_grants(db, actor, character)

    # Humanity falls, free and with no XP back.
    morality = morality_row(db, character)
    if morality is not None and plan.humanity_lowered:
        trait = morality.trait
        rating = (trait.rating or 0) - plan.humanity_lowered
        trait.rating = rating
        trait.free_rating = min(trait.free_rating, rating)
        if trait.creation_pick is not None:
            trait.creation_pick = min(trait.creation_pick, trait.free_rating)
        db.flush()

    # A Lesser Generation or Thin Blooded flaw, as the troupe plays it.
    plan.flaw = None
    troupe = db.get_one(Troupe, character.home_troupe_id) if character.home_troupe_id else None
    setting = troupe.diablerie_flaws if troupe else "leave"
    for row in sheets.sheet_rows(db, character):
        if row.category.key != "flaws" or row.definition.name not in LESSER_FLAWS:
            continue
        gave = max(0, -net_spent(db, character, row.definition.id, row.trait.detail))
        taken = min(gave, max(0, sheets.xp_balance(db, character))) if setting == "remove" else 0
        plan.flaw = FlawPlan(
            name=row.definition.name,
            rating=row.trait.rating or 0,
            setting=setting,
            gave=gave,
            taken=taken,
        )
        if setting != "leave":
            removing_flaw(db, actor, character, row, taken)
        break

    # The sheet as it now is: Caitiff's limit is set aside; anything else is refused.
    db.expire_all()
    plan.caitiff = False
    refusals: list[sheets.Problem] = []
    for violation in sheets.sheet_violations(db, character):
        if violation.key in before.broken:
            continue
        if violation.check.category == "clan" and violation.check.name == "Caitiff":
            plan.caitiff = True
            if staff is not None:
                set_aside(db, staff, character, violation, plan)
        elif sheets.blocking(violation, character):
            refusals.append(sheets.problem(violation))
    if refusals:
        raise conflict(sheets.refusal(refusals))
    if plan.beast_traits and staff is not None:
        play.add_beast(db, character, plan.beast_traits)
    db.flush()


def removing_flaw(
    db: Session, actor: User, character: Character, row: sheets.SheetRow, taken: int
) -> None:
    """Take a flaw off the sheet; with `taken` XP, a correction line takes back the
    XP it gave."""
    if taken:
        gave = db.scalars(
            select(XpEntry)
            .where(
                XpEntry.character_id == character.id,
                XpEntry.trait_definition_id == row.definition.id,
                XpEntry.kind == "purchase",
                XpEntry.amount > 0,
            )
            .order_by(XpEntry.id.desc())
        ).first()
        assert gave is not None
        db.add(
            XpEntry(
                character_id=character.id,
                kind="correction",
                amount=-taken,
                reason=f"{row.definition.name} removed by diablerie: the XP it gave taken back",
                entered_by=actor.id,
                corrects_id=gave.id,
            )
        )
    db.delete(row.trait)
    db.flush()


def set_aside(
    db: Session, staff: User, character: Character, violation: Violation, plan: Plan
) -> None:
    """Keep an exception on the trait a check is about, so the sheet stops flagging
    it, as for any trait given by exception."""
    subject = violation.subject
    key = (subject.category, subject.name, subject.detail)
    row = next((r for r in sheets.sheet_rows(db, character) if r.key == key), None)
    if row is None:
        return
    db.add(
        TraitException(
            character_id=character.id,
            character_trait_id=row.trait.id,
            rating=row.trait.rating or 0,
            checks=checks_of([violation]),
            free=True,
            reason=f"Diablerie, Generation {plan.from_generation} → {plan.to_generation}",
            requested_by=staff.id,
            given_by=staff.id,
            given_at=datetime.now(UTC),
        )
    )


def ensure_may_record(db: Session, character: Character) -> None:
    refused = can_have(character)
    if refused:
        raise conflict(refused)


def record(
    db: Session,
    staff: User,
    character: Character,
    diablerie: Diablerie,
    adjust: Adjust | None = None,
) -> Plan:
    """Record a diablerie: make its changes, and keep what they were on it. The
    caller holds the character's lock. Refused if the sheet would break a rule
    that a diablerie does not set aside."""
    ensure_may_record(db, character)
    adjust = adjust or Adjust()
    if adjust.victim is not None:
        diablerie.victim = adjust.victim.strip()
    plan = plan_for(db, character, adjust)
    if plan.refused:
        raise conflict(plan.refused)
    savepoint = db.begin_nested()
    try:
        change(db, staff, character, plan)
    except BaseException:
        savepoint.rollback()
        raise
    savepoint.commit()
    diablerie.recorded_by = staff.id
    diablerie.recorded_at = datetime.now(UTC)
    diablerie.outcome = plan.as_outcome()
    db.flush()
    assert character.home_troupe_id is not None
    audit.record(
        db,
        staff,
        "sheet.diablerie",
        troupe_id=character.home_troupe_id,
        character_id=character.id,
        committed_on=when(diablerie.committed_on),
        generation=f"{plan.from_generation} → {plan.to_generation}",
        techniques=", ".join(t.name for t in plan.techniques) or "none",
        humanity=plan.humanity_lowered,
        beast=plan.beast_traits,
        flaw=plan.flaw.name if plan.flaw else "none",
    )
    notifications.notify(
        db,
        [character.player_id],
        "sheet.diablerie",
        f"{character.name}'s diablerie of {when(diablerie.committed_on)} is on the sheet: "
        + told(plan),
        f"/characters/{character.id}",
        troupe_id=character.home_troupe_id,
        character_id=character.id,
    )
    return plan


def told(plan: Plan) -> str:
    """What the player is told a diablerie did."""
    parts = [f"Generation {plan.from_generation} → {plan.to_generation}"]
    if plan.techniques:
        refund = sum(t.refund for t in plan.techniques)
        names = ", ".join(t.name for t in plan.techniques)
        parts.append(f"{names} lost, {refund} XP back")
    if plan.humanity_lowered:
        parts.append(f"{plan.morality} −{plan.humanity_lowered}")
    if plan.beast_traits:
        parts.append(f"{plan.beast_traits} Beast traits at your next game")
    if plan.flaw and plan.flaw.setting != "leave":
        parts.append(f"{plan.flaw.name} removed")
    return ", ".join(parts) + "."


def start(
    db: Session,
    staff: User,
    character: Character,
    committed_on: date,
    victim: str,
    note: str,
    adjust: Adjust | None = None,
) -> Plan:
    """Staff record a diablerie from the character's page."""
    ensure_may_record(db, character)
    assert character.home_troupe_id is not None
    diablerie = Diablerie(
        character_id=character.id,
        troupe_id=character.home_troupe_id,
        committed_on=committed_on,
        victim=victim.strip(),
        note=note.strip(),
        requested_by=staff.id,
    )
    db.add(diablerie)
    db.flush()
    return record(db, staff, character, diablerie, adjust)


def ask(db: Session, player: User, character: Character, committed_on: date, note: str) -> Approval:
    """The player says they committed diablerie: it waits on the home troupe's staff."""
    refused = can_have(character)
    if refused:
        raise conflict(refused)
    assert character.home_troupe_id is not None
    if sheets.pending_approvals(db, character, "diablerie"):
        raise conflict(
            "A diablerie is already waiting on the storytellers. Withdraw it to ask again."
        )
    plan = plan_for(db, character)
    if plan.refused:
        raise conflict(plan.refused)
    approval = Approval(
        character_id=character.id,
        troupe_id=character.home_troupe_id,
        kind="diablerie",
        requested_by=player.id,
        player_note=note.strip(),
    )
    db.add(approval)
    db.flush()
    db.add(
        Diablerie(
            character_id=character.id,
            troupe_id=character.home_troupe_id,
            approval_id=approval.id,
            committed_on=committed_on,
            note=note.strip(),
            requested_by=player.id,
        )
    )
    db.flush()
    audit.record(
        db,
        player,
        "approval.request",
        troupe_id=approval.troupe_id,
        character_id=character.id,
        approval_id=approval.id,
        kind="diablerie",
        committed_on=when(committed_on),
    )
    notifications.approval_waiting(db, approval)
    return approval


def asked_for(db: Session, approval: Approval) -> Diablerie | None:
    return db.scalar(select(Diablerie).where(Diablerie.approval_id == approval.id))


def approve_asked(
    db: Session,
    staff: User,
    character: Character,
    approval: Approval,
    adjust: Adjust | None,
) -> None:
    """Approving a player's request does what recording one does."""
    asked = asked_for(db, approval)
    if asked is None:
        raise conflict("This diablerie is no longer there; decline this instead.")
    record(db, staff, character, asked, adjust)


def declined(db: Session, character: Character, approval: Approval) -> None:
    """Declining changes nothing on the sheet; the player is told."""
    asked = asked_for(db, approval)
    if asked is None or character.home_troupe_id is None:
        return
    notifications.notify(
        db,
        [character.player_id],
        "sheet.diablerie",
        f"The storytellers declined {character.name}'s diablerie of {when(asked.committed_on)}; "
        "the sheet is unchanged.",
        f"/characters/{character.id}",
        troupe_id=character.home_troupe_id,
        character_id=character.id,
    )


def recorded(db: Session, character: Character) -> list[Diablerie]:
    """The character's diablerie on the sheet, earliest first."""
    return list(
        db.scalars(
            select(Diablerie)
            .where(Diablerie.character_id == character.id, Diablerie.recorded_at.is_not(None))
            .order_by(Diablerie.committed_on, Diablerie.created_at)
        )
    )
