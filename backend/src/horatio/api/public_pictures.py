"""The pictures Horatio sends to Discord as a message's sender, for Discord to fetch
without signing in (horatio.public_pictures)."""

import uuid

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from horatio import public_pictures
from horatio.auth.deps import DbSession

router = APIRouter(prefix="/public-pictures", tags=["pictures"])


@router.get("/{kind}/{owner_id}/{picture_id}/{signed}.webp", response_class=FileResponse)
def public_picture(
    kind: str, owner_id: uuid.UUID, picture_id: uuid.UUID, signed: str, db: DbSession
) -> FileResponse:
    """A news agency's portrait or a character's picture, at an address only the
    messages Horatio sends to Discord carry. Its files never change (a new picture
    has a new id), so anyone may keep them."""
    path = public_pictures.picture_file(db, kind, owner_id, picture_id, signed)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such picture.")
    return FileResponse(
        path,
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
