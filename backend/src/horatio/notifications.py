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
is a call to `notify` wherever the event happens. Either may also come by email
to those who choose it (horatio.notification_emails): `notify` sees to that for
messages; a task emails when its work arrives (`approval_waiting`,
`troupe_request_waiting`).
"""

import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from horatio import notification_emails
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


def approvers(db: Session, troupe: Troupe) -> list[uuid.UUID]:
    """Who decides the running troupe's approvals: the people `troupes_where` finds
    it for."""
    roles = [r.value for r in TROUPE_POLICY[TroupeAction.APPROVE_CHANGES]]
    staff = db.scalars(
        select(TroupeStaff.user_id).where(
            TroupeStaff.troupe_id == troupe.id, TroupeStaff.role.in_(roles)
        )
    )
    lead = [troupe.lead_user_id] if "lead_storyteller" in roles else []
    return list(dict.fromkeys([*lead, *staff]))


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
    return approval_items(db, troupes, [(approval, about) for approval, about in rows])


def approval_items(
    db: Session, troupes: dict[uuid.UUID, Troupe], rows: list[tuple[Approval, Character]]
) -> list[Item]:
    """Waiting approvals as tasks, saying what each asks for."""
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
        if approval.kind == "exception" and approval.id in disciplines:
            name, bought = disciplines[approval.id]
            detail = f": {bought.detail}" if bought.detail else ""
            summary = (
                f"{character} asks for {name}{detail} {bought.from_rating} → {bought.to_rating}"
                " by exception"
            )
        elif approval.id in disciplines:
            name, bought = disciplines[approval.id]
            detail = f": {bought.detail}" if bought.detail else ""
            summary = (
                f"{character} bought {name}{detail} {bought.from_rating} → {bought.to_rating}"
                f" ({bought.cost} XP)"
            )
        elif approval.kind == "diablerie":
            summary = f"{character} says they committed diablerie"
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


def approval_waiting(db: Session, approval: Approval) -> None:
    """A request has just been made: email the troupe's approvers who want that,
    except whoever asked. The bell's task needs nothing; it appears by itself."""
    troupe = db.get_one(Troupe, approval.troupe_id)
    if troupe.archived_at is not None:
        return
    about = db.get_one(Character, approval.character_id)
    [item] = approval_items(db, {troupe.id: troupe}, [(approval, about)])
    people = [p for p in approvers(db, troupe) if p != approval.requested_by]
    notification_emails.queue(db, people, item.kind, item.summary, item.link, troupe_id=troupe.id)


def troupe_request_waiting(db: Session, request: TroupeRequest, requester: User) -> None:
    """Someone has just asked for a new troupe: email the custodians who want that."""
    custodians = db.scalars(select(User.id).where(User.is_custodian, User.id != requester.id))
    notification_emails.queue(
        db,
        custodians,
        "troupe_request",
        f"{requester.display_name} asks for a new troupe, {request.name}",
        "/custodian/troupe-requests",
    )


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
    """Leave a message for each of `user_ids`, in the same transaction as the event,
    and an email for those who want this kind by email."""
    user_ids = list(dict.fromkeys(user_ids))
    for user_id in user_ids:
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
    notification_emails.queue(db, user_ids, kind, summary, link, troupe_id=troupe_id)


def mark_read(db: Session, user: User, ids: Iterable[uuid.UUID] | None = None) -> None:
    """Mark the person's messages read: these, or all of them."""
    query = update(Notification).where(
        Notification.user_id == user.id, Notification.read_at.is_(None)
    )
    if ids is not None:
        query = query.where(Notification.id.in_(list(ids)))
    db.execute(query.values(read_at=datetime.now(UTC)))
