"""Equipment given from a downtime response (issue #508): a new item, or a quality on
an item the character already holds. The book has characters get equipment through
downtime: an item beyond their means (MET: VTM pp. 307-308), crafting (p. 93),
items in general (p. 515), and the Antique (p. 404), Stylish or Nondescript
(p. 487) qualities.

The storytellers and assistant storytellers of the character's home troupe add it
while writing the response. It reaches the character when the response is
delivered, with the results (horatio.responses.deliver_cycle), which say "You
received: ..."; the item's history links back to the response. Until then they
change it or take it off; once given it is an item like any other, changed on the
Equipment tab.

`add` is how anything else gives equipment from a response, such as a downtime
keyword (#509).
"""

import uuid
from collections import defaultdict
from collections.abc import Collection, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit, equipment
from horatio.equipment import EquipmentRefused, FromDowntime, ItemFields, ItemQuality
from horatio.models import (
    Answer,
    Character,
    DowntimeCycle,
    EquipmentItem,
    Response,
    ResponseItem,
    Submission,
    Troupe,
    User,
)
from horatio.rules.equipment import item_qualities
from horatio.sheets import conflict, unprocessable

if TYPE_CHECKING:
    from horatio.responses import WorkItem

ITEM = "item"
QUALITY = "quality"


@dataclass(frozen=True)
class NewItem:
    """A new item, built as the Equipment tab builds one."""

    fields: ItemFields
    # The template it was started from, for its history.
    template: str | None = None


@dataclass(frozen=True)
class NewQuality:
    """A quality on an item the character holds."""

    item_id: uuid.UUID
    quality: ItemQuality


Giving = NewItem | NewQuality


def now() -> datetime:
    return datetime.now(UTC)


def on_responses(
    db: Session, response_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, list[ResponseItem]]:
    """What each response gives, in the order it was added."""
    found: dict[uuid.UUID, list[ResponseItem]] = defaultdict(list)
    if not response_ids:
        return found
    for row in db.scalars(
        select(ResponseItem)
        .where(ResponseItem.response_id.in_(response_ids))
        .order_by(ResponseItem.created_at, ResponseItem.id)
    ):
        found[row.response_id].append(row)
    return found


def fields_of(raw: Mapping[str, Any]) -> ItemFields:
    """A new item's fields, as kept."""
    return ItemFields(
        name=raw["name"],
        kind=raw["kind"],
        grade=raw["grade"],
        qualities=item_qualities(raw.get("qualities", [])),
        crafted=raw.get("crafted", False),
        effects=equipment.effects_of(raw.get("effects", [])),
        description=raw.get("description", ""),
        staff_note=raw.get("staff_note", ""),
        archaic=raw.get("archaic", False),
    )


def quality_of(row: ResponseItem) -> ItemQuality:
    return ItemQuality(row.fields["name"], row.fields.get("detail", ""))


def text(row: ResponseItem) -> str:
    """What the player receives, in a few words: "Sniper rifle (Accurate, Scoped)",
    or "Antique on Grandfather's revolver"."""
    if row.kind == QUALITY:
        return f"{equipment.quality_text(quality_of(row))} on {row.fields['item_name']}"
    fields = fields_of(row.fields)
    shown = [equipment.quality_text(q) for q in fields.qualities]
    shown += [e.name for e in fields.effects]
    return f"{fields.name} ({', '.join(shown)})" if shown else fields.name


def received(rows: Collection[ResponseItem]) -> str:
    """The line the results carry for a response's equipment."""
    return "; ".join(text(row) for row in rows)


def require_giver(db: Session, staff: User, work: "WorkItem", troupe: Troupe) -> None:
    """Only the staff who give the character equipment: its home troupe's
    storytellers and assistant storytellers, and the custodian."""
    if not equipment.can_manage(db, staff, troupe):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only the troupe's storytellers and assistant storytellers give equipment.",
        )
    equipment.require_home(troupe, work.character)
    if work.cycle.status == "complete":
        raise conflict("This cycle is complete.")


def pending_qualities(
    db: Session, item_id: uuid.UUID, leaving_out: uuid.UUID | None
) -> tuple[ItemQuality, ...]:
    """Qualities other responses will add to the item, not yet given."""
    rows = db.scalars(
        select(ResponseItem)
        .where(
            ResponseItem.kind == QUALITY,
            ResponseItem.item_id == item_id,
            ResponseItem.given_at.is_(None),
        )
        .order_by(ResponseItem.created_at, ResponseItem.id)
    )
    return tuple(quality_of(r) for r in rows if r.id != leaving_out)


def held_item(db: Session, character: Character, item_id: uuid.UUID | None) -> EquipmentItem:
    item = db.get(EquipmentItem, item_id) if item_id else None
    if item is None or item.character_id != character.id or item.status != "held":
        raise unprocessable(f"{character.name} doesn't hold that item now.")
    return item


def fill(db: Session, work: "WorkItem", row: ResponseItem, giving: Giving) -> None:
    """Set what the row gives, checked as the item would be now: EquipmentRefused
    if it breaks the rules between qualities."""
    rules = equipment.equipment_rules(db, work.character.splat, work.cycle.troupe_id)
    if isinstance(giving, NewItem):
        fields = equipment.checked(rules, giving.fields)
        row.kind = ITEM
        row.item_id = None
        row.fields = {
            **equipment.as_recorded(fields),
            **({"template": giving.template} if giving.template else {}),
        }
        return
    item = held_item(db, work.character, giving.item_id)
    quality = ItemQuality(giving.quality.name, giving.quality.detail.strip())
    held = equipment.fields_of(item)
    added = (*pending_qualities(db, item.id, row.id), quality)
    equipment.checked(rules, replace(held, qualities=held.qualities + added))
    row.kind = QUALITY
    row.item_id = item.id
    row.fields = {"name": quality.name, "detail": quality.detail, "item_name": item.name}


def add(db: Session, staff: User, work: "WorkItem", troupe: Troupe, giving: Giving) -> ResponseItem:
    """Give the character an item, or a quality on one it holds, from the response,
    when the response is delivered."""
    require_giver(db, staff, work, troupe)
    row = ResponseItem(response_id=work.response.id, created_by=staff.id, fields={})
    fill(db, work, row, giving)
    db.add(row)
    db.flush()
    audit.record(
        db,
        staff,
        "response.item_added",
        troupe_id=troupe.id,
        character_id=work.character.id,
        response_id=work.response.id,
        what=text(row),
    )
    return row


def not_given(work: "WorkItem", row: ResponseItem) -> None:
    if row.given_at is not None:
        raise conflict(
            f"{text(row)} has gone to {work.character.name} with the results:"
            " change it on the Equipment tab."
        )


def change(
    db: Session, staff: User, work: "WorkItem", troupe: Troupe, row: ResponseItem, giving: Giving
) -> ResponseItem:
    """Change what the response gives, before it is delivered."""
    require_giver(db, staff, work, troupe)
    not_given(work, row)
    fill(db, work, row, giving)
    db.flush()
    audit.record(
        db,
        staff,
        "response.item_changed",
        troupe_id=troupe.id,
        character_id=work.character.id,
        response_id=work.response.id,
        what=text(row),
    )
    return row


def remove(db: Session, staff: User, work: "WorkItem", troupe: Troupe, row: ResponseItem) -> None:
    """Take it off the response, before it is delivered: nothing is given."""
    require_giver(db, staff, work, troupe)
    not_given(work, row)
    what = text(row)
    db.delete(row)
    db.flush()
    audit.record(
        db,
        staff,
        "response.item_removed",
        troupe_id=troupe.id,
        character_id=work.character.id,
        response_id=work.response.id,
        what=what,
    )


def deliver(
    db: Session,
    cycle: DowntimeCycle,
    troupe: Troupe,
    character: Character,
    submission: Submission,
) -> int:
    """With the submission's delivery, give what its written responses carry that
    hasn't been given, from whoever added each. Something that can't be given now,
    such as a quality on an item the character no longer holds, stops the delivery
    with the reason. Returns how many were given."""
    rows = db.execute(
        select(ResponseItem, Response)
        .join(Response, ResponseItem.response_id == Response.id)
        .join(Answer, Response.answer_id == Answer.id)
        .where(
            Answer.submission_id == submission.id,
            Response.status == "written",
            ResponseItem.given_at.is_(None),
        )
        .order_by(ResponseItem.created_at, ResponseItem.id)
    ).all()
    for row, response in rows:
        giver = db.get_one(User, row.created_by)
        downtime = FromDowntime(cycle.id, cycle.name, response.id)
        try:
            if row.kind == ITEM:
                item = equipment.give(
                    db,
                    giver,
                    troupe,
                    character,
                    fields_of(row.fields),
                    template=row.fields.get("template"),
                    downtime=downtime,
                )
                row.item_id = item.id
            else:
                item = held_item(db, character, row.item_id)
                held = equipment.fields_of(item)
                equipment.change(
                    db,
                    giver,
                    troupe,
                    item,
                    replace(held, qualities=(*held.qualities, quality_of(row))),
                    "",
                    downtime=downtime,
                )
        except (EquipmentRefused, HTTPException) as error:
            reason = str(error) if isinstance(error, EquipmentRefused) else error.detail
            raise conflict(
                f"Couldn't give {character.name} {text(row)} from the {cycle.name} downtime:"
                f" {reason} Change it or take it off the response, then deliver again."
            ) from None
        row.given_at = now()
    db.flush()
    return len(rows)
