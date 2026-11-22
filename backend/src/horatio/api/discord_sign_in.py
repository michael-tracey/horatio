"""Signing in, and signing up, with Discord (#1128).

The sign-in and sign-up pages send the person to Discord, asking for `identify`
and `email` only. Discord comes back through its one callback,
`/api/discord/callback`, which hands it here when its `state` begins with
`signin.` (horatio.api.discord). The state waits on the server, in
`discord_sign_ins`, and in a cookie: it works once, for 10 minutes, and only in the
browser that started it.

Discord says who they are, and Horatio finds the account by the Discord account's
id (horatio.discord_links.holder_of), never by its email:

- A linked account signs in, as a password does: refused while suspended, and for
  an account with a second step, Discord is only the first. The second step is
  asked for as after a password (horatio.auth.two_step), and only it signs them in.
- An account merged into another is refused.
- With no account linked, an account already using Discord's email is not linked
  to it: they sign in with their password, then link Discord in Account › Sign-in.
- Otherwise they sign up, with the email Discord has verified (refused if it has
  none): they choose their name and handle, as sign-up asks, on `/sign-up/discord`.
  What Discord said waits on the server for 30 minutes, named by another cookie.

Each try counts as a sign-in try from where it comes, at a login of its own,
"Discord" (horatio.auth.attempts.DISCORD), and a new account as a sign-up. The
audit log has them as it has password sign-ins, with `kind` saying Discord.
"""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from horatio import discord_links, handles, notifications, suspensions
from horatio.api.auth import (
    Me,
    me,
    set_second_step_cookie,
    set_session_cookie,
    user_by_email,
)
from horatio.api.discord_account import link
from horatio.audit import record, sign_in_ip
from horatio.auth import attempts, two_step
from horatio.auth.deps import DbSession
from horatio.auth.resets import same_site_path
from horatio.auth.sessions import hash_token, start_session
from horatio.auth.two_step import allowed_first
from horatio.config import get_settings
from horatio.connectors import SendError, discord
from horatio.models import DiscordSignIn, User

router = APIRouter(prefix="/auth/discord", tags=["auth"])

# The state, between the sign-in page and Discord's callback.
COOKIE = "horatio_discord_sign_in"
COOKIE_PATH = "/api/discord"
STATE_FOR = timedelta(minutes=10)
# What Discord said of someone with no account, between the callback and the sign-up.
SIGN_UP_COOKIE = "horatio_discord_sign_up"
SIGN_UP_PATH = "/api/auth/discord"
SIGN_UP_FOR = timedelta(minutes=30)
# How many may wait from one place at once, while sign-ins are limited: as for
# passkeys, a whole troupe may sign in together on a venue's Wi-Fi. Only so the
# table can't be filled without end.
WAITING_FROM_ONE_PLACE = 200

GONE = "That took too long. Sign up with Discord again."


class DiscordSignInHelp(BaseModel):
    # Whether Discord is set up on this server, so the pages offer it.
    available: bool


class DiscordStart(BaseModel):
    # Where they were going, to go on to once signed in: a path on this site.
    next: str | None = None


class DiscordStarted(BaseModel):
    # Discord's page, to send the browser to.
    url: str


class DiscordSignUpFor(BaseModel):
    """What Discord said of someone with no account yet, to start the form with."""

    # The email Discord has verified, which the account is made with.
    email: str
    # Their Discord username, to say which account it is.
    discord_username: str
    # Suggestions: the name they show on Discord, and a free handle made from it.
    display_name: str
    handle: str


class DiscordSignUp(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    # How others will find them (horatio.handles); made from their name if not given.
    handle: str | None = None


@router.get("")
@allowed_first
def discord_sign_in_help() -> DiscordSignInHelp:
    """Whether someone can sign in, or up, with Discord here."""
    return DiscordSignInHelp(available=discord.configured())


@router.post("/start")
@allowed_first
def start(
    body: DiscordStart, request: Request, db: DbSession, response: Response
) -> DiscordStarted:
    """Discord's page for signing in with Discord. The state waits here, and in a
    cookie for the callback, for 10 minutes."""
    if not discord.configured():
        raise HTTPException(status.HTTP_409_CONFLICT, "Discord isn't set up on this server yet.")
    ip = attempts.source(request)
    db.execute(delete(DiscordSignIn).where(DiscordSignIn.expires_at <= func.now()))
    from_there = DiscordSignIn.ip_address == ip if ip else DiscordSignIn.ip_address.is_(None)
    waiting = db.scalar(select(func.count()).where(from_there)) or 0
    if get_settings().auth_limits and waiting >= WAITING_FROM_ONE_PLACE:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, attempts.SIGN_INS_WAIT)
    token = secrets.token_urlsafe(32)
    db.add(
        DiscordSignIn(
            token_hash=hash_token(token),
            ip_address=ip,
            expires_at=datetime.now(UTC) + STATE_FOR,
            next=same_site_path(body.next),
        )
    )
    db.commit()
    response.set_cookie(
        COOKIE,
        token,
        max_age=int(STATE_FOR.total_seconds()),
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="lax",
        path=COOKIE_PATH,
    )
    return DiscordStarted(url=discord.sign_in_url(token))


def take(db: Session, token: str, *, signing_up: bool) -> DiscordSignIn | None:
    """The waiting row the token names, if it hasn't timed out: a state waiting on
    Discord, or with `signing_up`, a sign-up waiting on a name and handle."""
    waiting = (
        DiscordSignIn.discord_user_id.isnot(None)
        if signing_up
        else (DiscordSignIn.discord_user_id.is_(None))
    )
    return db.scalar(
        select(DiscordSignIn)
        .where(
            DiscordSignIn.token_hash == hash_token(token),
            DiscordSignIn.expires_at > func.now(),
            # Not someone signed in confirming it's them (horatio.api.discord_confirm).
            DiscordSignIn.session_id.is_(None),
            waiting,
        )
        .with_for_update()
    )


def with_next(path: str, then: str | None, **query: str) -> str:
    """`path`, with `query` and somewhere to go on to after, if any."""
    params = {**query, **({"next": then} if then else {})}
    return f"{path}?{urlencode(params)}" if params else path


def finish_sign_in(
    request: Request, db: Session, state: str, code: str | None, error: str | None
) -> RedirectResponse:
    """Discord's callback for signing in (horatio.api.discord.discord_callback)."""
    then: str | None = None

    def go(path: str) -> RedirectResponse:
        answer = RedirectResponse(path, status_code=303)
        answer.delete_cookie(COOKIE, path=COOKIE_PATH)
        return answer

    def back(outcome: str) -> RedirectResponse:
        """To the sign-in page, saying why they aren't signed in."""
        return go(with_next("/sign-in", then, discord=outcome))

    token = state.removeprefix(discord.SIGN_IN_STATE)
    expected = request.cookies.get(COOKIE) or ""
    if not token or not secrets.compare_digest(token, expected):
        return back("expired")
    # Used up, and committed, before Discord is asked: it works once either way.
    waiting = take(db, token, signing_up=False)
    if waiting is not None:
        then = waiting.next
        db.delete(waiting)
    db.commit()
    if waiting is None:
        return back("expired")
    if error or not code:
        return back("cancelled")

    ip = attempts.source(request)
    from_ip = sign_in_ip(db, request)
    if (held := attempts.discord_held_back(db, ip)) is not None:
        record(
            db,
            None,
            "account.sign_in_throttled" if held.first else "account.sign_in_throttled_again",
            kind="discord",
            limit=held.limit.key,
            **from_ip,
        )
        db.commit()
        return back("throttled")
    try:
        account = discord.account_from_code(code)
    except SendError:
        record(db, None, "account.sign_in_failed", kind="discord", **from_ip)
        db.commit()
        return back("failed")

    def failed(user: User | None, kind: str, outcome: str) -> RedirectResponse:
        whose: dict[str, Any] = {} if user is None else {"member": user.display_name}
        if user is not None:
            whose["user_id"] = user.id
        record(db, user, "account.sign_in_failed", kind=kind, **whose, **from_ip)
        db.commit()
        return back(outcome)

    user = discord_links.holder_of(db, account.id)
    if user is not None and user.merged_into_id is not None:
        return failed(user, "discord_merged", "merged")
    if user is None:
        if not account.email or not account.verified:
            return failed(None, "discord_no_email", "no_email")
        if (using := user_by_email(db, account.email)) is not None:
            # Never linked by email: whoever has the email signs in with their password,
            # and links Discord themselves.
            return failed(using, "discord_email", "email_taken")
        # Discord has said who they are; signing up is a try of its own.
        attempts.signed_in_at(db, attempts.DISCORD, ip)
        db.execute(delete(DiscordSignIn).where(DiscordSignIn.expires_at <= func.now()))
        sign_up_token = secrets.token_urlsafe(32)
        db.add(
            DiscordSignIn(
                token_hash=hash_token(sign_up_token),
                ip_address=ip,
                expires_at=datetime.now(UTC) + SIGN_UP_FOR,
                next=then,
                discord_user_id=account.id,
                email=account.email,
                discord_username=account.username,
                discord_name=account.name,
            )
        )
        db.commit()
        answer = go(with_next("/sign-up/discord", then))
        answer.set_cookie(
            SIGN_UP_COOKIE,
            sign_up_token,
            max_age=int(SIGN_UP_FOR.total_seconds()),
            httponly=True,
            secure=get_settings().cookie_secure,
            samesite="lax",
            path=SIGN_UP_PATH,
        )
        return answer

    try:
        suspensions.refuse(db, user)
    except HTTPException:
        return failed(user, "discord_suspended", "suspended")
    # Linked before Discord could sign in (#857), or by an identity row alone: the
    # two agree from now on.
    if user.discord_user_id is None:
        user.discord_user_id = account.id
    discord_links.keep_identity(db, user)
    whose = {"member": user.display_name, "user_id": user.id}
    if two_step.has_second_step(db, user):
        # Discord is the first step only; its tries still count as failed until the
        # second step signs them in.
        answer = go(with_next("/sign-in/second-step", then))
        set_second_step_cookie(answer, two_step.begin(db, user, attempts.DISCORD))
        record(db, user, "account.second_step_asked", kind="discord", **whose, **from_ip)
        db.commit()
        return answer
    attempts.signed_in_at(db, attempts.DISCORD, ip)
    record(db, user, "account.signed_in", kind="discord", **whose, **from_ip)
    answer = go(then or "/characters")
    set_session_cookie(answer, start_session(db, user, request))
    db.commit()
    return answer


def signing_up(db: Session, request: Request) -> DiscordSignIn:
    """The sign-up waiting on a name and handle in this browser; 410 if none, or it
    has timed out."""
    token = request.cookies.get(SIGN_UP_COOKIE)
    waiting = take(db, token, signing_up=True) if token else None
    if waiting is None:
        raise HTTPException(status.HTTP_410_GONE, GONE)
    return waiting


@router.get("/sign-up")
@allowed_first
def sign_up_for(request: Request, db: DbSession) -> DiscordSignUpFor:
    """What Discord said of someone signing up with it, to start the form with."""
    waiting = signing_up(db, request)
    username = waiting.discord_username or ""
    name = waiting.discord_name or username or "Player"
    return DiscordSignUpFor(
        email=waiting.email or "",
        discord_username=username,
        display_name=name,
        handle=handles.suggest(db, username or name),
    )


@router.post("/sign-up", status_code=status.HTTP_201_CREATED)
@allowed_first
def sign_up(body: DiscordSignUp, request: Request, db: DbSession, response: Response) -> Me:
    """Make the account Discord sign-in waited on, with the email Discord verified, the
    name and handle chosen, no password, and the Discord account linked; and sign in."""
    if (held := attempts.sign_up_held_back(db, attempts.source(request))) is not None:
        record(
            db,
            None,
            "account.sign_up_throttled" if held.first else "account.sign_up_throttled_again",
            kind="discord",
            limit=held.limit.key,
            **sign_in_ip(db, request),
        )
        db.commit()
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, held.wait)
    waiting = signing_up(db, request)
    assert waiting.discord_user_id is not None and waiting.email is not None
    if discord_links.holder_of(db, waiting.discord_user_id) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "That Discord account has a Horatio account already. Sign in with Discord.",
        )
    if user_by_email(db, waiting.email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with that email already exists.")
    user = User(
        email=waiting.email,
        display_name=body.display_name,
        handle=(
            handles.choose(db, body.handle)
            if body.handle and body.handle.strip()
            else handles.suggest(db, body.display_name)
        ),
        password_hash=None,
    )
    db.add(user)
    db.flush()
    said = discord.Account(id=waiting.discord_user_id, username=waiting.discord_username or "")
    link(db, user, said)
    notifications.signed_up(db, user)
    from_ip = sign_in_ip(db, request)
    whose = {"member": user.display_name, "user_id": user.id}
    record(db, user, "account.signed_up", kind="discord", **whose, **from_ip)
    record(db, user, "account.discord_linked", discord=user.discord_handle or "")
    discord_links.account_linked(db, user)
    db.delete(waiting)
    set_session_cookie(response, start_session(db, user, request))
    response.delete_cookie(SIGN_UP_COOKIE, path=SIGN_UP_PATH)
    db.commit()
    return me(user, db)
