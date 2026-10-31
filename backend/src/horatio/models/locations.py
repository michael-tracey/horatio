import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class Location(Record):
    """A Stock Location, or a character's Haven placed on the list (CONTEXT.md:
    Location). The troupe's storytellers and assistant storytellers keep it
    (horatio.locations), which records each change in the audit log; players
    never see the record."""

    __tablename__ = "locations"
    __table_args__ = (
        UniqueConstraint("troupe_id", "name", name="uq_locations_name"),
        CheckConstraint("kind in ('standard', 'prestige', 'iconic', 'haven')", name="kind"),
        CheckConstraint("rating between 1 and 5", name="rating"),
        CheckConstraint(
            "control in ('character', 'named', 'none', 'uncontrollable')", name="control"
        ),
        CheckConstraint("(control = 'character') = (controller_id is not null)", name="controller"),
        CheckConstraint("(control = 'named') = (controller_name <> '')", name="controller_name"),
        CheckConstraint("parent_id is null or parent_id <> id", name="not_own_parent"),
        CheckConstraint(
            "influence_type is null or influence_type in ('elite', 'underworld')",
            name="influence_type",
        ),
        CheckConstraint("(kind = 'haven') <= (haven_of_id is not null)", name="haven_has_owner"),
    )

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    name: Mapped[str]
    # Its conglomerate (house option): the location it is a subsidiary of.
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL"), index=True
    )
    # standard, prestige or iconic (p. 118); or haven, a Haven background placed here.
    kind: Mapped[str]
    rating: Mapped[int]
    # Each {"name", "detail"}: from the troupe's catalogue (horatio.rules.locations).
    qualities: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    # Each {"name", "level", "secret", "by"}: a negative quality, ×1 to ×3, kept
    # secret from the controller or not, and who is behind it (p. 127). Out of Code
    # also counts the "games" passed at its level (horatio.location_quests).
    negatives: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    # The qualities Damaged has switched off, as staff chose them (p. 127).
    damaged_off: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    # Who controls it: a character, an NPC known only by name, nobody, or nobody
    # ever (uncontrollable, p. 121).
    control: Mapped[str] = mapped_column(default="none", server_default="none")
    controller_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("characters.id"), index=True)
    controller_name: Mapped[str] = mapped_column(default="", server_default="")
    # Joint control, and an heir or ranking officer to pick it up (p. 121): a
    # character, or a name.
    joint_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("characters.id"), index=True)
    joint_name: Mapped[str] = mapped_column(default="", server_default="")
    heir_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("characters.id"))
    heir_name: Mapped[str] = mapped_column(default="", server_default="")
    # Its influence area: an Elite or Underworld specialisation.
    influence_type: Mapped[str | None]
    influence_area: Mapped[str] = mapped_column(default="", server_default="")
    address: Mapped[str] = mapped_column(default="", server_default="")
    web_address: Mapped[str] = mapped_column(default="", server_default="")
    map_link: Mapped[str] = mapped_column(default="", server_default="")
    feeding_block: Mapped[str] = mapped_column(default="", server_default="")
    # Staff are holding it: no quest may target it.
    locked: Mapped[bool] = mapped_column(default=False, server_default="false")
    # The character whose Haven it is (p. 117), and the Haven's advantages.
    haven_of_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("characters.id"), index=True)
    haven_advantages: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    # An Elysium: the year since which it has stood unviolated, which gives it its
    # Elysium qualities (p. 131). None for a location that is not one.
    elysium_since: Mapped[int | None]
    notes: Mapped[str] = mapped_column(default="", server_default="")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class TroupeLocationQuality(Record):
    """A location quality a troupe added to the catalogue, as it adds house merits:
    its text and the suggested requirements of a quest for it."""

    __tablename__ = "troupe_location_qualities"
    __table_args__ = (
        UniqueConstraint("troupe_id", "name", name="uq_troupe_location_qualities_name"),
        CheckConstraint("kind in ('standard', 'iconic', 'supernatural', 'elysium')", name="kind"),
    )

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    name: Mapped[str]
    kind: Mapped[str] = mapped_column(default="standard", server_default="standard")
    text: Mapped[str]
    # What an instance can name, such as a specialisation; empty for nothing.
    detail: Mapped[str] = mapped_column(default="", server_default="")
    repeatable: Mapped[bool] = mapped_column(default=False, server_default="false")
    # As the catalogue's `suggested` (horatio.rules.locations.Suggestion).
    suggested: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    # Archived: no longer offered; locations that have it keep it.
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
