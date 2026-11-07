import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey
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
        # Only an item moved from a sheet with no home troupe has no troupe (#341).
        CheckConstraint("troupe_id is not null or from_sheet", name="troupe_given"),
        # An expiry (#443): on a date, after a number of the holder's games, or when a
        # downtime cycle closes, each with what it needs.
        CheckConstraint(
            "expiry_kind is null"
            " or (expiry_kind = 'date' and expires_on is not null)"
            " or (expiry_kind = 'games' and expires_after_games > 0)"
            " or (expiry_kind = 'cycle' and expires_cycle_id is not null)",
            name="expiry",
        ),
    )

    # Who holds it; once taken back or discarded, who last held it.
    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("characters.id"), index=True)
    # The troupe that gave it: for one moved from the sheet, the holder's home troupe
    # then, if it had one.
    troupe_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("troupes.id"), index=True)
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
    # An archaic ranged weapon (a bow, a crossbow) may shoot with Athletics instead
    # of Firearms (MET: VTM p. 279).
    archaic: Mapped[bool] = mapped_column(default=False, server_default="false")
    # A special item's own effects, which no quality covers: each {name, effect}.
    effects: Mapped[list[dict[str, str]]] = mapped_column(JSONB, default=list, server_default="[]")
    description: Mapped[str] = mapped_column(default="", server_default="")
    # Only staff see it.
    staff_note: Mapped[str] = mapped_column(default="", server_default="")
    # The troupe that made it special: null unless it is.
    special_troupe_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("troupes.id"))
    status: Mapped[str] = mapped_column(default="held", server_default="held", index=True)
    # A Vampiric Text the character held as a trait on its sheet, which migration
    # 0115 made an item (#341): nobody gave it.
    from_sheet: Mapped[bool] = mapped_column(default=False, server_default="false")
    # When it expires (horatio.item_expiry, #443), while its holder's home troupe lets
    # items expire: "date", once the day `expires_on` is over; "games", once the
    # holder has been to `expires_after_games` games starting from `expiry_from`;
    # "cycle", when the downtime cycle `expires_cycle_id` closes. None: never.
    expiry_kind: Mapped[str | None]
    expires_on: Mapped[date | None] = mapped_column(Date)
    expires_after_games: Mapped[int | None]
    expires_cycle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("downtime_cycles.id"))
    # When the expiry was set: games are counted from then.
    expiry_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # What happens when it expires, for its holder: "The blessing fades".
    expiry_note: Mapped[str] = mapped_column(default="", server_default="")
    # When its holder was warned it is about to expire; None until then.
    expiry_warned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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


class ResponseItem(Record):
    """Equipment staff give from a downtime response (issue #508): a new item, or a
    quality on an item the character holds. It reaches the character when the
    response is delivered, with the results (horatio.response_items); until then
    staff change it or take it off the response."""

    __tablename__ = "response_items"
    __table_args__ = (CheckConstraint("kind in ('item', 'quality')", name="kind"),)

    response_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("responses.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str]
    # A new item as staff built it (horatio.equipment.as_recorded), with the
    # template it was started from; a quality, {name, detail, item_name}, with the
    # name of the item it goes on as it was then.
    fields: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    # A quality's item; a new item's, once given.
    item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("equipment_items.id", ondelete="SET NULL")
    )
    # Who added it: the item's giver.
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # When it reached the character; None until the response is delivered.
    given_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
