"""Viewing as someone: the custodian sees Horatio exactly as one person does, with
their permissions, read-only, for support (CONTEXT.md: View As).

A viewing belongs to the custodian's own sign-in. While it is live, every request
that sign-in makes is answered as the person (horatio.auth.deps), and nothing
changes:

- every change (any request but GET, HEAD and OPTIONS) is refused before it reaches
  its route, except stopping and signing out (`read_only_while_viewing`);
- and the request's database session refuses to write at all, so a GET that would
  write something on the side cannot either (`refuse_writes`).

It ends after 30 minutes, when the custodian stops, or when they sign out. Starting
and ending go in the audit log, with the custodian's reason.
"""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import event, select, update
from sqlalchemy.orm import ORMExecuteState, Session

from horatio.audit import record
from horatio.auth.sessions import hash_token
from horatio.config import get_settings
from horatio.db import get_session
from horatio.models import Session as SignInSession
from horatio.models import User, Viewing

VIEW_FOR = timedelta(minutes=30)
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# On a database session serving someone viewing as another: why it may not write.
READ_ONLY = "horatio.read_only"
# Routes that still work while viewing: stopping, and signing out.
ALLOWED: set[Callable[..., Any]] = set()


def allowed_while_viewing[F: Callable[..., Any]](endpoint: F) -> F:
    ALLOWED.add(endpoint)
    return endpoint


def end(db: Session, viewing: Viewing, kind: str, *, at: datetime | None = None) -> None:
    """End a viewing, recording how: "stopped", "signed_out", "timed_out" or
    "not_custodian". Only the first to end it records it, should two requests find
    it at once."""
    ended = db.execute(
        update(Viewing)
        .where(Viewing.id == viewing.id, Viewing.ended_at.is_(None))
        .values(ended_at=at or datetime.now(UTC))
        .returning(Viewing.id)
    ).first()
    if ended is None:
        return
    person = db.get_one(User, viewing.user_id)
    record(
        db,
        db.get(User, viewing.custodian_id),
        "account.view_as_ended",
        member=person.display_name,
        user_id=person.id,
        handle=person.handle,
        kind=kind,
    )


def live(db: Session, token: str) -> Viewing | None:
    """The viewing a sign-in token's session has going, if any. One found timed out,
    or whose custodian is one no longer, is ended here."""
    now = datetime.now(UTC)
    row = db.execute(
        select(Viewing, User.is_custodian)
        .join(SignInSession, Viewing.session_id == SignInSession.id)
        .join(User, SignInSession.user_id == User.id)
        .where(
            SignInSession.token_hash == hash_token(token),
            SignInSession.revoked_at.is_(None),
            SignInSession.expires_at > now,
            Viewing.ended_at.is_(None),
        )
        .order_by(Viewing.created_at.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    viewing, is_custodian = row
    if viewing.ends_at <= now:
        end(db, viewing, "timed_out", at=viewing.ends_at)
    elif not is_custodian:
        end(db, viewing, "not_custodian")
    else:
        return viewing
    db.commit()
    return None


_UNKNOWN = object()


def viewing_for(request: Request, db: Session) -> Viewing | None:
    """The viewing this request's sign-in has going, worked out once per request."""
    known = getattr(request.state, "viewing", _UNKNOWN)
    if isinstance(known, Viewing) or known is None:
        return known
    token = request.cookies.get(get_settings().session_cookie_name)
    found = live(db, token) if token else None
    request.state.viewing = found
    return found


def refusal(db: Session, viewing: Viewing) -> str:
    handle = db.get_one(User, viewing.user_id).handle
    return f"You are viewing Horatio as @{handle}, read-only. Stop viewing to make changes."


def read_only_while_viewing(
    request: Request, db: Annotated[Session, Depends(get_session)]
) -> Iterator[None]:
    """For every API route: while the custodian views as someone, refuse every
    change, and keep the database session from writing anything for the rest of
    the request."""
    route = request.scope.get("route")
    if getattr(route, "endpoint", None) in ALLOWED:
        yield
        return
    viewing = viewing_for(request, db)
    if viewing is None:
        yield
        return
    why = refusal(db, viewing)
    if request.method not in SAFE_METHODS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, why)
    db.info[READ_ONLY] = why
    try:
        yield
    finally:
        db.info.pop(READ_ONLY, None)
        # Anything a refused write left pending goes with it.
        db.rollback()


def read_only(db: Session) -> bool:
    """Whether this database session is serving someone viewing as another, so may
    not write: for the few GETs that write something on the side, to skip it."""
    return READ_ONLY in db.info


@event.listens_for(Session, "before_flush")
def refuse_writes(db: Session, _context: object, _instances: object) -> None:
    if READ_ONLY in db.info:
        raise HTTPException(status.HTTP_403_FORBIDDEN, db.info[READ_ONLY])


@event.listens_for(Session, "do_orm_execute")
def refuse_statements(state: ORMExecuteState) -> None:
    if READ_ONLY in state.session.info and (state.is_insert or state.is_update or state.is_delete):
        raise HTTPException(status.HTTP_403_FORBIDDEN, state.session.info[READ_ONLY])
