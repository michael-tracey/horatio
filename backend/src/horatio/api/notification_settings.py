"""Account › Notifications (#1053): every kind of notification Horatio sends the
signed-in person, grouped, with where each comes, and the choices that go with a
role (horatio.notification_choices). Each person reads and changes only their own."""

import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import exists, or_, select

from horatio import boon_reports_told, delivery, notification_choices, preferences
from horatio.auth.deps import CurrentUser, DbSession
from horatio.connectors import CONNECTORS, email
from horatio.models import Character, Troupe, TroupeStaff, User
from horatio.notification_choices import Audience, Group, Topic, Way

router = APIRouter(prefix="/notification-settings", tags=["preferences"])


class NotificationRouteOut(BaseModel):
    way: Way
    # Whether it comes this way, as the person chose or as it is until they do.
    on: bool
    # It always comes this way: the person can't turn it off.
    always: bool


class NotificationRoleOut(BaseModel):
    """Whether the person is told at all in one troupe, as a role (#1018): changed with
    `PUT /troupes/{troupe_id}/boon-reports-told`, as beside the role."""

    troupe_id: uuid.UUID
    troupe_name: str
    role: Literal["staff", "keeper"]
    on: bool
    # For the Harpy or a Lesser Harpy: their character, and the office as the troupe
    # names it.
    character_name: str | None = None
    office: str | None = None


class NotificationTroupeOut(BaseModel):
    """A troupe that also sends it through its own connectors: its choice."""

    troupe_id: uuid.UUID
    troupe_name: str
    # "Discord", "Email".
    connectors: list[str]


class NotificationTopicOut(BaseModel):
    name: str
    title: str
    hint: str
    # Work waiting on the person: in the bell until it is done.
    task: bool
    # The ways it can come; a way not listed never carries it.
    routes: list[NotificationRouteOut]
    troupes_send: list[NotificationTroupeOut]
    # Whether the person is told at all goes with a role: each of theirs, by troupe.
    # None for a topic that doesn't.
    roles: list[NotificationRoleOut] | None = None


class NotificationGroupOut(BaseModel):
    name: str
    title: str
    topics: list[NotificationTopicOut]


class NotificationSettingsOut(BaseModel):
    # Whether this server can send email at all.
    email: bool
    # The groups that apply to the person: staff work only for staff, the custodian's
    # only for the custodian.
    groups: list[NotificationGroupOut]


class NotificationChoiceIn(BaseModel):
    topic: str
    way: Way
    on: bool


def audience_of(db: DbSession, user: User) -> set[Audience]:
    """Who the person is, for the groups shown: staff of a troupe still running, the
    custodian."""
    found: set[Audience] = {"everyone"}
    staffed = db.scalar(
        select(
            exists().where(
                Troupe.archived_at.is_(None),
                or_(
                    Troupe.lead_user_id == user.id,
                    exists().where(
                        TroupeStaff.troupe_id == Troupe.id, TroupeStaff.user_id == user.id
                    ),
                ),
            )
        )
    )
    if staffed:
        found.add("staff")
    if user.is_custodian:
        found.add("custodian")
    return found


def troupes_sending(db: DbSession, user: User) -> list[NotificationTroupeOut]:
    """The troupes home to one of the person's characters that send results and quest
    news through connectors of their own."""
    homes = db.scalars(
        select(Troupe)
        .where(
            Troupe.archived_at.is_(None),
            Troupe.id.in_(
                select(Character.home_troupe_id).where(
                    Character.player_id == user.id, Character.kind == "pc"
                )
            ),
        )
        .order_by(Troupe.name)
    )
    found: list[NotificationTroupeOut] = []
    for troupe in homes:
        names = [CONNECTORS[c.kind].name for c in delivery.enabled_connectors(db, troupe.id)]
        if names:
            found.append(
                NotificationTroupeOut(
                    troupe_id=troupe.id, troupe_name=troupe.name, connectors=names
                )
            )
    return found


def topic_out(
    db: DbSession, user: User, topic: Topic, sending: list[NotificationTroupeOut]
) -> NotificationTopicOut:
    roles = None
    if topic.by_role:
        roles = [
            NotificationRoleOut(
                troupe_id=c.troupe.id,
                troupe_name=c.troupe.name,
                role=c.role,
                on=c.on,
                character_name=c.character.name if c.character else None,
                office=c.office,
            )
            for c in boon_reports_told.choices_of(db, user)
        ]
    return NotificationTopicOut(
        name=topic.name,
        title=topic.title,
        hint=topic.hint,
        task=topic.task,
        routes=[
            NotificationRouteOut(
                way=way,
                on=notification_choices.chosen(user, topic, way),
                always=route.always,
            )
            for way, route in topic.routes.items()
        ],
        troupes_send=sending if topic.connectors else [],
        roles=roles,
    )


def group_out(
    db: DbSession, user: User, group: Group, sending: list[NotificationTroupeOut]
) -> NotificationGroupOut:
    return NotificationGroupOut(
        name=group.name,
        title=group.title,
        topics=[topic_out(db, user, t, sending) for t in group.topics],
    )


def settings_out(db: DbSession, user: User) -> NotificationSettingsOut:
    shown = audience_of(db, user)
    sending = troupes_sending(db, user)
    return NotificationSettingsOut(
        email=email.configured(),
        groups=[
            group_out(db, user, g, sending)
            for g in notification_choices.GROUPS
            if g.audience in shown
        ],
    )


@router.get("")
def read_notification_settings(db: DbSession, user: CurrentUser) -> NotificationSettingsOut:
    """Every kind of notification Horatio sends you, and where each comes."""
    return settings_out(db, user)


@router.put("")
def choose_notification(
    body: NotificationChoiceIn, db: DbSession, user: CurrentUser
) -> NotificationSettingsOut:
    """Choose whether one kind of notification comes to you one way: in the bell, or by
    email. Some always come, and can't be turned off."""
    topic = notification_choices.BY_NAME.get(body.topic)
    if topic is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such kind of notification.")
    route = topic.routes.get(body.way)
    if route is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"{topic.title}: these never come that way."
        )
    if route.always:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{topic.title}: these always come that way.")
    preferences.change(user, {topic.setting(body.way): body.on})
    db.commit()
    return settings_out(db, user)
