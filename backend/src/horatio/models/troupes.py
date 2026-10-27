import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Imported, Record


class Troupe(Imported, Record):
    """The top-level group. Archived rather than deleted."""

    __tablename__ = "troupes"
    __table_args__ = (
        CheckConstraint(
            "diablerie_flaws in ('leave', 'remove', 'keep_xp')", name="diablerie_flaws"
        ),
        CheckConstraint("status_by in ('players', 'staff')", name="status_by"),
        CheckConstraint("badge_status in ('all', 'negative', 'none')", name="badge_status"),
    )

    name: Mapped[str]
    description: Mapped[str] = mapped_column(default="", server_default="")
    # Not null: every troupe has exactly one lead storyteller, enforced here
    # rather than by counting rows in troupe_staff.
    lead_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Sects whose PCs may join; empty means any.
    allowed_sects: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    # Splats whose PCs may join, and be built for it (horatio.rules.splats): never
    # empty. NPCs are the troupe's own, of any splat.
    allowed_splats: Mapped[list[str]] = mapped_column(
        JSONB, default=lambda: ["vampire"], server_default='["vampire"]'
    )
    # Experience the troupe usually gives: for a game session, and for completing a
    # downtime. Defaults for awarding and for new cycles; each can be changed there.
    session_xp: Mapped[int] = mapped_column(default=8, server_default="8")
    downtime_xp: Mapped[int] = mapped_column(default=2, server_default="2")
    # The XP a character had when the chronicle began: where the troupe's XP floor
    # and ceiling start (horatio.xp_range).
    starting_xp: Mapped[int] = mapped_column(default=30, server_default="30")
    # House rule: the blood characters start a game with (no more than their
    # generation's most). None starts them full.
    starting_blood: Mapped[int | None]
    # House rule: how many days back Gossip & Insider Trading and Word on the
    # Street look in the influence log, from the close of the lookup's cycle
    # (horatio.influence_lookups). The rules' "within the last 3 months".
    influence_lookback_days: Mapped[int] = mapped_column(default=90, server_default="90")
    # House rule: what a diablerie does to a Lesser Generation or Thin Blooded flaw
    # (horatio.diablerie): "leave" it, "remove" it and the XP it gave, or "keep_xp"
    # to remove it and keep that XP.
    diablerie_flaws: Mapped[str] = mapped_column(default="leave", server_default="leave")
    # Status on sheets (horatio.sect_status): who adds and removes fleeting and
    # negative status on its characters' sheets: "players", each on their own, naming
    # the patron; or "staff", its running staff only. Running staff always can.
    status_by: Mapped[str] = mapped_column(default="players", server_default="players")
    # What its game badges print (horatio.badges): the titles held here, or not; and
    # the status carried into a game here, "all" of it, "negative" status only, or
    # "none", leaving the space for stickers.
    badge_titles: Mapped[bool] = mapped_column(default=True, server_default="true")
    badge_status: Mapped[str] = mapped_column(default="all", server_default="all")
    # Its Who's Who (horatio.whos_who) adds the negative status each character carries
    # into a game here, which is public in the sect anyway (MET: VTM p. 312).
    whos_who_negative: Mapped[bool] = mapped_column(default=False, server_default="false")
    # Its profile (horatio.troupe_profiles), which anyone signed in can see, and
    # anyone at all when `public` is ticked. The portrait and banner are the ids
    # their files are kept under (horatio.pictures); the portrait's crop is as a
    # character picture's.
    public: Mapped[bool] = mapped_column(default=False, server_default="false")
    portrait_id: Mapped[uuid.UUID | None]
    portrait_crop: Mapped[dict[str, float] | None] = mapped_column(JSONB)
    banner_id: Mapped[uuid.UUID | None]
    # Links, schedule, venue, setting, new players, age and content: all optional
    # text, kept as horatio.troupe_profiles.Profile writes it.
    profile: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    # Who new players should contact: one of its staff.
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class ScheduledGame(Record):
    """A game the troupe will run, on its profile. Kept once it is past, but no
    longer shown."""

    __tablename__ = "scheduled_games"
    __table_args__ = (CheckConstraint("ends_at > starts_at", name="ends_after_start"),)

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class XpRangeEntry(Record):
    """One change to a troupe's XP floor and ceiling: a game's XP, a downtime
    cycle's XP for completing it, or staff setting either figure by hand. The
    figures are the troupe's starting XP plus every change (horatio.xp_range)."""

    __tablename__ = "xp_range_entries"
    __table_args__ = (CheckConstraint("kind in ('game', 'downtime', 'set')", name="kind"),)

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    kind: Mapped[str]
    floor_change: Mapped[int]
    ceiling_change: Mapped[int]
    reason: Mapped[str] = mapped_column(default="", server_default="")
    entered_on: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    # Null for a downtime cycle counted when the floor and ceiling began.
    entered_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    # For a downtime: the cycle whose closing added it.
    cycle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("downtime_cycles.id"))


class TroupeRequest(Record):
    """Someone asking the custodian for a new troupe, which they would lead. Kept
    after it is decided or withdrawn, as the record of how the troupe began."""

    __tablename__ = "troupe_requests"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending', 'approved', 'declined', 'withdrawn')", name="status"
        ),
    )

    requester_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str]
    description: Mapped[str] = mapped_column(default="", server_default="")
    # Anything the requester wants the custodian to know.
    note: Mapped[str] = mapped_column(default="", server_default="")
    status: Mapped[str] = mapped_column(default="pending", server_default="pending", index=True)
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Why it was declined, if the custodian said.
    reason: Mapped[str] = mapped_column(default="", server_default="")
    # The troupe approving it made.
    troupe_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("troupes.id"))


class TroupeStaff(Record):
    """A storyteller, assistant storyteller or narrator. The lead is not listed here."""

    __tablename__ = "troupe_staff"
    __table_args__ = (
        UniqueConstraint("troupe_id", "user_id"),
        CheckConstraint(
            "role in ('storyteller', 'assistant_storyteller', 'narrator')", name="role"
        ),
    )

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str]


class TroupeMembership(Record):
    """A character's membership of a troupe. Kept after the character leaves."""

    __tablename__ = "troupe_memberships"
    __table_args__ = (
        # A character can rejoin a troupe, but is only a current member once.
        Index(
            "uq_troupe_memberships_current",
            "troupe_id",
            "character_id",
            unique=True,
            postgresql_where=text("left_at is null"),
        ),
        CheckConstraint("left_at is null or left_at >= joined_at", name="left_after_joined"),
    )

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("characters.id"), index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The sheet as this troupe accepted it as the character's home troupe. Null for a
    # troupe the character only visits.
    approved_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sheet_versions.id", use_alter=True)
    )


class TroupeSpecialization(Record):
    """An option a troupe offers for one kind of specialisation (an Influence's
    areas, its city's notable Contacts). Where a troupe has a list for a kind,
    its characters choose from it."""

    __tablename__ = "troupe_specializations"
    __table_args__ = (UniqueConstraint("troupe_id", "category_key", "name"),)

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    category_key: Mapped[str]
    name: Mapped[str]


class TroupeTitle(Record):
    """A title a troupe added to the rule set's list: its sect, if it has one, and
    the abiding status it gives (horatio.rules.status)."""

    __tablename__ = "troupe_titles"
    __table_args__ = (UniqueConstraint("troupe_id", "name"),)

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    name: Mapped[str]
    # None: it can go to a character of any sect.
    sect: Mapped[str | None]
    status: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    # Where it comes on the troupe's Who's Who, after the rule sets' titles
    # (horatio.whos_who): the troupe sets the order of its own.
    position: Mapped[int] = mapped_column(default=0, server_default="0")


class CharacterTitle(Record):
    """A title a character holds in one troupe (CONTEXT.md: Title)."""

    __tablename__ = "character_titles"
    __table_args__ = (UniqueConstraint("troupe_id", "character_id", "name"),)

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("characters.id"), index=True)
    name: Mapped[str]
