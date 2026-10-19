"""A troupe's connectors, and how each cycle's deliveries went on each channel."""

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from horatio import audit, delivery
from horatio.api.downtimes import staff_cycle, staff_troupe
from horatio.auth.deps import CurrentUser, DbSession
from horatio.connectors import CONNECTORS
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
from horatio.permissions import TroupeAction

router = APIRouter(tags=["connectors"])


class ConnectorOut(BaseModel):
    kind: str
    name: str
    # Why this server cannot use it (it is not set up), or None.
    unavailable: str | None
    enabled: bool
    mode: Literal["full", "alert"]
    test_mode: bool
    settings: dict[str, Any]


class ConnectorChange(BaseModel):
    enabled: bool
    mode: Literal["full", "alert"] = "alert"
    test_mode: bool = False
    settings: dict[str, Any] = {}


def connector_row(db: DbSession, troupe_id: uuid.UUID, kind: str) -> TroupeConnector | None:
    return db.scalar(
        select(TroupeConnector).where(
            TroupeConnector.troupe_id == troupe_id, TroupeConnector.kind == kind
        )
    )


def connectors_out(db: DbSession, troupe_id: uuid.UUID) -> list[ConnectorOut]:
    found: list[ConnectorOut] = []
    for kind, connector in sorted(CONNECTORS.items()):
        row = connector_row(db, troupe_id, kind)
        found.append(
            ConnectorOut(
                kind=kind,
                name=connector.name,
                unavailable=connector.unavailable(),
                enabled=row.enabled if row else False,
                mode=row.mode if row else "alert",  # type: ignore[arg-type]  # checked by the database
                test_mode=row.test_mode if row else False,
                settings=row.settings if row else {},
            )
        )
    return found


@router.get("/troupes/{troupe_id}/connectors")
def list_connectors(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[ConnectorOut]:
    """The connectors this server offers, as the troupe has set them up. In-app
    delivery is always on and is not listed."""
    staff_troupe(db, user, troupe_id, TroupeAction.DELIVER_RESPONSES)
    return connectors_out(db, troupe_id)


@router.put("/troupes/{troupe_id}/connectors/{kind}")
def change_connector(
    troupe_id: uuid.UUID, kind: str, body: ConnectorChange, db: DbSession, user: CurrentUser
) -> ConnectorOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_CONNECTORS)
    connector = CONNECTORS.get(kind)
    if connector is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such connector.")
    if body.enabled and (reason := connector.unavailable()) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, reason)
    row = connector_row(db, troupe.id, kind)
    try:
        settings = connector.check_settings(body.settings, row.settings if row else {})
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    if row is None:
        row = TroupeConnector(troupe_id=troupe.id, kind=kind, settings={})
        db.add(row)
    row.enabled = body.enabled
    row.mode = body.mode
    row.test_mode = body.test_mode
    row.settings = settings
    audit.record(
        db,
        user,
        "connector.changed",
        troupe_id=troupe.id,
        connector=connector.name,
        state=("on, in test mode" if body.test_mode else "on") if body.enabled else "off",
    )
    db.commit()
    return next(c for c in connectors_out(db, troupe.id) if c.kind == kind)


# --- delivery status ---------------------------------------------------------------------


class DeliveryOut(BaseModel):
    id: uuid.UUID
    channel: str
    status: Literal["pending", "sent", "failed"]
    test_mode: bool
    attempts: int
    last_error: str | None
    sent_at: datetime | None
    next_attempt_at: datetime | None
    # Who marked it sent by hand, if anyone did.
    marked_by: str | None


class ParticipantDeliveries(BaseModel):
    character_id: uuid.UUID
    character_name: str
    # The latest delivery on each channel; a channel with none is missing.
    deliveries: dict[str, DeliveryOut]


class DeliveryStatus(BaseModel):
    # In-app first, then each of the troupe's connectors that is on.
    channels: list[str]
    participants: list[ParticipantDeliveries]


@router.get("/cycles/{cycle_id}/deliveries")
def cycle_deliveries(cycle_id: uuid.UUID, db: DbSession, user: CurrentUser) -> DeliveryStatus:
    """Each submission against each channel: how its delivery went."""
    cycle, troupe = staff_cycle(db, user, cycle_id, TroupeAction.DELIVER_RESPONSES)
    rows = db.execute(
        select(Submission, Character)
        .join(CycleParticipant, Submission.participant_id == CycleParticipant.id)
        .join(Character, CycleParticipant.character_id == Character.id)
        .where(
            CycleParticipant.cycle_id == cycle.id,
            CycleParticipant.removed_at.is_(None),
            Submission.status == "submitted",
        )
        .order_by(Character.name)
    ).all()
    deliveries = db.scalars(
        select(Delivery)
        .where(Delivery.submission_id.in_([s.id for s, _ in rows]))
        .order_by(Delivery.created_at, Delivery.id)
    ).all()
    names = {
        user_id: name
        for user_id, name in db.execute(
            select(User.id, User.display_name).where(
                User.id.in_([d.marked_by for d in deliveries if d.marked_by])
            )
        )
    }
    latest: dict[tuple[uuid.UUID, str], Delivery] = {}
    for d in deliveries:
        latest[(d.submission_id, d.channel)] = d
    channels = ["horatio", *[c.kind for c in delivery.enabled_connectors(db, troupe.id)]]
    channels += sorted({d.channel for d in deliveries} - set(channels))
    return DeliveryStatus(
        channels=channels,
        participants=[
            ParticipantDeliveries(
                character_id=character.id,
                character_name=character.name,
                deliveries={
                    channel: delivery_out(d, names)
                    for channel in channels
                    if (d := latest.get((submission.id, channel))) is not None
                },
            )
            for submission, character in rows
        ],
    )


def delivery_out(d: Delivery, names: dict[uuid.UUID, str]) -> DeliveryOut:
    return DeliveryOut(
        id=d.id,
        channel=d.channel,
        status=d.status,  # type: ignore[arg-type]  # checked by the database
        test_mode=d.test_mode,
        attempts=d.attempts,
        last_error=d.last_error,
        sent_at=d.sent_at,
        next_attempt_at=d.next_attempt_at,
        marked_by=names.get(d.marked_by) if d.marked_by else None,
    )


def staff_delivery(
    db: DbSession, user: User, delivery_id: uuid.UUID
) -> tuple[Delivery, Troupe, Character]:
    found = db.execute(
        select(Delivery, DowntimeCycle, Character)
        .join(Submission, Delivery.submission_id == Submission.id)
        .join(CycleParticipant, Submission.participant_id == CycleParticipant.id)
        .join(DowntimeCycle, CycleParticipant.cycle_id == DowntimeCycle.id)
        .join(Character, CycleParticipant.character_id == Character.id)
        .where(Delivery.id == delivery_id)
        .with_for_update(of=Delivery)
    ).first()
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such delivery.")
    d, cycle, character = found
    troupe = staff_troupe(db, user, cycle.troupe_id, TroupeAction.DELIVER_RESPONSES)
    return d, troupe, character


@router.post("/deliveries/{delivery_id}/retry")
def retry_delivery(delivery_id: uuid.UUID, db: DbSession, user: CurrentUser) -> DeliveryOut:
    d, troupe, character = staff_delivery(db, user, delivery_id)
    if d.status != "failed":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a failed delivery can be retried.")
    delivery.retry(d)
    audit.record(
        db,
        user,
        "delivery.retried",
        troupe_id=troupe.id,
        character_id=character.id,
        channel=d.channel,
    )
    db.commit()
    return delivery_out(d, {})


@router.post("/deliveries/{delivery_id}/mark-sent")
def mark_delivery_sent(delivery_id: uuid.UUID, db: DbSession, user: CurrentUser) -> DeliveryOut:
    d, troupe, character = staff_delivery(db, user, delivery_id)
    if d.status == "sent":
        raise HTTPException(status.HTTP_409_CONFLICT, "That delivery was already sent.")
    delivery.mark_sent(d, user)
    audit.record(
        db,
        user,
        "delivery.marked_sent",
        troupe_id=troupe.id,
        character_id=character.id,
        channel=d.channel,
    )
    db.commit()
    return delivery_out(d, {user.id: user.display_name})
