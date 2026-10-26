"""Clan logos for badges, which the custodian uploads: one per clan or bloodline,
images the troupe has the right to use. The official symbols belong to the
game's publisher and cannot ship with Horatio, but a server's operator can
import them from Paradox's Dark Pack (horatio.dark_pack): a clan with no upload
then uses its Dark Pack symbol. Otherwise a clan without one shows its name
only; a bloodline without one takes its clan's."""

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select, text

from horatio import dark_pack, pictures
from horatio.api.pictures import uploads
from horatio.audit import record
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import ClanLogo, RuleSet, TraitCategory, TraitDefinition
from horatio.permissions import require_custodian
from horatio.rules.splats import SPLATS

router = APIRouter(prefix="/clan-logos", tags=["clan logos"])


class ClanLogoOut(BaseModel):
    splat: str
    clan: str
    # Where its logo is (add "/128.webp" or "/600.webp"), or None for none yet.
    logo: str | None
    logo_id: uuid.UUID | None
    # Its Dark Pack symbol (add "/128.webp"), used while there is no upload.
    dark_pack: str | None


class ClanLogosOut(BaseModel):
    # False where uploads are not set up (HORATIO_UPLOAD_DIR).
    available: bool
    # Whether the operator has imported the Dark Pack resources.
    dark_pack: bool
    clans: list[ClanLogoOut]


def clans(db: DbSession) -> list[tuple[str, str]]:
    """Every clan and bloodline in the rule sets, as (splat, name). A splat whose
    clans are another's (a ghoul's are the vampire's) has no logos of its own."""
    borrowing = [s for s, splat in SPLATS.items() if splat.clans_from]
    return list(
        db.execute(
            select(RuleSet.splat, TraitDefinition.name)
            .join(TraitCategory, TraitCategory.rule_set_id == RuleSet.id)
            .join(TraitDefinition, TraitDefinition.category_id == TraitCategory.id)
            .where(
                TraitCategory.key == "clan",
                TraitDefinition.retired.is_(False),
                RuleSet.splat.not_in(borrowing),
            )
            .order_by(RuleSet.splat, TraitDefinition.name)
        )
    )


@router.get("")
def list_logos(db: DbSession, user: CurrentUser) -> ClanLogosOut:
    kept = {(lg.splat, lg.clan): lg for lg in db.scalars(select(ClanLogo))}
    symbols = dark_pack.clan_logos()
    return ClanLogosOut(
        available=pictures.upload_dir() is not None,
        dark_pack=dark_pack.folder() is not None,
        clans=[
            ClanLogoOut(
                splat=splat,
                clan=clan,
                logo=pictures.logo_url(kept[(splat, clan)].image_id)
                if (splat, clan) in kept
                else None,
                logo_id=kept[(splat, clan)].id if (splat, clan) in kept else None,
                dark_pack=symbols[clan][0] if splat == "vampire" and clan in symbols else None,
            )
            for splat, clan in clans(db)
        ],
    )


@router.post("")
def upload_logo(
    db: DbSession,
    user: CurrentUser,
    clan: Annotated[str, Form()],
    file: Annotated[UploadFile, File(description="JPEG, PNG, WebP or HEIC, up to 10 MB.")],
    splat: Annotated[str, Form()] = "vampire",
) -> ClanLogoOut:
    """A clan's logo, replacing any it has."""
    require_custodian(user)
    if (splat, clan) not in set(clans(db)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No clan called {clan}.")
    root = uploads()
    try:
        image = pictures.read_image(file.file.read(pictures.MAX_BYTES + 1))
    except pictures.PictureError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    # One upload for a clan at a time, so two at once replace one another cleanly.
    db.execute(
        text("select pg_advisory_xact_lock(hashtext(:key))"), {"key": f"clan_logo:{splat}:{clan}"}
    )
    logo = db.scalar(select(ClanLogo).where(ClanLogo.splat == splat, ClanLogo.clan == clan))
    old = logo.image_id if logo else None
    new = uuid.uuid4()
    directory = pictures.logo_dir(root, new)
    with pictures.writing(directory):
        pictures.write_logo(directory, image)
        if logo is None:
            logo = ClanLogo(splat=splat, clan=clan, image_id=new, uploaded_by=user.id)
            db.add(logo)
        else:
            logo.image_id = new
            logo.uploaded_by = user.id
        record(db, user, "clan_logo.uploaded", clan=clan)
        db.commit()
    if old is not None:
        pictures.remove(pictures.logo_dir(root, old))
    symbol = dark_pack.clan_logos().get(clan) if splat == "vampire" else None
    return ClanLogoOut(
        splat=splat,
        clan=clan,
        logo=pictures.logo_url(new),
        logo_id=logo.id,
        dark_pack=symbol[0] if symbol else None,
    )


@router.delete("/{logo_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_logo(logo_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    require_custodian(user)
    logo = db.get(ClanLogo, logo_id)
    if logo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such logo.")
    image_id = logo.image_id
    record(db, user, "clan_logo.removed", clan=logo.clan)
    db.delete(logo)
    db.commit()
    root = pictures.upload_dir()
    if root is not None:
        pictures.remove(pictures.logo_dir(root, image_id))


@router.get("/{image_id}/{name}", response_class=FileResponse)
def logo_file(image_id: uuid.UUID, name: str, db: DbSession, user: CurrentUser) -> FileResponse:
    """A logo's file, for anyone signed in. Like pictures' files, they never change."""
    root = pictures.upload_dir()
    known = db.scalar(select(ClanLogo.id).where(ClanLogo.image_id == image_id))
    path = pictures.logo_file(root, image_id, name) if root and known else None
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such logo.")
    return FileResponse(
        path,
        media_type="image/webp",
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )
