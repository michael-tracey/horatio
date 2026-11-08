"""The custodian's tools (Custodian › Tools): maintenance that would otherwise need a
command on the server. Each previews what it would do before doing it, or, for
what the server fetches from elsewhere (#534), says what it has now."""

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select

from horatio import audit, dark_pack, fetching, troupe_fit, vtes_symbols
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import RuleSet, TraitCategory, TraitDefinition, Troupe, User
from horatio.permissions import require_custodian

router = APIRouter(prefix="/tools", tags=["custodian"])


class FittedNpc(BaseModel):
    id: uuid.UUID
    name: str
    # Its sheet's worth in XP at the troupe's prices, before and after fitting.
    xp_now: int
    xp_after: int
    changed: bool


class SkippedNpc(BaseModel):
    id: uuid.UUID
    name: str
    why: str


class NpcPicksFit(BaseModel):
    troupe_id: uuid.UUID
    troupe_name: str
    fitted: list[FittedNpc]
    skipped: list[SkippedNpc]
    xp_now: int
    xp_after: int
    # How many NPCs fitting moves picks on (or moved, once fitted).
    changed: int


def custodians_troupe(db: DbSession, user: User, troupe_id: uuid.UUID) -> Troupe:
    require_custodian(user)
    troupe = db.get(Troupe, troupe_id)
    if troupe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    return troupe


def out(troupe: Troupe, found: troupe_fit.TroupeFit) -> NpcPicksFit:
    return NpcPicksFit(
        troupe_id=troupe.id,
        troupe_name=troupe.name,
        fitted=[
            FittedNpc(id=f.id, name=f.name, xp_now=f.xp_now, xp_after=f.xp_after, changed=f.changed)
            for f in found.fitted
        ],
        skipped=[SkippedNpc(id=s.id, name=s.name, why=s.why) for s in found.skipped],
        xp_now=sum(f.xp_now for f in found.fitted),
        xp_after=sum(f.xp_after for f in found.fitted),
        changed=found.changed,
    )


@router.get("/npc-picks/{troupe_id}")
def preview_npc_picks(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> NpcPicksFit:
    """What fitting the troupe's NPCs' creation picks would do. Changes nothing."""
    troupe = custodians_troupe(db, user, troupe_id)
    return out(troupe, troupe_fit.fit_troupe(db, troupe, apply=False))


@router.post("/npc-picks/{troupe_id}")
def fit_npc_picks(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> NpcPicksFit:
    """Fit the creation picks of the troupe's NPCs built without the wizard, keeping
    what staff set by hand. Fitting again changes nothing."""
    troupe = custodians_troupe(db, user, troupe_id)
    done = troupe_fit.fit(db, user, troupe)
    db.commit()
    return out(troupe, done)


# --- resources the server fetches (#534) -------------------------------------------------------


class FetchJob(BaseModel):
    # What it is doing: "Downloading", "Importing", "Fetching the symbols"...
    stage: str
    done: int
    # Out of how many: bytes while downloading, files while fetching. None if unknown.
    total: int | None
    started_at: datetime
    by: str


class FetchIn(BaseModel):
    # Where to fetch from: https only.
    address: str
    # The custodian accepts Paradox's Dark Pack Agreement for this server.
    accept_licence: bool


class DarkPackTool(BaseModel):
    # Whether the server has a Dark Pack folder (HORATIO_DARK_PACK_DIR), and can
    # write to it.
    configured: bool
    writable: bool
    default_address: str
    agreement: str
    imported: bool
    imported_at: datetime | None
    # "fetched", "uploaded", or "command" (python -m horatio.dark_pack).
    how: str | None
    address: str | None
    # The zips the files came from.
    sources: list[str]
    logo: bool
    clans: list[str]
    # Clans Horatio looks for a symbol for that the import had none for.
    missing: list[str]
    job: FetchJob | None
    # Why the last fetch failed, and when.
    error: str | None
    error_at: datetime | None


class SymbolCount(BaseModel):
    # "svg", "webp" or "png".
    kind: str
    clans: int
    inferior: int
    superior: int
    icons: int


class Matched(BaseModel):
    # Horatio's name for it.
    name: str
    # KRCG's, if it was fetched; None for none.
    symbol: str | None


class LargeSymbol(BaseModel):
    path: str
    size: int


class VtesSymbolsTool(BaseModel):
    configured: bool
    writable: bool
    default_address: str
    agreement: str
    fetched: bool
    fetched_at: datetime | None
    address: str | None
    counts: list[SymbolCount]
    fonts: list[str]
    clans: list[Matched]
    disciplines: list[Matched]
    # PNGs over Discord's 256 KB for an emoji.
    large_png: list[LargeSymbol]
    job: FetchJob | None
    error: str | None
    error_at: datetime | None


def job_state(job: fetching.Job) -> tuple[FetchJob | None, str | None, datetime | None]:
    progress, error, error_at = job.state()
    out = None
    if progress is not None:
        out = FetchJob(
            stage=progress.stage,
            done=progress.done,
            total=progress.total,
            started_at=progress.started_at,
            by=progress.by,
        )
    return out, error, error_at


def can_write() -> bool:
    root = dark_pack.root()
    return root is not None and fetching.writable(root)


def dark_pack_tool() -> DarkPackTool:
    record = dark_pack.manifest()
    clans = sorted(dark_pack.clan_logos())
    running, error, error_at = job_state(dark_pack.job)
    return DarkPackTool(
        configured=dark_pack.root() is not None,
        writable=can_write(),
        default_address=dark_pack.DEFAULT_ADDRESS,
        agreement=dark_pack.AGREEMENT,
        imported=bool(record),
        imported_at=dark_pack.imported_at(record) if record else None,
        how=record.get("how", "command") if record else None,
        address=record.get("address"),
        sources=list(record.get("sources", [])),
        logo=dark_pack.has_logo(),
        clans=clans,
        missing=sorted(set(dark_pack.CLAN_SYMBOLS) - set(clans)) if record else [],
        job=running,
        error=error,
        error_at=error_at,
    )


def vampire_names(db: DbSession, key: str) -> list[str]:
    """Horatio's clans and bloodlines, or disciplines, in the vampire rules."""
    return list(
        db.scalars(
            select(TraitDefinition.name)
            .join(TraitCategory, TraitCategory.id == TraitDefinition.category_id)
            .join(RuleSet, RuleSet.id == TraitCategory.rule_set_id)
            .where(
                RuleSet.splat == "vampire",
                TraitCategory.key == key,
                TraitDefinition.retired.is_(False),
            )
            .distinct()
        )
    )


def vtes_symbols_tool(db: DbSession) -> VtesSymbolsTool:
    record = vtes_symbols.manifest()
    files: dict[str, list[str]] = record.get("files", {})
    running, error, error_at = job_state(vtes_symbols.job)
    clans = vtes_symbols.symbols(record, "clan")
    inferior = vtes_symbols.symbols(record, "disc/inf")
    disciplines = sorted({vtes_symbols.discipline_of(n) for n in vampire_names(db, "disciplines")})
    fetched_at = record.get("fetched_at")
    return VtesSymbolsTool(
        configured=dark_pack.root() is not None,
        writable=can_write(),
        default_address=vtes_symbols.DEFAULT_ADDRESS,
        agreement=dark_pack.AGREEMENT,
        fetched=bool(record),
        fetched_at=datetime.fromisoformat(fetched_at) if fetched_at else None,
        address=record.get("address"),
        counts=[
            SymbolCount(
                kind=kind,
                clans=len(files.get(f"{kind}/clan", [])),
                inferior=len(files.get(f"{kind}/disc/inf", [])),
                superior=len(files.get(f"{kind}/disc/sup", [])),
                icons=len(files.get(f"{kind}/icon", [])),
            )
            for kind in vtes_symbols.KINDS
        ]
        if record
        else [],
        fonts=list(record.get("fonts", [])),
        clans=[
            Matched(name=n, symbol=s)
            for n, s in vtes_symbols.matched(
                sorted(vampire_names(db, "clan")), vtes_symbols.CLANS, clans
            )
        ],
        disciplines=[
            Matched(name=n, symbol=s)
            for n, s in vtes_symbols.matched(disciplines, vtes_symbols.DISCIPLINES, inferior)
        ],
        large_png=[
            LargeSymbol(path=p, size=n) for p, n in sorted(record.get("large_png", {}).items())
        ],
        job=running,
        error=error,
        error_at=error_at,
    )


def started(start: Callable[[], None]) -> None:
    """Start a fetch, saying why not if it can't."""
    try:
        start()
    except fetching.Busy:
        raise HTTPException(status.HTTP_409_CONFLICT, "A fetch is under way already.") from None
    except fetching.Failed as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    except OSError as error:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, fetching.message(error)
        ) from None


def accepted(licence: bool) -> None:
    if not licence:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Accept Paradox's Dark Pack Agreement for this server first.",
        )


@router.get("/dark-pack")
def dark_pack_status(user: CurrentUser) -> DarkPackTool:
    """The Dark Pack resources on the server, and any fetch under way."""
    require_custodian(user)
    return dark_pack_tool()


@router.post("/dark-pack/fetch", status_code=status.HTTP_202_ACCEPTED)
def fetch_dark_pack(body: FetchIn, user: CurrentUser) -> DarkPackTool:
    """Fetch Paradox's kit from the address and import it, in the background. What
    was imported before stays until the new import is whole."""
    require_custodian(user)
    accepted(body.accept_licence)
    started(lambda: dark_pack.fetch(user, body.address))
    return dark_pack_tool()


@router.post("/dark-pack/upload")
def upload_dark_pack(
    db: DbSession,
    user: CurrentUser,
    file: Annotated[UploadFile, File(description="The Dark Pack folder an import wrote, zipped.")],
    accept_licence: Annotated[bool, Form()] = False,
) -> DarkPackTool:
    """Put in place what `python -m horatio.dark_pack` wrote on another computer."""
    require_custodian(user)
    accepted(accept_licence)
    data = file.file.read(dark_pack.MAX_RESULT + 1)
    found: dict[str, object] = {}
    started(lambda: found.update(dark_pack.install_result(user, file.filename or "", data)))
    audit.record(db, user, "dark_pack.uploaded", **dark_pack.counts(found))
    db.commit()
    return dark_pack_tool()


@router.delete("/dark-pack")
def remove_dark_pack(db: DbSession, user: CurrentUser) -> DarkPackTool:
    """Take the Dark Pack resources off the server. The VTES symbols stay."""
    require_custodian(user)
    started(lambda: dark_pack.remove(user))
    audit.record(db, user, "dark_pack.removed")
    db.commit()
    return dark_pack_tool()


@router.get("/vtes-symbols")
def vtes_symbols_status(db: DbSession, user: CurrentUser) -> VtesSymbolsTool:
    """The VTES symbols on the server, and any fetch under way."""
    require_custodian(user)
    return vtes_symbols_tool(db)


@router.post("/vtes-symbols/fetch", status_code=status.HTTP_202_ACCEPTED)
def fetch_vtes_symbols(body: FetchIn, db: DbSession, user: CurrentUser) -> VtesSymbolsTool:
    """Fetch the symbols and fonts from the address (KRCG's), in the background,
    replacing the last fetch once this one is whole."""
    require_custodian(user)
    accepted(body.accept_licence)
    started(lambda: vtes_symbols.fetch(user, body.address))
    return vtes_symbols_tool(db)


@router.delete("/vtes-symbols")
def remove_vtes_symbols(db: DbSession, user: CurrentUser) -> VtesSymbolsTool:
    """Take the VTES symbols off the server."""
    require_custodian(user)
    started(lambda: vtes_symbols.remove(user))
    audit.record(db, user, "vtes_symbols.removed")
    db.commit()
    return vtes_symbols_tool(db)
