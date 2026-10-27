import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record
from horatio.models.rules import EQUIPMENT_KIND_CHECK


class EquipmentItem(Record):
    """An item of equipment a character holds (horatio.equipment): given by its home
    troupe's storytellers, and the character's from then on, wherever its home is."""

    __tablename__ = "equipment_items"
    __table_args__ = (
        CheckConstraint(EQUIPMENT_KIND_CHECK, name="kind"),
        CheckConstraint("grade in ('cheap', 'standard', 'special')", name="grade"),
        # Held by its character, taken back by staff, or discarded by its player (#282).
        CheckConstraint("status in ('held', 'taken_back', 'discarded')", name="status"),
        # A special item says which troupe made it so.
        CheckConstraint(
            "(grade = 'special') = (special_troupe_id is not null)", name="special_troupe"
        ),
    )

    # Who holds it; once taken back or discarded, who last held it.
    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("characters.id"), index=True)
    # The troupe that gave it.
    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    given_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    given_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    name: Mapped[str]
    kind: Mapped[str]
    grade: Mapped[str]
    # Each {name, detail?}, checked by horatio.equipment.check.
    qualities: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    # Its Artisan and Masterwork were added while crafting, and take no slot.
    crafted: Mapped[bool] = mapped_column(default=False, server_default="false")
    # A special item's own effects, which no quality covers: each {name, effect}.
    effects: Mapped[list[dict[str, str]]] = mapped_column(JSONB, default=list, server_default="[]")
    description: Mapped[str] = mapped_column(default="", server_default="")
    # Only staff see it.
    staff_note: Mapped[str] = mapped_column(default="", server_default="")
    # The troupe that made it special: null unless it is.
    special_troupe_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("troupes.id"))
    status: Mapped[str] = mapped_column(default="held", server_default="held", index=True)


class EquipmentEvent(Record):
    """One line in an item's history: where it came from, and every change since."""

    __tablename__ = "equipment_events"
    __table_args__ = (
        # Given by a troupe, changed or taken back by its staff; and, from #282,
        # passed from one character to another, discarded and restored.
        CheckConstraint(
            "action in ('given', 'changed', 'taken_back', 'passed', 'discarded', 'restored')",
            name="action",
        ),
    )

    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("equipment_items.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str]
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    # The troupe whose staff did it; null for a player's own doing (#282).
    troupe_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("troupes.id"))
    # Who held it before and after: the same character for a change. Null for a
    # character since deleted, whose name the event keeps.
    from_character_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL")
    )
    to_character_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL")
    )
    from_name: Mapped[str] = mapped_column(default="", server_default="")
    to_name: Mapped[str] = mapped_column(default="", server_default="")
    reason: Mapped[str] = mapped_column(default="", server_default="")
    # For a change, each field changed: {field: {"from": ..., "to": ...}}.
    changes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
