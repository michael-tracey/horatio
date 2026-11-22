"""Notifications that also come by email (issue #106).

Each person chooses in Account › Notifications which kinds of notification reach them
by email as well as in the bell (the topics of horatio.notification_choices, a
setting each, all off until they turn one on but announcements, which are on), and
whether each email goes at once or everything waiting is gathered into one digest a
day or a week (#1196), at the hour they choose (and on the day, for a week's) in
their time zone (UTC while they follow their device's, which the server cannot know).
A digest groups its notices by topic.

Word about the person's account's safety (`Topic.urgent`), and an announcement its
staff marked important (`forced`), never wait for a digest: they go at once, on their
own, whatever the person chose.

`queue` keeps an `EmailNotice` for each person who wants that kind, in the same
transaction as what happened, due at once or at their next digest; nothing is kept
while the server has no email set up. The delivery worker (horatio.delivery) calls
`send_due`, which sends what is due, each person's notices locked while they go so
two workers never send them twice. A digest is sent once a window, the day or the
week it is for: the window is kept (`EmailDigest`), so a second worker, or the person
moving their digest's hour after it went, never sends that window another. Changing
how emails come re-times what is waiting (`retime`). A notice the person no longer
wants by the time it is due is dropped, unless it is `forced`: an important
announcement goes to everyone. A temporary refusal is tried again later, backing off
as deliveries do; after `delivery.MAX_ATTEMPTS`, or a permanent refusal, the notices
are dropped and the reason logged: the bell still has them.

An announcement's own email carries the announcement itself: its title, byline,
picture and words (horatio.announcement_emails, #831). A digest keeps a line for
each.

Every email links to turning its kind off (a digest, every kind), without
signing in: the link holds a signature made with a key kept on the person's
account (`users.unsubscribe_key`), good for that and nothing else.
"""

import base64
import hashlib
import hmac
import html
import logging
import uuid
from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta
from email.message import EmailMessage
from email.utils import formataddr
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from horatio import (
    announcement_emails,
    audit,
    delivery,
    email_design,
    mail_sender,
    notification_choices,
    preferences,
    suspensions,
)
from horatio.config import get_settings
from horatio.connectors import SendError, email
from horatio.email_design import Body, Design, Line, compose, text_html
from horatio.mail_sender import Sender
from horatio.models import EmailDigest, EmailNotice, Troupe, User
from horatio.notification_choices import BY_NAME, TOPICS, Topic
from horatio.preferences import WEEKDAYS, Preferences

log = logging.getLogger(__name__)
# Logged when Horatio stops trying to email someone their notifications.
GAVE_UP = "mail.gave_up"


# An unsubscribe link that turns off every kind, as a digest carries.
ALL = "all"
# Where each person chooses (#1053).
SETTINGS_PAGE = "/account/notifications"

# Settings that change when a digest goes: changing one re-times what is waiting.
DIGEST_SETTINGS = frozenset({"email_digest", "digest_hour", "digest_day", "time_zone"})


def by_email(topic: Topic) -> bool:
    """Whether the person chooses if `topic` comes by email: those its links can stop."""
    return topic.choosable("email")


def wants(user: User, topic: Topic) -> bool:
    return notification_choices.chosen(user, topic, "email")


def zone(prefs: Preferences) -> ZoneInfo:
    return ZoneInfo(prefs.time_zone or "UTC")


def at_hour(day: date, hour: int, where: ZoneInfo) -> datetime:
    """`hour` o'clock on `day` where the person is, in UTC. An hour the clocks skip
    that day (spring forward) is read by the offset before the change, so 2 am is
    3 am; an hour they go through twice (fall back) is the first of the two."""
    return datetime.combine(day, time(hour), tzinfo=where).astimezone(UTC)


def slots(prefs: Preferences, after: datetime) -> Iterable[datetime]:
    """When the person's digests go from `after` on, in order."""
    where = zone(prefs)
    day = after.astimezone(where).date() - timedelta(days=1)
    weekday = WEEKDAYS.index(prefs.digest_day)
    while True:
        if prefs.email_digest != "weekly" or day.weekday() == weekday:
            yield at_hour(day, prefs.digest_hour, where)
        day += timedelta(days=1)


def last_slot(prefs: Preferences, at: datetime) -> datetime:
    """When the person's last digest was due, at or before `at`."""
    found = None
    for slot in slots(prefs, at - timedelta(days=8)):
        if slot > at:
            break
        found = slot
    assert found is not None
    return found


def window(prefs: Preferences, slot: datetime) -> str:
    """The window a digest going at `slot` is for, in the person's time zone: the day
    ("2026-11-23") for a daily one, the ISO week ("2026-W48") for a weekly one."""
    local = slot.astimezone(zone(prefs)).date()
    if prefs.email_digest == "weekly":
        year, week, _ = local.isocalendar()
        return f"{year}-W{week:02d}"
    return local.isoformat()


def next_digest(prefs: Preferences, after: datetime, sent: str | None = None) -> datetime:
    """When the person's next digest goes, after `after`: the next one whose window
    isn't `sent`, the window of the last one they were sent."""
    for slot in slots(prefs, after):
        if slot > after and window(prefs, slot) != sent:
            return slot
    raise AssertionError("unreachable")


def last_window(db: Session, user_id: uuid.UUID) -> str | None:
    return db.scalar(select(EmailDigest.window).where(EmailDigest.user_id == user_id))


def at_once(topic: Topic, forced: bool) -> bool:
    """Whether a notice goes on its own and at once, whatever the person chose: word
    about their account's safety, or an announcement marked important."""
    return forced or topic.urgent


def due(db: Session, user: User, topic: Topic, forced: bool, at: datetime) -> datetime:
    """When a notice for `user` queued at `at` goes."""
    prefs = preferences.read(user)
    if prefs.email_digest == "at_once" or at_once(topic, forced):
        return at
    return next_digest(prefs, at, last_window(db, user.id))


def queue(
    db: Session,
    user_ids: Iterable[uuid.UUID],
    kind: str,
    summary: str,
    link: str,
    *,
    troupe_id: uuid.UUID | None = None,
    forced: bool = False,
) -> None:
    """Keep the notification to email to each of `user_ids` who wants this kind by
    email, at once or with their digest; `forced`, to each of them whether they
    want it or not, and at once (an important announcement)."""
    topic = notification_choices.topic_for(kind)
    ids = list(dict.fromkeys(user_ids))
    if "email" not in topic.routes or not ids or not email.configured():
        return
    troupe = db.get_one(Troupe, troupe_id).name if troupe_id is not None else None
    at = delivery.now()
    # Someone suspended gets no notification emails (horatio.suspensions).
    for user in db.scalars(select(User).where(User.id.in_(ids), ~suspensions.suspended_user())):
        if not forced and not wants(user, topic):
            continue
        db.add(
            EmailNotice(
                user_id=user.id,
                topic=topic.name,
                troupe=troupe,
                summary=summary,
                link=link,
                due_at=due(db, user, topic, forced, at),
                forced=forced,
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
    if topic != ALL and not (topic in BY_NAME and by_email(BY_NAME[topic])):
        return None
    try:
        user = db.get(User, uuid.UUID(user_id))
    except ValueError:
        return None
    if user is None or not hmac.compare_digest(given, signature(user, topic)):
        return None
    return user, topic


def topics_for(topic: str) -> list[Topic]:
    """The topics a link stops by email: one, or for `ALL` every one the person chooses."""
    return [t for t in TOPICS if by_email(t)] if topic == ALL else [BY_NAME[topic]]


def subscribed(user: User, topic: str) -> bool:
    """Whether any of the emails the link stops are on."""
    return any(wants(user, t) for t in topics_for(topic))


def unsubscribe(user: User, topic: str) -> None:
    """Turn off by email what the link stops, as Account › Notifications would."""
    preferences.change(user, {t.setting("email"): False for t in topics_for(topic)})


def about(topic: str) -> str:
    """What the emails a link stops are about, for a sentence."""
    return "any notification" if topic == ALL else BY_NAME[topic].title.lower()


def absolute(link: str) -> str:
    """A notice's link as an email gives it: Horatio's own, or one elsewhere (a
    Discord channel or invite, horatio.discord_channels) as it is."""
    if link.startswith(("https://", "http://")):
        return link
    return f"{get_settings().public_url.rstrip('/')}{link}"


def line(notice: EmailNotice) -> str:
    return f"{notice.troupe}: {notice.summary}" if notice.troupe else notice.summary


def footer(user: User, topic: str) -> list[Line]:
    """Why the email came and how to stop it, under the email design's footer."""
    return [
        Line(
            f"You asked Horatio to email you about {about(topic)}.",
            unsubscribe_url(user, topic),
            "Stop these emails",
        ),
        Line(
            "Choose which notifications come by email.",
            absolute(SETTINGS_PAGE),
            "Notification settings",
        ),
    ]


def to(user: User) -> str:
    return formataddr((user.display_name, user.email))


IMPORTANT = "Its staff marked this important, so it comes to everyone in the troupe."


def one_email(
    user: User,
    notice: EmailNotice,
    sender: Sender | None = None,
    design: Design | None = None,
    announcement: announcement_emails.Content | None = None,
) -> EmailMessage:
    """One notification, as it happened; for an announcement, the announcement
    itself (`announcement`, #831)."""
    mail = email.new_message(to(user), line(notice).removesuffix("."), sender)
    why = [Line(IMPORTANT)] if notice.forced else []
    lines = [*why, *footer(user, notice.topic)]
    if announcement is not None:
        body = Body(
            text=announcement.text,
            html=announcement.html,
            action=("Read it in Horatio", absolute(notice.link)),
            lines=lines,
            images=announcement.images,
            preheader=announcement.preheader,
        )
    else:
        body = Body(
            text=f"Hello {user.display_name},\n\n{line(notice)}\n\n{absolute(notice.link)}",
            html=text_html(
                f"Hello {user.display_name},\n\n{line(notice)}", None, "margin: 0 0 16px 0"
            ),
            action=("Open it in Horatio", absolute(notice.link)),
            lines=lines,
            preheader=line(notice),
        )
    compose(mail, body, design)
    mail["List-Unsubscribe"] = f"<{unsubscribe_url(user, notice.topic)}>"
    return mail


def digest_email(
    user: User,
    notices: list[EmailNotice],
    sender: Sender | None = None,
    design: Design | None = None,
    weekly: bool = False,
) -> EmailMessage:
    """Every notification waiting, by topic, each topic with its own way to stop it:
    the day's, or the week's."""
    sections: list[str] = []
    pieces: list[str] = []
    for topic in TOPICS:
        these = [n for n in notices if n.topic == topic.name]
        if not these:
            continue
        lines = "\n".join(f"- {line(n)}\n  {absolute(n.link)}" for n in these)
        stop = f"Stop emails about {about(topic.name)}: {unsubscribe_url(user, topic.name)}"
        sections.append(f"{topic.title}\n\n{lines}\n\n{stop}")
        items = "".join(
            f'<li style="margin: 0 0 6px 0"><a href="{html.escape(absolute(n.link), quote=True)}">'
            f"{html.escape(line(n))}</a></li>"
            for n in these
        )
        pieces.append(
            f'<h2 style="margin: 20px 0 8px 0; font-size: 18px">{html.escape(topic.title)}</h2>'
            f'<ul style="margin: 0 0 8px 0; padding-left: 20px">{items}</ul>'
            f'<p style="margin: 0 0 8px 0; font-size: 13px">'
            f'<a href="{html.escape(unsubscribe_url(user, topic.name), quote=True)}">'
            f"Stop emails about {html.escape(about(topic.name))}</a></p>"
        )
    span = "this week" if weekly else "today"
    greeting = (
        f"Hello {user.display_name},\n\nHere is the {'week' if weekly else 'day'}'s news"
        " from Horatio."
    )
    mail = email.new_message(to(user), f"Horatio: {len(notices)} notifications {span}", sender)
    compose(
        mail,
        Body(
            text=greeting + "\n\n" + "\n\n\n".join(sections),
            html=text_html(greeting, None, "margin: 0 0 16px 0") + "".join(pieces),
            lines=footer(user, ALL),
            preheader=f"{len(notices)} notifications from Horatio {span}.",
        ),
        design,
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
        if suspended or topic is None or not (notice.forced or wants(user, topic)):
            db.delete(notice)
        else:
            wanted.append(notice)
    # Word about the account's safety and important announcements go on their own.
    alone = [n for n in wanted if at_once(BY_NAME[n.topic], n.forced)]
    gathered = [n for n in wanted if n not in alone]
    batches = [[n] for n in alone if n.due_at <= at]
    digest: list[EmailNotice] = []
    if prefs.email_digest == "at_once":
        batches += [[n] for n in gathered if n.due_at <= at]
    elif any(n.due_at <= at for n in gathered):
        this = window(prefs, last_slot(prefs, at))
        sent = last_window(db, user.id)
        if sent == this:
            # This window's digest already went: what is waiting goes with the next.
            later = next_digest(prefs, at, sent)
            for notice in gathered:
                notice.due_at = max(notice.due_at, later)
        else:
            # Whatever is waiting goes with the digest, even if it came in after it was due.
            digest = gathered
            batches.append(digest)
    sender = mail_sender.sender(db)
    design = email_design.current(db)
    for batch in batches:
        if len(batch) == 1:
            shown = announcement_emails.content(db, user, batch[0], design)
            mail = one_email(user, batch[0], sender, design, shown)
        else:
            mail = digest_email(user, batch, sender, design, prefs.email_digest == "weekly")
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
                # For the custodian's Mail card (#833): the bell still has them.
                audit.record(
                    db,
                    None,
                    GAVE_UP,
                    member=user.display_name,
                    user_id=user.id,
                    count=len(batch),
                    error=error.reason,
                )
                for notice in batch:
                    db.delete(notice)
            continue
        if batch is digest:
            sent_digest(db, user, window(prefs, last_slot(prefs, at)), at)
        for notice in batch:
            db.delete(notice)
    return len(batches)


def sent_digest(db: Session, user: User, sent: str, at: datetime) -> None:
    """Keep the window of the digest just sent to `user`, so it gets no other."""
    kept = db.scalar(select(EmailDigest).where(EmailDigest.user_id == user.id))
    if kept is None:
        db.add(EmailDigest(user_id=user.id, window=sent, sent_at=at))
    else:
        kept.window = sent
        kept.sent_at = at
    db.flush()


def retime(db: Session, user: User) -> None:
    """Re-time what waits to be emailed to `user`, after they change how emails come
    (`DIGEST_SETTINGS`): at once, or with their next digest. Those waiting after a
    refusal keep their wait."""
    at = delivery.now()
    for notice in db.scalars(
        select(EmailNotice).where(EmailNotice.user_id == user.id, EmailNotice.attempts == 0)
    ):
        topic = BY_NAME.get(notice.topic)
        if topic is not None:
            notice.due_at = due(db, user, topic, notice.forced, at)
    db.flush()


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
