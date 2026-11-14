"""A player linking their own Discord account (#857): Discord confirms who they
are, so Horatio knows their Discord account rather than a username they typed.

Linking uses the `identify` scope only, and changes nothing about how they sign
in. It comes back through Discord's one callback, `/api/discord/callback`, which
hands it here when its `state` begins with `link.` (horatio.api.discord). The
state's other half is also kept in a short-lived cookie, so only the browser that
started linking can finish it.

A Discord account linked to another Horatio account is refused. Unlinking is
refused while Discord is the person's only way to sign in.
"""

import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select

from horatio import audit, discord_links
from horatio.api.players import DISCORD_HANDLE
from horatio.auth.deps import CurrentUser, DbSession
from horatio.config import get_settings
from horatio.connectors import SendError, discord
from horatio.models import AuthIdentity, User

router = APIRouter(tags=["players"])

# Holds the linking state between Horatio and Discord's callback.
COOKIE = "horatio_discord_link"
COOKIE_MINUTES = 10


class DiscordAccount(BaseModel):
    # Whether Discord is set up on this server, so linking is possible.
    available: bool
    linked: bool
    # Their Discord username: from Discord when linked, else as they typed it.
    handle: str | None
    # Whether unlinking is allowed: not while Discord is their only way to sign in.
    can_unlink: bool


class LinkStart(BaseModel):
    url: str


def only_by_discord(db: DbSession, user: User) -> bool:
    """Whether Discord is the only way this person signs in."""
    if user.password_hash:
        return False
    others = db.scalars(
        select(AuthIdentity.provider).where(
            AuthIdentity.user_id == user.id, AuthIdentity.provider != "discord"
        )
    ).first()
    return others is None


def account_of(db: DbSession, user: User) -> DiscordAccount:
    linked = user.discord_user_id is not None
    return DiscordAccount(
        available=discord.configured(),
        linked=linked,
        handle=user.discord_handle,
        can_unlink=linked and not only_by_discord(db, user),
    )


@router.get("/account/discord")
def discord_account(db: DbSession, user: CurrentUser) -> DiscordAccount:
    """The signed-in person's Discord account, linked or not."""
    return account_of(db, user)


@router.post("/account/discord/link")
def start_link(response: Response, user: CurrentUser) -> LinkStart:
    """Discord's page for linking. Its other half of the state goes in a cookie."""
    if not discord.configured():
        raise HTTPException(status.HTTP_409_CONFLICT, "Discord isn't set up on this server yet.")
    token = secrets.token_urlsafe(24)
    response.set_cookie(
        COOKIE,
        token,
        max_age=COOKIE_MINUTES * 60,
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="lax",
        path="/",
    )
    return LinkStart(url=discord.link_url(f"{user.id}.{token}"))


@router.delete("/account/discord")
def unlink(db: DbSession, user: CurrentUser) -> DiscordAccount:
    """Forget the person's Discord account. Their Discord username stays, as typed."""
    if user.discord_user_id is None:
        return account_of(db, user)
    if only_by_discord(db, user):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Discord is your only way to sign in, so it stays linked.",
        )
    user.discord_user_id = None
    audit.record(db, user, "account.discord_unlinked")
    db.commit()
    return account_of(db, user)


def finish_link(
    request: Request,
    db: DbSession,
    user: User,
    state: str,
    code: str | None,
    error: str | None,
) -> RedirectResponse:
    """Discord's callback for linking (horatio.api.discord.discord_callback)."""

    def back(outcome: str) -> RedirectResponse:
        answer = RedirectResponse(f"/account?{urlencode({'discord': outcome})}", status_code=303)
        answer.delete_cookie(COOKIE, path="/")
        return answer

    whose, _, token = state.removeprefix(discord.LINK_STATE).partition(".")
    expected = request.cookies.get(COOKIE) or ""
    if whose != str(user.id) or not token or not secrets.compare_digest(token, expected):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That link has expired; try again.")
    if error or not code:
        return back("cancelled")
    try:
        account = discord.account_from_code(code)
    except SendError as failure:
        return back(failure.reason)
    holder = db.scalars(
        select(User).where(User.discord_user_id == account.id, User.id != user.id)
    ).first()
    if holder is not None:
        audit.record(db, user, "account.discord_link_refused", other_user_id=holder.id)
        db.commit()
        return back("taken")
    user.discord_user_id = account.id
    if DISCORD_HANDLE.fullmatch(account.username):
        user.discord_handle = account.username
    audit.record(db, user, "account.discord_linked", discord=user.discord_handle or "")
    discord_links.account_linked(db, user)
    db.commit()
    return back("linked")
