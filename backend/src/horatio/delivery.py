"""Delivering downtime results through a troupe's connectors (CONTEXT.md:
Connector, Channel), a quest's news: its requirements, and each scenario's
result, to each of its characters (horatio.quests), and a troupe's posts to its
Discord server (horatio.posts).

Delivering a cycle records the in-app delivery at once and queues a `pending`
delivery on each connector the troupe has switched on. `send_due` sends what
is due, one delivery at a time, each row locked while it is sent so two
workers never send it twice. A failure worth retrying is tried again later,
backing off each time; after `MAX_ATTEMPTS`, or a failure that is not worth
retrying, the delivery is `failed` for storytellers to retry or mark as sent
by hand.

A player can turn off what the troupe's Discord connector posts to their
character's own channel (#1077, horatio.notification_choices): nothing is queued
there while it is off, outside test mode. The troupe's shared channels, the
delivery in Horatio and the player's notification are unchanged. What was already
waiting there when they turned it off is `cancelled`, never sent, and logged
(#1134): at once (`cancel_own_channel`), and by the sender for one it meets later,
such as one queued as they turned it off.
"""

import asyncio
import logging
import uuid
from collections.abc import Collection, Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

import horatio.connectors.discord
import horatio.connectors.email
from horatio import audit, email_design, mail_sender, notification_choices, suspensions
from horatio.config import get_settings
from horatio.connectors import CONNECTORS, Message, Recipient, SendError
from horatio.models import (
    Character,
    CycleParticipant,
    Delivery,
    DowntimeCycle,
    Quest,
    Submission,
    Troupe,
    TroupeConnector,
    User,
)

log = logging.getLogger(__name__)

# Each connector registers itself when imported.
CONNECTOR_MODULES = (horatio.connectors.discord, horatio.connectors.email)

MAX_ATTEMPTS = 6
FIRST_WAIT = timedelta(minutes=1)


def now() -> datetime:
    """The current time; tests replace this."""
    return datetime.now(UTC)


def results_link(character: Character) -> str:
    return f"{get_settings().public_url.rstrip('/')}/characters/{character.id}/results"


def alert(character: Character, cycle: DowntimeCycle, updated: bool = False) -> str:
    news = "have been updated" if updated else "are ready"
    return (
        f"Your downtime results for {character.name} ({cycle.name}) {news}: "
        f"{results_link(character)}"
    )


def enabled_connectors(db: Session, troupe_id: uuid.UUID) -> list[TroupeConnector]:
    """The troupe's connectors that are on and that this server can use."""
    return [
        c
        for c in db.scalars(
            select(TroupeConnector)
            .where(TroupeConnector.troupe_id == troupe_id, TroupeConnector.enabled)
            .order_by(TroupeConnector.kind)
        )
        if c.kind in CONNECTORS and CONNECTORS[c.kind].unavailable() is None
    ]


def to_own_channel(db: Session, connector: TroupeConnector, character: Character) -> bool:
    """Whether the connector sends to the character: anything but Discord outside test
    mode does; Discord, to the character's own channel, unless its player turned that
    off (#1077)."""
    if connector.kind != "discord" or connector.test_mode:
        return True
    player = db.get_one(User, character.player_id)
    return notification_choices.own_channel_on(player, character.id)


def turned_off(
    db: Session, connectors: Sequence[TroupeConnector], character_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, list[str]]:
    """Of these characters, those whose player turned off their own channel on one of
    these connectors (#1077), with the connectors, for staff to see."""
    if not any(c.kind == "discord" and not c.test_mode for c in connectors):
        return {}
    found: dict[uuid.UUID, list[str]] = {}
    for character, player in db.execute(
        select(Character, User)
        .join(User, Character.player_id == User.id)
        .where(Character.id.in_(list(character_ids)))
    ):
        if not notification_choices.own_channel_on(player, character.id):
            found[character.id] = ["discord"]
    return found


def own_channel_off(db: Session, delivery: Delivery) -> bool:
    """Whether the delivery is for a character's own Discord channel, outside test
    mode, which its player has turned off (#1077): not to be sent."""
    if delivery.channel != "discord" or delivery.test_mode or delivery.post_id is not None:
        return False
    character, _, _ = about(db, delivery)
    player = db.get_one(User, character.player_id)
    return not notification_choices.own_channel_on(player, character.id)


def about(db: Session, delivery: Delivery) -> tuple[Character, uuid.UUID, str]:
    """A downtime's results or a quest's news: the character it goes to, its troupe,
    and what it is, as "downtime results (Spring 1999)" or "Quest: The Lost Journal"."""
    if delivery.quest_id is not None:
        assert delivery.character_id is not None
        troupe_id = db.get_one(Quest, delivery.quest_id).troupe_id
        return db.get_one(Character, delivery.character_id), troupe_id, delivery.subject
    character, cycle = db.execute(
        select(Character, DowntimeCycle)
        .select_from(Submission)
        .join(CycleParticipant, Submission.participant_id == CycleParticipant.id)
        .join(Character, CycleParticipant.character_id == Character.id)
        .join(DowntimeCycle, CycleParticipant.cycle_id == DowntimeCycle.id)
        .where(Submission.id == delivery.submission_id)
    ).one()
    what = delivery.subject or "downtime results"
    return character, cycle.troupe_id, f"{what} ({cycle.name})"


def cancel(db: Session, delivery: Delivery, actor: User | None) -> None:
    """Cancel a delivery waiting for a character's own Discord channel, which its
    player turned off (#1134): it is never sent. On its record, and in the log."""
    delivery.status = "cancelled"
    delivery.next_attempt_at = None
    character, troupe_id, what = about(db, delivery)
    audit.record(
        db,
        actor,
        "delivery.cancelled",
        troupe_id=troupe_id,
        character_id=character.id,
        channel=delivery.channel,
        what=what,
    )


def cancel_own_channel(db: Session, player: User, character: Character) -> int:
    """The player has turned off the character's own Discord channel (#1134): cancel
    its results and quest news waiting to go there, outside test mode. One the worker
    is sending at this moment is locked, and left to go; should that try fail, the
    sender cancels it before trying again (`send_one`). Returns how many."""
    submissions = (
        select(Submission.id)
        .join(CycleParticipant, Submission.participant_id == CycleParticipant.id)
        .where(CycleParticipant.character_id == character.id)
    )
    waiting = db.scalars(
        select(Delivery)
        .where(
            Delivery.channel == "discord",
            Delivery.status == "pending",
            Delivery.test_mode.is_(False),
            or_(Delivery.submission_id.in_(submissions), Delivery.character_id == character.id),
        )
        .order_by(Delivery.created_at, Delivery.id)
        .with_for_update(skip_locked=True)
    ).all()
    for found in waiting:
        cancel(db, found, player)
    return len(waiting)


def queue(
    db: Session,
    staff: User,
    connectors: list[TroupeConnector],
    cycle: DowntimeCycle,
    character: Character,
    submission: Submission,
    full_text: str,
    update_text: str,
    revision: int,
) -> int:
    """Queue this revision of the submission's results on each connector that has
    not had it (in the connector's current test mode) and sends to the character
    (`to_own_channel`). On a channel that already sent an earlier one, it goes as an
    update; one still waiting there is replaced, so the player gets the results
    once, as they now stand. Returns how many were queued."""
    queued = 0
    for connector in connectors:
        if not to_own_channel(db, connector, character):
            continue
        earlier = db.scalars(
            select(Delivery).where(
                Delivery.submission_id == submission.id,
                Delivery.channel == connector.kind,
                Delivery.test_mode.is_(connector.test_mode),
            )
        ).all()
        # One cancelled never went (#1134): turned back on, it goes again.
        if any(d.revision == revision and d.status != "cancelled" for d in earlier):
            continue
        update = any(d.status == "sent" for d in earlier)
        if connector.mode == "full":
            message = update_text if update else full_text
        else:
            message = alert(character, cycle, updated=update)
        # One the worker is sending now is locked, and left to go.
        waiting = db.scalar(
            select(Delivery)
            .where(
                Delivery.id.in_([d.id for d in earlier]),
                Delivery.status == "pending",
            )
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        row = waiting or Delivery(
            submission_id=submission.id,
            channel=connector.kind,
            status="pending",
            test_mode=connector.test_mode,
            sent_by=staff.id,
            next_attempt_at=now(),
        )
        row.revision = revision
        row.message = message
        row.subject = "updated downtime results" if update else ""
        if waiting is None:
            db.add(row)
            queued += 1
    return queued


def test_only(
    db: Session, submission_ids: Collection[uuid.UUID], connectors: Sequence[TroupeConnector]
) -> dict[uuid.UUID, list[str]]:
    """For each submission, the connectors among these that have had its results
    only in test mode: sent (or on their way) to the test channel or address, and
    never for real. They wait there for storytellers to send them to players
    (`send_test_only`); switching test mode off sends nothing by itself."""
    kinds = {c.kind for c in connectors}
    tried: dict[tuple[uuid.UUID, str], set[bool]] = {}
    for submission_id, channel, test_mode in db.execute(
        select(Delivery.submission_id, Delivery.channel, Delivery.test_mode).where(
            Delivery.submission_id.in_(list(submission_ids)),
            Delivery.channel.in_(kinds),
            Delivery.status.not_in(("failed", "cancelled")),
        )
    ):
        assert submission_id is not None
        tried.setdefault((submission_id, channel), set()).add(test_mode)
    found: dict[uuid.UUID, list[str]] = {}
    for (submission_id, channel), modes in sorted(tried.items(), key=lambda t: t[0][1]):
        if modes == {True}:
            found.setdefault(submission_id, []).append(channel)
    return found


def quest_link(character_id: uuid.UUID, quest_id: uuid.UUID) -> str:
    return f"{get_settings().public_url.rstrip('/')}/characters/{character_id}/quests/{quest_id}"


def queue_quest(
    db: Session,
    staff: User,
    troupe_id: uuid.UUID,
    quest_id: uuid.UUID,
    character: Character,
    subject: str,
    full_text: str,
) -> int:
    """Queue a quest's news for one of its characters (horatio.quests) on each of the
    troupe's connectors that send to the character (`to_own_channel`): the whole of
    it, or an alert with the link. Returns how many were queued."""
    connectors = [c for c in enabled_connectors(db, troupe_id) if to_own_channel(db, c, character)]
    for connector in connectors:
        alert_text = f"{subject}, for {character.name}: {quest_link(character.id, quest_id)}"
        db.add(
            Delivery(
                quest_id=quest_id,
                character_id=character.id,
                subject=subject,
                channel=connector.kind,
                status="pending",
                test_mode=connector.test_mode,
                message=full_text if connector.mode == "full" else alert_text,
                sent_by=staff.id,
                next_attempt_at=now(),
            )
        )
    return len(connectors)


def backoff(attempts: int) -> timedelta:
    """How long to wait after the `attempts`th failure: 1, 2, 4, 8… minutes."""
    return FIRST_WAIT * 2 ** (attempts - 1)


def send_one(db: Session, delivery: Delivery, at: datetime) -> None:
    """Try to send one locked, pending delivery, and record how it went. One no longer
    pending, cancelled while it waited, is left alone; one for a character's own Discord
    channel that its player has turned off since it was queued is cancelled, not sent
    (#1134)."""
    if delivery.status != "pending":
        return
    if own_channel_off(db, delivery):
        cancel(db, delivery, None)
        return
    delivery.attempts += 1
    try:
        if delivery.post_id is not None:
            from horatio import posts  # imports this module

            external = posts.send(db, delivery)
        else:
            external = send_message(db, delivery)
    except SendError as error:
        delivery.last_error = error.reason
        if error.retry and delivery.attempts < MAX_ATTEMPTS:
            wait = backoff(delivery.attempts)
            if error.retry_after is not None:
                wait = max(wait, timedelta(seconds=error.retry_after))
            delivery.next_attempt_at = at + wait
        else:
            if error.retry:
                delivery.last_error = f"Gave up after {delivery.attempts} tries: {error.reason}"
            delivery.status = "failed"
            delivery.next_attempt_at = None
        return
    delivery.status = "sent"
    delivery.sent_at = at
    delivery.last_error = None
    delivery.next_attempt_at = None
    delivery.external_ids = external


def send_message(db: Session, delivery: Delivery) -> dict[str, object]:
    """Send a downtime's results, or a quest's news, to its character's player.
    Returns what the connector called it, and where it went. Raises SendError."""
    if delivery.quest_id is not None:
        character, troupe, player = db.execute(
            select(Character, Troupe, User)
            .select_from(Quest)
            .join(Troupe, Quest.troupe_id == Troupe.id)
            .join(Character, Character.id == delivery.character_id)
            .join(User, Character.player_id == User.id)
            .where(Quest.id == delivery.quest_id)
        ).one()
        subject = f"{troupe.name}: {delivery.subject} ({character.name})"
        link = quest_link(character.id, delivery.quest_id)
    else:
        character, cycle, troupe, player = db.execute(
            select(Character, DowntimeCycle, Troupe, User)
            .select_from(Submission)
            .join(CycleParticipant, Submission.participant_id == CycleParticipant.id)
            .join(Character, CycleParticipant.character_id == Character.id)
            .join(DowntimeCycle, CycleParticipant.cycle_id == DowntimeCycle.id)
            .join(Troupe, DowntimeCycle.troupe_id == Troupe.id)
            .join(User, Character.player_id == User.id)
            .where(Submission.id == delivery.submission_id)
        ).one()
        what = delivery.subject or "downtime results"
        subject = f"{troupe.name}: {what} for {character.name} ({cycle.name})"
        link = results_link(character)
    connector = CONNECTORS.get(delivery.channel)
    config = db.scalar(
        select(TroupeConnector).where(
            TroupeConnector.troupe_id == troupe.id, TroupeConnector.kind == delivery.channel
        )
    )
    if connector is None or config is None:
        raise SendError(f"The troupe has no {delivery.channel} connector.", retry=False)
    if (reason := connector.unavailable()) is not None:
        raise SendError(reason, retry=False)
    if suspensions.current(db, player.id) is not None:
        raise SendError(f"{player.display_name}'s account is suspended.", retry=False)
    recipient = Recipient(
        character_id=character.id,
        character_name=character.name,
        player_name=player.display_name,
        player_email=player.email,
    )
    target = connector.target(config.settings, recipient, delivery.test_mode)
    message = Message(
        troupe=troupe.name,
        subject=subject,
        text=delivery.message,
        link=link,
        sender=mail_sender.sender(db),
        design=email_design.current(db),
    )
    return {**connector.send(config.settings, target, message), "target": target}


def send_due(db: Session, at: datetime | None = None, limit: int = 50) -> int:
    """Send pending deliveries that are due, each in its own transaction. Returns
    how many were tried."""
    tried = 0
    while tried < limit:
        at_now = at or now()
        delivery = db.scalar(
            select(Delivery)
            .where(
                Delivery.status == "pending",
                Delivery.channel != "horatio",
                Delivery.next_attempt_at <= at_now,
            )
            .order_by(Delivery.next_attempt_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if delivery is None:
            break
        try:
            send_one(db, delivery, at_now)
        except Exception:
            # A bug, not a failed send: record it and keep the worker going.
            log.exception("sending delivery %s", delivery.id)
            delivery.last_error = "Horatio could not send this; see the server log."
            delivery.status = "failed"
        db.commit()
        tried += 1
    return tried


def retry(delivery: Delivery) -> None:
    """Try a failed delivery again, straight away."""
    delivery.status = "pending"
    delivery.next_attempt_at = now()
    delivery.attempts = 0


def mark_sent(delivery: Delivery, user: User) -> None:
    """Record that someone sent it themselves."""
    delivery.status = "sent"
    delivery.sent_at = now()
    delivery.next_attempt_at = None
    delivery.marked_by = user.id


def send_due_now() -> int:
    """`send_due` in a session of its own, for the worker, after publishing the
    posts scheduled for now (horatio.posts) and telling everyone of the blog's new
    articles on the bell (horatio.blog_bell); then the notifications
    people asked for by email (horatio.notification_emails) and by push
    (horatio.web_push), the suspensions whose
    end date has passed (horatio.suspensions), the free changes by date that have
    run out (horatio.free_changes), the items that have expired or are about to
    (horatio.item_expiry), the Yorick pages kept long enough
    (horatio.yorick_imports), the Discord character channels troupes asked
    Horatio to make, keep in step and check (horatio.discord_channels), the
    emoji they asked it to add or remove (horatio.discord_emoji), and, once a day,
    the audit log's events kept long enough (horatio.audit_retention)."""
    from horatio import (
        audit_retention,
        blog_bell,
        discord_channels,
        discord_emoji,
        free_changes,
        item_expiry,
        notification_emails,
        posts,
        web_push,
        yorick_imports,
    )
    from horatio.db import get_sessionmaker

    # Scheduled posts first, so their Discord deliveries go in the same round.
    posts.publish_due_now()
    blog_bell.tell_due_now()
    with get_sessionmaker()() as db:
        sent = send_due(db) + notification_emails.send_due(db) + web_push.send_due(db)
    suspensions.end_due_now()
    free_changes.close_due_now()
    item_expiry.check_due_now()
    yorick_imports.expire_due_now()
    sent += discord_channels.make_due_now()
    sent += discord_channels.keep_in_step_now()
    sent += discord_emoji.push_due_now()
    audit_retention.purge_due_now()
    return sent


async def send_forever(interval: float) -> None:
    """The worker: send whatever is due every `interval` seconds, for as long as
    the API runs. Several API processes can each run one; row locks keep them
    from sending the same delivery."""
    while True:
        try:
            await asyncio.to_thread(send_due_now)
        except Exception:
            log.exception("sending deliveries")
        await asyncio.sleep(interval)
