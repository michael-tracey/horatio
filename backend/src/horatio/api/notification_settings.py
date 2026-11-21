"""Account › Notifications (#1053): every kind of notification Horatio sends the
signed-in person, grouped, with where each comes, and the choices that go with a
role (horatio.notification_choices), their characters' own Discord channels
(#1077), and the devices where they turned on push (#1054, horatio.web_push). Each
person reads and changes only their own."""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import exists, or_, select

from horatio import (
    boon_reports_told,
    delivery,
    discord_channels,
    notification_choices,
    preferences,
    web_push,
)
from horatio.auth.deps import CurrentUser, DbSession
from horatio.connectors import CONNECTORS, email
from horatio.models import Character, Troupe, TroupeConnector, TroupeStaff, User
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


class NotificationOwnChannelOut(BaseModel):
    """A character of the person's with its own channel on the troupe's Discord: whether
    the connector posts there (#1077), changed with `PUT
    /notification-settings/own-channel`."""

    character_id: uuid.UUID
    character_name: str
    on: bool


class NotificationTroupeOut(BaseModel):
    """A troupe that also sends it through its own connectors: its choice."""

    troupe_id: uuid.UUID
    troupe_name: str
    # "Discord", "Email".
    connectors: list[str]
    # The person's characters with their own channel on its Discord, on the topic that
    # shows their switches (Topic.own_channels); empty on the others.
    own_channels: list[NotificationOwnChannelOut] = []


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


class PushDeviceOut(BaseModel):
    """A phone or computer where the person turned on push."""

    id: uuid.UUID
    # Such as "Chrome on Android".
    name: str
    # The browser's subscription, so the page knows which of these it is on.
    endpoint: str
    created_at: datetime


class NotificationSettingsOut(BaseModel):
    # Whether this server can send email at all.
    email: bool
    # Whether it can send push notifications, and the key a browser subscribes with.
    push: bool
    push_key: str | None
    # The devices where the person turned push on.
    devices: list[PushDeviceOut]
    # The groups that apply to the person: staff work only for staff, the custodian's
    # only for the custodian.
    groups: list[NotificationGroupOut]


class NotificationChoiceIn(BaseModel):
    topic: str
    way: Way
    on: bool


class OwnChannelChoiceIn(BaseModel):
    character_id: uuid.UUID
    on: bool


class PushDeviceIn(BaseModel):
    """A browser's push subscription (`PushSubscription.toJSON()`): where its push
    service takes messages for it, and its keys, base64url."""

    endpoint: str = Field(max_length=2048)
    p256dh: str = Field(max_length=200)
    auth: str = Field(max_length=100)


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
        connectors = delivery.enabled_connectors(db, troupe.id)
        if connectors:
            found.append(
                NotificationTroupeOut(
                    troupe_id=troupe.id,
                    troupe_name=troupe.name,
                    connectors=[CONNECTORS[c.kind].name for c in connectors],
                    own_channels=own_channels(db, user, troupe, connectors),
                )
            )
    return found


def own_channels(
    db: DbSession, user: User, troupe: Troupe, connectors: list[TroupeConnector]
) -> list[NotificationOwnChannelOut]:
    """The person's characters the troupe's Discord connector has a channel for."""
    found = next((c for c in connectors if c.kind == "discord"), None)
    channels = (found.settings.get("channels") or {}) if found else {}
    return [
        NotificationOwnChannelOut(
            character_id=c.id,
            character_name=c.name,
            on=notification_choices.own_channel_on(user, c.id),
        )
        for c in discord_channels.characters(db, troupe.id)
        if c.player_id == user.id and channels.get(str(c.id))
    ]


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
        troupes_send=[
            t if topic.own_channels else t.model_copy(update={"own_channels": []}) for t in sending
        ]
        if topic.connectors
        else [],
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
        push=web_push.configured(),
        push_key=web_push.public_key(),
        devices=[
            PushDeviceOut(id=d.id, name=d.name, endpoint=d.endpoint, created_at=d.created_at)
            for d in web_push.devices_of(db, user)
        ],
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
    """Choose whether one kind of notification comes to you one way: in the bell, by
    email, or by push to your devices. Some always come, and can't be turned off."""
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


@router.put("/own-channel")
def choose_own_channel(
    body: OwnChannelChoiceIn, db: DbSession, user: CurrentUser
) -> NotificationSettingsOut:
    """Turn on or off what a troupe's Discord connector posts to your character's own
    channel: its downtime results and quest news. They still come in Horatio, and the
    troupe's shared channels are unchanged. Turned off, what is waiting to go there is
    cancelled."""
    character = db.get(Character, body.character_id)
    if character is None or character.player_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such character of yours.")
    notification_choices.choose_own_channel(user, character.id, body.on)
    if not body.on:
        # What was already waiting to go there is cancelled, not sent (#1134).
        delivery.cancel_own_channel(db, user, character)
    db.commit()
    return settings_out(db, user)


@router.put("/devices")
def turn_on_push(
    body: PushDeviceIn, request: Request, db: DbSession, user: CurrentUser
) -> NotificationSettingsOut:
    """Turn on push notifications on this device: its browser's subscription. Which
    kinds come by push is chosen per kind, as for the bell and email."""
    if not web_push.configured():
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Push notifications aren't set up on this server."
        )
    try:
        web_push.turn_on(
            db, user, body.endpoint, body.p256dh, body.auth, request.headers.get("user-agent")
        )
    except web_push.BadDevice as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    db.commit()
    return settings_out(db, user)


@router.delete("/devices/{device_id}")
def turn_off_push(
    device_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> NotificationSettingsOut:
    """Turn off push notifications on one of your devices: nothing more goes to it."""
    if not web_push.turn_off(db, user, device_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such device of yours.")
    db.commit()
    return settings_out(db, user)
