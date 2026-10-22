"""Import a troupe's influence log from LotsLarp's old spreadsheet (#132):

    uv run python -m horatio.import_influence_log SOURCE --troupe TROUPE [--dry-run]
        [--timezone ZONE]

SOURCE is the spreadsheet downloaded as .xlsx, or a folder holding its
`Elite Infl.` and `UW Infl.` tabs downloaded as CSV. TROUPE is the troupe's id or
name. Each row with a date becomes one entry in the troupe's influence log
(horatio.influence_log):

- **when:** the sheet's date at midnight in ZONE (troupes have no time zone of
  their own; LotsLarp's is the default). A month alone is its 1st, and a date
  with no year takes the year that puts it nearest the rows around it;
- **who:** the character in the troupe of that name, ignoring case and spacing,
  also by a name it had before a rename or its Alternate Identity's detail.
  Otherwise the name is kept as text and reported;
- **the action:** the rules' action of that number ("5: Lockdown") or name
  ("Attack"). One the rules don't have is imported as needing details, and
  reported;
- **times taken:** from a note in Details such as "(this action is logged 3
  times)", which is taken out of the purpose;
- **the sheet's id**, E334 or UW259 (the row number), is kept as the entry's
  reference, and is its short id too unless that is taken.

Running it again updates the entries it made, matched on the sheet's id, rather
than adding them twice, and links name-only entries to characters added since.
An entry keeps a character or action staff gave it where the sheet has none.
`--dry-run` reports what it would do and saves nothing.
"""

import argparse
import calendar
import csv
import re
import sys
import uuid
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import openpyxl
from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from horatio import influence, influence_log
from horatio.db import get_sessionmaker
from horatio.influence import InfluenceAction, InfluenceType
from horatio.influence_log import Details
from horatio.models import (
    AuditEvent,
    Character,
    CharacterTrait,
    InfluenceEntry,
    TraitDefinition,
    Troupe,
    TroupeMembership,
)

TABS: dict[InfluenceType, str] = {"elite": "Elite Infl.", "underworld": "UW Infl."}
DEFAULT_TIMEZONE = "America/New_York"  # LotsLarp's

# The columns read, by their headings. Age and Output are worked out by formulas.
DATE = "date"
AGE = "age"
CHARACTER = "character"
SPECIALIZATION = "specialization"
ACTION = "action"
DETAILS = "details"
BLOCKS = "any blocks?"

Cell = Any  # what a spreadsheet cell holds: text, a number, a date, or None


class CannotImport(Exception):
    """The source can't be imported at all; the message says why."""


# --- reading the source -----------------------------------------------------------------


@dataclass
class Row:
    number: int  # its row number in the sheet, counting the heading's
    cells: dict[str, Cell]

    def text(self, column: str) -> str:
        value = self.cells.get(column)
        if value is None:
            return ""
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return " ".join(str(value).split())


def rows_of(name: str, table: Iterable[Sequence[Cell]]) -> list[Row]:
    """The rows under the tab's heading row, which names at least Date, Character
    and Action."""
    headings: list[str] | None = None
    rows: list[Row] = []
    for number, values in enumerate(table, start=1):
        if headings is None:
            found = [" ".join(str(v or "").split()).casefold() for v in values]
            if {DATE, CHARACTER, ACTION} <= set(found):
                headings = found
            elif number >= 10:
                break
            continue
        cells = {h: v for h, v in zip(headings, values, strict=False) if h}
        rows.append(Row(number, cells))
    if headings is None:
        raise CannotImport(f"The {name} tab has no heading row with Date, Character and Action.")
    return rows


def read_xlsx(path: Path) -> dict[InfluenceType, list[Row]]:
    try:
        # Read-only, as the whole spreadsheet is much more than these two tabs.
        book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as error:  # openpyxl raises several kinds for a file it can't read
        raise CannotImport(f"Can't read {path} as a spreadsheet: {error}") from error
    try:
        sheets = {" ".join(s.title.split()).casefold(): s for s in book.worksheets}
        found: dict[InfluenceType, list[Row]] = {}
        for influence_type, name in TABS.items():
            sheet = sheets.get(name.casefold())
            if sheet is None:
                raise CannotImport(f"{path} has no {name} tab.")
            found[influence_type] = rows_of(name, sheet.iter_rows(min_row=1, values_only=True))
        return found
    finally:
        book.close()


def csv_file(folder: Path, name: str) -> Path:
    """The tab's CSV in the folder: "Elite Infl.csv", or as Google names a download,
    "LotsLarp - Elite Infl..csv"."""
    wanted = name.rstrip(".").casefold()
    found = [
        p
        for p in sorted(folder.glob("*.csv"))
        if p.name[: -len(".csv")].rstrip(".").casefold().endswith(wanted)
    ]
    if len(found) != 1:
        some = "no" if not found else "more than one"
        raise CannotImport(f"{folder} has {some} CSV file for the {name} tab.")
    return found[0]


def read_csv_folder(folder: Path) -> dict[InfluenceType, list[Row]]:
    found: dict[InfluenceType, list[Row]] = {}
    for influence_type, name in TABS.items():
        with csv_file(folder, name).open(newline="", encoding="utf-8-sig") as file:
            found[influence_type] = rows_of(name, csv.reader(file))
    return found


def read_source(path: Path) -> dict[InfluenceType, list[Row]]:
    if path.is_dir():
        return read_csv_folder(path)
    if not path.is_file():
        raise CannotImport(f"There is no {path}.")
    if path.suffix.casefold() != ".xlsx":
        raise CannotImport("Give the spreadsheet as .xlsx, or a folder of its tabs as CSV.")
    return read_xlsx(path)


# --- reading a row ----------------------------------------------------------------------

MONTHS = [m.casefold() for m in calendar.month_name[1:]]


@dataclass(frozen=True)
class SheetDate:
    """A date as the sheet writes it, perhaps with no year."""

    month: int
    day: int
    year: int | None

    def on(self, year: int) -> date | None:
        try:
            return date(year, self.month, self.day)
        except ValueError:
            return None


def month_named(word: str) -> int | None:
    word = word.casefold().rstrip(".")
    if len(word) < 3:
        return None
    return next((n for n, m in enumerate(MONTHS, start=1) if m.startswith(word)), None)


def parse_date(value: Cell) -> SheetDate | None:
    """A date written in one of the sheet's ways: "November 2024" (its 1st), "June 7
    2025", "June 6, 2026", "July 5" (no year), "7th June 2025", "6/7/2025" (month
    first), "7/2026" or "2025-06-07"; or a spreadsheet's own date."""
    if isinstance(value, datetime | date):
        return SheetDate(value.month, value.day, value.year)
    text = " ".join(str(value or "").split())
    if not text:
        return None
    if found := re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", text):
        return SheetDate(int(found[2]), int(found[3]), int(found[1]))
    if found := re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", text):
        return SheetDate(int(found[1]), int(found[2]), int(found[3]))
    if found := re.fullmatch(r"(\d{1,2})/(\d{4})", text):
        return SheetDate(int(found[1]), 1, int(found[2]))
    words = re.findall(r"[A-Za-z]+\.?|\d+", re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text))
    months = [m for w in words if not w[0].isdigit() and (m := month_named(w))]
    numbers = [w for w in words if w.isdigit()]
    if len(months) != 1 or len(words) != 1 + len(numbers) or len(numbers) > 2:
        return None
    years = [int(n) for n in numbers if len(n) == 4]
    days = [int(n) for n in numbers if len(n) <= 2]
    if len(years) > 1 or len(days) > 1 or len(years) + len(days) != len(numbers):
        return None
    if not years and not days:
        return None  # a month alone could be any year
    year = years[0] if years else None
    day = days[0] if days else 1
    return SheetDate(months[0], day, year)


def nearest(sheet_date: SheetDate, near: date) -> date | None:
    """The yearless date in the year that puts it nearest `near`."""
    candidates = [d for y in (near.year - 1, near.year, near.year + 1) if (d := sheet_date.on(y))]
    return min(candidates, key=lambda d: abs((d - near).days), default=None)


NUMBER_WORDS = {
    "once": 1,
    "one": 1,
    "twice": 2,
    "two": 2,
    "thrice": 3,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}
# "(this action is logged 3 times)", "(This is logged twice)", "(there are three
# entries of this)", and the same with its closing bracket missing.
TIMES_NOTE = re.compile(
    r"\((?P<note>[^()]*\b(?:logged|entries of this)\b[^()]*?)(?:\)|$)", re.IGNORECASE
)
COUNT = re.compile(r"\b(\d+|" + "|".join(NUMBER_WORDS) + r")\b", re.IGNORECASE)


def times_taken(details: str) -> tuple[str, int]:
    """The purpose without its "logged N times" note, and the times it gives."""
    for note in TIMES_NOTE.finditer(details):
        count = COUNT.search(note["note"])
        if count is None:
            continue
        word = count[1].casefold()
        times = int(word) if word.isdigit() else NUMBER_WORDS[word]
        if times < 1:
            continue
        purpose = details[: note.start()] + " " + details[note.end() :]
        purpose = re.sub(r"\s+([.,;:!?])", r"\1", " ".join(purpose.split()))
        return purpose, times
    return details, 1


def simple(text: str) -> str:
    """An action's name, for matching: "Gossip & Insider Trading" is "Gossip and
    Insider Trading", "The Power Behind the Throne" is "Power Behind the Throne"."""
    words = re.findall(r"[a-z0-9]+", text.casefold().replace("&", " and "))
    if words[:1] == ["the"]:
        words = words[1:]
    return " ".join(words)


def find_action(choices: Sequence[InfluenceAction], text: str) -> InfluenceAction | None:
    """The action "5: Lockdown", "5", "Lockdown" or "Attack" names: by its number,
    else by its name or key."""
    numbered = re.fullmatch(r"(\d+)\s*[:.)-]?\s*(.*)", text)
    if numbered is not None:
        level = int(numbered[1])
        found = next((a for a in choices if a.general and a.level == level), None)
        if found is not None:
            return found
        text = numbered[2]
    wanted = simple(text)
    if not wanted:
        return None
    return next(
        (a for a in choices if wanted in (simple(a.name), simple(a.key.replace("_", " ")))),
        None,
    )


def blocks_in(value: Cell) -> int | None:
    """The discovery blocks: blank is none. None when it isn't a count."""
    if value is None:
        return 0
    if isinstance(value, int | float) and not isinstance(value, bool):
        return int(value) if value >= 0 and float(value).is_integer() else None
    text = str(value).strip()
    if not text:
        return 0
    return int(text) if text.isdigit() else None


@dataclass
class Line:
    """A row read as an entry."""

    reference: str
    number: int
    day: date
    name: str
    specialization: str
    action: InfluenceAction | None
    action_text: str
    purpose: str
    times: int
    blocks: int


ONLY_AN_AGE = "only an age"


@dataclass
class Skipped:
    reference: str
    reason: str


def read_rows(
    influence_type: InfluenceType, rows: Sequence[Row], choices: Sequence[InfluenceAction]
) -> tuple[list[Line], list[Skipped]]:
    """The tab's rows as entries, and the rows skipped with why. A blank row is
    neither, and a row with nothing but an age (a formula's) is skipped."""
    prefix = influence_log.PREFIXES[influence_type]
    read: list[tuple[Row, str, int, SheetDate]] = []
    skipped: list[Skipped] = []
    for row in rows:
        reference, number = f"{prefix}{row.number}", row.number
        if not any(row.text(c) for c in (DATE, CHARACTER, ACTION, DETAILS, SPECIALIZATION)):
            if row.text(AGE):
                skipped.append(Skipped(reference, ONLY_AN_AGE))
            continue
        written = row.text(DATE)
        if not written:
            skipped.append(Skipped(reference, "no date"))
            continue
        sheet_date = parse_date(row.cells.get(DATE))
        if sheet_date is None or (
            sheet_date.year is not None and not sheet_date.on(sheet_date.year)
        ):
            skipped.append(Skipped(reference, f"can't read the date {written!r}"))
            continue
        read.append((row, reference, number, sheet_date))

    # A date with no year takes it from the date before, or the first after.
    lines: list[Line] = []
    before: date | None = None
    for at, (row, reference, number, sheet_date) in enumerate(read):
        if sheet_date.year is not None:
            day = sheet_date.on(sheet_date.year)
        else:
            near = before or next(
                (d.on(d.year) for _, _, _, d in read[at + 1 :] if d.year is not None), None
            )
            day = nearest(sheet_date, near) if near else None
            if day is None:
                skipped.append(Skipped(reference, f"no year for {row.text(DATE)!r}"))
                continue
        assert day is not None
        before = day
        name = row.text(CHARACTER)
        if not name:
            skipped.append(Skipped(reference, "no character"))
            continue
        blocks = blocks_in(row.cells.get(BLOCKS))
        if blocks is None:
            skipped.append(Skipped(reference, f"blocks not a count: {row.text(BLOCKS)!r}"))
            continue
        action_text = row.text(ACTION)
        purpose, times = times_taken(row.text(DETAILS))
        lines.append(
            Line(
                reference=reference,
                number=number,
                day=day,
                name=name,
                specialization=row.text(SPECIALIZATION),
                action=find_action(choices, action_text),
                action_text=action_text,
                purpose=purpose,
                times=times,
                blocks=blocks,
            )
        )
    skipped.sort(key=lambda s: int(s.reference.lstrip("EUW")))
    return lines, skipped


# --- matching names ---------------------------------------------------------------------


def plain(name: str) -> str:
    return " ".join(name.split()).casefold()


def troupe_names(db: Session, troupe_id: uuid.UUID) -> dict[str, set[uuid.UUID]]:
    """The characters in the troupe now, by every name they go by: their own, any
    they had before a rename, and their Alternate Identity's."""
    members = select(TroupeMembership.character_id).where(
        TroupeMembership.troupe_id == troupe_id, TroupeMembership.left_at.is_(None)
    )
    characters = list(
        db.scalars(
            select(Character).where(
                or_(Character.owner_troupe_id == troupe_id, Character.id.in_(members))
            )
        )
    )
    ids = [c.id for c in characters]
    names: list[tuple[uuid.UUID, str]] = [(c.id, c.name) for c in characters]
    for character_id, data in db.execute(
        select(AuditEvent.character_id, AuditEvent.data).where(
            AuditEvent.action == "character.renamed", AuditEvent.character_id.in_(ids)
        )
    ):
        if character_id is not None and isinstance(data.get("from_name"), str):
            names.append((character_id, data["from_name"]))
    names += [
        (character_id, detail)
        for character_id, detail in db.execute(
            select(CharacterTrait.character_id, CharacterTrait.detail)
            .join(TraitDefinition, TraitDefinition.id == CharacterTrait.trait_definition_id)
            .where(
                CharacterTrait.character_id.in_(ids),
                TraitDefinition.name == "Alternate Identity",
                CharacterTrait.detail != "",
            )
        )
    ]
    found: dict[str, set[uuid.UUID]] = {}
    for character_id, name in names:
        if plain(name):
            found.setdefault(plain(name), set()).add(character_id)
    return found


# --- importing --------------------------------------------------------------------------


@dataclass
class TabReport:
    name: str
    rows: int = 0
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    linked: int = 0
    skipped: list[Skipped] = field(default_factory=list)
    # Rows imported as needing details: the action the sheet gives isn't one of the rules'.
    unknown_actions: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class Report:
    tabs: list[TabReport] = field(default_factory=list)
    # Names kept as text, with how many entries each.
    unmatched: Counter[str] = field(default_factory=Counter)
    # Names more than one character in the troupe goes by, also kept as text.
    ambiguous: dict[str, int] = field(default_factory=dict)


def import_log(
    db: Session,
    troupe: Troupe,
    tabs: dict[InfluenceType, list[Row]],
    zone: ZoneInfo,
) -> Report:
    """Bring the tabs into the troupe's log, in the session's transaction."""
    rules = influence_log.troupe_rules(db, troupe.id)
    names = troupe_names(db, troupe.id)
    imported = {
        e.reference: e
        for e in db.scalars(
            select(InfluenceEntry).where(
                InfluenceEntry.troupe_id == troupe.id, InfluenceEntry.reference.is_not(None)
            )
        )
    }
    report = Report()
    for influence_type, rows in tabs.items():
        tab = TabReport(TABS[influence_type])
        report.tabs.append(tab)
        lines, tab.skipped = read_rows(
            influence_type, rows, influence.actions(rules, influence_type)
        )
        tab.rows = len(lines) + len(tab.skipped)
        for line in lines:
            matches = names.get(plain(line.name), set())
            character_id = next(iter(matches)) if len(matches) == 1 else None
            details = Details(
                influence_type=influence_type,
                happened_at=datetime(line.day.year, line.day.month, line.day.day, tzinfo=zone),
                character_id=character_id,
                name=line.name,
                specialization=line.specialization,
                action_key=line.action.key if line.action else None,
                purpose=line.purpose,
                times=line.times,
                blocks=line.blocks,
                needs_details=line.action is None,
            )
            entry = imported.get(line.reference)
            if entry is not None:
                # What staff gave it stays where the sheet says nothing more.
                if details.character_id is None and entry.character_id is not None:
                    details.character_id = entry.character_id
                if details.action_key is None and entry.action_key is not None:
                    details.action_key, details.needs_details = entry.action_key, False
                if details.influence_type != entry.type:
                    raise CannotImport(f"{line.reference} is a {entry.type} entry in the log.")
            if line.action is None and details.action_key is None:
                tab.unknown_actions.append((line.reference, line.action_text))
            if details.character_id is None:
                if len(matches) > 1:
                    report.ambiguous[line.name] = report.ambiguous.get(line.name, 0) + 1
                else:
                    report.unmatched[line.name] += 1
            try:
                if entry is None:
                    influence_log.add_entry(
                        db,
                        None,
                        troupe,
                        details,
                        source="import",
                        reference=line.reference,
                        number=line.number,
                    )
                    tab.added += 1
                    continue
                was_linked = entry.character_id is not None
                changed = influence_log.change_entry(db, None, entry, details)
            except HTTPException as error:
                raise CannotImport(f"{line.reference}: {error.detail}") from error
            if not changed:
                tab.unchanged += 1
                continue
            tab.updated += 1
            if not was_linked and entry.character_id is not None:
                tab.linked += 1
    return report


def describe(report: Report, dry_run: bool) -> str:
    lines: list[str] = []
    for tab in report.tabs:
        lines.append(
            f"{tab.name}: {tab.rows} rows; {tab.added} entries added, {tab.updated} updated"
            f" ({tab.linked} linked to a character), {tab.unchanged} unchanged,"
            f" {len(tab.skipped)} rows skipped."
        )
        aged = [s.reference for s in tab.skipped if s.reason == ONLY_AN_AGE]
        if aged:
            # Often a formula filled down past the last row, so only the first few.
            rows = "1 row" if len(aged) == 1 else f"{len(aged)} rows"
            more = f" and {len(aged) - 10} more" if len(aged) > 10 else ""
            lines.append(f"  Skipped {rows} with only an age: {', '.join(aged[:10])}{more}")
        for skipped in tab.skipped:
            if skipped.reason != ONLY_AN_AGE:
                lines.append(f"  Skipped {skipped.reference}: {skipped.reason}")
        for reference, text in tab.unknown_actions:
            action = repr(text) if text else "no action"
            lines.append(f"  Needs details {reference}: {action} is not one of the actions")
    if report.unmatched:
        lines.append("Names that match no character in the troupe, kept as text:")
        for name, count in sorted(report.unmatched.items(), key=lambda n: n[0].casefold()):
            lines.append(f"  {name} ({count} {'entry' if count == 1 else 'entries'})")
    if report.ambiguous:
        lines.append("Names more than one character goes by, kept as text:")
        for name, count in sorted(report.ambiguous.items(), key=lambda n: n[0].casefold()):
            lines.append(f"  {name} ({count} {'entry' if count == 1 else 'entries'})")
    if dry_run:
        lines.append("Dry run: nothing was saved.")
    return "\n".join(lines)


def find_troupe(db: Session, text: str) -> Troupe:
    try:
        found = db.get(Troupe, uuid.UUID(text))
    except ValueError:
        found = None
    if found is not None:
        return found
    named = list(db.scalars(select(Troupe).where(func.lower(Troupe.name) == plain(text))))
    if not named:
        raise CannotImport(f"No troupe has the id or name {text!r}.")
    if len(named) > 1:
        ids = ", ".join(str(t.id) for t in named)
        raise CannotImport(f"More than one troupe is called {text!r}; give its id: {ids}.")
    return named[0]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m horatio.import_influence_log",
        description="Import a troupe's influence log from the old spreadsheet.",
    )
    parser.add_argument(
        "source", type=Path, help="the spreadsheet as .xlsx, or a folder of its tabs as CSV"
    )
    parser.add_argument("--troupe", required=True, help="the troupe's id or name")
    parser.add_argument(
        "--dry-run", action="store_true", help="report what it would do, and save nothing"
    )
    parser.add_argument(
        "--timezone",
        default=DEFAULT_TIMEZONE,
        help=f"where the sheet's dates are midnight (default {DEFAULT_TIMEZONE})",
    )
    args = parser.parse_args(argv)
    try:
        zone = ZoneInfo(args.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        print(f"There is no time zone {args.timezone!r}.", file=sys.stderr)
        return 2
    try:
        tabs = read_source(args.source)
        with get_sessionmaker()() as db:
            report = import_log(db, find_troupe(db, args.troupe), tabs, zone)
            if args.dry_run:
                db.rollback()
            else:
                db.commit()
    except CannotImport as error:
        print(error, file=sys.stderr)
        return 1
    print(describe(report, args.dry_run))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
