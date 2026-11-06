"""Import a troupe's characters from Yorick's Print Characters page as sheeted NPCs
of the troupe (#482), for staff to give each to its player as they sign up (#481):

    uv run python -m horatio.import_yorick_print PAGE --troupe TROUPE [--dry-run]
        [--names TABLE.toml ...] [--out FOLDER] [--as HANDLE] [--no-backup]

PAGE is the page saved from the browser as HTML, with its `_files/` folder beside it
(the portraits). TROUPE is the troupe's id or name. The characters are made by
HANDLE, the troupe's lead storyteller unless given.

Each printed character (horatio.yorick_print) is matched to Horatio's names
(horatio.yorick_names, with the table in yorick_names.toml and any --names tables
over it) and made a sheeted NPC of the troupe, its traits set straight from the
printout as staff set an NPC's. Rule checks do not stop it: what the sheet breaks is
flagged on it as on any sheet, and listed in the report. Its portrait is attached,
where the list shows one. It keeps its Yorick id as its `legacy_id` (or, with none, a
stable hash of its printed name), and the log says it was imported.

**Running it again** updates the characters it made before, matched on `legacy_id`,
rather than making them twice: their name and every trait the printout gives are set
again. Nothing else is taken off, so what staff added by hand stays, and a picture
staff changed is kept. A character given to its player since is left alone.

The whole import is one transaction. Before it writes anything it makes a database
backup (horatio.backups), unless --no-backup says not to; a dry run needs none.

**What it writes for review**, in FOLDER (by default `yorick-import/` beside the page;
keep it out of git, as it holds what the page holds): `report.txt`, a report for each
character of what imported cleanly, every line it could not match, what the sheet
breaks and what it costs at the troupe's prices; and `characters.json`, each character
as read and as matched. The summary, with every unmatched line, is printed too.
`--dry-run` does all of it and saves nothing: the import is rolled back.

No XP is written: a character's XP is set when it is given to its player (#481).
"""

import argparse
import json
import sys
import tomllib
import uuid
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio import audit, backups, npcs, pictures, sheets
from horatio.config import get_settings
from horatio.db import get_sessionmaker
from horatio.models import Character, CharacterTrait, Troupe, User
from horatio.rules.pricing import fixed_rating
from horatio.rules.store import read_troupe_rules
from horatio.specializations import troupe_options
from horatio.yorick_names import (
    Catalogue,
    Mapped,
    Mapper,
    Table,
    Trait,
    catalogue_of,
    read_table,
    spelling_renames,
)
from horatio.yorick_print import CannotRead, PrintedCharacter, read_file

SPLAT = "vampire"
# Unrated choices first: a faction needs its sect, a merit's value can depend on the
# clan. Then the rest as printed.
FIRST = ("clan", "sect", "faction", "archetype")


class CannotImport(Exception):
    """The import can't go ahead at all; the message says why."""


# --- one character ------------------------------------------------------------------------


@dataclass
class Result:
    """What became of one printed character."""

    printed: PrintedCharacter
    mapped: Mapped
    # made | updated | skipped | failed
    outcome: str = "made"
    # Why it was skipped, or what went wrong.
    skipped_because: str = ""
    character_id: str | None = None
    # Traits matched but refused on the sheet, with why ("Only a Sabbat character has
    # a Faction.").
    refused: list[tuple[str, str]] = field(default_factory=list)
    # Merits and flaws printed at another value than Horatio holds them at here.
    revalued: list[tuple[str, int, int]] = field(default_factory=list)
    # The checks the sheet breaks, as their messages.
    problems: list[str] = field(default_factory=list)
    xp: int = 0
    # Traits the troupe's rules give no price for, with why.
    unpriced: list[tuple[str, str]] = field(default_factory=list)
    portrait: str = "none"

    @property
    def clean(self) -> bool:
        return not (self.mapped.unmatched or self.refused)


def catalogue_for(db: Session, troupe: Troupe) -> Catalogue:
    rules = read_troupe_rules(db, SPLAT, troupe.id)
    return catalogue_of(rules.rule_set, troupe_options(db, troupe.id))


def put(db: Session, npc: Character, trait: Trait) -> None:
    """Set one trait on the NPC as the printout has it, as staff set an NPC's rating
    directly (horatio.npcs.set_rating), but keeping what the printout holds that a
    usual sheet would not, such as two focuses for one attribute: the sheet's checks
    flag it instead."""
    definition, category = sheets.find_definition(db, npc, trait.category, trait.name)
    if not category.rated:
        sheets.replace_choice(db, npc, definition, category, trait.detail)
        db.flush()
        return
    rows = sheets.sheet_rows(db, npc)
    if category.key == "paths":
        # One Morality: the printed one takes Humanity's place.
        for row in rows:
            other = row.category.key == "paths" and row.definition.id != definition.id
            if other and not row.trait.granted_rating:
                db.delete(row.trait)
    held = next(
        (
            r.trait
            for r in rows
            if r.definition.id == definition.id and r.trait.detail == trait.detail
        ),
        None,
    )
    if held is None:
        held = CharacterTrait(
            character_id=npc.id, trait_definition_id=definition.id, detail=trait.detail
        )
        db.add(held)
    rating = trait.rating
    if rating is None:
        # Printed with no rating: a ritual is held at its level, a technique at 1.
        rating = sheets.held_at(db, npc, category.key, definition.name) or 1
    held.rating = rating
    held.free_rating = min(held.free_rating or 0, rating)
    held.granted_rating = min(held.granted_rating or 0, rating)
    if held.creation_pick is not None and held.creation_pick > held.free_rating:
        held.creation_pick = None
    held.note = trait.note
    db.flush()


def hold_fixed_values(db: Session, npc: Character, result: Result) -> None:
    """Merits and flaws are held at their value here (a troupe's price for one is its
    value): one printed at another is held at Horatio's, and listed."""
    rules = sheets.rules_for(db, npc)
    rows = sheets.sheet_rows(db, npc)
    sheet = [r.as_rules_trait() for r in rows]
    for row in rows:
        value = fixed_rating(rules, sheet, row.category.key, row.definition.name)
        if value is None or not row.trait.rating or row.trait.rating == value:
            continue
        result.revalued.append((row.definition.name, row.trait.rating, value))
        row.trait.rating = value
        row.trait.free_rating = min(row.trait.free_rating, value)
        row.trait.granted_rating = min(row.trait.granted_rating, value)
    db.flush()


def name_primary_paths(db: Session, npc: Character) -> None:
    """Yorick prints no primary path. Where the clan's own path (if any) is not the
    highest the character holds of a discipline, its highest is named primary: no
    other path can go above the primary (MET: VTM p. 187). A tie at the top is left
    for staff."""
    ratings = {r.definition.name: r.trait.rating or 0 for r in sheets.sheet_rows(db, npc)}
    named = dict(npc.primary_paths)
    for primary in sheets.primary_paths(db, npc):
        top = primary.options[0]
        tied = [p for p in primary.options if ratings[p] == ratings[top]]
        current = ratings.get(primary.path or "", 0)
        if len(tied) == 1 and ratings[top] > current and top != primary.default:
            named[primary.discipline] = top
    if named != npc.primary_paths:
        npc.primary_paths = named
        db.flush()


def order(traits: Sequence[Trait]) -> list[Trait]:
    first = {category: n for n, category in enumerate(FIRST)}
    return sorted(traits, key=lambda t: first.get(t.category, len(FIRST)))


class Importer:
    def __init__(
        self,
        db: Session,
        troupe: Troupe,
        staff: User,
        mapper: Mapper,
        page_dir: Path,
        *,
        pictures_root: Path | None,
        dry_run: bool = False,
    ) -> None:
        self.db = db
        self.troupe = troupe
        self.staff = staff
        self.mapper = mapper
        self.page_dir = page_dir
        self.pictures_root = pictures_root
        self.dry_run = dry_run
        # Picture folders written, removed again if the import does not go through.
        self.written: list[Path] = []

    def existing(self, ids: Sequence[str]) -> dict[str, Character]:
        found = self.db.scalars(select(Character).where(Character.legacy_id.in_(ids)))
        return {c.legacy_id: c for c in found if c.legacy_id is not None}

    def run(self, printed: Sequence[PrintedCharacter]) -> list[Result]:
        before = self.existing([p.legacy_id for p in printed])
        results: list[Result] = []
        for character in printed:
            savepoint = self.db.begin_nested()
            try:
                results.append(self.one(character, before.get(character.legacy_id)))
            except Exception as error:
                # Kept going, so a dry run reports every character; a real run with
                # one that failed saves nothing.
                savepoint.rollback()
                failed = Result(character, self.mapper.character(character), "failed")
                failed.skipped_because = f"{type(error).__name__}: {error}"
                results.append(failed)
                continue
            savepoint.commit()
        return results

    def one(self, printed: PrintedCharacter, npc: Character | None) -> Result:
        result = Result(printed, self.mapper.character(printed))
        if npc is not None and (npc.kind != "npc" or npc.owner_troupe_id != self.troupe.id):
            result.outcome = "skipped"
            result.skipped_because = (
                "it has been given to its player"
                if npc.kind != "npc"
                else "an NPC of another troupe has its Yorick id"
            )
            result.character_id = str(npc.id)
            return result
        if npc is None:
            npc = npcs.create_npc(
                self.db, self.staff, self.troupe, SPLAT, printed.name, wizard=False
            )
            npc.legacy_id = printed.legacy_id
        else:
            result.outcome = "updated"
            npc.name = printed.name
        self.db.flush()
        result.character_id = str(npc.id)

        converts_before = sheets.sheet_effects(self.db, npc).converts
        for trait in order(result.mapped.traits):
            savepoint = self.db.begin_nested()
            try:
                put(self.db, npc, trait)
            except HTTPException as error:
                savepoint.rollback()
                result.refused.append((trait.source, str(error.detail)))
                continue
            savepoint.commit()
        hold_fixed_values(self.db, npc, result)
        name_primary_paths(self.db, npc)
        # What the sheet's merits and flaws give (Rugged's health levels), as when
        # staff set an NPC's ratings (horatio.sheets.checked).
        sheets.apply_grants(self.db, self.staff, npc, converts_before)

        result.problems = list(
            dict.fromkeys(v.message for v in sheets.sheet_violations(self.db, npc))
        )
        result.xp, lines = npcs.tally(self.db, npc)
        result.unpriced = [(line.name, line.note) for line in lines if line.cost is None]
        result.portrait = self.portrait(printed, npc)
        audit.record(
            self.db,
            self.staff,
            "npc.imported" if result.outcome == "made" else "npc.reimported",
            troupe_id=self.troupe.id,
            character_id=npc.id,
            legacy_id=printed.legacy_id,
            label=printed.label or "none",
            unmatched=len(result.mapped.unmatched) + len(result.refused),
        )
        return result

    def portrait(self, printed: PrintedCharacter, npc: Character) -> str:
        """Attach the printed character's portrait, unless the NPC has a picture."""
        if printed.portrait is None:
            return "none"
        if npc.picture_id is not None:
            return "kept the one it has"
        path = self.page_dir / printed.portrait
        try:
            image = pictures.read_image(path.read_bytes())
        except (OSError, pictures.PictureError) as error:
            return f"not attached: {error}"
        if self.dry_run:
            return "to be attached"
        if self.pictures_root is None:
            return "not attached: pictures are not set up here (HORATIO_UPLOAD_DIR)"
        new = uuid.uuid4()
        directory = pictures.picture_dir(self.pictures_root, npc.id, new)
        self.written.append(directory)
        pictures.write_picture(directory, image, None)
        box = pictures.square_box(image.width, image.height, None)
        npc.picture_id = new
        npc.picture_crop = {
            "x": box[0] / image.width,
            "y": box[1] / image.height,
            "size": (box[2] - box[0]) / image.width,
        }
        npc.picture_by = self.staff.id
        npc.picture_at = datetime.now(UTC)
        self.db.flush()
        return "attached"

    def undo_pictures(self) -> None:
        for directory in self.written:
            pictures.remove(directory)


# --- the report ---------------------------------------------------------------------------


def plural(count: int, one: str, many: str | None = None) -> str:
    return f"{count} {one if count == 1 else (many or one + 's')}"


def summary(
    results: Sequence[Result], dry_run: bool, left_out: Mapping[str, str] | None = None
) -> list[str]:
    """The import as a whole, and every printed line it could not match. `left_out` is
    why the table leaves each heading to staff."""
    outcomes = Counter(r.outcome for r in results)
    unmatched = [u for r in results for u in r.mapped.unmatched]
    refused = [(s, why) for r in results for s, why in r.refused]
    lines = [
        f"{plural(len(results), 'character')} read from the page: "
        f"{outcomes['made']} {'to be made' if dry_run else 'made'}, "
        f"{outcomes['updated']} {'to be updated' if dry_run else 'updated'}, "
        f"{outcomes['skipped']} skipped, {outcomes['failed']} failed.",
        f"{sum(r.clean for r in results)} import cleanly; "
        f"{plural(len(unmatched), 'printed line')} matched nothing "
        f"({len({(u.heading, u.text) for u in unmatched})} different), and "
        f"{plural(len(refused), 'trait')} could not be put on a sheet.",
        f"{sum(bool(r.problems) for r in results)} sheets break a rule check "
        f"({plural(sum(len(r.problems) for r in results), 'check')} in all); "
        f"{sum(bool(r.revalued) for r in results)} hold a merit or flaw at another value.",
        f"{sum(r.portrait in ('attached', 'to be attached') for r in results)} portraits "
        f"{'to be attached' if dry_run else 'attached'}.",
        f"{sum(r.xp for r in results)} XP in all at the troupe's prices "
        f"(none of it written: XP is set when a character is given to its player).",
    ]
    left = Counter(item.split(":")[0] for r in results for item in r.mapped.left_out)
    if left:
        lines += ["", "Left to staff, as printed in each character's report:"]
        for heading, count in sorted(left.items()):
            why = (left_out or {}).get(heading, "")
            lines.append(f"  {heading}: {plural(count, 'line')}" + (f". {why}" if why else ""))
    if unmatched or refused:
        lines += ["", "Printed lines that matched nothing, by heading:"]
        grouped: dict[str, Counter[str]] = defaultdict(Counter)
        for u in unmatched:
            grouped[u.heading][f"{u.text} ({u.reason})"] += 1
        for heading in sorted(grouped):
            lines.append(f"  {heading}:")
            for text, count in sorted(grouped[heading].items()):
                lines.append(f"    {text}" + (f" x{count}" if count > 1 else ""))
        if refused:
            lines.append("  Matched, but could not be put on a sheet:")
            for (source, why), count in sorted(Counter(refused).items()):
                lines.append(f"    {source}: {why}" + (f" x{count}" if count > 1 else ""))
    return lines


def character_report(result: Result) -> list[str]:
    printed = result.printed
    head = f"== {printed.name} (Yorick id {printed.legacy_id}"
    head += f"; labelled {printed.label})" if printed.label else ")"
    lines = [head]
    if result.outcome == "skipped":
        return [*lines, f"Skipped: {result.skipped_because}."]
    if result.outcome == "failed":
        return [*lines, f"Failed: {result.skipped_because}"]
    mapped = result.mapped
    lines.append(
        f"{'Made' if result.outcome == 'made' else 'Updated'}: "
        f"{plural(len(mapped.traits) - len(result.refused), 'trait')} imported"
        + (" cleanly." if result.clean else ".")
    )
    sections: list[tuple[str, list[str]]] = [
        ("Matched nothing", [f"{u.source} ({u.reason})" for u in mapped.unmatched]),
        ("Could not be put on the sheet", [f"{s}: {why}" for s, why in result.refused]),
        (
            "Held at Horatio's value",
            [f"{name}: printed {was}, held at {now}" for name, was, now in result.revalued],
        ),
        ("Read as several", mapped.split),
        ("Rule checks the sheet breaks", result.problems),
        ("No price in this troupe", [f"{name}: {why}" for name, why in result.unpriced]),
        ("Left to staff", mapped.left_out),
    ]
    for title, items in sections:
        if items:
            lines.append(f"{title}:")
            lines += [f"  {item}" for item in items]
    lines.append(f"XP at the troupe's prices: {result.xp}")
    lines.append(f"Portrait: {result.portrait}")
    if printed.extended_text:
        lines.append("Its extended print text is not imported (see characters.json).")
    return lines


def write_review(
    folder: Path, results: Sequence[Result], dry_run: bool, left_out: Mapping[str, str]
) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    text = summary(results, dry_run, left_out)
    for result in results:
        text += ["", *character_report(result)]
    (folder / "report.txt").write_text("\n".join(text) + "\n", encoding="utf-8")
    records: list[dict[str, Any]] = [
        {
            "printed": asdict(r.printed),
            "outcome": r.outcome,
            "skipped_because": r.skipped_because,
            "character_id": r.character_id,
            "traits": [asdict(t) for t in r.mapped.traits],
            "unmatched": [asdict(u) for u in r.mapped.unmatched],
            "refused": r.refused,
            "revalued": r.revalued,
            "left_out": r.mapped.left_out,
            "split": r.mapped.split,
            "problems": r.problems,
            "xp": r.xp,
            "unpriced": r.unpriced,
            "portrait": r.portrait,
        }
        for r in results
    ]
    (folder / "characters.json").write_text(
        json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


# --- the command --------------------------------------------------------------------------


def plain(text: str) -> str:
    return " ".join(text.split()).casefold()


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


def find_staff(db: Session, troupe: Troupe, handle: str | None) -> User:
    if handle is None:
        return db.get_one(User, troupe.lead_user_id)
    found = db.scalar(select(User).where(func.lower(User.handle) == handle.strip().casefold()))
    if found is None:
        raise CannotImport(f"No one has the handle {handle!r}.")
    return found


def import_page(
    db: Session,
    troupe: Troupe,
    staff: User,
    printed: Sequence[PrintedCharacter],
    page_dir: Path,
    table: Table,
    *,
    dry_run: bool,
) -> list[Result]:
    """Import the printed characters in one transaction, and save them unless it is a
    dry run or any of them failed."""
    mapper = Mapper(table, catalogue_for(db, troupe))
    importer = Importer(
        db,
        troupe,
        staff,
        mapper,
        page_dir,
        pictures_root=None if dry_run else pictures.upload_dir(),
        dry_run=dry_run,
    )
    try:
        results = importer.run(printed)
        if dry_run or any(r.outcome == "failed" for r in results):
            db.rollback()
        else:
            db.commit()
    except BaseException:
        db.rollback()
        importer.undo_pictures()
        raise
    if not dry_run and any(r.outcome == "failed" for r in results):
        importer.undo_pictures()
    return results


def make_backup() -> str:
    """Back the database up (horatio.backups); the backup's name."""
    directory = backups.backup_dir()
    if directory is None:
        raise CannotImport(
            "Backups are not set up here (HORATIO_BACKUP_DIR), so none can be made first;"
            " give --no-backup to import without one."
        )
    try:
        return backups.make(directory, get_settings().database_url).name
    except backups.BackupError as error:
        raise CannotImport(f"The backup failed, so nothing was imported: {error}") from error


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m horatio.import_yorick_print",
        description="Import a troupe's characters from Yorick's Print Characters page as NPCs.",
    )
    parser.add_argument(
        "page", type=Path, help="the page saved as HTML, its _files folder beside it"
    )
    parser.add_argument("--troupe", required=True, help="the troupe's id or name")
    parser.add_argument(
        "--dry-run", action="store_true", help="report what it would do, and save nothing"
    )
    parser.add_argument(
        "--names",
        type=Path,
        action="append",
        default=[],
        help="a table of more names, in yorick_names.toml's shape (can be given again)",
    )
    parser.add_argument(
        "--out", type=Path, help="where to write the report and JSON (default: beside the page)"
    )
    parser.add_argument(
        "--as", dest="handle", help="the staff member who makes them (default: the lead)"
    )
    parser.add_argument(
        "--no-backup", action="store_true", help="import without making a backup first"
    )
    args = parser.parse_args(argv)
    out: Path = args.out or args.page.parent / "yorick-import"
    try:
        printed = read_file(args.page)
        table = read_table(args.names, renames=spelling_renames())
        with get_sessionmaker()() as db:
            troupe = find_troupe(db, args.troupe)
            staff = find_staff(db, troupe, args.handle)
            if not args.dry_run and not args.no_backup:
                print(f"Backed up the database first: {make_backup()}")
            results = import_page(
                db, troupe, staff, printed, args.page.parent, table, dry_run=args.dry_run
            )
    except (CannotRead, CannotImport, OSError, tomllib.TOMLDecodeError) as error:
        print(error, file=sys.stderr)
        return 1
    write_review(out, results, args.dry_run, table.left_out)
    print("\n".join(summary(results, args.dry_run, table.left_out)))
    print(f"\nThe report for each character, and the JSON, are in {out}.")
    failed = [r for r in results if r.outcome == "failed"]
    if args.dry_run:
        print("Dry run: nothing was saved.")
    elif failed:
        print(
            f"{plural(len(failed), 'character')} could not be imported (see the report),"
            " so nothing was saved.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
