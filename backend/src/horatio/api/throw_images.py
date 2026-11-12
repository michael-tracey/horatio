"""A troupe's own rock, paper and scissors for the Play View's Throws tab (issue #670).

Its storytellers (and the custodian) upload a picture for each, through the same
pipeline as portraits and logos (horatio.pictures): checked to be a picture, stripped
of its metadata, and kept only as WebP squares, transparency and all. The set has an
optional name ("Land of the Sky bones"). It is offered to players (issue #671) only
once all three are there; removing it puts the troupe back on Horatio's own.

The troupe's members see the set and its pictures: its staff, and the players of its
active characters, home or visiting (horatio.permissions.is_member).

Each person chooses which set their Throws tab uses (issue #671): Horatio's, or the
whole set of any troupe they play in (horatio.preferences `throw_images`). `/throw-images`
says which sets they may choose and which one counts now; a choice whose troupe they
no longer play in, or whose set is gone, counts as Horatio's.
"""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import pictures, preferences
from horatio.api.pictures import uploads
from horatio.api.troupe_profiles import image_response, read_upload
from horatio.audit import record
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Troupe, User
from horatio.permissions import TroupeAction, is_member, member_troupe_ids, require_troupe_action

router = APIRouter(prefix="/troupes/{troupe_id}/throw-images", tags=["throw images"])
# The signed-in person's choice of set (#671).
mine_router = APIRouter(prefix="/throw-images", tags=["throw images"])

Which = Literal["rock", "paper", "scissors"]
WHICH: tuple[Which, ...] = ("rock", "paper", "scissors")
NAMES: dict[Which, str] = {"rock": "Rock", "paper": "Paper", "scissors": "Scissors"}


class ThrowImagesOut(BaseModel):
    # The set's name, if it has one ("Land of the Sky bones").
    name: str
    # Where each picture is: add "/512.webp" or "/128.webp". None until uploaded.
    rock: str | None
    paper: str | None
    scissors: str | None
    # All three are there, so the set can be offered.
    complete: bool


class ThrowImagesNameIn(BaseModel):
    name: str = Field(max_length=60)


def image_id(troupe: Troupe, which: Which) -> uuid.UUID | None:
    value = (troupe.throw_images or {}).get(which)
    return uuid.UUID(value) if value else None


def images_out(troupe: Troupe) -> ThrowImagesOut:
    ids = {which: image_id(troupe, which) for which in WHICH}
    return ThrowImagesOut(
        name=(troupe.throw_images or {}).get("name", ""),
        rock=pictures.throw_image_url(troupe.id, ids["rock"]),
        paper=pictures.throw_image_url(troupe.id, ids["paper"]),
        scissors=pictures.throw_image_url(troupe.id, ids["scissors"]),
        complete=all(ids.values()),
    )


def troupe_of(db: Session, troupe_id: uuid.UUID) -> Troupe:
    troupe = db.get(Troupe, troupe_id)
    if troupe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    return troupe


def seen_by(db: Session, user: User, troupe_id: uuid.UUID) -> Troupe:
    """The troupe, if `user` is one of its members or the custodian; 404 otherwise."""
    troupe = troupe_of(db, troupe_id)
    if not (user.is_custodian or is_member(db, user, troupe)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    return troupe


def changed_by(db: Session, user: User, troupe_id: uuid.UUID) -> Troupe:
    """The troupe, if `user` may change its settings: its storytellers and the custodian."""
    troupe = troupe_of(db, troupe_id)
    require_troupe_action(db, user, troupe, TroupeAction.MANAGE_HOUSE_RULES)
    return troupe


@router.get("")
def read_images(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> ThrowImagesOut:
    """The troupe's rock, paper and scissors, for its members."""
    return images_out(seen_by(db, user, troupe_id))


@router.post("/{which}")
def upload_image(
    troupe_id: uuid.UUID,
    which: Which,
    file: Annotated[UploadFile, File(description="JPEG, PNG, WebP or HEIC, up to 10 MB.")],
    db: DbSession,
    user: CurrentUser,
) -> ThrowImagesOut:
    """A new picture for one throw, kept whole on a transparent square. It replaces
    the one before, whose files go once the new one is saved."""
    troupe = changed_by(db, user, troupe_id)
    root = uploads()
    image = read_upload(file)
    old, new = image_id(troupe, which), uuid.uuid4()
    directory = pictures.throw_image_dir(root, troupe.id, new)
    with pictures.writing(directory):
        pictures.write_throw_image(directory, image)
        troupe.throw_images = {**(troupe.throw_images or {}), which: str(new)}
        action = "troupe.throw_image_replaced" if old else "troupe.throw_image_uploaded"
        record(db, user, action, troupe_id=troupe.id, throw=NAMES[which])
        db.commit()
    if old is not None:
        pictures.remove(pictures.throw_image_dir(root, troupe.id, old))
    return images_out(troupe)


@router.put("/name")
def name_images(
    troupe_id: uuid.UUID, body: ThrowImagesNameIn, db: DbSession, user: CurrentUser
) -> ThrowImagesOut:
    """Name the set, or clear its name with an empty one."""
    troupe = changed_by(db, user, troupe_id)
    name = " ".join(body.name.split())
    if name != (troupe.throw_images or {}).get("name", ""):
        troupe.throw_images = {**(troupe.throw_images or {}), "name": name}
        record(db, user, "troupe.throw_images_named", troupe_id=troupe.id, name=name or "no name")
        db.commit()
    return images_out(troupe)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def remove_images(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    """Remove the whole set: the troupe throws with Horatio's own again."""
    troupe = changed_by(db, user, troupe_id)
    old = [i for i in (image_id(troupe, which) for which in WHICH) if i is not None]
    if not troupe.throw_images:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The troupe has no throw images.")
    troupe.throw_images = {}
    record(db, user, "troupe.throw_images_removed", troupe_id=troupe.id)
    db.commit()
    root = pictures.upload_dir()
    if root is not None:
        for each in old:
            pictures.remove(pictures.throw_image_dir(root, troupe.id, each))


@router.get("/{picture_id}/{name}", response_class=FileResponse)
def image_file(
    troupe_id: uuid.UUID, picture_id: uuid.UUID, name: str, db: DbSession, user: CurrentUser
) -> FileResponse:
    """One of the set's files, for the troupe's members, while it is in the set."""
    troupe = seen_by(db, user, troupe_id)
    root = pictures.upload_dir()
    current = {image_id(troupe, which) for which in WHICH}
    path = (
        pictures.throw_image_file(root, troupe.id, picture_id, name)
        if root is not None and picture_id in current
        else None
    )
    return image_response(path)


# --- Each person's choice (#671) ----------------------------------------------------


class ThrowSetOut(BaseModel):
    """A troupe's whole set, as a person may choose it for their Throws tab."""

    troupe_id: uuid.UUID
    troupe_name: str
    # The set's own name, if it has one.
    name: str
    # Where each picture is: add "/512.webp" or "/128.webp".
    rock: str
    paper: str
    scissors: str


class MyThrowImagesOut(BaseModel):
    # The set the Throws tab uses now; None for Horatio's.
    chosen: ThrowSetOut | None
    # Every set the person may choose: each troupe they play in with all three pictures.
    offered: list[ThrowSetOut]


def offered(db: Session, user: User) -> list[ThrowSetOut]:
    """The whole sets of the troupes `user` plays in: their characters' troupes, home
    or visiting, and those they are staff of; never an archived troupe's."""
    ids = member_troupe_ids(db, user)
    if not ids:
        return []
    troupes = db.scalars(select(Troupe).where(Troupe.id.in_(ids)).order_by(Troupe.name))
    sets: list[ThrowSetOut] = []
    for troupe in troupes:
        images = images_out(troupe)
        if images.rock and images.paper and images.scissors:
            sets.append(
                ThrowSetOut(
                    troupe_id=troupe.id,
                    troupe_name=troupe.name,
                    name=images.name,
                    rock=images.rock,
                    paper=images.paper,
                    scissors=images.scissors,
                )
            )
    return sets


def may_choose(db: Session, user: User, troupe_id: str) -> bool:
    return any(str(s.troupe_id) == troupe_id for s in offered(db, user))


@mine_router.get("")
def my_images(db: DbSession, user: CurrentUser) -> MyThrowImagesOut:
    """The set the person's Throws tab uses, and the sets they may choose from."""
    sets = offered(db, user)
    want = preferences.read(user).throw_images
    chosen = next((s for s in sets if str(s.troupe_id) == want), None)
    return MyThrowImagesOut(chosen=chosen, offered=sets)
