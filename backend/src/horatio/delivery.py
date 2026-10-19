"""Delivering downtime results through a troupe's connectors (CONTEXT.md:
Connector, Channel).

Delivering a cycle records the in-app delivery at once and queues a `pending`
delivery on each connector the troupe has switched on. `send_due` sends what
is due, one delivery at a time, each row locked while it is sent so two
workers never send it twice. A failure worth retrying is tried again later,
backing off each time; after `MAX_ATTEMPTS`, or a failure that is not worth
retrying, the delivery is `failed` for storytellers to retry or mark as sent
by hand.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

import horatio.connectors.discord
import horatio.connectors.email
from horatio.config import get_settings
from horatio.connectors import CONNECTORS, Message, Recipient, SendError
from horatio.models import (
    Character,
    CycleParticipant,
    Delivery,
    DowntimeCycle,
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


def alert(character: Character, cycle: DowntimeCycle) -> str:
    return (
        f"Your downtime results for {character.name} ({cycle.name}) are ready: "
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


def queue(
    db: Session,
    staff: User,
    connectors: list[TroupeConnector],
    cycle: DowntimeCycle,
    character: Character,
    submission: Submission,
    full_text: str,
) -> int:
    """Queue the submission on each connector that has no delivery for it yet (in
    the connector's current test mode). Returns how many were queued."""
    queued = 0
    for connector in connectors:
        exists = db.scalar(
            select(Delivery.id).where(
                Delivery.submission_id == submission.id,
                Delivery.channel == connector.kind,
                Delivery.test_mode.is_(connector.test_mode),
            )
        )
        if exists is not None:
            continue
        db.add(
            Delivery(
                submission_id=submission.id,
                channel=connector.kind,
                status="pending",
                test_mode=connector.test_mode,
                message=full_text if connector.mode == "full" else alert(character, cycle),
                sent_by=staff.id,
                next_attempt_at=now(),
            )
        )
        queued += 1
    return queued


def backoff(attempts: int) -> timedelta:
    """How long to wait after the `attempts`th failure: 1, 2, 4, 8… minutes."""
    return FIRST_WAIT * 2 ** (attempts - 1)


def send_one(db: Session, delivery: Delivery, at: datetime) -> None:
    """Try to send one locked, pending delivery, and record how it went."""
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
    delivery.attempts += 1
    connector = CONNECTORS.get(delivery.channel)
    config = db.scalar(
        select(TroupeConnector).where(
            TroupeConnector.troupe_id == troupe.id, TroupeConnector.kind == delivery.channel
        )
    )
    try:
        if connector is None or config is None:
            raise SendError(f"The troupe has no {delivery.channel} connector.", retry=False)
        if (reason := connector.unavailable()) is not None:
            raise SendError(reason, retry=False)
        recipient = Recipient(
            character_id=character.id,
            character_name=character.name,
            player_name=player.display_name,
            player_email=player.email,
        )
        target = connector.target(config.settings, recipient, delivery.test_mode)
        message = Message(
            troupe=troupe.name,
            subject=f"{troupe.name}: downtime results for {character.name} ({cycle.name})",
            text=delivery.message,
            link=results_link(character),
        )
        external = connector.send(config.settings, target, message)
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
    delivery.external_ids = {**external, "target": target}


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
    """`send_due` in a session of its own, for the worker."""
    from horatio.db import get_sessionmaker

    with get_sessionmaker()() as db:
        return send_due(db)


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
