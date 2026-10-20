"""Characters' pictures: upload one, move its crop, remove it, and show it.

The character's player, the staff of a troupe it is in and the custodian (whoever
can see the character) can upload one; it shows straight away, with no approval.
They can all remove it too, and if it was someone else's upload, that person is
told. Each change goes in the character's log. Only people who can see the
character are shown its picture.
"""

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel, Field

from horatio import pictures
from horatio.audit import record
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, User
from horatio.notifications import notify
from horatio.permissions import visible_character

router = APIRouter(prefix="/characters/{character_id}", tags=["pictures"])


class CropIn(BaseModel):
    """The square portrait's place in the picture, as fractions: its left and top
    edges of the picture's width and height, and its side of the width."""

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    size: float = Field(gt=0, le=1)


class PictureOut(BaseModel):
    # False where pictures are not set up (HORATIO_UPLOAD_DIR), as in some local development.
    available: bool
    # Where it is: add "/48.webp", "/128.webp", "/512.webp", "/portrait.webp",
    # "/portrait.jpg" (for printing) or "/full.webp" (to crop). None: no picture.
    picture: str | None
    crop: CropIn | None
    uploaded_by: str | None
    uploaded_at: datetime | None


def picture_out(db: DbSession, character: Character) -> PictureOut:
    by = db.get(User, character.picture_by) if character.picture_by else None
    return PictureOut(
        available=pictures.upload_dir() is not None,
        picture=pictures.picture_url(character.id, character.picture_id),
        crop=CropIn(**character.picture_crop) if character.picture_crop else None,
        uploaded_by=by.display_name if by else None,
        uploaded_at=character.picture_at,
    )


def uploads() -> Path:
    root = pictures.upload_dir()
    if root is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Pictures are not set up here.")
    return root


def changeable(db: DbSession, user: User, character_id: uuid.UUID) -> Character:
    """Whoever can see the character can change its picture, unless it is retired."""
    character = visible_character(db, user, character_id)
    if character.status == "retired":
        raise HTTPException(status.HTTP_409_CONFLICT, "This character is retired.")
    return character


def log_troupe(character: Character) -> uuid.UUID | None:
    """The troupe whose log records picture changes: the one holding the sheet."""
    return character.home_troupe_id or character.owner_troupe_id


def as_fractions(width: int, height: int, box: pictures.Box) -> dict[str, float]:
    return {"x": box[0] / width, "y": box[1] / height, "size": (box[2] - box[0]) / width}


def save(
    db: DbSession,
    user: User,
    character: Character,
    root: Path,
    image: Image.Image,
    crop: pictures.Crop | None,
    action: str,
) -> None:
    """Write the picture's files under a new id, point the character at them, and
    only then remove the files they replace."""
    old = character.picture_id
    new = uuid.uuid4()
    directory = pictures.picture_dir(root, character.id, new)
    with pictures.writing(directory):
        pictures.write_picture(directory, image, crop)
        box = pictures.square_box(image.width, image.height, crop)
        character.picture_id = new
        character.picture_crop = as_fractions(image.width, image.height, box)
        record(db, user, action, troupe_id=log_troupe(character), character_id=character.id)
        db.commit()
    if old is not None:
        pictures.remove(pictures.picture_dir(root, character.id, old))


@router.get("/picture")
def read_picture(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> PictureOut:
    return picture_out(db, visible_character(db, user, character_id))


@router.post("/picture")
def upload_picture(
    character_id: uuid.UUID,
    file: Annotated[UploadFile, File(description="JPEG, PNG, WebP or HEIC, up to 10 MB.")],
    db: DbSession,
    user: CurrentUser,
    crop_x: Annotated[float | None, Form(ge=0, le=1)] = None,
    crop_y: Annotated[float | None, Form(ge=0, le=1)] = None,
    crop_size: Annotated[float | None, Form(gt=0, le=1)] = None,
) -> PictureOut:
    """A new picture, replacing any the character has. Without a crop, the
    portrait is the biggest square in the middle."""
    character = changeable(db, user, character_id)
    root = uploads()
    try:
        image = pictures.read_image(file.file.read(pictures.MAX_BYTES + 1))
    except pictures.PictureError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    crop = (
        pictures.Crop(crop_x, crop_y, crop_size)
        if crop_x is not None and crop_y is not None and crop_size is not None
        else None
    )
    action = "picture.replaced" if character.picture_id else "picture.uploaded"
    character.picture_by = user.id
    character.picture_at = datetime.now(UTC)
    save(db, user, character, root, image, crop, action)
    return picture_out(db, character)


@router.put("/picture/crop")
def crop_picture(
    character_id: uuid.UUID, body: CropIn, db: DbSession, user: CurrentUser
) -> PictureOut:
    """Move the portrait's crop, cutting it again from the picture as kept."""
    character = changeable(db, user, character_id)
    root = uploads()
    kept = (
        pictures.picture_file(root, character.id, character.picture_id, "full.webp")
        if character.picture_id
        else None
    )
    if kept is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The character has no picture.")
    with Image.open(kept) as opened:
        image = opened.copy()
    crop = pictures.Crop(body.x, body.y, body.size)
    save(db, user, character, root, image, crop, "picture.cropped")
    return picture_out(db, character)


@router.delete("/picture", status_code=status.HTTP_204_NO_CONTENT)
def remove_picture(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    """Take the picture away. Whoever uploaded it is told, unless it was them."""
    character = changeable(db, user, character_id)
    if character.picture_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The character has no picture.")
    old, uploader = character.picture_id, character.picture_by
    character.picture_id = None
    character.picture_crop = None
    character.picture_by = None
    character.picture_at = None
    troupe_id = log_troupe(character)
    record(db, user, "picture.removed", troupe_id=troupe_id, character_id=character.id)
    if uploader is not None and uploader != user.id:
        notify(
            db,
            [uploader],
            "picture.removed",
            f"{user.display_name} removed {character.name}'s picture.",
            f"/characters/{character.id}",
            troupe_id=troupe_id,
            character_id=character.id,
        )
    db.commit()
    root = pictures.upload_dir()
    if root is not None:
        pictures.remove(pictures.picture_dir(root, character.id, old))


@router.get("/pictures/{picture_id}/{name}", response_class=FileResponse)
def picture_file(
    character_id: uuid.UUID, picture_id: uuid.UUID, name: str, db: DbSession, user: CurrentUser
) -> FileResponse:
    """One of the picture's files. A picture's files never change (a new one has a
    new id), so browsers may keep them; privately, as only some people see them."""
    character = visible_character(db, user, character_id)
    root = pictures.upload_dir()
    path = (
        pictures.picture_file(root, character.id, picture_id, name)
        if root is not None and character.picture_id == picture_id
        else None
    )
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such picture.")
    return FileResponse(
        path,
        media_type="image/jpeg" if name.endswith(".jpg") else "image/webp",
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )
