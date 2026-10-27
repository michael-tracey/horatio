"""Players' profiles: who someone is, for anyone signed in. The player edits their
own, and changes their handle; those who pick people (the custodian, and a
troupe's storytellers for its staff) list them by handle, and the custodian finds
anyone, and makes (or cancels) a reset link for someone locked out."""

import re
import uuid
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import aliased

from horatio import handles, pronouns
from horatio.api.auth import Me, me
from horatio.api.roster import LogEntry, log_entries
from horatio.audit import record
from horatio.auth.deps import CurrentUser, DbSession
from horatio.auth.resets import cancel_reset, email_reset, issue_reset, live_reset, reset_url
from horatio.connectors import email
from horatio.models import AuditEvent, Character, PasswordReset, Troupe, User
from horatio.permissions import (
    Role,
    TroupeAction,
    can_view_character,
    require_custodian,
    require_troupe_action,
)

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
    handle: str
    # When they joined: the account's creation, carried over from Yorick if imported.
    member_since: datetime
    # Such as "they/them"; None for none given.
    pronouns: str | None
    bio: str | None
    links: list[Link]
    discord_handle: str | None
    is_custodian: bool
    # Only for the player themself and the custodian.
    email: str | None
    # Their characters that the viewer may see.
    characters: list[PlayerCharacter]
    # When their live reset link expires, if they have one. Only for the custodian.
    reset_expires_at: datetime | None


class PlayerSummary(BaseModel):
    id: uuid.UUID
    display_name: str
    handle: str
    email: str
    member_since: datetime
    # When their live reset link expires, if they have one.
    reset_expires_at: datetime | None


class ProfileIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    # Empty for none; None leaves them as they are.
    pronouns: str | None = None
    bio: str | None = None
    links: list[Link] = []
    discord_handle: str | None = None


class Someone(BaseModel):
    """A person as others find them: never their email."""

    id: uuid.UUID
    handle: str
    display_name: str
    # Picking for a troupe: whether they have a character there, and their role
    # on its staff if they are on it.
    plays_here: bool = False
    staff_role: Role | None = None


class People(BaseModel):
    people: list[Someone]
    # Where the next page starts; None after the last.
    next_offset: int | None


class HandleIn(BaseModel):
    handle: str


class ResetIn(BaseModel):
    # Email the link to the player's address too.
    email: bool = False


class ResetLink(BaseModel):
    url: str
    expires_at: datetime
    # Where it was emailed, or why it could not be.
    emailed_to: str | None = None
    email_error: str | None = None


class LiveReset(BaseModel):
    user_id: uuid.UUID
    display_name: str
    email: str
    expires_at: datetime
    # Who made it: the custodian's name, or the player's own if they asked for it.
    made_by: str
    asked_themselves: bool


class PasswordResets(BaseModel):
    live: list[LiveReset]
    # Links made, emailed, asked for, cancelled and used, newest first.
    log: list[LogEntry]


# What the password resets log shows.
ACCOUNT_ACTIONS = (
    "account.reset_link",
    "account.reset_sent",
    "account.reset_email_failed",
    "account.reset_requested",
    "account.reset_cancelled",
    "account.password_reset",
)


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
        handle=user.handle,
        member_since=user.created_at,
        pronouns=user.pronouns,
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
        reset_expires_at=reset_expiry(db, user) if viewer.is_custodian else None,
    )


def reset_expiry(db: DbSession, user: User) -> datetime | None:
    live = live_reset(db, user)
    return live.expires_at if live else None


def web_address(url: str) -> str:
    """`url` trimmed, if it is an http or https address; refused otherwise, so a
    link can never run script (javascript:) or open something else."""
    url = url.strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc or len(url) > 300:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"{url or 'A link'} is not a web address: start it with https://.",
        )
    return url


def clean_link(link: Link) -> Link:
    url = web_address(link.url)
    host = urlsplit(url).netloc.removeprefix("www.")
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
def find_players(
    db: DbSession, user: CurrentUser, q: str = "", troupe_id: uuid.UUID | None = None
) -> list[PlayerSummary]:
    """Every account whose name, handle or email has `q` in it, for the custodian. With
    `troupe_id`, only those with an active PC whose home troupe is that troupe."""
    require_custodian(user)
    query = select(User).order_by(func.lower(User.display_name)).limit(50)
    if q.strip():
        like = f"%{q.strip().removeprefix('@')}%"
        query = query.where(
            or_(User.display_name.ilike(like), User.handle.ilike(like), User.email.ilike(like))
        )
    if troupe_id is not None:
        query = query.where(
            select(Character.id)
            .where(
                Character.player_id == User.id,
                Character.kind == "pc",
                Character.status == "active",
                Character.home_troupe_id == troupe_id,
            )
            .exists()
        )
    found = list(db.scalars(query))
    expiries = {
        user_id: expires_at
        for user_id, expires_at in db.execute(
            select(PasswordReset.user_id, PasswordReset.expires_at).where(
                PasswordReset.user_id.in_([u.id for u in found]),
                PasswordReset.expires_at > datetime.now(UTC),
            )
        )
    }
    return [
        PlayerSummary(
            id=u.id,
            display_name=u.display_name,
            handle=u.handle,
            email=u.email,
            member_since=u.created_at,
            reset_expires_at=expiries.get(u.id),
        )
        for u in found
    ]


@router.get("/handles")
def find_handles(
    db: DbSession,
    user: CurrentUser,
    q: str = "",
    troupe_id: uuid.UUID | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> People:
    """People to pick from, a page at a time: everyone, or with `q` those whose
    handle starts with it, then those whose name has it in it. Only for those who
    pick people: the custodian, and for a troupe, those who manage its staff, who
    see its players first and who is on its staff already."""
    troupe = None
    if troupe_id is None:
        require_custodian(user)
    else:
        troupe = db.get(Troupe, troupe_id)
        if troupe is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
        require_troupe_action(db, user, troupe, TroupeAction.MANAGE_STAFF)
    found = handles.find(db, q, troupe=troupe, offset=offset, limit=limit + 1)
    return People(
        people=[
            Someone(
                id=f.user.id,
                handle=f.user.handle,
                display_name=f.user.display_name,
                plays_here=f.plays_here,
                staff_role=Role(f.staff_role) if f.staff_role else None,
            )
            for f in found[:limit]
        ],
        next_offset=offset + limit if len(found) > limit else None,
    )


@router.put("/handle")
def change_handle(body: HandleIn, db: DbSession, user: CurrentUser) -> Me:
    """Change the signed-in person's handle: at most once in 30 days, and to one no
    one has or has held in the last 90."""
    handles.change(db, user, body.handle)
    db.commit()
    return me(user)


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
    said = user.pronouns if body.pronouns is None else pronouns.clean(body.pronouns)
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
    user.pronouns = said
    user.bio = bio or None
    user.links = [clean_link(link).model_dump() for link in links]
    user.discord_handle = clean_handle(body.discord_handle)
    db.commit()
    return profile(db, user, user)


@router.post("/players/{user_id}/password-reset", status_code=status.HTTP_201_CREATED)
def reset_password(
    user_id: uuid.UUID, db: DbSession, user: CurrentUser, body: ResetIn | None = None
) -> ResetLink:
    """A one-time link, good for a day, that lets the player set a new password.
    The custodian passes it on, or has Horatio email it to the player's address;
    it replaces any earlier link."""
    require_custodian(user)
    target = player(db, user_id)
    send = body is not None and body.email
    if send and not email.configured():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Email is not set up on this server, so copy the link and send it yourself.",
        )
    token, expires_at = issue_reset(db, target, user)
    record(db, user, "account.reset_link", member=target.display_name, user_id=target.id)
    link = ResetLink(url=reset_url(token), expires_at=expires_at)
    if send:
        link.email_error = email_reset(db, target, link.url, by=user)
        link.emailed_to = None if link.email_error else target.email
    db.commit()
    return link


@router.delete("/players/{user_id}/password-reset", status_code=status.HTTP_204_NO_CONTENT)
def cancel_password_reset(user_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    """Cancel the player's live reset link, so it no longer works."""
    require_custodian(user)
    target = player(db, user_id)
    if not cancel_reset(db, target):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no live reset link to cancel.")
    record(db, user, "account.reset_cancelled", member=target.display_name, user_id=target.id)
    db.commit()


@router.get("/password-resets")
def password_resets(db: DbSession, user: CurrentUser, limit: int = 50) -> PasswordResets:
    """For the custodian: the reset links live now, and who has made, asked for and
    used them."""
    require_custodian(user)
    maker = aliased(User)
    live = db.execute(
        select(PasswordReset, User, maker.display_name)
        .join(User, PasswordReset.user_id == User.id)
        .join(maker, PasswordReset.created_by_id == maker.id)
        .where(PasswordReset.expires_at > datetime.now(UTC))
        .order_by(PasswordReset.expires_at)
    )
    query = (
        select(AuditEvent, User.display_name)
        .outerjoin(User, AuditEvent.actor_id == User.id)
        .where(AuditEvent.action.in_(ACCOUNT_ACTIONS))
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(min(max(limit, 1), 500))
    )
    return PasswordResets(
        live=[
            LiveReset(
                user_id=u.id,
                display_name=u.display_name,
                email=u.email,
                expires_at=reset.expires_at,
                made_by=made_by,
                asked_themselves=reset.created_by_id == u.id,
            )
            for reset, u, made_by in live
        ],
        log=log_entries(db, query),
    )
