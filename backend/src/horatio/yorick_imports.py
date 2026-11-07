"""The custodian's import from Yorick (#518), in the app: a troupe's characters come
across from Yorick's Print Characters page as sheeted NPCs of the troupe
(horatio.import_yorick_print), for staff to give each to its player (#481).

The custodian chooses the troupe and uploads the page, saved from the browser: a zip
of the `.html` and its `_files` folder (the portraits), or the `.html` alone (no
portraits then). A dry run starts at once. The custodian gives the lines that matched
nothing their names here (the troupe's own table, over the bundled one), or leaves
them for staff to put right by hand, and chooses what to do with each printed
character whose name a character here has. Then they import it.

A troupe may come across over months, a few players at a time, so a troupe keeps
one import (YorickImport): a new upload replaces the page, and the troupe's names and
choices stay for the next. Importing again updates the NPCs made before.

**The page is private.** It holds real players' names and emails. It is kept under the
upload directory, served by nothing, and read only by the custodian through the API;
it is deleted once imported, when the custodian deletes it, or `KEPT_FOR` after it
was uploaded. The report goes with it, likewise `KEPT_FOR` after it was made.

**The dry run and the import run in the background**, in a thread of the API
process: a page of 150 characters takes over a minute, longer than a request may.
Their progress is kept in memory, as the API runs as one process. A job its process
no longer has (a restart) is reported as stopped: an import that never finished
saved nothing, being one transaction.
"""

import logging
import shutil
import threading
import tomllib
import uuid
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from horatio import audit, backups, pictures
from horatio.config import get_settings
from horatio.db import get_sessionmaker
from horatio.import_yorick_print import (
    CHOICES,
    Importer,
    Result,
    catalogue_for,
    record_of,
    report_text,
    summary,
)
from horatio.models import Troupe, TroupeStaff, User, YorickImport
from horatio.yorick_names import Catalogue, Mapper, Table, read_table, spelling_renames
from horatio.yorick_print import CannotRead, PrintedCharacter, read_file

log = logging.getLogger(__name__)

KEPT_FOR = timedelta(days=30)
# The upload, and what a zip may unpack to.
MAX_UPLOAD = 50 * 1024 * 1024
MAX_UNPACKED = 200 * 1024 * 1024
PAGE_SUFFIXES = (".html", ".htm")
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".gif", ".webp")
# The table's parts a name can be given in, from the custodian's Match to...
TABLE_PARTS = ("names", "values", "paths")


class CannotUpload(Exception):
    """The upload is not a page the import can read; the message says why."""


class Busy(Exception):
    """A dry run or import is running for the troupe already."""


# --- the page -----------------------------------------------------------------------------


def root() -> Path | None:
    """Where pages are kept, or None where uploads are not set up."""
    uploads = pictures.upload_dir()
    return uploads / "yorick-imports" if uploads is not None else None


def page_folder(troupe_id: uuid.UUID) -> Path | None:
    kept = root()
    return kept / str(troupe_id) if kept is not None else None


def page_path(record: YorickImport) -> Path | None:
    folder = page_folder(record.troupe_id)
    if folder is None or record.page_name is None:
        return None
    path = folder / record.page_name
    return path if path.is_file() else None


@dataclass
class Page:
    # The page's path inside its folder: "Print Troupe Characters.html".
    name: str
    characters: int
    portraits: int


def safe_parts(name: str) -> tuple[str, ...] | None:
    """A zip entry's path as parts to write under the page's folder, or None for one
    that would land outside it."""
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or any(p in ("", ".", "..") for p in path.parts):
        return None
    if path.parts and (":" in path.parts[0] or path.parts[0] == "__MACOSX"):
        return None
    return path.parts


def unpack(data: bytes, into: Path) -> str:
    """Unpack a zip of the saved page into `into`: its one `.html` and the images
    beside it, nothing else. The page's path inside it."""
    try:
        archive = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile as error:
        raise CannotUpload("That zip can't be opened.") from error
    with archive:
        entries = [e for e in archive.infolist() if not e.is_dir()]
        if sum(e.file_size for e in entries) > MAX_UNPACKED:
            raise CannotUpload("That zip unpacks to more than 200 MB.")
        kept: list[tuple[zipfile.ZipInfo, tuple[str, ...]]] = []
        for entry in entries:
            parts = safe_parts(entry.filename)
            if parts is None:
                if entry.filename.split("/")[0] == "__MACOSX":
                    continue
                raise CannotUpload(f"The zip holds a file outside its folder: {entry.filename}")
            suffix = PurePosixPath(parts[-1]).suffix.lower()
            if suffix in PAGE_SUFFIXES or suffix in IMAGE_SUFFIXES:
                kept.append((entry, parts))
        found = [
            parts for _, parts in kept if PurePosixPath(parts[-1]).suffix.lower() in PAGE_SUFFIXES
        ]
        if not found:
            raise CannotUpload("The zip has no saved page (.html) in it.")
        if len(found) > 1:
            raise CannotUpload("The zip holds more than one page (.html); zip just the one.")
        for entry, parts in kept:
            target = into.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry) as source, target.open("wb") as out:
                shutil.copyfileobj(source, out)
        return "/".join(found[0])


def save_page(troupe_id: uuid.UUID, filename: str, data: bytes) -> Page:
    """Keep the upload as the troupe's page, replacing any before, once it reads as
    Yorick's Print Characters page."""
    folder = page_folder(troupe_id)
    if folder is None:
        raise CannotUpload("Uploads are not set up here.")
    if len(data) > MAX_UPLOAD:
        raise CannotUpload("That file is over 50 MB.")
    suffix = PurePosixPath(filename).suffix.lower()
    folder.parent.mkdir(parents=True, exist_ok=True)
    new = folder.parent / f"{troupe_id}.{uuid.uuid4()}.new"
    new.mkdir()
    try:
        if suffix == ".zip" or data[:4] == b"PK\x03\x04":
            name = unpack(data, new)
        elif suffix in PAGE_SUFFIXES:
            name = PurePosixPath(filename).name
            if safe_parts(name) is None:
                raise CannotUpload("That file's name can't be used.")
            (new / name).write_bytes(data)
        else:
            raise CannotUpload(
                "Upload the page saved from Yorick: a zip of the .html and its _files folder,"
                " or the .html alone."
            )
        try:
            printed = read_file(new / name)
        except CannotRead as error:
            raise CannotUpload(str(error)) from error
        portraits = sum(
            1 for p in printed if p.portrait and (new / name).parent.joinpath(p.portrait).is_file()
        )
        shutil.rmtree(folder, ignore_errors=True)
        new.rename(folder)
    except BaseException:
        shutil.rmtree(new, ignore_errors=True)
        raise
    return Page(name, len(printed), portraits)


def delete_page(record: YorickImport) -> None:
    """Delete the page and its report."""
    folder = page_folder(record.troupe_id)
    if folder is not None:
        shutil.rmtree(folder, ignore_errors=True)
    record.page_name = record.page_at = record.page_by = None
    clear_report(record)


def clear_report(record: YorickImport) -> None:
    record.report = record.report_text = record.report_kind = record.report_at = None
    record.report_stale = False


# --- the troupe's import --------------------------------------------------------------------


def for_troupe(db: Session, troupe: Troupe) -> YorickImport:
    """The troupe's import, made the first time it is asked for."""
    found = db.scalar(select(YorickImport).where(YorickImport.troupe_id == troupe.id))
    if found is None:
        found = YorickImport(troupe_id=troupe.id, names={}, by_hand=[], decisions={})
        db.add(found)
        db.flush()
    return found


def staff_choices(db: Session, troupe: Troupe) -> list[User]:
    """Who the NPCs may be made by: the lead, then the troupe's storytellers."""
    lead = db.get_one(User, troupe.lead_user_id)
    storytellers = db.scalars(
        select(User)
        .join(TroupeStaff, TroupeStaff.user_id == User.id)
        .where(TroupeStaff.troupe_id == troupe.id, TroupeStaff.role == "storyteller")
        .order_by(User.handle)
    )
    return [lead, *[u for u in storytellers if u.id != lead.id]]


def staff_for(db: Session, troupe: Troupe, record: YorickImport) -> User:
    """Who the NPCs are made by: the one chosen while they are still a storyteller,
    else the lead."""
    choices = staff_choices(db, troupe)
    return next((u for u in choices if u.id == record.staff_id), choices[0])


def table_for(record: YorickImport) -> Table:
    return read_table(renames=spelling_renames(), more=[record.names or {}])


def catalogue(db: Session, troupe: Troupe) -> Catalogue:
    return catalogue_for(db, troupe)


def options(db: Session, troupe: Troupe, part: str, category: str) -> list[str]:
    """What a line can be given as, in a part of the table and a category: the
    troupe's list where it keeps one, else the catalogue's names."""
    found = catalogue(db, troupe)
    if part == "values" and category in found.lists:
        return list(found.lists[category])
    names = sorted(found.names.get(category, frozenset()))
    if part == "paths":
        return [n for n in names if n.split(":")[0] in ("Thaumaturgy", "Necromancy") and ":" in n]
    if part == "values":
        return [n for n in names if n != "Custom"]
    return names


def set_name(
    record: YorickImport, part: str, category: str, yorick: str, horatio: str | None
) -> None:
    """Give a printed name Horatio's, or (`horatio` None) take it out of the table."""
    names: dict[str, Any] = {k: dict(v) for k, v in (record.names or {}).items()}
    if part == "paths":
        section: dict[str, Any] = names.setdefault("paths", {})
    else:
        section = names.setdefault(part, {}).setdefault(category, {})
        section = names[part][category] = dict(section)
    if horatio is None:
        section.pop(yorick, None)
    else:
        section[yorick] = horatio
    record.names = {k: v for k, v in names.items() if v}
    record.report_stale = record.report is not None


def entries(record: YorickImport) -> list[tuple[str, str, str, str]]:
    """The troupe's own table, as (part, category, Yorick's, Horatio's)."""
    found: list[tuple[str, str, str, str]] = []
    for part, section in (record.names or {}).items():
        if part == "paths":
            found += [("paths", "disciplines", k, v) for k, v in section.items()]
            continue
        for category, names in section.items():
            found += [(part, category, k, v) for k, v in names.items()]
    return sorted(found, key=lambda e: (e[0], e[1], e[2].casefold()))


def add_table(record: YorickImport, text: str) -> int:
    """Add a table in yorick_names.toml's shape to the troupe's: its names, values and
    paths. How many it gave."""
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise CannotUpload(f"That table can't be read: {error}") from error
    count = 0
    for part in TABLE_PARTS:
        section = raw.get(part, {})
        if not isinstance(section, Mapping):
            continue
        for key, value in section.items():
            if part == "paths" and isinstance(value, str):
                set_name(record, part, "disciplines", key, value)
                count += 1
            elif part != "paths" and isinstance(value, Mapping):
                for yorick, horatio in value.items():
                    if isinstance(horatio, str):
                        set_name(record, part, key, yorick, horatio)
                        count += 1
    return count


def set_by_hand(record: YorickImport, source: str, by_hand: bool) -> None:
    kept = [s for s in record.by_hand or [] if s != source]
    record.by_hand = [*kept, source] if by_hand else kept


def decide(
    record: YorickImport, legacy_id: str, choice: str | None, character_id: str | None
) -> None:
    decisions = dict(record.decisions or {})
    if choice is None:
        decisions.pop(legacy_id, None)
    else:
        if choice not in CHOICES:
            raise ValueError(choice)
        decisions[legacy_id] = {"choice": choice, "character_id": character_id}
    record.decisions = decisions
    record.report_stale = record.report is not None


# --- running it ---------------------------------------------------------------------------

# By troupe, the jobs running in this process and how far each has got.
_running: dict[uuid.UUID, tuple[int, int]] = {}
_lock = threading.Lock()


def open_session() -> Session:
    """A session of the job's own; tests replace this."""
    return get_sessionmaker()()


def launch(work: Callable[[], None]) -> None:
    """Run the job in the background; tests replace this to run it straight away."""
    threading.Thread(target=work, name="yorick-import", daemon=True).start()


def progress(troupe_id: uuid.UUID) -> tuple[int, int] | None:
    with _lock:
        return _running.get(troupe_id)


def check_stopped(record: YorickImport) -> bool:
    """Whether a job the record says is running was lost, as when the server restarts:
    if so it is cleared, with why."""
    if record.job is None or progress(record.troupe_id) is not None:
        return False
    kind = "import" if record.job == "import" else "dry run"
    record.error = f"The {kind} stopped when the server restarted; nothing was saved."
    record.job = record.job_at = record.job_by = None
    return True


def start(
    db: Session, user: User, troupe: Troupe, record: YorickImport, kind: str, *, backup: bool = True
) -> None:
    """Start a dry run or the import of the troupe's page in the background."""
    with _lock:
        if troupe.id in _running:
            raise Busy
        _running[troupe.id] = (0, 0)
    try:
        record.job, record.job_at, record.job_by = kind, datetime.now(UTC), user.id
        record.error = None
        db.commit()
    except BaseException:
        with _lock:
            _running.pop(troupe.id, None)
        raise
    troupe_id, user_id = troupe.id, user.id
    launch(lambda: run_job(troupe_id, user_id, kind, backup=backup))


def run_job(troupe_id: uuid.UUID, user_id: uuid.UUID, kind: str, *, backup: bool) -> None:
    try:
        with open_session() as db:
            try:
                run(db, troupe_id, user_id, kind, backup=backup)
            except Exception as error:
                log.exception("Yorick import for troupe %s", troupe_id)
                db.rollback()
                record = db.scalars(
                    select(YorickImport).where(YorickImport.troupe_id == troupe_id)
                ).one()
                record.error = str(error) or type(error).__name__
                record.job = record.job_at = record.job_by = None
                db.commit()
    finally:
        with _lock:
            _running.pop(troupe_id, None)


def run(db: Session, troupe_id: uuid.UUID, user_id: uuid.UUID, kind: str, *, backup: bool) -> None:
    record = db.scalars(select(YorickImport).where(YorickImport.troupe_id == troupe_id)).one()
    troupe = db.get_one(Troupe, troupe_id)
    user = db.get_one(User, user_id)
    dry_run = kind == "dry_run"
    path = page_path(record)
    if path is None:
        raise RuntimeError("The page has gone; upload it again.")
    printed = read_file(path)
    table = table_for(record)
    by_hand = list(record.by_hand or [])
    made_backup: str | None = None
    if not dry_run and backup:
        directory = backups.backup_dir()
        if directory is None:
            raise RuntimeError("Backups are not set up here, so none could be made first.")
        try:
            made_backup = backups.make(directory, get_settings().database_url).name
        except backups.BackupError as error:
            raise RuntimeError(f"The backup failed, so nothing was imported: {error}") from error

    def step(done: int, total: int) -> None:
        with _lock:
            _running[troupe_id] = (done, total)

    importer = Importer(
        db,
        troupe,
        staff_for(db, troupe, record),
        Mapper(table, catalogue(db, troupe)),
        path.parent,
        pictures_root=None if dry_run else pictures.upload_dir(),
        dry_run=dry_run,
        decisions=dict(record.decisions or {}),
    )
    try:
        results = importer.run(printed, step)
        failed = any(r.outcome == "failed" for r in results)
        # What the import would have done stays only in the report.
        if dry_run or failed:
            db.rollback()
            importer.undo_pictures()
        record = db.scalars(select(YorickImport).where(YorickImport.troupe_id == troupe_id)).one()
        keep_report(record, results, printed, dry_run, table, by_hand)
        record.job = record.job_at = record.job_by = None
        if failed and not dry_run:
            record.error = (
                "A character could not be imported (see the report), so nothing was saved."
            )
            audit.record(db, user, "yorick_import.failed", troupe_id=troupe_id)
        if not dry_run and not failed:
            audit.record(
                db,
                user,
                "yorick_import.imported",
                troupe_id=troupe_id,
                made=sum(r.outcome == "made" for r in results),
                updated=sum(r.outcome in ("updated", "overwritten") for r in results),
                skipped=sum(r.outcome in ("skipped", "undecided") for r in results),
                backup=made_backup or "none",
            )
        db.commit()
    except BaseException:
        db.rollback()
        importer.undo_pictures()
        raise
    if not dry_run and not failed:
        # Imported: the page goes, its report stays a while.
        folder = page_folder(troupe_id)
        if folder is not None:
            shutil.rmtree(folder, ignore_errors=True)
        record.page_name = record.page_at = record.page_by = None
        db.commit()


def keep_report(
    record: YorickImport,
    results: list[Result],
    printed: list[PrintedCharacter],
    dry_run: bool,
    table: Table,
    by_hand: list[str],
) -> None:
    record.report = {
        "summary": summary(results, dry_run, table.left_out, by_hand),
        "characters": [record_of(r) for r in results],
    }
    record.report_text = report_text(results, dry_run, table.left_out, by_hand)
    record.report_kind = "dry_run" if dry_run else "import"
    record.report_at = datetime.now(UTC)
    record.report_stale = False


# --- keeping it no longer than needed ----------------------------------------------------------


def expire_due(db: Session, now: datetime | None = None) -> int:
    """Delete pages and reports kept `KEPT_FOR`; how many imports it cleared."""
    cutoff = (now or datetime.now(UTC)) - KEPT_FOR
    cleared = 0
    due = select(YorickImport).where(
        YorickImport.job.is_(None),
        or_(YorickImport.page_at < cutoff, YorickImport.report_at < cutoff),
    )
    for record in db.scalars(due):
        changed = False
        if record.page_at is not None and record.page_at < cutoff:
            folder = page_folder(record.troupe_id)
            if folder is not None:
                shutil.rmtree(folder, ignore_errors=True)
            record.page_name = record.page_at = record.page_by = None
            changed = True
        if record.report_at is not None and record.report_at < cutoff:
            clear_report(record)
            changed = True
        if changed:
            audit.record(db, None, "yorick_import.expired", troupe_id=record.troupe_id)
            cleared += 1
    db.commit()
    return cleared


def expire_due_now() -> None:
    with get_sessionmaker()() as db:
        expire_due(db)
