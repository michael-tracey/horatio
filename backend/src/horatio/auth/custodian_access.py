"""Custodian access (#1213): the custodian's powers are switched on, not always on.

A custodian is often a player too. Signed in, they see Horatio as their troupe roles
make them, player here and storyteller there. To use the custodian's powers they
switch custodian access on, giving their second step again and a reason
(horatio.api.custodian_access). It belongs to that one sign-in, and while it is on
horatio.permissions.acting_as_custodian says yes.

- It lasts an hour from the last use of the powers: each request a check lets through
  on them alone moves the end on (`kept`, after the request is answered).
- Switching it off, signing out, or the sign-in ending ends it at once; so does the
  account no longer being the custodian's.
- The first time it is used in a troupe the custodian has an active character in, home
  or visiting, that troupe's lead storyteller is told in the bell, with the reason:
  once a switch-on, for each troupe. Site-wide work tells no one.

Switching on and its end go in the audit log, the reason with it, as each lead told.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from horatio import notifications
from horatio.audit import record
from horatio.auth.sessions import hash_token
from horatio.config import get_settings
from horatio.db import get_session
from horatio.models import Character, CustodianAccess, Troupe, TroupeMembership, User
from horatio.models import Session as SignInSession
from horatio.permissions import Acting, acting_of, set_acting

ACCESS_FOR = timedelta(hours=1)
# Sent with a refusal that custodian access would have let through, so the app can
# offer to switch it on.
HEADER = "X-Horatio-Custodian-Access"


def ends_at(access: CustodianAccess) -> datetime:
    return access.last_used_at + access.lasts


def end(db: Session, access: CustodianAccess, kind: str, *, at: datetime | None = None) -> None:
    """End custodian access, recording how: "stopped", "signed_out", "timed_out" or
    "not_custodian". Only the first to end it records it, should two requests find it
    at once."""
    ended = db.execute(
        update(CustodianAccess)
        .where(CustodianAccess.id == access.id, CustodianAccess.ended_at.is_(None))
        .values(ended_at=at or datetime.now(UTC))
        .returning(CustodianAccess.id)
    ).first()
    if ended is None:
        return
    custodian = db.get_one(User, access.custodian_id)
    record(db, custodian, "account.custodian_access_off", member=custodian.display_name, kind=kind)


def live(db: Session, user: User, token: str) -> CustodianAccess | None:
    """The custodian access a sign-in token's session has on, if any. One found timed
    out, or whose account is no longer the custodian's, is ended here."""
    access = db.scalar(
        select(CustodianAccess)
        .join(SignInSession, CustodianAccess.session_id == SignInSession.id)
        .where(
            SignInSession.token_hash == hash_token(token),
            SignInSession.user_id == user.id,
            SignInSession.revoked_at.is_(None),
            SignInSession.expires_at > func.now(),
            CustodianAccess.ended_at.is_(None),
        )
        .order_by(CustodianAccess.created_at.desc(), CustodianAccess.id.desc())
        .limit(1)
    )
    if access is None:
        return None
    if ends_at(access) <= datetime.now(UTC):
        end(db, access, "timed_out", at=ends_at(access))
    elif not user.is_custodian:
        end(db, access, "not_custodian")
    else:
        return access
    db.commit()
    return None


def for_request(request: Request, db: Session, user: User | None) -> CustodianAccess | None:
    """Note on `user`, signed in with this request's sign-in, whether custodian access
    is on for it (horatio.permissions.acting_as_custodian). Anyone but a custodian
    never has it, nor does whoever the custodian views Horatio as."""
    if user is None:
        return None
    access = None
    if user.is_custodian:
        token = request.cookies.get(get_settings().session_cookie_name)
        access = live(db, user, token) if token else None
    acting = Acting(access.id if access else None)
    set_acting(user, acting)
    request.state.custodian_acting = acting
    return access


def wanted(request: Request) -> bool:
    """Whether a check in this request would have let the custodian through had they
    custodian access on."""
    acting = getattr(request.state, "custodian_acting", None)
    return isinstance(acting, Acting) and acting.wanted


def kept(request: Request, db: Annotated[Session, Depends(get_session)]) -> Iterator[None]:
    """For every API route: once it has answered, and only if it did without error, a
    use of the custodian's powers moves the end of the access on, and tells the lead
    storyteller of each troupe used in that the custodian plays in."""
    yield
    acting = getattr(request.state, "custodian_acting", None)
    if not isinstance(acting, Acting) or not acting.used or acting.access_id is None:
        return
    access = db.get(CustodianAccess, acting.access_id)
    if access is None or access.ended_at is not None:
        return
    access.last_used_at = datetime.now(UTC)
    tell_leads(db, access, troupes_used(db, acting))
    db.commit()


def troupes_used(db: Session, acting: Acting) -> set[uuid.UUID]:
    """The troupes a request used the custodian's powers in: those named, and those
    of each character it used them on (its home, the troupes it is in, an NPC's)."""
    found = set(acting.troupe_ids)
    if acting.character_ids:
        ids = list(acting.character_ids)
        found |= set(
            db.scalars(
                select(TroupeMembership.troupe_id).where(
                    TroupeMembership.character_id.in_(ids), TroupeMembership.left_at.is_(None)
                )
            )
        )
        for home, owner in db.execute(
            select(Character.home_troupe_id, Character.owner_troupe_id).where(Character.id.in_(ids))
        ):
            found |= {t for t in (home, owner) if t is not None}
    return found


def played_in(db: Session, user: User, troupe_ids: set[uuid.UUID]) -> list[Troupe]:
    """Those of the troupes where `user` has an active character now, home or visiting."""
    if not troupe_ids:
        return []
    return list(
        db.scalars(
            select(Troupe)
            .where(
                Troupe.id.in_(troupe_ids),
                select(TroupeMembership.id)
                .join(Character, TroupeMembership.character_id == Character.id)
                .where(
                    TroupeMembership.troupe_id == Troupe.id,
                    TroupeMembership.left_at.is_(None),
                    Character.kind == "pc",
                    Character.player_id == user.id,
                    Character.status == "active",
                )
                .exists(),
            )
            .order_by(Troupe.name, Troupe.id)
        )
    )


def tell_leads(db: Session, access: CustodianAccess, troupe_ids: set[uuid.UUID]) -> None:
    """Tell the lead storyteller of each troupe the custodian plays in, of these, that
    they used custodian access there: in the bell only, once a switch-on."""
    custodian = db.get_one(User, access.custodian_id)
    for troupe in played_in(db, custodian, troupe_ids - set(access.told_troupe_ids)):
        # One statement, so two requests at once can't both tell them.
        told = db.execute(
            update(CustodianAccess)
            .where(
                CustodianAccess.id == access.id,
                func.array_position(CustodianAccess.told_troupe_ids, troupe.id).is_(None),
            )
            .values(told_troupe_ids=func.array_append(CustodianAccess.told_troupe_ids, troupe.id))
            .returning(CustodianAccess.id)
        ).first()
        if told is None:
            continue
        record(
            db,
            custodian,
            "troupe.custodian_access_used",
            troupe_id=troupe.id,
            member=custodian.display_name,
            reason=access.reason,
        )
        if troupe.lead_user_id is not None and troupe.lead_user_id != custodian.id:
            notifications.notify(
                db,
                [troupe.lead_user_id],
                "troupe.custodian_access",
                f"{custodian.display_name}, the custodian, who plays in {troupe.name}, switched"
                f" on custodian access and opened what only its staff see: {access.reason}",
                f"/troupes/{troupe.id}/log",
                troupe_id=troupe.id,
                email=False,
            )
    db.refresh(access)


def switch_on(
    db: Session, user: User, session_id: uuid.UUID, reason: str, lasts: timedelta = ACCESS_FOR
) -> CustodianAccess:
    """Switch custodian access on for the sign-in `session_id`, in place of any on
    there now. The caller has checked who they are."""
    for old in db.scalars(
        select(CustodianAccess).where(
            CustodianAccess.session_id == session_id, CustodianAccess.ended_at.is_(None)
        )
    ):
        end(db, old, "stopped")
    access = CustodianAccess(
        custodian_id=user.id,
        session_id=session_id,
        reason=reason,
        last_used_at=datetime.now(UTC),
        lasts=lasts,
        told_troupe_ids=[],
    )
    db.add(access)
    db.flush()
    record(db, user, "account.custodian_access_on", member=user.display_name, reason=reason)
    acting = acting_of(user)
    if acting is not None:
        acting.access_id = access.id
    return access


def end_for_session(db: Session, session_id: uuid.UUID | None, kind: str) -> None:
    """End any custodian access on for the sign-in: signing out, switching off."""
    if session_id is None:
        return
    for access in db.scalars(
        select(CustodianAccess).where(
            CustodianAccess.session_id == session_id, CustodianAccess.ended_at.is_(None)
        )
    ):
        end(db, access, kind)
