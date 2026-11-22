"""Blog authors (#1159): each person's public profile as a writer for the game
developer blog (tracker #1155), new and separate from their player profile.

A person sets it in Account › Blog author: a display name, a handle for its
address (their Horatio handle until they choose another), a short bio in
Markdown, up to six links and a picture. It is made when they first save it, and
nothing from their player profile is in it unless they put it there: no email,
pronouns, Discord or lines and veils, and never their player profile's bio.

Anyone at all, signed in or not, can see an author's page (GET
/blog/authors/<handle>) and picture, while the author writes for the blog (horatio.blog.may_write:
the custodian, or anyone on the staff of a troupe that isn't archived), or has an
article published. Until then it is theirs alone to see, so an account made only
to post links has no public page. While their account is suspended it is hidden
again, as for an account merged into another (#1182): their articles stay up,
under a card with their name alone, and it all comes back when the suspension
ends. The custodian can clear an author's bio, links
or picture: it is logged, and the author is told in the bell.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio import handles, pictures, suspensions
from horatio.api.pictures import CropIn, as_fractions, uploads
from horatio.api.players import Link, clean_link
from horatio.api.troupe_profiles import read_upload
from horatio.audit import record
from horatio.auth.deps import CurrentUser, DbSession, MaybeUser
from horatio.blog import may_write
from horatio.models import BlogAuthor, BlogPost, User
from horatio.notifications import notify
from horatio.permissions import require_custodian
from horatio.sheets import conflict, unprocessable
from horatio.titles import and_list

router = APIRouter(prefix="/blog", tags=["blog authors"])

MAX_LINKS = 6
# Short: it shows under every article.
MAX_BIO = 1000
CLEARED = "account.blog_author_cleared"


class AuthorShown(BaseModel):
    """What anyone may see of an author. Never their email or anything else from
    their player profile."""

    display_name: str
    # Markdown.
    bio: str
    links: list[Link]
    # Where their picture is (add "/96.webp", "/256.webp" or "/512.webp"), or None.
    picture: str | None


class AuthorCard(AuthorShown):
    """An author as anyone may see them, under each of their articles."""

    # Their page's handle. None while their page is hidden as their account is
    # suspended (#1182): then the card has their name alone (`name_only`).
    handle: str | None


class AuthorPage(AuthorShown):
    """An author's page. The articles they have published join it with the blog's
    reading pages (#1158)."""

    handle: str
    # The viewer's own page.
    yours: bool
    # The viewer is the custodian, who can clear its bio, links or picture.
    can_clear: bool


class MyAuthor(BaseModel):
    """The signed-in person's own author profile, as Account › Blog author edits it.
    Before they first save it, what it would start as."""

    saved: bool
    display_name: str
    handle: str
    bio: str
    links: list[Link]
    picture: str | None
    # Add "/full.webp" to `picture` for the whole picture, to move this crop on.
    picture_crop: CropIn | None
    # Whether anyone else can see the page now: only while they write for the blog.
    public: bool
    # Whether pictures can be uploaded here (HORATIO_UPLOAD_DIR).
    pictures_available: bool


class MyAuthorIn(BaseModel):
    display_name: str = Field(max_length=100)
    handle: str = Field(max_length=31)
    bio: str = ""
    links: list[Link] = []


class ClearIn(BaseModel):
    """What the custodian clears; at least one."""

    bio: bool = False
    links: bool = False
    picture: bool = False
    reason: str = Field(default="", max_length=500)


def shown(db: Session, author: BlogAuthor) -> bool:
    """Whether anyone at all may see the author's page and picture: while they write
    for the blog, or while an article of theirs is published; never for an account
    merged into another, nor while their account is suspended (#1182)."""
    user = db.get_one(User, author.user_id)
    if user.merged_into_id is not None or suspensions.current(db, user.id) is not None:
        return False
    published = select(BlogPost.id).where(
        BlogPost.author_id == user.id, BlogPost.status == "published"
    )
    return may_write(db, user) or db.scalar(published.limit(1)) is not None


def card(author: BlogAuthor) -> AuthorCard:
    """The author as shown under each of their articles."""
    return AuthorCard(
        handle=author.handle,
        display_name=author.display_name,
        bio=author.bio,
        links=[Link(**link) for link in author.links],
        picture=pictures.author_picture_url(author.id, author.picture_id),
    )


def name_only(author: BlogAuthor) -> AuthorCard:
    """The card under their articles while their account is suspended: their name
    and nothing else, so nothing leads to the page that is hidden (#1182)."""
    return AuthorCard(handle=None, display_name=author.display_name, bio="", links=[], picture=None)


def by_handle(db: Session, handle: str) -> BlogAuthor | None:
    wanted = handle.strip().removeprefix("@").lower()
    return db.scalar(select(BlogAuthor).where(func.lower(BlogAuthor.handle) == wanted))


def own(db: Session, user: User) -> BlogAuthor | None:
    return db.scalar(select(BlogAuthor).where(BlogAuthor.user_id == user.id))


def viewable(db: Session, viewer: User | None, handle: str) -> BlogAuthor:
    """The author, if `viewer` may see their page: anyone while it is shown, and
    always its author and the custodian. 404 otherwise, so a page not shown does
    not show that it exists."""
    author = by_handle(db, handle)
    if author is None or not (
        shown(db, author)
        or (viewer is not None and (viewer.id == author.user_id or viewer.is_custodian))
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such author.")
    return author


def mine_out(db: Session, user: User, author: BlogAuthor | None) -> MyAuthor:
    if author is None:
        # Their name and handle to start from; nothing else of their player profile.
        return MyAuthor(
            saved=False,
            display_name=user.display_name,
            handle=user.handle,
            bio="",
            links=[],
            picture=None,
            picture_crop=None,
            public=False,
            pictures_available=pictures.upload_dir() is not None,
        )
    shows = card(author)
    return MyAuthor(
        saved=True,
        display_name=shows.display_name,
        handle=author.handle,
        bio=shows.bio,
        links=shows.links,
        picture=shows.picture,
        picture_crop=CropIn(**author.picture_crop) if author.picture_crop else None,
        public=shown(db, author),
        pictures_available=pictures.upload_dir() is not None,
    )


def clean_handle(db: Session, user: User, handle: str) -> str:
    """A handle for the blog: as a Horatio handle is made, and no other author's,
    regardless of case. Nor another person's Horatio handle, or one they hold, so
    no one writes as someone they are not."""
    handle = handles.clean(handle)
    taken = by_handle(db, handle)
    if taken is not None and taken.user_id != user.id:
        raise conflict(f"Another author has the handle {handle}.")
    holder = handles.holder(db, handle)
    if holder is not None and holder.id != user.id:
        raise conflict(f"{handle} is someone else's handle on Horatio. Choose another.")
    return handle


@router.get("/author")
def read_mine(db: DbSession, user: CurrentUser) -> MyAuthor:
    """The signed-in person's own author profile."""
    return mine_out(db, user, own(db, user))


@router.put("/author")
def save_mine(body: MyAuthorIn, db: DbSession, user: CurrentUser) -> MyAuthor:
    """Save the signed-in person's author profile, making it the first time."""
    name = body.display_name.strip()
    if not name:
        raise unprocessable("Give a display name.")
    bio = body.bio.strip()
    if len(bio) > MAX_BIO:
        raise unprocessable(f"Keep the bio to {MAX_BIO} characters.")
    links = [link for link in body.links if link.url.strip()]
    if len(links) > MAX_LINKS:
        raise unprocessable(f"Give at most {MAX_LINKS} links.")
    handle = clean_handle(db, user, body.handle)
    author = own(db, user)
    if author is None:
        author = BlogAuthor(user_id=user.id, display_name=name, handle=handle)
        db.add(author)
    author.display_name = name
    author.handle = handle
    author.bio = bio
    author.links = [clean_link(link).model_dump() for link in links]
    db.commit()
    return mine_out(db, user, author)


def saved(db: Session, user: User) -> BlogAuthor:
    author = own(db, user)
    if author is None:
        raise conflict("Save your author profile first, then add a picture.")
    return author


def save_picture(
    db: Session, author: BlogAuthor, image: Image.Image, crop: pictures.Crop | None
) -> None:
    """Write the picture's files under a new id, point the author at them, and only
    then remove the files they replace."""
    root = uploads()
    old, new = author.picture_id, uuid.uuid4()
    directory = pictures.author_picture_dir(root, author.id, new)
    with pictures.writing(directory):
        pictures.write_author_picture(directory, image, crop)
        box = pictures.square_box(image.width, image.height, crop)
        author.picture_id = new
        author.picture_crop = as_fractions(image.width, image.height, box)
        db.commit()
    if old is not None:
        pictures.remove(pictures.author_picture_dir(root, author.id, old))


def without_picture(author: BlogAuthor) -> uuid.UUID | None:
    """Take the author's picture away; the id of its files, to remove once saved."""
    old = author.picture_id
    author.picture_id = None
    author.picture_crop = None
    return old


def remove_files(author: BlogAuthor, picture_id: uuid.UUID | None) -> None:
    root = pictures.upload_dir()
    if picture_id is not None and root is not None:
        pictures.remove(pictures.author_picture_dir(root, author.id, picture_id))


@router.post("/author/picture")
def upload_mine(
    file: Annotated[UploadFile, File(description="JPEG, PNG, WebP or HEIC, up to 10 MB.")],
    db: DbSession,
    user: CurrentUser,
    crop_x: Annotated[float | None, Form(ge=0, le=1)] = None,
    crop_y: Annotated[float | None, Form(ge=0, le=1)] = None,
    crop_size: Annotated[float | None, Form(gt=0, le=1)] = None,
) -> MyAuthor:
    """A new picture, cut square. Without a crop, the biggest square in the middle."""
    author = saved(db, user)
    uploads()
    image = read_upload(file)
    crop = (
        pictures.Crop(crop_x, crop_y, crop_size)
        if crop_x is not None and crop_y is not None and crop_size is not None
        else None
    )
    save_picture(db, author, image, crop)
    return mine_out(db, user, author)


@router.put("/author/picture/crop")
def crop_mine(body: CropIn, db: DbSession, user: CurrentUser) -> MyAuthor:
    """Move the picture's crop, cutting it again from the picture as kept."""
    author = saved(db, user)
    root = uploads()
    kept = (
        pictures.author_picture_file(root, author.id, author.picture_id, "full.webp")
        if author.picture_id
        else None
    )
    if kept is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "You have no picture on the blog.")
    with Image.open(kept) as opened:
        image = opened.copy()
    save_picture(db, author, image, pictures.Crop(body.x, body.y, body.size))
    return mine_out(db, user, author)


@router.delete("/author/picture")
def remove_mine(db: DbSession, user: CurrentUser) -> MyAuthor:
    author = saved(db, user)
    if author.picture_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "You have no picture on the blog.")
    old = without_picture(author)
    db.commit()
    remove_files(author, old)
    return mine_out(db, user, author)


@router.get("/authors/{handle}")
def read_author(handle: str, db: DbSession, user: MaybeUser) -> AuthorPage:
    """An author's page, for anyone at all while they write for the blog or have an
    article published."""
    author = viewable(db, user, handle)
    return AuthorPage(
        **card(author).model_dump(),
        yours=user is not None and user.id == author.user_id,
        can_clear=user is not None and user.is_custodian,
    )


@router.post("/authors/{handle}/clear")
def clear_author(handle: str, body: ClearIn, db: DbSession, user: CurrentUser) -> AuthorPage:
    """For the custodian: clear an author's bio, links or picture, such as one that
    breaks the site's rules. Logged; the rest of their profile stays."""
    require_custodian(user)
    author = by_handle(db, handle)
    if author is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such author.")
    parts = [
        part
        for part, chosen, there in (
            ("bio", body.bio, bool(author.bio)),
            ("links", body.links, bool(author.links)),
            ("picture", body.picture, author.picture_id is not None),
        )
        if chosen and there
    ]
    if not parts:
        raise unprocessable("Choose something there is to clear: the bio, links or picture.")
    if "bio" in parts:
        author.bio = ""
    if "links" in parts:
        author.links = []
    old = without_picture(author) if "picture" in parts else None
    member = db.get_one(User, author.user_id)
    reason = body.reason.strip()
    record(
        db,
        user,
        CLEARED,
        member=member.display_name,
        user_id=member.id,
        handle=author.handle,
        cleared=and_list(parts),
        reason=reason,
    )
    # Told in the bell, with the reason if there is one.
    notify(
        db,
        [member.id],
        "blog.author_cleared",
        f"The custodian cleared the {and_list(parts)} of your author profile on the blog"
        + (f": {reason}" if reason else "."),
        "/account/blog",
    )
    db.commit()
    remove_files(author, old)
    return AuthorPage(**card(author).model_dump(), yours=user.id == author.user_id, can_clear=True)


@router.get("/author-pictures/{author_id}/{picture_id}/{name}", response_class=FileResponse)
def picture_file(
    author_id: uuid.UUID, picture_id: uuid.UUID, name: str, db: DbSession, user: MaybeUser
) -> FileResponse:
    """One of an author's picture's files, for whoever may see their page."""
    author = db.get(BlogAuthor, author_id)
    root = pictures.upload_dir()
    path = (
        pictures.author_picture_file(root, author.id, picture_id, name)
        if author is not None
        and root is not None
        and author.picture_id == picture_id
        and viewable(db, user, author.handle)
        else None
    )
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such picture.")
    # Shown to people signed out, so any cache may keep it; but only for an hour, so
    # a picture the custodian clears, or of a page no longer shown, soon goes.
    return FileResponse(
        path,
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=3600"},
    )
