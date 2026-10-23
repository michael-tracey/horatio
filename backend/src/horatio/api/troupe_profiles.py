"""Troupes' profiles (issue #119): what a troupe is, where and when it plays, and how
to reach it, for its players and for people thinking of joining.

Its storytellers edit it. Anyone signed in can see it; when the troupe ticks
`public`, so can anyone at all, at /t/<troupe id>, which link previews show with
the troupe's portrait and name. A profile never holds emails, characters or
anything else only members see: staff show by display name and handle, and the
venue's street address only to people signed in, even on a public profile.
"""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import pictures
from horatio.api.pictures import CropIn, as_fractions, uploads
from horatio.api.players import web_address
from horatio.audit import record
from horatio.auth.deps import CurrentUser, DbSession, MaybeUser
from horatio.models import ScheduledGame, Troupe, TroupeStaff, User
from horatio.permissions import TroupeAction, allows, require_troupe_action, troupe_role

router = APIRouter(prefix="/troupes/{troupe_id}", tags=["troupe profiles"])

# How many upcoming games a profile shows, and how long one game may run.
SHOWN_GAMES = 12
LONGEST_GAME = timedelta(days=7)

Short = Annotated[str, Field(max_length=200)]
Long = Annotated[str, Field(max_length=2000)]


class ProfileLinks(BaseModel):
    """Each an http or https address, or None."""

    website: str | None = None
    discord: str | None = None
    facebook: str | None = None
    instagram: str | None = None
    # Where to read how to join.
    join: str | None = None


class Venue(BaseModel):
    # The city or region, such as "Leeds" or "North Yorkshire".
    region: Short = ""
    name: Short = ""
    # Only ever shown to people signed in.
    address: Short = ""
    # Step-free access, parking, a quiet room.
    access: Long = ""


class Setting(BaseModel):
    chronicle: Short = ""
    city: Short = ""
    era: Short = ""
    # A short line on its tone.
    tone: Short = ""


class Profile(BaseModel):
    """What a troupe's profile says, as Troupe.profile keeps it. All optional."""

    links: ProfileLinks = ProfileLinks()
    # How often games run, as text: "Second Saturday of the month, 7 pm to midnight".
    schedule: Short = ""
    venue: Venue = Venue()
    setting: Setting = Setting()
    # Whether it is taking new players; None says nothing either way.
    new_players: Literal["welcoming", "closed"] | None = None
    min_age: int | None = Field(default=None, ge=0, le=99)
    content_notes: Long = ""


class TroupeProfileIn(Profile):
    # Show the profile to anyone, even people not signed in; None leaves it as it is.
    public: bool | None = None
    # Who new players should contact: one of the troupe's staff, or None.
    contact_id: uuid.UUID | None = None


class VenueOut(BaseModel):
    region: str
    name: str
    # None to people not signed in.
    address: str | None
    # There is an address, but the viewer must sign in to see it.
    address_hidden: bool
    access: str


class ScheduledGameIn(BaseModel):
    starts_at: AwareDatetime
    ends_at: AwareDatetime


class ScheduledGameOut(BaseModel):
    id: uuid.UUID
    starts_at: datetime
    ends_at: datetime


class ProfilePerson(BaseModel):
    """A person a profile names, as anyone may see them: never their email."""

    id: uuid.UUID
    handle: str
    display_name: str


class TroupeProfileOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    public: bool
    # Where its portrait is (add "/48.webp", "/128.webp", "/512.webp", or
    # "/full.webp" to crop), and its banner (add "/1500.webp" or "/750.webp").
    portrait: str | None
    portrait_crop: CropIn | None
    banner: str | None
    links: ProfileLinks
    schedule: str
    # Games still to come (or under way), soonest first.
    games: list[ScheduledGameOut]
    venue: VenueOut
    setting: Setting
    new_players: Literal["welcoming", "closed"] | None
    contact: ProfilePerson | None
    lead: ProfilePerson
    min_age: int | None
    content_notes: str
    # Whether the viewer may edit it, and whether pictures can be uploaded here.
    can_edit: bool
    pictures_available: bool


def someone(user: User) -> ProfilePerson:
    return ProfilePerson(id=user.id, handle=user.handle, display_name=user.display_name)


def is_staff(db: Session, troupe: Troupe, user_id: uuid.UUID) -> bool:
    """The lead storyteller, or anyone on the troupe's staff."""
    return user_id == troupe.lead_user_id or bool(
        db.scalar(
            select(TroupeStaff.id).where(
                TroupeStaff.troupe_id == troupe.id, TroupeStaff.user_id == user_id
            )
        )
    )


def upcoming(db: Session, troupe: Troupe) -> list[ScheduledGame]:
    return list(
        db.scalars(
            select(ScheduledGame)
            .where(ScheduledGame.troupe_id == troupe.id, ScheduledGame.ends_at > datetime.now(UTC))
            .order_by(ScheduledGame.starts_at)
            .limit(SHOWN_GAMES)
        )
    )


def profile_out(db: Session, viewer: User | None, troupe: Troupe) -> TroupeProfileOut:
    """The profile as `viewer` may see it; None for someone not signed in."""
    kept = Profile.model_validate(troupe.profile)
    # A contact who has left the staff is no longer anyone's to contact.
    contact = (
        db.get(User, troupe.contact_id)
        if troupe.contact_id and is_staff(db, troupe, troupe.contact_id)
        else None
    )
    can_edit = (
        viewer is not None
        and (troupe.archived_at is None or viewer.is_custodian)
        and allows(
            troupe_role(db, viewer, troupe),
            TroupeAction.EDIT_PROFILE,
            is_custodian=viewer.is_custodian,
        )
    )
    return TroupeProfileOut(
        id=troupe.id,
        name=troupe.name,
        description=troupe.description,
        public=troupe.public,
        portrait=pictures.troupe_portrait_url(troupe.id, troupe.portrait_id),
        portrait_crop=CropIn(**troupe.portrait_crop) if troupe.portrait_crop else None,
        banner=pictures.banner_url(troupe.id, troupe.banner_id),
        links=kept.links,
        schedule=kept.schedule,
        games=[
            ScheduledGameOut(id=g.id, starts_at=g.starts_at, ends_at=g.ends_at)
            for g in upcoming(db, troupe)
        ],
        venue=VenueOut(
            region=kept.venue.region,
            name=kept.venue.name,
            address=kept.venue.address if viewer is not None else None,
            address_hidden=viewer is None and bool(kept.venue.address),
            access=kept.venue.access,
        ),
        setting=kept.setting,
        new_players=kept.new_players,
        contact=someone(contact) if contact else None,
        lead=someone(db.get_one(User, troupe.lead_user_id)),
        min_age=kept.min_age,
        content_notes=kept.content_notes,
        can_edit=can_edit,
        pictures_available=pictures.upload_dir() is not None,
    )


def viewable(db: Session, viewer: User | None, troupe_id: uuid.UUID) -> Troupe:
    """The troupe, if `viewer` may see its profile: anyone signed in, or anyone at
    all when it is public. 404 otherwise, so a private troupe's profile does not
    show that it exists. An archived troupe's is only for the custodian."""
    troupe = db.get(Troupe, troupe_id)
    if (
        troupe is None
        or (troupe.archived_at is not None and not (viewer and viewer.is_custodian))
        or (viewer is None and not troupe.public)
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    return troupe


def editable(db: Session, user: User, troupe_id: uuid.UUID) -> Troupe:
    troupe = db.get(Troupe, troupe_id)
    if troupe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    require_troupe_action(db, user, troupe, TroupeAction.EDIT_PROFILE)
    return troupe


def address(url: str | None) -> str | None:
    """A link as given, trimmed; None for none."""
    return web_address(url) if url and url.strip() else None


@router.get("/profile")
def read_profile(troupe_id: uuid.UUID, db: DbSession, user: MaybeUser) -> TroupeProfileOut:
    """The troupe's profile, for anyone signed in, and for anyone at all if the
    troupe has made it public."""
    return profile_out(db, user, viewable(db, user, troupe_id))


@router.put("/profile")
def edit_profile(
    troupe_id: uuid.UUID, body: TroupeProfileIn, db: DbSession, user: CurrentUser
) -> TroupeProfileOut:
    troupe = editable(db, user, troupe_id)
    if body.contact_id is not None and not is_staff(db, troupe, body.contact_id):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "The contact for new players must be one of the troupe's staff.",
        )
    links = ProfileLinks(**{k: address(v) for k, v in body.links.model_dump().items()})
    trimmed = Profile.model_validate(
        {
            **body.model_dump(exclude={"public", "contact_id", "links"}),
            "links": links,
        }
    )
    troupe.profile = _stripped(trimmed).model_dump(mode="json")
    troupe.contact_id = body.contact_id
    if body.public is not None:
        make_public(db, user, troupe, body.public)
    record(db, user, "troupe.profile_changed", troupe_id=troupe.id)
    db.commit()
    return profile_out(db, user, troupe)


class PublicIn(BaseModel):
    public: bool


@router.put("/profile/public")
def set_public(
    troupe_id: uuid.UUID, body: PublicIn, db: DbSession, user: CurrentUser
) -> TroupeProfileOut:
    """Show the profile to anyone, or only to people signed in, without touching
    the rest of it: the Profile tab's switch, which saves at once."""
    troupe = editable(db, user, troupe_id)
    make_public(db, user, troupe, body.public)
    db.commit()
    return profile_out(db, user, troupe)


def make_public(db: Session, user: User, troupe: Troupe, public: bool) -> None:
    if public == troupe.public:
        return
    troupe.public = public
    record(
        db,
        user,
        "troupe.public",
        troupe_id=troupe.id,
        state="public" if public else "for people signed in only",
    )


def _stripped(profile: Profile) -> Profile:
    """Every piece of text with the spaces around it taken off."""

    def strip(value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items()}
        return value

    return Profile.model_validate(strip(profile.model_dump()))


@router.post("/games", status_code=status.HTTP_201_CREATED)
def add_game(
    troupe_id: uuid.UUID, body: ScheduledGameIn, db: DbSession, user: CurrentUser
) -> ScheduledGameOut:
    """A game the troupe will run, for its profile's schedule."""
    troupe = editable(db, user, troupe_id)
    if body.ends_at <= body.starts_at:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "A game must end after it starts."
        )
    if body.ends_at - body.starts_at > LONGEST_GAME:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "A game can run for a week at most."
        )
    if body.ends_at <= datetime.now(UTC):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That game is over already.")
    game = ScheduledGame(troupe_id=troupe.id, starts_at=body.starts_at, ends_at=body.ends_at)
    db.add(game)
    record(db, user, "troupe.game_added", troupe_id=troupe.id)
    db.commit()
    return ScheduledGameOut(id=game.id, starts_at=game.starts_at, ends_at=game.ends_at)


@router.delete("/games/{game_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_game(troupe_id: uuid.UUID, game_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    troupe = editable(db, user, troupe_id)
    game = db.get(ScheduledGame, game_id)
    if game is None or game.troupe_id != troupe.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such game.")
    db.delete(game)
    record(db, user, "troupe.game_removed", troupe_id=troupe.id)
    db.commit()


def read_upload(file: UploadFile) -> Image.Image:
    try:
        return pictures.read_image(file.file.read(pictures.MAX_BYTES + 1))
    except pictures.PictureError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None


def save_portrait(
    db: Session,
    user: User,
    troupe: Troupe,
    image: Image.Image,
    crop: pictures.Crop | None,
    action: str,
) -> None:
    """Write the portrait's files under a new id, point the troupe at them, and
    only then remove the files they replace."""
    root = uploads()
    old, new = troupe.portrait_id, uuid.uuid4()
    directory = pictures.troupe_portrait_dir(root, troupe.id, new)
    with pictures.writing(directory):
        pictures.write_troupe_portrait(directory, image, crop)
        box = pictures.square_box(image.width, image.height, crop)
        troupe.portrait_id = new
        troupe.portrait_crop = as_fractions(image.width, image.height, box)
        record(db, user, action, troupe_id=troupe.id)
        db.commit()
    if old is not None:
        pictures.remove(pictures.troupe_portrait_dir(root, troupe.id, old))


@router.post("/portrait")
def upload_portrait(
    troupe_id: uuid.UUID,
    file: Annotated[UploadFile, File(description="JPEG, PNG, WebP or HEIC, up to 10 MB.")],
    db: DbSession,
    user: CurrentUser,
    crop_x: Annotated[float | None, Form(ge=0, le=1)] = None,
    crop_y: Annotated[float | None, Form(ge=0, le=1)] = None,
    crop_size: Annotated[float | None, Form(gt=0, le=1)] = None,
) -> TroupeProfileOut:
    """A new portrait, cut square like a character's picture. Without a crop, it
    is the biggest square in the middle."""
    troupe = editable(db, user, troupe_id)
    uploads()
    image = read_upload(file)
    crop = (
        pictures.Crop(crop_x, crop_y, crop_size)
        if crop_x is not None and crop_y is not None and crop_size is not None
        else None
    )
    action = "troupe.portrait_replaced" if troupe.portrait_id else "troupe.portrait_uploaded"
    save_portrait(db, user, troupe, image, crop, action)
    return profile_out(db, user, troupe)


@router.put("/portrait/crop")
def crop_portrait(
    troupe_id: uuid.UUID, body: CropIn, db: DbSession, user: CurrentUser
) -> TroupeProfileOut:
    """Move the portrait's crop, cutting it again from the picture as kept."""
    troupe = editable(db, user, troupe_id)
    root = uploads()
    kept = (
        pictures.troupe_portrait_file(root, troupe.id, troupe.portrait_id, "full.webp")
        if troupe.portrait_id
        else None
    )
    if kept is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The troupe has no portrait.")
    with Image.open(kept) as opened:
        image = opened.copy()
    crop = pictures.Crop(body.x, body.y, body.size)
    save_portrait(db, user, troupe, image, crop, "troupe.portrait_cropped")
    return profile_out(db, user, troupe)


@router.delete("/portrait", status_code=status.HTTP_204_NO_CONTENT)
def remove_portrait(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    troupe = editable(db, user, troupe_id)
    if troupe.portrait_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The troupe has no portrait.")
    old = troupe.portrait_id
    troupe.portrait_id = None
    troupe.portrait_crop = None
    record(db, user, "troupe.portrait_removed", troupe_id=troupe.id)
    db.commit()
    root = pictures.upload_dir()
    if root is not None:
        pictures.remove(pictures.troupe_portrait_dir(root, troupe.id, old))


@router.post("/banner")
def upload_banner(
    troupe_id: uuid.UUID,
    file: Annotated[UploadFile, File(description="JPEG, PNG, WebP or HEIC, up to 10 MB.")],
    db: DbSession,
    user: CurrentUser,
) -> TroupeProfileOut:
    """A wide banner across the top of the troupe's page, cut 3:1 from the middle
    of the picture."""
    troupe = editable(db, user, troupe_id)
    root = uploads()
    image = read_upload(file)
    old, new = troupe.banner_id, uuid.uuid4()
    directory = pictures.banner_dir(root, troupe.id, new)
    with pictures.writing(directory):
        pictures.write_banner(directory, image)
        troupe.banner_id = new
        record(db, user, "troupe.banner_uploaded", troupe_id=troupe.id)
        db.commit()
    if old is not None:
        pictures.remove(pictures.banner_dir(root, troupe.id, old))
    return profile_out(db, user, troupe)


@router.delete("/banner", status_code=status.HTTP_204_NO_CONTENT)
def remove_banner(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    troupe = editable(db, user, troupe_id)
    if troupe.banner_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The troupe has no banner.")
    old = troupe.banner_id
    troupe.banner_id = None
    record(db, user, "troupe.banner_removed", troupe_id=troupe.id)
    db.commit()
    root = pictures.upload_dir()
    if root is not None:
        pictures.remove(pictures.banner_dir(root, troupe.id, old))


def image_response(path: Path | None) -> FileResponse:
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such picture.")
    # Their files never change (a new one has a new id), so browsers may keep them.
    return FileResponse(
        path,
        media_type="image/webp",
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


@router.get("/portraits/{portrait_id}/{name}", response_class=FileResponse)
def portrait_file(
    troupe_id: uuid.UUID, portrait_id: uuid.UUID, name: str, db: DbSession, user: MaybeUser
) -> FileResponse:
    """One of the portrait's files, for whoever may see the profile."""
    troupe = viewable(db, user, troupe_id)
    root = pictures.upload_dir()
    path = (
        pictures.troupe_portrait_file(root, troupe.id, portrait_id, name)
        if root is not None and troupe.portrait_id == portrait_id
        else None
    )
    return image_response(path)


@router.get("/banners/{banner_id}/{name}", response_class=FileResponse)
def banner_file(
    troupe_id: uuid.UUID, banner_id: uuid.UUID, name: str, db: DbSession, user: MaybeUser
) -> FileResponse:
    troupe = viewable(db, user, troupe_id)
    root = pictures.upload_dir()
    path = (
        pictures.banner_file(root, troupe.id, banner_id, name)
        if root is not None and troupe.banner_id == banner_id
        else None
    )
    return image_response(path)


def link_preview(db: Session, troupe_id: uuid.UUID) -> dict[str, str] | None:
    """What a link to a public profile shows where it is shared: the troupe's name,
    a line about it, and its portrait's address on this site. None for a troupe
    whose profile is not public."""
    troupe = db.get(Troupe, troupe_id)
    if troupe is None or troupe.archived_at is not None or not troupe.public:
        return None
    kept = Profile.model_validate(troupe.profile)
    where = kept.venue.region or kept.setting.city
    line = troupe.description.strip().split("\n")[0][:200] or (
        f"A Mind's Eye Theatre troupe in {where}." if where else "A Mind's Eye Theatre troupe."
    )
    portrait = pictures.troupe_portrait_url(troupe.id, troupe.portrait_id)
    return {
        "title": troupe.name,
        "description": line,
        "image": f"{portrait}/512.webp" if portrait else "",
    }
