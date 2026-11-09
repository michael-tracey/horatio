"""Bringing characters in from backups by the batch (issue #567): a troupe's staff
import a troupe's export (a .zip, or character files one by one), and a player
imports the .zip that Export all made of their characters.

**Reading** an upload: a .zip as a troupe's or a player's export writes it (a JSON file
for each character, its picture under pictures/), or character files on their own,
each with its picture in it. A file that isn't a Horatio character, or is from a
newer Horatio, is listed with why, and the rest come in. A zip is opened in memory and
only its character files and pictures are read; a path outside its folder, or more
than it may unpack to, refuses the lot.

**A troupe's import** brings each character in as the troupe's own:
- An NPC comes in as an NPC of the troupe, its sheet as the file has it, free dots
  and picks too. One whose picks are fitted (horatio.npc_picks), or that has no
  picks at all (an older or a foreign file), has them fitted here, at this troupe's
  prices.
- A player character is matched to its player: by the email in the file (when staff
  exported it with emails), else by its handle. Staff see the match and may change it.
  A matched one is made an NPC and given to its player at once (horatio.npc_gifts):
  at home here and accepted, its sheet bought at this troupe's prices, with what
  unspent XP staff choose to carry over. One with no player is held as an NPC, to
  give later. Only those who give NPCs (the lead and storytellers) give them: for an
  assistant storyteller every player character is held.
- A retired character comes in retired: given and then retired, or held retired.
- One with the name of a character already here (an NPC of the troupe, or for a
  player character, one of its player's at home here) waits for staff to choose:
  skip it, replace it (an NPC only: its sheet, Retainers, backstory and picture as the
  file has them, the NPC itself kept), or add a copy.
- Its XP history isn't written: an NPC has none to keep, and giving one to its player
  writes its own (the "Imported" award, and what staff carry over).
- Equipment, titles and status are shown, never imported, as on a player's import.

Each character is tried on its own, so one that can't come in says why and the rest
come in. Reviewing is the same import, rolled back.

**A player's import** of a .zip imports each character file in it as the single
import does (horatio.character_backup.import_character), with its picture from the
zip's pictures/, each as a new character of theirs in their vault.
"""

import json
import uuid
import zipfile
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from horatio import audit, backstories, handles, npc_gifts, npc_picks, npcs
from horatio import character_backup as backup
from horatio.models import (
    Character,
    CharacterTrait,
    RuleSet,
    StockNpc,
    Troupe,
    TroupeMembership,
    User,
)
from horatio.rules import stock
from horatio.rules.store import read_troupe_rules
from horatio.sheets import sync_fixed_ratings, unprocessable

# The upload, and what a zip may unpack to.
MAX_UPLOAD = 50 * 1024 * 1024
MAX_UNPACKED = 200 * 1024 * 1024
MAX_ENTRIES = 5000
PICTURE_SUFFIXES = (".webp", ".jpg", ".jpeg", ".png", ".gif")


class CannotRead(Exception):
    """The upload can't be read at all; the message says why."""


# --- reading an upload --------------------------------------------------------------------


@dataclass
class Entry:
    """One character file in an upload: where it is in it, and what it holds or why
    it can't be read."""

    key: str
    document: backup.CharacterDocument | None = None
    problem: str | None = None


@dataclass
class Bundle:
    entries: list[Entry] = field(default_factory=list[Entry])
    # The pictures beside them in a zip, by their path in it.
    files: dict[str, bytes] = field(default_factory=dict[str, bytes])


def safe_path(name: str) -> str | None:
    """A zip entry's path, or None for one that would land outside its folder."""
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or any(p in ("", ".", "..") for p in path.parts):
        return None
    if path.parts and ":" in path.parts[0]:
        return None
    return str(path)


def entry_of(key: str, data: bytes) -> Entry:
    """The character a file holds, or why it can't be read."""
    if len(data) > backup.MAX_BYTES:
        return Entry(key, problem="That file is too large to be a Horatio character.")
    try:
        raw = json.loads(data)
    except (UnicodeDecodeError, ValueError):
        return Entry(
            key, problem="That file isn't a Horatio character: it isn't a .json file Horatio wrote."
        )
    try:
        return Entry(key, document=backup.read(raw))
    except HTTPException as error:
        return Entry(key, problem=str(error.detail))


def unzip(data: bytes, into: Bundle) -> None:
    try:
        archive = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile as error:
        raise CannotRead("That zip can't be opened.") from error
    with archive:
        found = [e for e in archive.infolist() if not e.is_dir()]
        if len(found) > MAX_ENTRIES:
            raise CannotRead(f"That zip holds more than {MAX_ENTRIES} files.")
        if sum(e.file_size for e in found) > MAX_UNPACKED:
            raise CannotRead("That zip unpacks to more than 200 MB.")
        for entry in found:
            if entry.filename.split("/")[0] == "__MACOSX":
                continue
            path = safe_path(entry.filename)
            if path is None:
                raise CannotRead(f"The zip holds a file outside its folder: {entry.filename}")
            name = PurePosixPath(path).name
            suffix = PurePosixPath(path).suffix.lower()
            if suffix == ".json" and name != "manifest.json":
                into.entries.append(entry_of(path, archive.read(entry)))
            elif suffix in PICTURE_SUFFIXES:
                into.files[path] = archive.read(entry)


def read_uploads(uploads: Sequence[tuple[str, bytes]]) -> Bundle:
    """The character files in the files uploaded: zips and character files alike."""
    if sum(len(data) for _, data in uploads) > MAX_UPLOAD:
        raise CannotRead("Those files come to more than 50 MB.")
    found = Bundle()
    keys: set[str] = set()
    for filename, data in uploads:
        name = PurePosixPath(filename.replace("\\", "/")).name or "file"
        if name.lower().endswith(".zip") or data[:4] == b"PK\x03\x04":
            before = len(found.entries)
            unzip(data, found)
            if len(found.entries) == before:
                raise CannotRead(f"{name} holds no character files.")
            continue
        # Two files of one name, chosen from two folders, are told apart.
        key, n = name, 1
        while key in keys:
            n += 1
            key = f"{name} ({n})"
        keys.add(key)
        found.entries.append(entry_of(key, data))
    if not found.entries:
        raise CannotRead("Choose a .zip exported from Horatio, or character files.")
    keys = set()
    for entry in found.entries:
        if entry.key in keys:
            raise CannotRead(f"{entry.key} is in the upload twice.")
        keys.add(entry.key)
    return found


def unspent_in(document: backup.CharacterDocument) -> int:
    earned, spent, lost = backup.history_totals(document.xp)
    return max(0, earned - spent - lost)


# --- a troupe's import --------------------------------------------------------------------

Choice = Literal["skip", "replace", "copy"]
Outcome = Literal["new", "given", "held", "replaced", "skipped", "undecided", "cannot"]
MatchedBy = Literal["email", "handle", "chosen"]


@dataclass(frozen=True)
class Decision:
    """What staff chose for one character file."""

    # For one with the name of a character here.
    choice: Choice | None = None
    # A player character's player, by handle; "" to hold it as an NPC; None for the
    # player the file names, if they are found.
    player: str | None = None
    carried_xp: int = 0
    carried_reason: str = ""


@dataclass(frozen=True)
class Here:
    """A character already here, with the name of one in the upload."""

    character_id: uuid.UUID
    name: str
    # "an NPC of the troupe", "@handle's character".
    whose: str
    npc: bool
    player_id: uuid.UUID | None


@dataclass
class Planned:
    """What the import does, or would do, with one character file."""

    entry: Entry
    outcome: Outcome
    problem: str | None = None
    player: User | None = None
    matched_by: MatchedBy | None = None
    duplicate: Here | None = None
    choice: Choice | None = None
    found: backup.Imported | None = None
    unspent: int = 0
    carried_xp: int = 0

    @property
    def can_replace(self) -> bool:
        return self.duplicate is not None and self.duplicate.npc


def same_name(name: str) -> str:
    return " ".join(name.casefold().split())


def npc_identity(document: backup.CharacterDocument) -> tuple[str, str, dict[str, Any] | None]:
    """The NPC kind, form and custom kind a character comes in as: an NPC's own, and a
    player character's a sheeted vampire or ghoul."""
    who = document.character
    if who.kind == "npc":
        kind = who.npc_kind or ("ghoul" if who.splat == "ghoul" else "vampire")
        return kind, who.npc_form or "sheeted", who.npc_custom_kind
    return ("ghoul" if who.splat == "ghoul" else "vampire"), "sheeted", None


def checked_kind(document: backup.CharacterDocument) -> tuple[str, str, dict[str, Any] | None]:
    kind, form, custom = npc_identity(document)
    who = document.character
    try:
        found = npcs.resolve_kind(kind, custom)
    except (KeyError, TypeError, ValueError) as error:
        raise unprocessable(f"{who.name}'s custom kind can't be read.") from error
    if npcs.splat_for(kind) != who.splat:
        raise unprocessable(
            f"{who.name} is a {found.name} on the {who.splat} rules: they don't go together."
        )
    return kind, form, custom


def set_stock(
    db: Session, npc: Character, troupe: Troupe, document: backup.CharacterDocument
) -> None:
    """A Stock NPC's rating and specializations, as the Stock NPC rules allow them."""
    found = document.stock or backup.BackupStock(rating=1)
    chosen: list[stock.Specialization] = []
    for s in found.specializations:
        kind_of, name = s.get("type"), s.get("name")
        if kind_of not in ("skill", "power") or not name:
            raise unprocessable("Its specializations can't be read.")
        chosen.append(stock.Specialization(type=kind_of, name=name))
    kind = npcs.resolve_kind(npc.npc_kind or "vampire", npc.npc_custom_kind)
    rule_set = read_troupe_rules(db, "vampire", troupe.id).rule_set
    names = {
        category: {name for (c, name) in rule_set.traits if c == category}
        for category in ("skills", "disciplines")
    }
    try:
        stock.check(kind, found.rating, chosen, names["skills"], names["disciplines"])
    except stock.StockError as error:
        raise unprocessable(str(error)) from error
    row = db.scalar(select(StockNpc).where(StockNpc.character_id == npc.id))
    if row is None:
        row = StockNpc(character_id=npc.id, rating=found.rating)
        db.add(row)
    row.rating = found.rating
    row.specializations = [{"type": s.type, "name": s.name} for s in chosen]


def fill_npc(
    db: Session,
    staff: User,
    troupe: Troupe,
    document: backup.CharacterDocument,
    *,
    root: Path | None,
    files: Mapping[str, bytes],
    write_pictures: bool,
    into: Character | None = None,
) -> backup.Imported:
    """The character as an NPC of the troupe, new or `into` one already here, its sheet
    as the file has it. Callers commit, or roll back for a review."""
    who = document.character
    kind, form, custom = checked_kind(document)
    if db.scalar(select(RuleSet.id).where(RuleSet.splat == who.splat)) is None:
        raise unprocessable(f"This Horatio has no rules for {who.splat!r} characters.")
    # Fitted here if it was there, or if it has no picks at all to keep.
    fits = form == "sheeted" and (
        who.fits_picks or not any(t.creation_pick is not None for t in document.traits)
    )
    if into is None:
        npc = Character(
            player_id=staff.id,
            splat=who.splat,
            name=who.name,
            kind="npc",
            npc_kind=kind,
            npc_form=form,
            npc_custom_kind=dict(custom) if custom is not None else None,
            owner_troupe_id=troupe.id,
            home_troupe_id=troupe.id,
            creation_completed_at=datetime.now(UTC),
        )
        db.add(npc)
        db.flush()
        db.add(TroupeMembership(troupe_id=troupe.id, character_id=npc.id))
    else:
        npc = into
        if npc.npc_form != form:
            here, there = (
                ("a Stock NPC", "a full sheet")
                if npc.npc_form == "stock"
                else ("a full sheet", "a Stock NPC")
            )
            raise unprocessable(
                f"{npc.name} is {here} here and {there} in the file: add it as a copy instead."
            )
        db.execute(delete(CharacterTrait).where(CharacterTrait.character_id == npc.id))
        npc.splat = who.splat
    npc.npc_kind = kind
    npc.npc_form = form
    npc.npc_custom_kind = dict(custom) if custom is not None else None
    npc.fits_picks = fits
    npc.pronouns = who.pronouns
    npc.primary_paths = dict(who.primary_paths)
    npc.domitor_name = who.domitor if backup.splat_of(who.splat).has_domitor else ""
    npc.card_text = who.card_text
    npc.card_flavour = who.card_flavour
    npc.on_whos_who = who.on_whos_who if who.kind == "npc" else False
    db.flush()
    found = backup.Imported(npc)
    found.items.append(
        backup.Reviewed(
            "character",
            who.name,
            "differs" if into is not None else "new",
            reason="Replaces the NPC here of this name: its sheet as the file has it."
            if into is not None
            else None,
            after=backup.splat_of(who.splat).label,
        )
    )
    if form == "stock":
        with backup.tried(db, found, "character", "Stock rating and specializations"):
            set_stock(db, npc, troupe, document)

    categories = backup.categories_of(db, who.splat)
    for item in backup.ordered(categories, document.traits):
        known = categories.get(item.category)
        label = f"{known.name if known else item.category}: {item.label()}"
        with backup.tried(db, found, "sheet", label):
            backup.put(db, npc, item, document.troupe)
    sync_fixed_ratings(db, npc)
    npc_picks.fit(db, npc)
    cannot = [i for i in found.items[1:] if i.status == "cannot"]
    found.items = [found.items[0], *backup.compare_sheet(db, npc, document), *cannot]

    earned, spent, lost = backup.history_totals(document.xp)
    here, unpriced = backup.priced_here(db, npc)
    found.xp = backup.XpFigures(
        earned=earned,
        spent=spent,
        lost=lost,
        sheet_there=sum(i.paid for i in document.traits),
        sheet_here=here,
        unpriced=unpriced,
    )
    if document.xp:
        found.items.append(
            backup.Reviewed(
                "xp",
                f"{len(document.xp)} lines of XP history",
                "info",
                reason="Shown only: an NPC keeps no XP history, and giving one to its player"
                " buys its sheet at this troupe's prices.",
            )
        )
    text = document.backstory
    if text.strip():
        with backup.tried(db, found, "character", "Backstory"):
            kept = backstories.held(db, npc)
            if kept.text != text:
                backstories.save(db, staff, npc, text, kept.version)
            found.items.append(backup.Reviewed("character", "Backstory", "new"))
    backup.import_retainers(db, staff, found, document)
    backup.attach_picture(found, document, root, files, write=write_pictures)
    backup.shown_only(found, document, staff=True)
    db.flush()
    audit.record(
        db,
        staff,
        "npc.replaced_from_backup" if into is not None else "npc.imported_from_backup",
        troupe_id=troupe.id,
        character_id=npc.id,
        whence=backup.whence(document),
        left_out=sum(1 for i in found.items if i.status == "cannot"),
        unspent=unspent_in(document),
    )
    return found


def retire_as_it_was(db: Session, character: Character, document: backup.CharacterDocument) -> None:
    """A character retired where it came from is retired here, not listed."""
    if not document.character.retired:
        return
    character.status = "retired"
    character.left_reason = document.character.left_reason
    character.left_listed = False
    db.flush()


class TroupeImport:
    """One run of a troupe's import, over every file in the upload."""

    def __init__(
        self,
        db: Session,
        staff: User,
        troupe: Troupe,
        bundle: Bundle,
        *,
        can_give: bool,
        decisions: Mapping[str, Decision],
        root: Path | None,
        write_pictures: bool,
    ) -> None:
        self.db = db
        self.staff = staff
        self.troupe = troupe
        self.bundle = bundle
        self.can_give = can_give
        self.decisions = decisions
        self.root = root
        self.write_pictures = write_pictures
        self.here = self.characters_here()
        self.replaced: set[uuid.UUID] = set()
        # Picture folders written, removed again if the import doesn't go through.
        self.written: list[Path] = []

    def characters_here(self) -> dict[str, list[Here]]:
        """The troupe's NPCs and the player characters at home here, still active, by
        name."""
        rows = self.db.execute(
            select(Character, User.handle)
            .join(User, User.id == Character.player_id)
            .where(
                Character.status == "active",
                (Character.owner_troupe_id == self.troupe.id)
                | ((Character.home_troupe_id == self.troupe.id) & (Character.kind == "pc")),
            )
            .order_by(Character.name, Character.id)
        )
        found: dict[str, list[Here]] = defaultdict(list)
        for character, handle in rows:
            npc = character.kind == "npc"
            found[same_name(character.name)].append(
                Here(
                    character_id=character.id,
                    name=character.name,
                    whose=(
                        "a Stock NPC of the troupe"
                        if npc and character.npc_form == "stock"
                        else "an NPC of the troupe"
                        if npc
                        else f"@{handle}'s character"
                    ),
                    npc=npc,
                    player_id=None if npc else character.player_id,
                )
            )
        return found

    def duplicate_of(self, name: str, player: User | None) -> Here | None:
        """A character here this one would be: one of its player's here of its name, or
        an NPC of the troupe of its name (a copy held from an earlier import)."""
        matches = self.here.get(same_name(name), [])
        if player is not None:
            mine = next((m for m in matches if m.player_id == player.id), None)
            if mine is not None:
                return mine
        return next((m for m in matches if m.npc and m.character_id not in self.replaced), None)

    def player_for(self, planned: Planned, decision: Decision) -> None:
        """Whom a player character goes to: whoever staff chose, else the player the
        file names, found by email and then by handle."""
        document = planned.entry.document
        assert document is not None
        if not self.can_give or document.character.kind != "pc":
            return
        if decision.player is not None:
            if not decision.player.strip():
                return
            chosen = handles.holder(self.db, decision.player)
            if chosen is None:
                raise unprocessable(f"Nobody has the handle {decision.player.strip()}.")
            planned.player, planned.matched_by = chosen, "chosen"
            return
        named = document.player
        if named is None:
            return
        if named.email:
            found = self.db.scalar(
                select(User).where(
                    func.lower(User.email) == named.email.strip().lower(),
                    User.merged_into_id.is_(None),
                )
            )
            if found is not None:
                planned.player, planned.matched_by = found, "email"
                return
        if named.handle:
            found = handles.holder(self.db, named.handle)
            if found is not None:
                planned.player, planned.matched_by = found, "handle"

    def one(self, entry: Entry) -> Planned:
        document = entry.document
        if document is None:
            return Planned(entry, "cannot", problem=entry.problem)
        decision = self.decisions.get(entry.key, Decision())
        planned = Planned(entry, "new", unspent=unspent_in(document))
        try:
            self.player_for(planned, decision)
        except HTTPException as error:
            planned.outcome, planned.problem = "cannot", str(error.detail)
            return planned
        planned.duplicate = self.duplicate_of(document.character.name, planned.player)
        if planned.duplicate is not None:
            planned.choice = decision.choice
            if decision.choice == "replace" and not planned.can_replace:
                planned.choice = None
            if planned.choice is None:
                planned.outcome = "undecided"
                return planned
            if planned.choice == "skip":
                planned.outcome = "skipped"
                return planned
        if planned.player is not None:
            try:
                planned.carried_xp, _ = npc_gifts.checked_carry(
                    decision.carried_xp, decision.carried_reason
                )
            except HTTPException as error:
                planned.outcome, planned.problem = "cannot", str(error.detail)
                return planned
        into = None
        if planned.choice == "replace" and planned.duplicate is not None:
            into = self.db.get_one(Character, planned.duplicate.character_id)
        savepoint = self.db.begin_nested()
        try:
            planned.found = fill_npc(
                self.db,
                self.staff,
                self.troupe,
                document,
                root=self.root,
                files=self.bundle.files,
                write_pictures=self.write_pictures,
                into=into,
            )
            self.written.extend(planned.found.written)
            character = planned.found.character
            if planned.player is not None:
                npc_gifts.give(
                    self.db,
                    self.staff,
                    character,
                    planned.player,
                    planned.carried_xp,
                    decision.carried_reason or f"from {backup.whence(document)}",
                )
                planned.outcome = "given"
            elif document.character.kind == "pc":
                planned.outcome = "held"
            else:
                planned.outcome = "replaced" if into is not None else "new"
            retire_as_it_was(self.db, character, document)
        except HTTPException as error:
            if error.status_code >= 500:
                raise
            savepoint.rollback()
            planned.found = None
            planned.outcome, planned.problem = "cannot", str(error.detail)
            return planned
        savepoint.commit()
        if into is not None:
            self.replaced.add(into.id)
        return planned

    def run(self, progress: Callable[[int, int], None] | None = None) -> list[Planned]:
        found: list[Planned] = []
        for done, entry in enumerate(self.bundle.entries):
            if progress is not None:
                progress(done, len(self.bundle.entries))
            found.append(self.one(entry))
        return found


# --- a player's import --------------------------------------------------------------------


@dataclass
class Mine:
    """What a player's import does, or would do, with one character file."""

    entry: Entry
    outcome: Literal["new", "skipped", "cannot"]
    problem: str | None = None
    found: backup.Imported | None = None


def import_mine(
    db: Session,
    user: User,
    bundle: Bundle,
    troupe_for: Callable[[backup.CharacterDocument], Troupe | None],
    *,
    root: Path | None,
    write_pictures: bool,
    only: set[str] | None = None,
) -> list[Mine]:
    """Each character file as a new character of `user`'s, as the single import makes
    one, built for the troupe `troupe_for` gives it; those not in `only` (if given)
    left out."""
    found: list[Mine] = []
    for entry in bundle.entries:
        document = entry.document
        if document is None:
            found.append(Mine(entry, "cannot", problem=entry.problem))
            continue
        if only is not None and entry.key not in only:
            found.append(Mine(entry, "skipped"))
            continue
        savepoint = db.begin_nested()
        try:
            done = backup.import_character(
                db,
                user,
                document,
                troupe_for(document),
                root=root,
                files=bundle.files,
                write_pictures=write_pictures,
            )
        except HTTPException as error:
            if error.status_code >= 500:
                raise
            savepoint.rollback()
            found.append(Mine(entry, "cannot", problem=str(error.detail)))
            continue
        savepoint.commit()
        found.append(Mine(entry, "new", found=done))
    return found
