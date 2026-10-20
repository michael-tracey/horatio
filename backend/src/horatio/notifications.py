"""What is waiting for someone's attention, for the bell in the menu bar.

Two kinds of item come through one list:

- Tasks: work waiting on the person, such as approvals to decide. They are
  worked out afresh from what is waiting each time, so they appear and go
  exactly as the work does, for everyone who can do it, and cannot be
  dismissed, only done.
- Messages: stored `Notification` rows about something that happened, such as
  downtime results arriving. They are written by `notify` when it happens and
  stay until the person reads them.

A new kind of task is a new function in `TASK_SOURCES`; a new kind of message
is a call to `notify` wherever the event happens.
"""

import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from horatio.models import (
    Approval,
    Character,
    DisciplinePurchase,
    HomeTroupeChange,
    Notification,
    TraitDefinition,
    Troupe,
    TroupeRequest,
    TroupeStaff,
    User,
)
from horatio.permissions import TROUPE_POLICY, TroupeAction
from horatio.pictures import picture_url


@dataclass(frozen=True)
class Item:
    # "approval:<id>" for a task; the stored notification's id for a message.
    id: str
    kind: str
    # Work waiting on the person: it goes when done, not when read.
    task: bool
    troupe_id: uuid.UUID | None
    troupe_name: str | None
    summary: str
    link: str
    at: datetime
    read: bool
    # The picture of the character it is about, if any (horatio.pictures).
    picture: str | None = None


def troupes_where(db: Session, user: User, action: TroupeAction) -> list[Troupe]:
    """Running troupes where `user` holds a role allowed `action`. Being custodian
    alone does not count: the custodian is not pestered with every troupe's work."""
    roles = [r.value for r in TROUPE_POLICY[action]]
    staffed = select(TroupeStaff.troupe_id).where(
        TroupeStaff.user_id == user.id, TroupeStaff.role.in_(roles)
    )
    query = select(Troupe).where(Troupe.archived_at.is_(None))
    if "lead_storyteller" in roles:
        query = query.where(or_(Troupe.lead_user_id == user.id, Troupe.id.in_(staffed)))
    else:
        query = query.where(Troupe.id.in_(staffed))
    return list(db.scalars(query))


def approval_tasks(db: Session, user: User) -> list[Item]:
    """Requests waiting in troupes where the person approves changes."""
    troupes = {t.id: t for t in troupes_where(db, user, TroupeAction.APPROVE_CHANGES)}
    if not troupes:
        return []
    rows = list(
        db.execute(
            select(Approval, Character)
            .join(Character, Approval.character_id == Character.id)
            .where(Approval.troupe_id.in_(troupes), Approval.status == "pending")
        )
    )
    disciplines = {
        approval_id: (name, bought)
        for approval_id, name, bought in db.execute(
            select(DisciplinePurchase.approval_id, TraitDefinition.name, DisciplinePurchase)
            .join(TraitDefinition, DisciplinePurchase.trait_definition_id == TraitDefinition.id)
            .where(DisciplinePurchase.approval_id.in_([a.id for a, _ in rows]))
        )
    }
    moves = {
        approval_id: from_troupe
        for approval_id, from_troupe in db.execute(
            select(HomeTroupeChange.approval_id, HomeTroupeChange.from_troupe_id).where(
                HomeTroupeChange.approval_id.in_([a.id for a, _ in rows])
            )
        )
    }
    items: list[Item] = []
    for approval, about in rows:
        character = about.name
        troupe = troupes[approval.troupe_id]
        if approval.id in disciplines:
            name, bought = disciplines[approval.id]
            detail = f": {bought.detail}" if bought.detail else ""
            summary = (
                f"{character} bought {name}{detail} {bought.from_rating} → {bought.to_rating}"
                f" ({bought.cost} XP)"
            )
        elif approval.kind == "home_troupe_change":
            moving = moves.get(approval.id) is not None
            summary = f"{character} asks to {'move' if moving else 'make'} {troupe.name} its home"
        else:
            summary = f"{character} is waiting for approval"
        items.append(
            Item(
                id=f"approval:{approval.id}",
                kind=f"approval.{approval.kind}",
                task=True,
                troupe_id=troupe.id,
                troupe_name=troupe.name,
                summary=summary,
                link=f"/troupes/{troupe.id}/approvals",
                at=approval.created_at,
                read=False,
                picture=picture_url(about.id, about.picture_id),
            )
        )
    return items


def troupe_request_tasks(db: Session, user: User) -> list[Item]:
    """New troupes people have asked for: the custodian's own work."""
    if not user.is_custodian:
        return []
    rows = db.execute(
        select(TroupeRequest, User.display_name)
        .join(User, TroupeRequest.requester_id == User.id)
        .where(TroupeRequest.status == "pending")
    )
    return [
        Item(
            id=f"troupe_request:{request.id}",
            kind="troupe_request",
            task=True,
            troupe_id=None,
            troupe_name=None,
            summary=f"{requester} asks for a new troupe, {request.name}",
            link="/custodian/troupe-requests",
            at=request.created_at,
            read=False,
        )
        for request, requester in rows
    ]


TASK_SOURCES: list[Callable[[Session, User], list[Item]]] = [approval_tasks, troupe_request_tasks]

# Read messages older than this many are left out of the list.
READ_MESSAGES_SHOWN = 20


def messages(db: Session, user: User) -> list[Item]:
    query = (
        select(Notification, Troupe.name, Character.picture_id)
        .outerjoin(Troupe, Notification.troupe_id == Troupe.id)
        .outerjoin(Character, Notification.character_id == Character.id)
    )
    rows = list(
        db.execute(
            query.where(Notification.user_id == user.id, Notification.read_at.is_(None)).order_by(
                Notification.created_at.desc()
            )
        )
    ) + list(
        db.execute(
            query.where(Notification.user_id == user.id, Notification.read_at.is_not(None))
            .order_by(Notification.created_at.desc())
            .limit(READ_MESSAGES_SHOWN)
        )
    )
    return [
        Item(
            id=str(n.id),
            kind=n.kind,
            task=False,
            troupe_id=n.troupe_id,
            troupe_name=troupe_name,
            summary=n.summary,
            link=n.link,
            at=n.created_at,
            read=n.read_at is not None,
            picture=picture_url(n.character_id, picture) if n.character_id else None,
        )
        for n, troupe_name, picture in rows
    ]


def for_user(db: Session, user: User) -> list[Item]:
    """Tasks first, oldest first so the longest waiting is on top; then messages,
    newest first, unread before read."""
    tasks = sorted(
        (item for source in TASK_SOURCES for item in source(db, user)), key=lambda i: i.at
    )
    return tasks + messages(db, user)


def notify(
    db: Session,
    user_ids: Iterable[uuid.UUID],
    kind: str,
    summary: str,
    link: str,
    *,
    troupe_id: uuid.UUID | None = None,
    character_id: uuid.UUID | None = None,
) -> None:
    """Leave a message for each of `user_ids`, in the same transaction as the event."""
    for user_id in dict.fromkeys(user_ids):
        db.add(
            Notification(
                user_id=user_id,
                kind=kind,
                troupe_id=troupe_id,
                character_id=character_id,
                summary=summary,
                link=link,
            )
        )
    db.flush()


def mark_read(db: Session, user: User, ids: Iterable[uuid.UUID] | None = None) -> None:
    """Mark the person's messages read: these, or all of them."""
    query = update(Notification).where(
        Notification.user_id == user.id, Notification.read_at.is_(None)
    )
    if ids is not None:
        query = query.where(Notification.id.in_(list(ids)))
    db.execute(query.values(read_at=datetime.now(UTC)))
