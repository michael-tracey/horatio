"""A troupe's own checks: ones its storytellers add beside the book's (issue #432).

Staff build one on the Checks page, from blocks rather than JSON: a subject from
the catalogue, whether it requires or forbids a condition, the condition, a
strength, the message the player sees, and for a check needed to finish creation
an optional step. The rules side (horatio.rules.house_checks) checks it and turns
it into a check the engine runs, which the troupe's rules list beside the book's
(horatio.rules.store), so it refuses, holds for review, blocks finishing creation
or notes exactly as a book check does.

Before saving, staff see which of the troupe's characters it would break. Those
characters are flagged, not changed: their sheets list it under "Against the
rules", and as a check the sheet already broke it stops no other change. Every
add, change and removal goes in the troupe's audit log.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace

from sqlalchemy.orm import Session

from horatio import audit, sheets
from horatio.house_preview import samples
from horatio.models import Character, HouseCheck, Troupe, User
from horatio.rules.checks import CheckData, violations
from horatio.rules.house_checks import (
    HouseCheckData,
    HouseCheckProblem,
    check_house_check,
    describe,
    to_check,
)
from horatio.rules.store import changes_rules, house_check_data, read_troupe_rules
from horatio.sheets import unprocessable


@dataclass(frozen=True)
class Breaking:
    """One of the troupe's characters a check would break, and what it says."""

    character: Character
    message: str


def checked(db: Session, troupe: Troupe, data: HouseCheckData) -> None:
    """Refuse a house check the troupe's rules cannot run (422), saying why."""
    try:
        check_house_check(data, read_troupe_rules(db, data.splat, troupe.id).rule_set)
    except HouseCheckProblem as problem:
        raise unprocessable(str(problem)) from problem


def text_of(db: Session, troupe: Troupe, data: HouseCheckData) -> str:
    return describe(data, read_troupe_rules(db, data.splat, troupe.id).rule_set)


def breaking(
    db: Session, troupe: Troupe, splat: str, checks: Sequence[CheckData]
) -> dict[str, list[Breaking]]:
    """The troupe's characters of the splat each check breaks now, by check key:
    those whose home it is, those being built for it, and its NPCs."""
    found: dict[str, list[Breaking]] = {c.key: [] for c in checks}
    if not checks:
        return found
    for character in samples(db, troupe, splat):
        sheet = [r.as_rules_trait() for r in sheets.sheet_rows(db, character)]
        context = sheets.check_context(db, character, sheet)
        seen: set[str] = set()
        for violation in violations(checks, sheet, context):
            if violation.check.key not in seen:
                seen.add(violation.check.key)
                found[violation.check.key].append(Breaking(character, violation.message))
    return found


def would_break(db: Session, troupe: Troupe, data: HouseCheckData) -> list[Breaking]:
    """The troupe's characters a house check, as staff are making it, would break."""
    check = to_check(data, troupe.name)
    return breaking(db, troupe, data.splat, [check])[check.key]


def breaking_words(count: int) -> str:
    if count == 0:
        return "no character breaks it"
    return "1 character breaks it" if count == 1 else f"{count} characters break it"


def stored(row: HouseCheck, data: HouseCheckData) -> None:
    row.splat = data.splat
    row.category = data.category
    row.name = data.name
    row.name_prefix = data.name_prefix or None
    row.kind = data.kind
    row.mode = data.mode
    row.condition = dict(data.condition)
    row.strength = data.strength
    row.message = data.message.strip()
    row.step = data.step


@changes_rules
def create(db: Session, staff: User, troupe: Troupe, data: HouseCheckData) -> HouseCheck:
    checked(db, troupe, data)
    row = HouseCheck(troupe_id=troupe.id)
    stored(row, data)
    db.add(row)
    db.flush()
    audit.record(
        db,
        staff,
        "house.check_added",
        troupe_id=troupe.id,
        text=text_of(db, troupe, data),
        breaking=breaking_words(len(would_break(db, troupe, data))),
    )
    return row


@changes_rules
def change(
    db: Session, staff: User, troupe: Troupe, row: HouseCheck, data: HouseCheckData
) -> HouseCheck:
    checked(db, troupe, data)
    stored(row, data)
    db.flush()
    audit.record(
        db,
        staff,
        "house.check_changed",
        troupe_id=troupe.id,
        text=text_of(db, troupe, data),
        breaking=breaking_words(len(would_break(db, troupe, replace(data, id=str(row.id))))),
    )
    return row


@changes_rules
def delete(db: Session, staff: User, troupe: Troupe, row: HouseCheck) -> None:
    data = house_check_data(row)
    try:
        text = text_of(db, troupe, data)
    except (KeyError, TypeError, ValueError):
        text = data.message
    db.delete(row)
    db.flush()
    audit.record(db, staff, "house.check_removed", troupe_id=troupe.id, text=text)


def row_of(db: Session, troupe: Troupe, check_id: uuid.UUID) -> HouseCheck | None:
    row = db.get(HouseCheck, check_id)
    return row if row is not None and row.troupe_id == troupe.id else None
