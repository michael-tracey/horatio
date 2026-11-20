import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class Notification(Record):
    """A message for one person about something that happened, such as their
    downtime results arriving. Kept until read and afterwards. Work waiting on
    someone (an approval to decide) is not stored here: it is worked out from
    what is waiting, so it can never go stale (see horatio/notifications.py)."""

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_unread", "user_id", "read_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # What kind of event, e.g. downtime.delivered; lets the app group or filter them.
    kind: Mapped[str]
    troupe_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("troupes.id"))
    character_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL")
    )
    # One line, written when the event happens, so it reads the same later.
    summary: Mapped[str]
    # Where in the app to go about it.
    link: Mapped[str]
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmailNotice(Record):
    """A notification waiting to go out by email as well, to someone who asked for
    that kind by email (horatio.notification_emails). Gone once sent, or once
    they no longer want it."""

    __tablename__ = "email_notices"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Which of the person's email settings it comes under, e.g. "downtime".
    topic: Mapped[str]
    # The troupe's name, the line and the link, as the bell shows them.
    troupe: Mapped[str | None]
    summary: Mapped[str]
    link: Mapped[str]
    # When it may go: at once, at the person's daily digest, or after a failure,
    # once the wait is over.
    due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    last_error: Mapped[str | None]
    # Sent whether or not the person wants this kind by email: an important
    # announcement (horatio.posts).
    forced: Mapped[bool] = mapped_column(default=False, server_default="false")


class PushDevice(Record):
    """A phone or computer where the person turned on push notifications (#1054): its
    browser's subscription with a push service, which Horatio sends to through the
    delivery worker (horatio.web_push). Gone once they turn it off there, sign out
    there, or the push service says the subscription is gone."""

    __tablename__ = "push_devices"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Where the push service takes messages for this browser: its own address, a
    # secret of the browser's. One device, one subscription.
    endpoint: Mapped[str] = mapped_column(unique=True)
    # The browser's keys, base64url: what each message is encrypted to.
    p256dh: Mapped[str]
    auth: Mapped[str]
    # As the person sees it in their list of devices, such as "Chrome on Android".
    name: Mapped[str]


class PushNotice(Record):
    """A notification waiting to go to one device by push (horatio.web_push): the line
    and link the bell shows. Gone once sent, or once it can't be."""

    __tablename__ = "push_notices"

    device_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("push_devices.id", ondelete="CASCADE"), index=True
    )
    # Which topic it comes under (horatio.notification_choices), e.g. "downtime".
    topic: Mapped[str]
    troupe: Mapped[str | None]
    summary: Mapped[str]
    link: Mapped[str]
    # When it may go: at once, or after a failure worth trying again.
    due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
