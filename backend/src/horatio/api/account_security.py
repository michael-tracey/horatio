"""Account › Sign-in's view of an account's safety (#1193): where it is signed in,
with a way to sign out there, and its recent sign-ins from the audit log.

Addresses follow the custodian's "Record IP addresses with sign-in events" setting
(horatio.audit.sign_in_ip): kept only while it is on, shown only while it still is,
and then only coarsely (horatio.auth.devices.place).

Signing out elsewhere asks for no password: it only ever takes access away, and
someone with no password (an account made with Discord) must be able to do it too."""

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select, update

from horatio import audit
from horatio.audit import record, sign_in_ip
from horatio.auth import devices
from horatio.auth.deps import CurrentUser, DbSession
from horatio.auth.sessions import hash_token, live
from horatio.config import get_settings
from horatio.models import AuditEvent, User
from horatio.models import Session as SignInSession

router = APIRouter(prefix="/account", tags=["auth"])


class SignedInAt(BaseModel):
    """One sign-in session still going."""

    id: uuid.UUID
    # The browser and system it was started from: "Firefox on Windows".
    device: str
    signed_in_at: datetime
    # When it was last used, to within a few minutes; None for one from before it was kept.
    last_active_at: datetime | None
    # Roughly where it was started from, "203.0.113.…": only while the custodian
    # records addresses with sign-in events, and None for one started while they didn't.
    place: str | None
    # It's the one this request comes with.
    this_device: bool


class RecentSignIn(BaseModel):
    at: datetime
    # Signed in; a wrong password or second step; or turned away by the limits.
    outcome: Literal["signed_in", "failed", "turned_away"]
    # How, in plain words: "Password, then authenticator app", "Wrong password".
    how: str
    # As for SignedInAt.place.
    place: str | None


class RecentSignIns(BaseModel):
    sign_ins: list[RecentSignIn]
    # Whether the log keeps every sign-in now. Signing in and wrong passwords are
    # routine (debug) events, kept only while the custodian records those; wrong
    # second steps and being turned away are always kept.
    all_kept: bool


class SignedOutElsewhere(BaseModel):
    # How many sign-ins were ended.
    ended: int


# How many recent sign-ins are shown.
RECENT = 10

# Each sign-in event at an account, and how it reads, by its kind (None: no kind).
HOW: dict[str, dict[str | None, str]] = {
    "account.signed_in": {
        None: "Password",
        "app": "Password, then authenticator app",
        "recovery_code": "Password, then a recovery code",
        "passkey": "Password, then a passkey",
        "passkey_alone": "Passkey alone",
        "discord": "Discord",
    },
    "account.sign_in_failed": {
        None: "Wrong password",
        "passkey": "A passkey that didn't check out",
        "discord_email": "A Discord account not linked to yours",
        "discord_suspended": "Discord, while suspended",
    },
    "account.second_step_failed": {
        None: "A wrong second step",
        "app": "A wrong code from the authenticator app",
        "recovery_code": "A wrong or used recovery code",
        "passkey": "A passkey that isn't yours, as a second step",
    },
    "account.sign_in_throttled": {None: "Too many tries"},
    "account.sign_in_throttled_again": {None: "Too many tries"},
    "account.second_step_throttled": {None: "Too many wrong codes"},
    "account.second_step_throttled_again": {None: "Too many wrong codes"},
}
# After Discord as the first step, a second step reads so.
AFTER_DISCORD: dict[str | None, str] = {
    "app": "Discord, then authenticator app",
    "recovery_code": "Discord, then a recovery code",
    "passkey": "Discord, then a passkey",
}
OUTCOMES: dict[str, Literal["signed_in", "failed", "turned_away"]] = {
    "account.signed_in": "signed_in",
    "account.sign_in_failed": "failed",
    "account.second_step_failed": "failed",
    "account.sign_in_throttled": "turned_away",
    "account.sign_in_throttled_again": "turned_away",
    "account.second_step_throttled": "turned_away",
    "account.second_step_throttled_again": "turned_away",
}


def how(action: str, data: dict[str, Any]) -> str:
    """How a sign-in event reads on the account's own page."""
    kind = data.get("kind")
    if action == "account.signed_in" and data.get("after") == "discord" and kind in AFTER_DISCORD:
        return AFTER_DISCORD[kind]
    worded = HOW[action]
    return worded.get(kind, worded[None])


def places_shown(db: DbSession) -> bool:
    """Whether addresses are shown now: only while the custodian records them."""
    return audit.settings(db).sign_in_ips


def this_token_hash(request: Request) -> str | None:
    token = request.cookies.get(get_settings().session_cookie_name)
    return hash_token(token) if token else None


@router.get("/sessions")
def sessions(request: Request, db: DbSession, user: CurrentUser) -> list[SignedInAt]:
    """Where you're signed in: each sign-in still going, this device first, then the
    most recently used."""
    mine = this_token_hash(request)
    shown = places_shown(db)
    rows = db.scalars(
        select(SignInSession)
        .where(SignInSession.user_id == user.id, *live())
        .order_by(
            SignInSession.last_active_at.desc().nulls_last(),
            SignInSession.created_at.desc(),
            SignInSession.id.desc(),
        )
    ).all()
    found = [
        SignedInAt(
            id=s.id,
            device=devices.device(s.user_agent),
            signed_in_at=s.created_at,
            last_active_at=s.last_active_at,
            place=devices.place(s.ip_address) if shown else None,
            this_device=s.token_hash == mine,
        )
        for s in rows
    ]
    return sorted(found, key=lambda s: not s.this_device)


def own_live_session(db: DbSession, user: User, session_id: uuid.UUID) -> SignInSession:
    session = db.scalar(
        select(SignInSession).where(
            SignInSession.id == session_id, SignInSession.user_id == user.id, *live()
        )
    )
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That sign-in has ended already.")
    return session


@router.post("/sessions/{session_id}/sign-out", status_code=status.HTTP_204_NO_CONTENT)
def sign_out_there(
    session_id: uuid.UUID, request: Request, db: DbSession, user: CurrentUser
) -> None:
    """Sign out one of your other sign-ins. This one signs out with /auth/logout."""
    session = own_live_session(db, user, session_id)
    if session.token_hash == this_token_hash(request):
        raise HTTPException(status.HTTP_409_CONFLICT, "That's this device: choose Sign out.")
    session.revoked_at = datetime.now(UTC)
    record(
        db,
        user,
        "account.session_ended",
        member=user.display_name,
        user_id=user.id,
        device=devices.device(session.user_agent),
        **sign_in_ip(db, request),
    )
    db.commit()


@router.post("/sessions/sign-out-others")
def sign_out_everywhere_else(
    request: Request, db: DbSession, user: CurrentUser
) -> SignedOutElsewhere:
    """Sign out every sign-in you have but this one."""
    others = [SignInSession.user_id == user.id, *live()]
    if (mine := this_token_hash(request)) is not None:
        others.append(SignInSession.token_hash != mine)
    ended = len(
        db.execute(
            update(SignInSession)
            .where(*others)
            .values(revoked_at=datetime.now(UTC))
            .returning(SignInSession.id)
        ).all()
    )
    record(
        db,
        user,
        "account.other_sessions_ended",
        member=user.display_name,
        user_id=user.id,
        ended=f"{ended} sign-in" if ended == 1 else f"{ended} sign-ins",
        **sign_in_ip(db, request),
    )
    db.commit()
    return SignedOutElsewhere(ended=ended)


@router.get("/sign-ins")
def recent_sign_ins(db: DbSession, user: CurrentUser) -> RecentSignIns:
    """Your last few sign-ins, and tries at your account that failed, as the audit
    log has them."""
    shown = places_shown(db)
    events = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.actor_id == user.id, AuditEvent.action.in_(HOW))
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(RECENT)
    ).all()
    return RecentSignIns(
        sign_ins=[
            RecentSignIn(
                at=e.created_at,
                outcome=OUTCOMES[e.action],
                how=how(e.action, e.data),
                place=devices.place(e.data.get("ip")) if shown else None,
            )
            for e in events
        ],
        all_kept=audit.recorded(db, "debug"),
    )
