"""Notifications that also come by email (issue #106).

Each person chooses in Account → Settings which kinds of notification reach them
by email as well as in the bell (`TOPICS`, a setting each, all off until they
turn one on), and whether each email goes at once or everything waiting is
gathered into one a day, at `DIGEST_HOUR` in their time zone (UTC while they
follow their device's, which the server cannot know).

`queue` keeps an `EmailNotice` for each person who wants that kind, in the same
transaction as what happened; nothing is kept while the server has no email set
up. The delivery worker (horatio.delivery) calls `send_due`, which sends what is
due, each person's notices locked while they go so two workers never send them
twice. A notice the person no longer wants by the time it is due is dropped. A
temporary refusal is tried again later, backing off as deliveries do; after
`delivery.MAX_ATTEMPTS`, or a permanent refusal, the notices are dropped and the reason
logged: the bell still has them.

Every email links to turning its kind off (a digest, every kind), without
signing in: the link holds a signature made with a key kept on the person's
account (`users.unsubscribe_key`), good for that and nothing else.
"""

import base64
import hashlib
import hmac
import logging
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from horatio import delivery, preferences, suspensions
from horatio.config import get_settings
from horatio.connectors import SendError, email
from horatio.models import EmailNotice, Troupe, User
from horatio.preferences import Preferences

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Topic:
    # As links name it; its setting is `email_<name>` (horatio.preferences).
    name: str
    title: str
    # The notification kinds it covers: a kind, or the first part of several
    # ("approval" for approval.discipline, approval.review…).
    kinds: tuple[str, ...]

    @property
    def setting(self) -> str:
        return f"email_{self.name}"


TOPICS = (
    Topic("downtime", "Downtime results", ("downtime.delivered",)),
    Topic("downtime_reminders", "Downtime reminders", ("downtime.reminder",)),
    Topic("approvals", "Approvals waiting", ("approval",)),
    Topic("troupe_requests", "Troupe requests", ("troupe_request",)),
    Topic("renames", "Character renames", ("character.renamed",)),
    Topic("pictures", "Pictures removed", ("picture.removed",)),
    Topic("titles", "Titles chosen", ("title",)),
)
BY_NAME = {topic.name: topic for topic in TOPICS}
# An unsubscribe link that turns off every kind, as a digest carries.
ALL = "all"

# When the daily digest goes, in the person's time zone.
DIGEST_HOUR = 8


def topic_for(kind: str) -> Topic | None:
    """The setting a kind of notification comes under, or None if it never
    comes by email."""
    for topic in TOPICS:
        if any(kind == k or kind.startswith(f"{k}.") for k in topic.kinds):
            return topic
    return None


def wants(prefs: Preferences, topic: Topic) -> bool:
    return bool(getattr(prefs, topic.setting))


def next_digest(prefs: Preferences, after: datetime) -> datetime:
    """When the person's next daily digest goes, after `after`."""
    local = after.astimezone(ZoneInfo(prefs.time_zone or "UTC"))
    send = local.replace(hour=DIGEST_HOUR, minute=0, second=0, microsecond=0)
    if send <= local:
        send += timedelta(days=1)
    return send.astimezone(UTC)


def queue(
    db: Session,
    user_ids: Iterable[uuid.UUID],
    kind: str,
    summary: str,
    link: str,
    *,
    troupe_id: uuid.UUID | None = None,
) -> None:
    """Keep the notification to email to each of `user_ids` who wants this kind by
    email, at once or with their digest."""
    topic = topic_for(kind)
    ids = list(dict.fromkeys(user_ids))
    if topic is None or not ids or not email.configured():
        return
    troupe = db.get_one(Troupe, troupe_id).name if troupe_id is not None else None
    at = delivery.now()
    # Someone suspended gets no notification emails (horatio.suspensions).
    for user in db.scalars(select(User).where(User.id.in_(ids), ~suspensions.suspended_user())):
        prefs = preferences.read(user)
        if not wants(prefs, topic):
            continue
        db.add(
            EmailNotice(
                user_id=user.id,
                topic=topic.name,
                troupe=troupe,
                summary=summary,
                link=link,
                due_at=at if prefs.email_digest == "at_once" else next_digest(prefs, at),
            )
        )
    db.flush()


def signature(user: User, topic: str) -> str:
    message = f"unsubscribe:{user.id}:{topic}".encode()
    digest = hmac.new(user.unsubscribe_key.bytes, message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def unsubscribe_url(user: User, topic: str) -> str:
    """A link that turns off `topic` (or `ALL`) by email for `user`, without signing in."""
    token = f"{user.id}.{topic}.{signature(user, topic)}"
    return f"{get_settings().public_url.rstrip('/')}/unsubscribe/{token}"


def unsubscribing(db: Session, token: str) -> tuple[User, str] | None:
    """Whose link this is and what it turns off, or None if it is not a real one."""
    user_id, _, rest = token.partition(".")
    topic, _, given = rest.partition(".")
    if topic != ALL and topic not in BY_NAME:
        return None
    try:
        user = db.get(User, uuid.UUID(user_id))
    except ValueError:
        return None
    if user is None or not hmac.compare_digest(given, signature(user, topic)):
        return None
    return user, topic


def settings_for(topic: str) -> list[str]:
    return [t.setting for t in TOPICS] if topic == ALL else [BY_NAME[topic].setting]


def subscribed(user: User, topic: str) -> bool:
    """Whether any of the emails the link stops are on."""
    prefs = preferences.read(user)
    return any(getattr(prefs, setting) for setting in settings_for(topic))


def unsubscribe(user: User, topic: str) -> None:
    preferences.change(user, dict.fromkeys(settings_for(topic), False))


def about(topic: str) -> str:
    """What the emails a link stops are about, for a sentence."""
    return "any notification" if topic == ALL else BY_NAME[topic].title.lower()


def absolute(link: str) -> str:
    return f"{get_settings().public_url.rstrip('/')}{link}"


def line(notice: EmailNotice) -> str:
    return f"{notice.troupe}: {notice.summary}" if notice.troupe else notice.summary


def footer(user: User, topic: str) -> str:
    return (
        f"-- \nYou asked Horatio to email you about {about(topic)}. "
        f"To stop: {unsubscribe_url(user, topic)}\n"
        f"Choose which notifications come by email: {absolute('/account/settings')}\n"
    )


def to(user: User) -> str:
    return formataddr((user.display_name, user.email))


def one_email(user: User, notice: EmailNotice) -> EmailMessage:
    """One notification, as it happened."""
    mail = email.new_message(to(user), line(notice).removesuffix("."))
    mail.set_content(
        f"Hello {user.display_name},\n\n{line(notice)}\n\n{absolute(notice.link)}\n\n"
        + footer(user, notice.topic)
    )
    mail["List-Unsubscribe"] = f"<{unsubscribe_url(user, notice.topic)}>"
    return mail


def digest_email(user: User, notices: list[EmailNotice]) -> EmailMessage:
    """Every notification waiting, by kind, each kind with its own way to stop it."""
    sections: list[str] = []
    for topic in TOPICS:
        these = [n for n in notices if n.topic == topic.name]
        if not these:
            continue
        lines = "\n".join(f"- {line(n)}\n  {absolute(n.link)}" for n in these)
        stop = f"Stop emails about {about(topic.name)}: {unsubscribe_url(user, topic.name)}"
        sections.append(f"{topic.title}\n\n{lines}\n\n{stop}")
    mail = email.new_message(to(user), f"Horatio: {len(notices)} notifications today")
    mail.set_content(
        f"Hello {user.display_name},\n\nHere is the day's news from Horatio.\n\n"
        + "\n\n\n".join(sections)
        + "\n\n"
        + footer(user, ALL)
    )
    mail["List-Unsubscribe"] = f"<{unsubscribe_url(user, ALL)}>"
    return mail


def send_to(db: Session, user: User, notices: list[EmailNotice], at: datetime) -> int:
    """Send `user` the notices of theirs that are due (locked). Returns how many
    emails were tried."""
    prefs = preferences.read(user)
    suspended = suspensions.current(db, user.id) is not None
    wanted: list[EmailNotice] = []
    for notice in notices:
        topic = BY_NAME.get(notice.topic)
        if suspended or topic is None or not wants(prefs, topic):
            db.delete(notice)
        else:
            wanted.append(notice)
    due = [n for n in wanted if n.due_at <= at]
    if not due:
        batches = []
    elif prefs.email_digest == "daily":
        # Whatever is waiting goes with the digest, even if it came in after it was due.
        batches = [wanted]
    else:
        batches = [[n] for n in due]
    for batch in batches:
        mail = one_email(user, batch[0]) if len(batch) == 1 else digest_email(user, batch)
        try:
            email.deliver(mail)
        except SendError as error:
            attempts = max(n.attempts for n in batch) + 1
            for notice in batch:
                notice.attempts = attempts
                notice.last_error = error.reason
                notice.due_at = at + delivery.backoff(attempts)
            if not error.retry or attempts >= delivery.MAX_ATTEMPTS:
                log.warning("gave up emailing notifications to %s: %s", user.id, error.reason)
                for notice in batch:
                    db.delete(notice)
            continue
        for notice in batch:
            db.delete(notice)
    return len(batches)


def send_due(db: Session, at: datetime | None = None, limit: int = 50) -> int:
    """Send the notification emails that are due, each person's in a transaction of
    their own. Returns how many emails were tried."""
    if not email.configured():
        return 0
    at = at or delivery.now()
    people = list(
        db.scalars(
            select(EmailNotice.user_id).where(EmailNotice.due_at <= at).distinct().limit(limit)
        )
    )
    tried = 0
    for user_id in people:
        notices = list(
            db.scalars(
                select(EmailNotice)
                .where(EmailNotice.user_id == user_id)
                .order_by(EmailNotice.created_at, EmailNotice.id)
                .with_for_update(skip_locked=True)
            )
        )
        try:
            tried += send_to(db, db.get_one(User, user_id), notices, at)
        except Exception:
            # A bug, not a refusal: record it, drop what was due, and keep the worker going.
            log.exception("emailing notifications to %s", user_id)
            db.rollback()
            db.execute(
                delete(EmailNotice).where(EmailNotice.user_id == user_id, EmailNotice.due_at <= at)
            )
        db.commit()
    return tried
