"""Confirming it's you with Discord, for an account with no password (#1140).

Adding, replacing or removing a passkey, setting up or turning off the authenticator
app and new recovery codes ask for the password again (#1110, #1148), and an account
made with Discord (#1128) has none. Such an account, with Discord linked, confirms
it's them by going through Discord instead. Discord comes back through its one callback,
`/api/discord/callback`, which hands it here when its `state` begins with `confirm.`
(horatio.api.discord).

The state waits on the server, in `discord_sign_ins` with the sign-in it belongs to,
and in a cookie: it works once, for 10 minutes, only in the browser and sign-in that
started it. Discord must say it is the Discord account linked to theirs. Then that
sign-in is confirmed for 5 minutes, and stands in for the password once
(horatio.api.two_step.check_password). An account with a password gives it instead.

Each try counts towards the limit on password tries at the account (#1095), as a
password given there does. The audit log has each confirmation, and each refusal.
"""

import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from horatio.api.discord_sign_in import DiscordStarted
from horatio.api.two_step import this_session
from horatio.audit import record, sign_in_ip
from horatio.auth import attempts
from horatio.auth.deps import CurrentUser, DbSession
from horatio.auth.resets import same_site_path
from horatio.auth.sessions import hash_token, user_for_token
from horatio.auth.two_step import ACCOUNT_PAGE, allowed_first
from horatio.config import get_settings
from horatio.connectors import SendError, discord
from horatio.models import DiscordSignIn, User
from horatio.models import Session as SignInSession

router = APIRouter(prefix="/auth/discord", tags=["auth"])

# The state, between the page and Discord's callback.
COOKIE = "horatio_discord_confirm"
COOKIE_PATH = "/api/discord"
STATE_FOR = timedelta(minutes=10)
# How long a confirmation stands in for the password, used once.
CONFIRMED_FOR = timedelta(minutes=5)


class DiscordConfirmStart(BaseModel):
    # Where to come back to: a path on this site, saying what they were doing.
    # Account › Sign-in if not given.
    next: str | None = None


@router.post("/confirm")
@allowed_first
def start_confirm(
    body: DiscordConfirmStart,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    response: Response,
) -> DiscordStarted:
    """Discord's page for confirming it's you, in place of a password you don't have.
    The state waits here, and in a cookie for the callback, for 10 minutes."""
    if not discord.configured():
        raise HTTPException(status.HTTP_409_CONFLICT, "Discord isn't set up on this server yet.")
    if user.password_hash is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "You have a password: give it to confirm it's you."
        )
    if user.discord_user_id is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "You have no Discord account linked. Set a password with Forgot your password? on"
            " the sign-in page instead.",
        )
    session = this_session(request, db, user)
    # One at a time from a sign-in: starting again forgets the last.
    db.execute(
        delete(DiscordSignIn).where(
            (DiscordSignIn.expires_at <= func.now()) | (DiscordSignIn.session_id == session.id)
        )
    )
    token = secrets.token_urlsafe(32)
    db.add(
        DiscordSignIn(
            token_hash=hash_token(token),
            ip_address=attempts.source(request),
            expires_at=datetime.now(UTC) + STATE_FOR,
            next=same_site_path(body.next),
            session_id=session.id,
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
    return DiscordStarted(url=discord.confirm_url(token))


def signed_in(request: Request, db: Session) -> tuple[SignInSession, User] | None:
    """The live sign-in this request comes with, and whose it is, if any: their own,
    never someone the custodian views as."""
    token = request.cookies.get(get_settings().session_cookie_name)
    user = user_for_token(db, token) if token else None
    if token is None or user is None:
        return None
    session = db.scalar(
        select(SignInSession).where(
            SignInSession.token_hash == hash_token(token), SignInSession.user_id == user.id
        )
    )
    return None if session is None else (session, user)


def confirmed(session: SignInSession) -> bool:
    """Whether the sign-in is confirmed with Discord now."""
    return session.confirmed_until is not None and session.confirmed_until > datetime.now(UTC)


def with_outcome(path: str, outcome: str) -> str:
    """`path`, which may have a query of its own, saying how confirming went."""
    joiner = "&" if "?" in path else "?"
    return f"{path}{joiner}{urlencode({'discord_confirm': outcome})}"


def finish_confirm(
    request: Request, db: Session, state: str, code: str | None, error: str | None
) -> RedirectResponse:
    """Discord's callback for confirming it's you (horatio.api.discord.discord_callback)."""
    then = ACCOUNT_PAGE

    def back(outcome: str) -> RedirectResponse:
        answer = RedirectResponse(with_outcome(then, outcome), status_code=303)
        answer.delete_cookie(COOKIE, path=COOKIE_PATH)
        return answer

    token = state.removeprefix(discord.CONFIRM_STATE)
    expected = request.cookies.get(COOKIE) or ""
    found = signed_in(request, db)
    if not token or not secrets.compare_digest(token, expected) or found is None:
        return back("expired")
    session, user = found
    # Used up, and committed, before Discord is asked: it works once either way.
    waiting = db.scalar(
        select(DiscordSignIn)
        .where(
            DiscordSignIn.token_hash == hash_token(token),
            DiscordSignIn.expires_at > func.now(),
            DiscordSignIn.session_id == session.id,
        )
        .with_for_update()
    )
    if waiting is not None:
        then = waiting.next or then
        db.delete(waiting)
    db.commit()
    if waiting is None:
        return back("expired")
    if error or not code:
        return back("cancelled")
    if user.password_hash is not None or user.discord_user_id is None:
        return back("not_needed")

    from_ip = sign_in_ip(db, request)
    whose = {"member": user.display_name, "user_id": user.id}
    if (held := attempts.password_change_held_back(db, user.id)) is not None:
        record(
            db,
            user,
            "account.password_change_throttled"
            if held.first
            else "account.password_change_throttled_again",
            kind="discord_confirm",
            limit=held.limit.key,
            **whose,
            **from_ip,
        )
        db.commit()
        return back("throttled")
    try:
        account = discord.account_from_code(code)
    except SendError:
        record(db, user, "account.discord_confirm_failed", **whose, **from_ip)
        db.commit()
        return back("failed")
    if account.id != user.discord_user_id:
        record(db, user, "account.discord_confirm_failed", kind="other_account", **whose, **from_ip)
        db.commit()
        return back("other_account")
    session.confirmed_until = datetime.now(UTC) + CONFIRMED_FOR
    record(db, user, "account.discord_confirmed", **whose, **from_ip)
    db.commit()
    return back("confirmed")
