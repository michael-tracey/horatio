"""Players' profiles: who someone is, for anyone signed in. The player edits their
own; the custodian finds anyone, and makes a reset link for someone locked out."""

import re
import uuid
from datetime import datetime
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from horatio.audit import record
from horatio.auth.deps import CurrentUser, DbSession
from horatio.auth.resets import issue_reset
from horatio.config import get_settings
from horatio.models import Character, Troupe, User
from horatio.permissions import can_view_character, require_custodian

router = APIRouter(tags=["players"])

MAX_LINKS = 6
MAX_BIO = 2000
# Discord's usernames: 2 to 32 of a-z, 0-9, _ and ., never two full stops together.
DISCORD_HANDLE = re.compile(r"(?!.*\.\.)[a-z0-9_.]{2,32}")


class Link(BaseModel):
    label: str
    url: str


class PlayerCharacter(BaseModel):
    id: uuid.UUID
    name: str
    home_troupe: str | None
    retired: bool


class PlayerOut(BaseModel):
    id: uuid.UUID
    display_name: str
    # When they joined: the account's creation, carried over from Yorick if imported.
    member_since: datetime
    bio: str | None
    links: list[Link]
    discord_handle: str | None
    is_custodian: bool
    # Only for the player themself and the custodian.
    email: str | None
    # Their characters that the viewer may see.
    characters: list[PlayerCharacter]


class PlayerSummary(BaseModel):
    id: uuid.UUID
    display_name: str
    email: str
    member_since: datetime


class ProfileIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    bio: str | None = None
    links: list[Link] = []
    discord_handle: str | None = None


class ResetLink(BaseModel):
    url: str
    expires_at: datetime


def player(db: DbSession, user_id: uuid.UUID) -> User:
    found = db.get(User, user_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such player.")
    return found


def profile(db: DbSession, viewer: User, user: User) -> PlayerOut:
    characters = db.execute(
        select(Character, Troupe.name)
        .outerjoin(Troupe, Character.home_troupe_id == Troupe.id)
        .where(Character.player_id == user.id, Character.kind == "pc")
        .order_by(Character.status, func.lower(Character.name))
    )
    return PlayerOut(
        id=user.id,
        display_name=user.display_name,
        member_since=user.created_at,
        bio=user.bio,
        links=[Link(**link) for link in user.links],
        discord_handle=user.discord_handle,
        is_custodian=user.is_custodian,
        email=user.email if viewer.is_custodian or viewer.id == user.id else None,
        characters=[
            PlayerCharacter(id=c.id, name=c.name, home_troupe=home, retired=c.status == "retired")
            for c, home in characters
            if can_view_character(db, viewer, c)
        ],
    )


def clean_link(link: Link) -> Link:
    url = link.url.strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc or len(url) > 300:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"{url or 'A link'} is not a web address: start it with https://.",
        )
    host = parts.netloc.removeprefix("www.")
    return Link(label=link.label.strip()[:40] or host, url=url)


def clean_handle(handle: str | None) -> str | None:
    handle = (handle or "").strip().removeprefix("@").lower()
    if handle and not DISCORD_HANDLE.fullmatch(handle):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "A Discord username is 2 to 32 letters, numbers, underscores and full stops.",
        )
    return handle or None


@router.get("/players")
def find_players(db: DbSession, user: CurrentUser, q: str = "") -> list[PlayerSummary]:
    """Every account whose name or email has `q` in it, for the custodian."""
    require_custodian(user)
    query = select(User).order_by(func.lower(User.display_name)).limit(50)
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.where(or_(User.display_name.ilike(like), User.email.ilike(like)))
    return [
        PlayerSummary(
            id=u.id, display_name=u.display_name, email=u.email, member_since=u.created_at
        )
        for u in db.scalars(query)
    ]


@router.get("/players/{user_id}")
def view_player(user_id: uuid.UUID, db: DbSession, user: CurrentUser) -> PlayerOut:
    """A player's profile. Anyone signed in may see it; it never shows their email
    to anyone but themself and the custodian."""
    return profile(db, user, player(db, user_id))


@router.put("/profile")
def edit_profile(body: ProfileIn, db: DbSession, user: CurrentUser) -> PlayerOut:
    """The signed-in player's own profile."""
    name = body.display_name.strip()
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give a display name.")
    bio = (body.bio or "").strip()
    if len(bio) > MAX_BIO:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Keep the bio to {MAX_BIO} characters."
        )
    links = [link for link in body.links if link.url.strip()]
    if len(links) > MAX_LINKS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Give at most {MAX_LINKS} links."
        )
    user.display_name = name
    user.bio = bio or None
    user.links = [clean_link(link).model_dump() for link in links]
    user.discord_handle = clean_handle(body.discord_handle)
    db.commit()
    return profile(db, user, user)


@router.post("/players/{user_id}/password-reset", status_code=status.HTTP_201_CREATED)
def reset_password(user_id: uuid.UUID, db: DbSession, user: CurrentUser) -> ResetLink:
    """A one-time link, good for a day, that lets the player set a new password.
    The custodian passes it on; it replaces any earlier link."""
    require_custodian(user)
    target = player(db, user_id)
    token, expires_at = issue_reset(db, target, user)
    record(db, user, "account.reset_link", member=target.display_name, user_id=target.id)
    db.commit()
    return ResetLink(
        url=f"{get_settings().public_url.rstrip('/')}/reset-password/{token}",
        expires_at=expires_at,
    )
