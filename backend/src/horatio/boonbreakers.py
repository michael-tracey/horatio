"""Boonbreakers, and the status a debtor loses for ignoring a great boon (#717).

A boon breaker is a vampire who refused to pay a boon (MET: VTM p. 397). Once the
Harpy has publicly given them the chance to repay and they haven't, the Harpy may
declare them a Boonbreaker: every boon owed to or by them is null and void, and they
carry Disgraced while the mark stands. In Horatio the troupe's running staff, or a
Harpy with the full ledger (#688, horatio.boon_harpy.keeper), declare it in one
troupe's ledger: its open boons (standing or waiting for review) on either side are
made void, each with the reason in its own log, and Disgraced is given through the
status rules (horatio.sect_status), held for as long as the mark stands, whatever
its own duration says. A character with no status gets the mark without it.

A Boonbreaker may appeal for mercy to the Harpy, and then to a court of seven to
thirteen Harpies (p. 398). Each appeal and its outcome is recorded on the mark. Mercy
lifts it, which ends the Disgraced it gave; the book doesn't say the boons come back,
so whoever lifts it chooses which voided boons to restore, any, all, or none. A
court that overturns the mark puts the rest of its term on the Harpy who gave it,
and one that upholds it adds six months for each vote against (p. 398): both are
staff's to carry out with the status tools; Horatio records the outcome.

The mark is public at court: the ledger, the Play View's Boons tab and the character's
status (as their Disgraced) show it.

Ignoring a boon (p. 395): a debtor who formally ignores a major, blood or life boon
always loses status. Settling one so marks it (`Boon.status_loss = "due"`) for the
troupe's staff, or its Harpy, to take the status with the status tools and say so,
or to say they won't: never automatic.
"""

import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from horatio import audit, boons, sect_status
from horatio.boon_harpy import Keeper
from horatio.models import Boon, Boonbreaker, Character, HeldStatus, Troupe, User
from horatio.sheets import conflict, unprocessable

DISGRACED = "Disgraced"
# What the mark is, for the status it gives and the logs.
PAGE = "p. 397"
# The boons a declaration makes void: those still open on either side.
OPEN = ("registered", "pending")
# Who an appeal for mercy goes to (p. 398).
APPEALS = {"harpy": "the Harpy", "court": "a court of Harpies"}
OUTCOMES = {"granted": "mercy granted", "refused": "mercy refused"}
# A court of Harpies sits seven to thirteen (p. 398).
COURT = (7, 13)
# What a debtor formally ignoring loses status for (p. 395).
GREAT = boons.COSTS_STATUS
LOSS = {"taken": "status taken", "waived": "no status taken"}


def standing_mark(db: Session, troupe_id: uuid.UUID, character_id: uuid.UUID) -> Boonbreaker | None:
    return db.scalar(
        select(Boonbreaker).where(
            Boonbreaker.troupe_id == troupe_id,
            Boonbreaker.character_id == character_id,
            Boonbreaker.lifted_at.is_(None),
        )
    )


def marked(db: Session, troupe_id: uuid.UUID) -> set[uuid.UUID]:
    """The characters marked as Boonbreakers in the troupe's ledger now."""
    return set(
        db.scalars(
            select(Boonbreaker.character_id).where(
                Boonbreaker.troupe_id == troupe_id, Boonbreaker.lifted_at.is_(None)
            )
        )
    )


def marks_of(db: Session, troupe: Troupe) -> list[Boonbreaker]:
    """Every mark in the troupe's ledger, standing ones first, newest first."""
    found = list(
        db.scalars(
            select(Boonbreaker)
            .where(Boonbreaker.troupe_id == troupe.id)
            .order_by(Boonbreaker.created_at.desc(), Boonbreaker.id.desc())
        )
    )
    found.sort(key=lambda m: m.lifted_at is not None)
    return found


def held_by_marks(db: Session, held_ids: Collection[uuid.UUID]) -> set[uuid.UUID]:
    """Of these held statuses, those a standing mark gave: they last while it stands."""
    if not held_ids:
        return set()
    return {
        i
        for i in db.scalars(
            select(Boonbreaker.held_status_id).where(
                Boonbreaker.held_status_id.in_(list(held_ids)),
                Boonbreaker.lifted_at.is_(None),
            )
        )
        if i is not None
    }


def open_boons(db: Session, troupe: Troupe, character: Character) -> list[Boon]:
    """The boons a declaration would make void: still open, owed to or by them."""
    return list(
        db.scalars(
            select(Boon)
            .where(
                Boon.troupe_id == troupe.id,
                Boon.state.in_(OPEN),
                or_(Boon.debtor_id == character.id, Boon.creditor_id == character.id),
            )
            .order_by(Boon.made_on, Boon.created_at, Boon.id)
        )
    )


@dataclass(frozen=True)
class Preview:
    boons: list[Boon]
    owed_by: int
    owed_to: int


def preview(db: Session, troupe: Troupe, character: Character) -> Preview:
    found = open_boons(db, troupe, character)
    by = sum(1 for b in found if b.debtor_id == character.id)
    return Preview(found, by, len(found) - by)


def doer(keeper: Keeper) -> str:
    return keeper.character.name if keeper.character is not None else "the Harpy"


def declare(
    db: Session,
    user: User,
    troupe: Troupe,
    keeper: Keeper,
    character: Character,
    note: str,
    refused_boon_id: uuid.UUID | None = None,
) -> Boonbreaker:
    """Declare the character a Boonbreaker in the troupe's ledger (p. 397): each open
    boon owed to or by them made void, and Disgraced given while the mark stands."""
    note = boons.need_note(note, "declaring a Boonbreaker")
    if not boons.in_troupe(db, troupe, character):
        raise unprocessable(f"{character.name} isn't in {troupe.name}.")
    if keeper.character is not None and keeper.character.id == character.id:
        raise unprocessable("A Harpy can't declare themself a Boonbreaker.")
    if standing_mark(db, troupe.id, character.id) is not None:
        raise conflict(f"{character.name} is a Boonbreaker already.")
    refused: Boon | None = None
    if refused_boon_id is not None:
        refused = db.get(Boon, refused_boon_id)
        if refused is None or refused.troupe_id != troupe.id or refused.debtor_id != character.id:
            raise unprocessable(f"Name a boon {character.name} owes in this ledger.")

    found = open_boons(db, troupe, character)
    why = f"{character.name} was declared a Boonbreaker ({PAGE}): {note}"
    for boon in found:
        boons.void(db, user, boon, why, keeper.character)

    mark = Boonbreaker(
        troupe_id=troupe.id,
        character_id=character.id,
        refused_boon_id=refused.id if refused is not None else None,
        note=note,
        declared_by=user.id,
        declared_as_id=keeper.character.id if keeper.character is not None else None,
        voided=[str(b.id) for b in found],
    )
    db.add(mark)
    db.flush()
    held = disgrace(db, user, troupe, keeper, character, note)
    mark.held_status_id = held.id if held is not None else None
    audit.record(
        db,
        user,
        "boon.boonbreaker",
        troupe_id=troupe.id,
        character_id=character.id,
        as_harpy=f", as {keeper.character.name}" if keeper.character is not None else "",
        voided=len(found),
        disgraced=", and gave them Disgraced"
        if held is not None
        else "; they hold no status, so no Disgraced",
        reason=note,
    )
    db.flush()
    return mark


def disgrace(
    db: Session, user: User, troupe: Troupe, keeper: Keeper, character: Character, note: str
) -> HeldStatus | None:
    """Disgraced for the mark, through the status rules; none for a character whose
    sect holds no status."""
    try:
        return sect_status.add(
            db,
            user,
            character,
            troupe,
            name=DISGRACED,
            patron_text=f"Declared a Boonbreaker by {doer(keeper)}",
            story=note,
            reason=f"a Boonbreaker, {PAGE}",
            acting="staff",
        )
    except HTTPException:
        return None


def appeal(
    db: Session,
    user: User,
    troupe: Troupe,
    keeper: Keeper,
    mark: Boonbreaker,
    to: str,
    outcome: str,
    note: str = "",
    against: int | None = None,
    on: date | None = None,
    restore: Sequence[uuid.UUID] = (),
) -> None:
    """Record an appeal for mercy and its outcome (p. 398). Mercy granted lifts the
    mark, restoring the voided boons in `restore`."""
    if mark.lifted_at is not None:
        raise conflict("That mark was lifted already.")
    if to not in APPEALS:
        raise unprocessable(f"An appeal goes to one of {', '.join(APPEALS)}.")
    if outcome not in OUTCOMES:
        raise unprocessable(f"An appeal ends in one of {', '.join(OUTCOMES)}.")
    if against is not None and (to != "court" or not 0 <= against <= COURT[1]):
        raise unprocessable(
            f"Votes against are a court's: 0 to {COURT[1]} of its {COURT[0]} to {COURT[1]}."
        )
    note = note.strip()
    if to == "court" and outcome == "granted":
        follows = "The rest of the mark's term falls on the Harpy who gave it (p. 398)."
    elif to == "court" and against:
        follows = f"Upheld: six more months for each of the {against} votes against (p. 398)."
    else:
        follows = ""
    mark.appeals = [
        *mark.appeals,
        {
            "to": to,
            "outcome": outcome,
            "against": against,
            "note": note,
            "follows": follows,
            "on": (on or datetime.now(UTC).date()).isoformat(),
            "by": doer(keeper),
        },
    ]
    flag_modified(mark, "appeals")
    audit.record(
        db,
        user,
        "boon.boonbreaker_appeal",
        troupe_id=troupe.id,
        character_id=mark.character_id,
        to=APPEALS[to],
        outcome=OUTCOMES[outcome],
        reason=" ".join(p for p in (note, follows) if p),
    )
    if outcome == "granted":
        why = f"Mercy from {APPEALS[to]}" + (f": {note}" if note else "")
        lift(db, user, troupe, keeper, mark, why, restore)
    db.flush()


def lift(
    db: Session,
    user: User,
    troupe: Troupe,
    keeper: Keeper,
    mark: Boonbreaker,
    note: str,
    restore: Sequence[uuid.UUID] = (),
) -> None:
    """Mercy: the mark lifted, the Disgraced it gave ended, and the voided boons in
    `restore` standing again."""
    voided = {uuid.UUID(i) for i in mark.voided}
    wanted = list(dict.fromkeys(restore))
    if any(i not in voided for i in wanted):
        raise unprocessable("Restore only boons the declaration made void.")
    character = db.get(Character, mark.character_id)
    name = character.name if character is not None else "a Boonbreaker"
    mark.lifted_at = datetime.now(UTC)
    mark.lifted_by = user.id
    mark.lifted_note = note
    db.flush()
    if mark.held_status_id is not None and character is not None:
        if db.get(HeldStatus, mark.held_status_id) is not None:
            sect_status.remove(
                db,
                user,
                character,
                troupe,
                mark.held_status_id,
                reason=f"No longer a Boonbreaker: {note}",
                acting="staff",
            )
        mark.held_status_id = None
    restored: list[str] = []
    for boon_id in wanted:
        boon = db.get(Boon, boon_id)
        if boon is None or boon.state != "void":
            continue
        boons.reopen(db, user, boon, f"Restored on mercy for {name}: {note}", keeper.character)
        restored.append(str(boon_id))
    mark.restored = restored
    audit.record(
        db,
        user,
        "boon.boonbreaker_lifted",
        troupe_id=troupe.id,
        character_id=mark.character_id,
        restored=len(restored),
        of=len(voided),
        reason=note,
    )
    db.flush()


# --- ignoring a great boon ------------------------------------------------------------------


def costs_status(boon: Boon) -> bool:
    """Formally ignoring this boon costs its debtor status (p. 395)."""
    return boon.state == "settled" and boon.settled_how == "ignored" and boon.kind in GREAT


def answer_loss(
    db: Session, user: User, boon: Boon, taken: bool, note: str, keeper: Keeper
) -> None:
    """Staff, or the Harpy, say they took the status the debtor lost for ignoring the
    boon, with the status tools, or that they won't."""
    if boon.status_loss != "due":
        raise conflict("That boon has no status loss waiting.")
    outcome = "taken" if taken else "waived"
    boon.status_loss = outcome
    note = note.strip()
    boons.log(
        db,
        user,
        "boon.status_loss",
        boon,
        outcome=LOSS[outcome],
        as_harpy=f", as {keeper.character.name}" if keeper.character is not None else "",
        reason=note,
    )
    db.flush()
