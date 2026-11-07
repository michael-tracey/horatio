"""The custodian's import from Yorick (horatio.yorick_imports): upload a troupe's Print
Characters page, check it with a dry run, give unmatched lines their names, choose what
to do with characters already here under a printed name, and import it."""

import json
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import backups, yorick_imports
from horatio.audit import record
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Troupe, User, YorickImport
from horatio.permissions import require_custodian
from horatio.yorick_imports import KEPT_FOR, TABLE_PARTS, Busy, CannotUpload

router = APIRouter(prefix="/yorick-imports", tags=["yorick imports"])

Part = Literal["names", "values", "paths"]
Choice = Literal["overwrite", "skip", "new"]


class StaffChoiceOut(BaseModel):
    id: uuid.UUID
    handle: str
    display_name: str
    lead: bool


class PageOut(BaseModel):
    # The page's file, inside what was uploaded.
    name: str
    uploaded_at: datetime
    uploaded_by: str | None
    # When it is deleted, if it has not been imported by then.
    expires_at: datetime


class JobOut(BaseModel):
    kind: Literal["dry_run", "import"]
    started_at: datetime
    # Characters done of the page's, once it has started on them.
    done: int
    total: int


class NameOut(BaseModel):
    part: Part
    category: str
    yorick: str
    horatio: str


class DecisionOut(BaseModel):
    legacy_id: str
    choice: Choice
    character_id: str | None


class YorickImportOut(BaseModel):
    troupe_id: uuid.UUID
    troupe_name: str
    # False where uploads are not set up (HORATIO_UPLOAD_DIR): nothing can be uploaded.
    uploads_available: bool
    # False where backups are not set up (HORATIO_BACKUP_DIR): an import then needs
    # the custodian to say to go ahead without one.
    backups_available: bool
    staff: list[StaffChoiceOut]
    # Who the NPCs are made by.
    staff_id: uuid.UUID
    page: PageOut | None
    job: JobOut | None
    # Why the last dry run or import stopped short.
    error: str | None
    report_kind: Literal["dry_run", "import"] | None
    report_at: datetime | None
    # Names or choices have changed since the report: run the dry run again.
    report_stale: bool
    report_expires_at: datetime | None
    # Printed characters waiting for a choice, by the report.
    undecided: int
    names: list[NameOut]
    by_hand: list[str]
    decisions: list[DecisionOut]
    # Why it can't be imported now, if it can't.
    cannot_import: str | None


class ImportSummaryOut(BaseModel):
    troupe_id: uuid.UUID
    troupe_name: str
    page_at: datetime | None
    report_kind: Literal["dry_run", "import"] | None
    report_at: datetime | None
    running: bool


class MatchOut(BaseModel):
    character_id: str
    name: str
    whose: str
    overwritable: bool


class UnmatchedOut(BaseModel):
    heading: str
    text: str
    reason: str
    # "Merits: Arcane (1)": what marks it to be put right by hand.
    source: str
    # Where in the table a name would match it, if anywhere.
    part: Part | None
    category: str
    key: str


class ReportCharacterOut(BaseModel):
    legacy_id: str
    name: str
    label: str
    outcome: Literal["made", "updated", "overwritten", "skipped", "undecided", "failed"]
    skipped_because: str
    character_id: str | None
    matches: list[MatchOut]
    choice: Choice | None
    unmatched: list[UnmatchedOut]
    # "Faction: Loyalist: Only a Sabbat character has a Faction."
    refused: list[str]
    revalued: list[str]
    problems: list[str]
    unpriced: list[str]
    left_out: list[str]
    split: list[str]
    traits: int
    xp: int
    portrait: str


class ReportOut(BaseModel):
    kind: Literal["dry_run", "import"]
    at: datetime
    stale: bool
    summary: list[str]
    characters: list[ReportCharacterOut]


class StaffIn(BaseModel):
    user_id: uuid.UUID


class NameIn(BaseModel):
    part: Part
    category: str
    yorick: str
    # Horatio's name; None takes the line out of the troupe's table.
    horatio: str | None


class ByHandIn(BaseModel):
    source: str
    by_hand: bool


class DecisionIn(BaseModel):
    # None takes the choice back.
    choice: Choice | None
    character_id: str | None = None


class ImportIn(BaseModel):
    # Where backups are not set up: go ahead without one.
    without_backup: bool = False


class TableAddedOut(BaseModel):
    added: int


# --- reading ----------------------------------------------------------------------------


def troupe_of(db: Session, user: User, troupe_id: uuid.UUID) -> Troupe:
    require_custodian(user)
    troupe = db.get(Troupe, troupe_id)
    if troupe is None or troupe.archived_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    return troupe


def import_of(db: Session, user: User, troupe_id: uuid.UUID) -> tuple[Troupe, YorickImport]:
    troupe = troupe_of(db, user, troupe_id)
    kept = yorick_imports.for_troupe(db, troupe)
    if yorick_imports.check_stopped(kept):
        db.commit()
    return troupe, kept


def report_of(kept: YorickImport) -> dict[str, Any]:
    return kept.report or {"summary": [], "characters": []}


def undecided(kept: YorickImport) -> int:
    return sum(c["outcome"] == "undecided" for c in report_of(kept)["characters"])


def cannot_import(kept: YorickImport) -> str | None:
    if kept.job is not None:
        return "A dry run or import is running."
    if kept.page_name is None:
        return "Upload the page first."
    if kept.report is None or kept.report_kind != "dry_run":
        return "Run the dry run first."
    if kept.report_stale:
        return "Names or choices have changed since the dry run: run it again first."
    waiting = undecided(kept)
    if waiting:
        return (
            f"{waiting} printed character{'s' if waiting != 1 else ''} share a name with a"
            " character here: choose what to do with each first."
        )
    return None


def out(db: Session, troupe: Troupe, kept: YorickImport) -> YorickImportOut:
    lead = troupe.lead_user_id
    staff = yorick_imports.staff_choices(db, troupe)
    page = None
    if kept.page_name is not None and kept.page_at is not None:
        by = db.get(User, kept.page_by) if kept.page_by else None
        page = PageOut(
            name=kept.page_name,
            uploaded_at=kept.page_at,
            uploaded_by=by.handle if by else None,
            expires_at=kept.page_at + KEPT_FOR,
        )
    job = None
    if kept.job is not None and kept.job_at is not None:
        done, total = yorick_imports.progress(troupe.id) or (0, 0)
        job = JobOut(kind=kept.job, started_at=kept.job_at, done=done, total=total)  # type: ignore[arg-type]
    return YorickImportOut(
        troupe_id=troupe.id,
        troupe_name=troupe.name,
        uploads_available=yorick_imports.root() is not None,
        backups_available=backups.backup_dir() is not None,
        staff=[
            StaffChoiceOut(id=u.id, handle=u.handle, display_name=u.display_name, lead=u.id == lead)
            for u in staff
        ],
        staff_id=yorick_imports.staff_for(db, troupe, kept).id,
        page=page,
        job=job,
        error=kept.error,
        report_kind=kept.report_kind,  # type: ignore[arg-type]
        report_at=kept.report_at,
        report_stale=kept.report_stale,
        report_expires_at=kept.report_at + KEPT_FOR if kept.report_at else None,
        undecided=undecided(kept),
        names=[
            NameOut(part=p, category=c, yorick=y, horatio=h)  # type: ignore[arg-type]
            for p, c, y, h in yorick_imports.entries(kept)
        ],
        by_hand=list(kept.by_hand or []),
        decisions=[
            DecisionOut(legacy_id=k, choice=v["choice"], character_id=v.get("character_id"))
            for k, v in sorted((kept.decisions or {}).items())
        ],
        cannot_import=cannot_import(kept),
    )


def character_out(c: dict[str, Any]) -> ReportCharacterOut:
    printed = c["printed"]
    return ReportCharacterOut(
        legacy_id=printed["legacy_id"],
        name=printed["name"],
        label=printed.get("label") or "",
        outcome=c["outcome"],
        skipped_because=c.get("skipped_because") or "",
        character_id=c.get("character_id"),
        matches=[
            MatchOut(
                character_id=m["character_id"],
                name=m["name"],
                whose=m["whose"],
                overwritable=m["overwritable"],
            )
            for m in c.get("matches", [])
        ],
        choice=c.get("choice"),
        unmatched=[
            UnmatchedOut(
                heading=u["heading"],
                text=u["text"],
                reason=u["reason"],
                source=f"{u['heading']}: {u['text']}",
                part=u.get("table") or None,
                category=u.get("category", ""),
                key=u.get("key", ""),
            )
            for u in c.get("unmatched", [])
        ],
        refused=[f"{source}: {why}" for source, why in c.get("refused", [])],
        revalued=[f"{n}: printed {was}, held at {now}" for n, was, now in c.get("revalued", [])],
        problems=c.get("problems", []),
        unpriced=[f"{n}: {why}" for n, why in c.get("unpriced", [])],
        left_out=c.get("left_out", []),
        split=c.get("split", []),
        traits=len(c.get("traits", [])) - len(c.get("refused", [])),
        xp=c.get("xp", 0),
        portrait=c.get("portrait", "none"),
    )


@router.get("")
def list_imports(db: DbSession, user: CurrentUser) -> list[ImportSummaryOut]:
    """The troupes with an import under way: a page or a report kept."""
    require_custodian(user)
    rows = db.execute(
        select(YorickImport, Troupe)
        .join(Troupe, Troupe.id == YorickImport.troupe_id)
        .where(
            Troupe.archived_at.is_(None),
            (YorickImport.page_name.is_not(None)) | (YorickImport.report_at.is_not(None)),
        )
        .order_by(Troupe.name)
    )
    return [
        ImportSummaryOut(
            troupe_id=troupe.id,
            troupe_name=troupe.name,
            page_at=kept.page_at,
            report_kind=kept.report_kind,  # type: ignore[arg-type]
            report_at=kept.report_at,
            running=kept.job is not None,
        )
        for kept, troupe in rows
    ]


@router.get("/{troupe_id}")
def get_import(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> YorickImportOut:
    troupe, kept = import_of(db, user, troupe_id)
    db.commit()
    return out(db, troupe, kept)


@router.get("/{troupe_id}/report")
def get_report(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> ReportOut:
    _, kept = import_of(db, user, troupe_id)
    if kept.report is None or kept.report_at is None or kept.report_kind is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no report yet.")
    db.commit()
    return ReportOut(
        kind=kept.report_kind,  # type: ignore[arg-type]
        at=kept.report_at,
        stale=kept.report_stale,
        summary=kept.report["summary"],
        characters=[character_out(c) for c in kept.report["characters"]],
    )


@router.get("/{troupe_id}/report.txt", response_class=Response)
def download_report(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Response:
    troupe, kept = import_of(db, user, troupe_id)
    if kept.report_text is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no report yet.")
    record(db, user, "yorick_import.downloaded", troupe_id=troupe.id, file="report.txt")
    db.commit()
    return Response(
        kept.report_text,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="report.txt"'},
    )


@router.get("/{troupe_id}/characters.json", response_class=Response)
def download_characters(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Response:
    troupe, kept = import_of(db, user, troupe_id)
    if kept.report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no report yet.")
    record(db, user, "yorick_import.downloaded", troupe_id=troupe.id, file="characters.json")
    db.commit()
    return Response(
        json.dumps(kept.report["characters"], indent=2, ensure_ascii=False) + "\n",
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="characters.json"'},
    )


@router.get("/{troupe_id}/options")
def get_options(
    troupe_id: uuid.UUID, part: Part, category: str, db: DbSession, user: CurrentUser
) -> list[str]:
    """What a printed line can be given as, for Match to..."""
    troupe = troupe_of(db, user, troupe_id)
    return yorick_imports.options(db, troupe, part, category)


# --- changing ---------------------------------------------------------------------------


def not_running(kept: YorickImport) -> None:
    if kept.job is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A dry run or import is running; wait for it to finish."
        )


def begin(
    db: Session, user: User, troupe: Troupe, kept: YorickImport, kind: str, *, backup: bool = True
) -> None:
    try:
        yorick_imports.start(db, user, troupe, kept, kind, backup=backup)
    except Busy:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A dry run or import is running; wait for it to finish."
        ) from None
    db.expire_all()


@router.post("/{troupe_id}/page")
def upload_page(
    troupe_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    file: Annotated[
        UploadFile,
        File(
            description="The page saved from Yorick: a zip of it with its _files folder,"
            " or the .html alone."
        ),
    ],
) -> YorickImportOut:
    """Keep the page, replacing any before, and start a dry run of it."""
    troupe, kept = import_of(db, user, troupe_id)
    not_running(kept)
    data = file.file.read(yorick_imports.MAX_UPLOAD + 1)
    try:
        page = yorick_imports.save_page(troupe.id, file.filename or "", data)
    except CannotUpload as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    kept.page_name, kept.page_at, kept.page_by = page.name, datetime.now(UTC), user.id
    yorick_imports.clear_report(kept)
    record(
        db,
        user,
        "yorick_import.uploaded",
        troupe_id=troupe.id,
        characters=page.characters,
        portraits=page.portraits,
    )
    db.commit()
    begin(db, user, troupe, kept, "dry_run")
    _, kept = import_of(db, user, troupe_id)
    return out(db, troupe, kept)


@router.delete("/{troupe_id}/page")
def delete_page(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> YorickImportOut:
    """Delete the page and its report. The troupe's names and choices stay."""
    troupe, kept = import_of(db, user, troupe_id)
    not_running(kept)
    yorick_imports.delete_page(kept)
    kept.error = None
    record(db, user, "yorick_import.deleted", troupe_id=troupe.id)
    db.commit()
    return out(db, troupe, kept)


@router.post("/{troupe_id}/dry-run")
def dry_run(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> YorickImportOut:
    troupe, kept = import_of(db, user, troupe_id)
    not_running(kept)
    if kept.page_name is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Upload the page first.")
    begin(db, user, troupe, kept, "dry_run")
    _, kept = import_of(db, user, troupe_id)
    return out(db, troupe, kept)


@router.post("/{troupe_id}/import")
def run_import(
    troupe_id: uuid.UUID, body: ImportIn, db: DbSession, user: CurrentUser
) -> YorickImportOut:
    """Import the page for real: a backup first, then every character in one go."""
    troupe, kept = import_of(db, user, troupe_id)
    why = cannot_import(kept)
    if why is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, why)
    backup = backups.backup_dir() is not None
    if not backup and not body.without_backup:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Backups are not set up here, so none can be made first: say to go ahead without one.",
        )
    begin(db, user, troupe, kept, "import", backup=backup)
    _, kept = import_of(db, user, troupe_id)
    return out(db, troupe, kept)


@router.put("/{troupe_id}/staff")
def set_staff(
    troupe_id: uuid.UUID, body: StaffIn, db: DbSession, user: CurrentUser
) -> YorickImportOut:
    """Who the NPCs are made by: the lead or one of the troupe's storytellers."""
    troupe, kept = import_of(db, user, troupe_id)
    not_running(kept)
    choices = yorick_imports.staff_choices(db, troupe)
    chosen = next((u for u in choices if u.id == body.user_id), None)
    if chosen is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Only the troupe's lead or one of its storytellers can make its NPCs.",
        )
    kept.staff_id = None if chosen.id == troupe.lead_user_id else chosen.id
    record(db, user, "yorick_import.staff", troupe_id=troupe.id, handle=chosen.handle)
    db.commit()
    return out(db, troupe, kept)


@router.put("/{troupe_id}/names")
def set_name(
    troupe_id: uuid.UUID, body: NameIn, db: DbSession, user: CurrentUser
) -> YorickImportOut:
    """Give a printed name Horatio's in the troupe's own table, or take it out."""
    troupe, kept = import_of(db, user, troupe_id)
    not_running(kept)
    if body.part not in TABLE_PARTS or not body.yorick.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Say which printed name.")
    if body.horatio is not None and body.horatio not in yorick_imports.options(
        db, troupe, body.part, body.category
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"{body.horatio} isn't one of the choices here."
        )
    yorick_imports.set_name(kept, body.part, body.category, body.yorick.strip(), body.horatio)
    record(
        db,
        user,
        "yorick_import.named" if body.horatio is not None else "yorick_import.unnamed",
        troupe_id=troupe.id,
        yorick=body.yorick.strip(),
        horatio=body.horatio or "",
    )
    db.commit()
    return out(db, troupe, kept)


@router.post("/{troupe_id}/names/file")
def add_table(
    troupe_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    file: Annotated[UploadFile, File(description="A table in yorick_names.toml's shape.")],
) -> TableAddedOut:
    """Add a table written for the command line import to the troupe's own."""
    troupe, kept = import_of(db, user, troupe_id)
    not_running(kept)
    try:
        text = file.file.read(1024 * 1024 + 1).decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "That table isn't text (UTF-8)."
        ) from None
    try:
        added = yorick_imports.add_table(kept, text)
    except CannotUpload as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    record(db, user, "yorick_import.table_added", troupe_id=troupe.id, count=added)
    db.commit()
    return TableAddedOut(added=added)


@router.put("/{troupe_id}/by-hand")
def set_by_hand(
    troupe_id: uuid.UUID, body: ByHandIn, db: DbSession, user: CurrentUser
) -> YorickImportOut:
    """Mark a printed line for staff to put right by hand, or take the mark off."""
    troupe, kept = import_of(db, user, troupe_id)
    not_running(kept)
    yorick_imports.set_by_hand(kept, body.source, body.by_hand)
    db.commit()
    return out(db, troupe, kept)


@router.put("/{troupe_id}/decisions/{legacy_id}")
def decide(
    troupe_id: uuid.UUID, legacy_id: str, body: DecisionIn, db: DbSession, user: CurrentUser
) -> YorickImportOut:
    """What to do with a printed character whose name a character here has."""
    troupe, kept = import_of(db, user, troupe_id)
    not_running(kept)
    printed = next(
        (c for c in report_of(kept)["characters"] if c["printed"]["legacy_id"] == legacy_id), None
    )
    if body.choice is not None and (printed is None or not printed.get("matches")):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No printed character in the report shares a name here."
        )
    character_id = None
    if body.choice == "overwrite":
        assert printed is not None
        match = next(
            (m for m in printed["matches"] if m["character_id"] == body.character_id), None
        )
        if match is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose which character to overwrite."
            )
        if not match["overwritable"]:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Only a sheeted NPC of the troupe can be overwritten. A player's character"
                " changes through the troupe's approvals, and a Stock NPC has no sheet.",
            )
        character_id = match["character_id"]
    yorick_imports.decide(kept, legacy_id, body.choice, character_id)
    record(
        db,
        user,
        "yorick_import.decided",
        troupe_id=troupe.id,
        name=printed["printed"]["name"] if printed else legacy_id,
        choice=body.choice or "none",
    )
    db.commit()
    return out(db, troupe, kept)
