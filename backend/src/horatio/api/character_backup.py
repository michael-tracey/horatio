"""Character backups (horatio.character_backup, issue #567): a player exports one
character, or all of theirs, and imports one as a new character; a troupe's running
staff export its characters and NPCs together.

One character is a `<name>.horatio-character.json`, with its printable sheet as an
HTML file to download beside it. Several are a .zip: a `manifest.json` saying what is
in it, a JSON file for each under `characters/` (player characters) or `npcs/`, its
picture under `pictures/` and its printable sheet under `sheets/`."""

import base64
import json
import uuid
from datetime import date
from io import BytesIO
from typing import Annotated, Literal
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field, JsonValue
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from horatio import character_backup as backup
from horatio import pictures
from horatio.api.characters import running_troupe_id
from horatio.api.downtimes import staff_troupe
from horatio.api.printing import print_sheet
from horatio.api.sheet_html import sheet_html
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, RuleSet, Troupe, TroupeMembership, User
from horatio.permissions import (
    TroupeAction,
    allows,
    can_edit_character,
    troupe_role,
    visible_character,
)

router = APIRouter(tags=["character backup"])

MANIFEST = "horatio-character-backup"
MANIFEST_VERSION = 1


async def capped(request: Request) -> None:
    """Refuse a document over the size cap before reading it."""
    if len(await request.body()) > backup.MAX_BYTES:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, "That file is too large to be a Horatio character."
        )


def exportable(db: Session, user: User, character_id: uuid.UUID) -> Character:
    """A character `user` may back up: their own, retired ones too; an NPC, its
    troupe's running staff; any, the custodian."""
    character = visible_character(db, user, character_id)
    if not (user.is_custodian or can_edit_character(db, user, character)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the character's player can export it.")
    return character


Sections = Annotated[list[backup.Section] | None, Query()]


@router.get("/characters/{character_id}/backup")
def export_character(
    character_id: uuid.UUID, db: DbSession, user: CurrentUser, sections: Sections = None
) -> backup.CharacterDocument:
    """The character as a file, its picture in it, with the optional `sections` chosen.
    Its player exports it, retired, killed or departed too."""
    character = exportable(db, user, character_id)
    return backup.export(db, character, sections or [], root=pictures.upload_dir())


def attachment(content: bytes | str, media_type: str, name: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/characters/{character_id}/backup/sheet", response_class=Response)
def export_sheet(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Response:
    """The character's printable sheet as one HTML file, readable without Horatio."""
    character = exportable(db, user, character_id)
    picture = None
    root = pictures.upload_dir()
    if root is not None and character.picture_id is not None:
        path = pictures.picture_file(root, character.id, character.picture_id, "128.webp")
        if path is not None:
            picture = "data:image/webp;base64," + base64.b64encode(path.read_bytes()).decode()
    page = sheet_html(print_sheet(db, character, None), picture, date.today().isoformat())
    return attachment(page, "text/html; charset=utf-8", backup.slug(character.name) + ".html")


# --- several at once ----------------------------------------------------------------------


class ManifestEntry(BaseModel):
    name: str
    kind: str
    file: str
    sheet: str
    picture: str | None
    # A player character's player, by handle.
    player: str | None


class Manifest(BaseModel):
    """What a .zip of characters holds."""

    format: Literal["horatio-character-backup"] = MANIFEST
    version: Literal[1] = MANIFEST_VERSION
    horatio: str
    rule_sets: dict[str, int]
    # The troupe they are from, for a troupe's export; empty for a player's own.
    troupe: str
    exported_on: date
    sections: list[backup.Section]
    # Whether players' emails are in it, beside their handles.
    emails: bool
    characters: list[ManifestEntry]


def unique(name: str, used: set[str]) -> str:
    found, n = name, 1
    while found in used:
        n += 1
        found = f"{name}-{n}"
    used.add(found)
    return found


def zipped(
    db: Session,
    characters: list[tuple[Character, backup.BackupPlayer | None]],
    sections: list[backup.Section],
    troupe: Troupe | None,
    *,
    emails: bool = False,
) -> bytes:
    root = pictures.upload_dir()
    today = date.today()
    used: set[str] = set()
    entries: list[ManifestEntry] = []
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for character, player in characters:
            name = unique(backup.slug(character.name), used)
            folder = "npcs" if character.kind == "npc" else "characters"
            document = backup.export(
                db,
                character,
                sections,
                root=root,
                picture_file=f"pictures/{name}.webp",
                player=player,
            )
            picture = document.picture.file if document.picture else None
            if picture is not None and root is not None and character.picture_id is not None:
                path = pictures.picture_file(root, character.id, character.picture_id, "full.webp")
                if path is not None:
                    archive.write(path, picture)
            file = f"{folder}/{name}{backup.SUFFIX}"
            archive.writestr(file, document.model_dump_json(indent=2))
            sheet = f"sheets/{name}.html"
            printed = print_sheet(db, character, troupe.id if troupe else None)
            archive.writestr(
                sheet, sheet_html(printed, f"../{picture}" if picture else None, today.isoformat())
            )
            entries.append(
                ManifestEntry(
                    name=character.name,
                    kind=character.kind,
                    file=file,
                    sheet=sheet,
                    picture=picture,
                    player=player.handle if player else None,
                )
            )
        splats = {c.splat for c, _ in characters}
        manifest = Manifest(
            horatio=backup.horatio_version(),
            rule_sets={
                splat: number
                for splat, number in db.execute(
                    select(RuleSet.splat, RuleSet.version)
                    .where(RuleSet.splat.in_(splats))
                    .order_by(RuleSet.splat)
                )
            },
            troupe=troupe.name if troupe else "",
            exported_on=today,
            sections=sections,
            emails=emails,
            characters=entries,
        )
        archive.writestr("manifest.json", json.dumps(manifest.model_dump(mode="json"), indent=2))
    return buffer.getvalue()


@router.get("/character-backups", response_class=Response)
def export_mine(db: DbSession, user: CurrentUser, sections: Sections = None) -> Response:
    """Every character the player has, retired ones too, in one .zip."""
    found = db.scalars(
        select(Character)
        .where(Character.player_id == user.id, Character.kind == "pc")
        .order_by(Character.name, Character.id)
    )
    content = zipped(db, [(c, None) for c in found], sections or [], None)
    return attachment(content, "application/zip", f"horatio-characters-{date.today()}.zip")


Which = Literal["all", "pcs", "npcs"]


@router.get("/troupes/{troupe_id}/character-backups", response_class=Response)
def export_troupe(
    troupe_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    which: Which = "all",
    characters: Annotated[list[uuid.UUID] | None, Query()] = None,
    sections: Sections = None,
    emails: bool = False,
) -> Response:
    """The troupe's own characters in one .zip: those at home here and its NPCs (not
    visitors, whose home troupe holds them), all, player characters or NPCs only, or
    those named in `characters`. Each player character names its player by handle,
    and by email too with `emails`, which only storytellers may ask for."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS)
    if emails and not allows(
        troupe_role(db, user, troupe), TroupeAction.GIVE_NPCS, is_custodian=user.is_custodian
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the troupe's storytellers can export players' emails."
        )
    query = (
        select(Character, User)
        .join(TroupeMembership, TroupeMembership.character_id == Character.id)
        .join(User, User.id == Character.player_id)
        .where(
            TroupeMembership.troupe_id == troupe.id,
            TroupeMembership.left_at.is_(None),
            or_(Character.home_troupe_id == troupe.id, Character.owner_troupe_id == troupe.id),
        )
        .order_by(Character.kind, Character.name, Character.id)
    )
    if which != "all":
        query = query.where(Character.kind == ("pc" if which == "pcs" else "npc"))
    rows = list(db.execute(query))
    if characters is not None:
        wanted = set(characters)
        rows = [(c, u) for c, u in rows if c.id in wanted]
        if len(rows) != len(wanted):
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Not all of those characters are this troupe's own."
            )
    found = [
        (
            c,
            backup.BackupPlayer(
                handle=u.handle, name=u.display_name, email=u.email if emails else None
            )
            if c.kind == "pc"
            else None,
        )
        for c, u in rows
    ]
    content = zipped(db, found, sections or [], troupe, emails=emails)
    return attachment(
        content, "application/zip", f"{backup.slug(troupe.name)}-characters-{date.today()}.zip"
    )


# --- importing ----------------------------------------------------------------------------


class CharacterImportIn(BaseModel):
    # The file's contents, as it was read: checked here, not by the client.
    document: dict[str, JsonValue]
    # The troupe to build it for; None for the plain rule set.
    troupe_id: uuid.UUID | None = None
    file_name: str | None = Field(default=None, max_length=200)


class BackupItemOut(BaseModel):
    label: str
    # new | differs (held otherwise here: `before` in the file, `after` here) |
    # cannot (left out: `reason` says why) | info (shown, never imported).
    status: backup.Status
    reason: str | None
    before: str | None
    after: str | None


class BackupPartOut(BaseModel):
    key: backup.Part
    label: str
    items: list[BackupItemOut]


class BackupXpOut(BaseModel):
    # The file's XP history: earned, spent, lost and unspent.
    earned: int
    spent: int
    lost: int
    unspent: int
    # What the sheet's paid dots cost where it came from, and at the prices it plays
    # by here; and traits those prices don't cover.
    sheet_there: int
    sheet_here: int
    unpriced: list[str]
    # What comes in as self-entered XP, for its home troupe to keep or remove.
    self_entered: int


class CharacterReviewOut(BaseModel):
    name: str
    splat: str
    # Where the file came from, and when, as it says.
    from_troupe: str
    exported_on: date | None
    horatio: str
    # The troupe it would be built for here; None for the plain rule set.
    troupe: str | None
    parts: list[BackupPartOut]
    xp: BackupXpOut | None
    warnings: list[str]


class CharacterImportOut(BaseModel):
    character_id: uuid.UUID
    name: str
    # Parts left out, as the review said.
    left_out: int


def building_troupe(
    db: Session, document: backup.CharacterDocument, body: CharacterImportIn
) -> Troupe | None:
    """The troupe to build for, if it is running and takes the character's splat."""
    found = running_troupe_id(db, body.troupe_id, document.character.splat)
    return db.get_one(Troupe, found) if found else None


def review_out(
    document: backup.CharacterDocument, troupe: Troupe | None, found: backup.Imported
) -> CharacterReviewOut:
    xp = found.xp
    return CharacterReviewOut(
        name=document.character.name,
        splat=document.character.splat,
        from_troupe=document.troupe,
        exported_on=document.exported_on,
        horatio=document.horatio,
        troupe=troupe.name if troupe else None,
        parts=[
            BackupPartOut(
                key=key,
                label=label,
                items=[
                    BackupItemOut(
                        label=i.label,
                        status=i.status,
                        reason=i.reason,
                        before=i.before,
                        after=i.after,
                    )
                    for i in found.items
                    if i.part == key
                ],
            )
            for key, label in backup.PARTS.items()
            if any(i.part == key for i in found.items)
        ],
        xp=BackupXpOut(
            earned=xp.earned,
            spent=xp.spent,
            lost=xp.lost,
            unspent=xp.unspent,
            sheet_there=xp.sheet_there,
            sheet_here=xp.sheet_here,
            unpriced=xp.unpriced,
            self_entered=found.self_entered,
        )
        if xp is not None and document.xp
        else None,
        warnings=found.warnings,
    )


@router.post("/characters/import/review", dependencies=[Depends(capped)])
def review_import(body: CharacterImportIn, db: DbSession, user: CurrentUser) -> CharacterReviewOut:
    """What importing the file as a new character would do, part by part: new, held
    otherwise here (a merit at this troupe's value), left out with why, or shown only;
    and its XP, as the file has it and at the prices it would play by here. Nothing is
    saved."""
    document = backup.read(body.document)
    troupe = building_troupe(db, document, body)
    found = backup.review(db, user, document, troupe, root=pictures.upload_dir())
    return review_out(document, troupe, found)


@router.post(
    "/characters/import", status_code=status.HTTP_201_CREATED, dependencies=[Depends(capped)]
)
def import_character(
    body: CharacterImportIn, db: DbSession, user: CurrentUser
) -> CharacterImportOut:
    """Import the file as a new character of the player's, in their vault, built for
    the troupe chosen: all its parts that can come in, as the review showed, in one
    transaction. It isn't in any troupe yet; its player asks one to make it home."""
    document = backup.read(body.document)
    troupe = building_troupe(db, document, body)
    found = backup.import_character(db, user, document, troupe, root=pictures.upload_dir())
    try:
        db.commit()
    except BaseException:
        for directory in found.written:
            pictures.remove(directory)
        raise
    return CharacterImportOut(
        character_id=found.character.id,
        name=found.character.name,
        left_out=sum(1 for i in found.items if i.status == "cannot"),
    )
