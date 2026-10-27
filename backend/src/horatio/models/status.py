import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class HeldStatus(Record):
    """A fleeting or negative status a character holds (horatio.sect_status), with
    who gave it, where, when and why: what Leadership reveals (MET: VTM p. 310). It
    lives on the character, not a troupe, and counts in every game of its sect.
    Abiding and innate status are never held: they come from titles, social age
    and merits."""

    __tablename__ = "held_statuses"

    character_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    # The status trait's name.
    name: Mapped[str]
    # The patron: a character of the holder's home troupe, picked from a list, and
    # its name and title there when it gave the status, kept as text so the record
    # still reads if it is deleted; and, or instead, words of the player's own.
    patron_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL")
    )
    patron_name: Mapped[str] = mapped_column(default="", server_default="")
    patron_title: Mapped[str] = mapped_column(default="", server_default="")
    patron_text: Mapped[str] = mapped_column(default="", server_default="")
    # Where: the troupe it was added in, and the troupe or domain as written.
    troupe_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("troupes.id"))
    place: Mapped[str] = mapped_column(default="", server_default="")
    given_on: Mapped[date] = mapped_column(Date)
    story: Mapped[str] = mapped_column(default="", server_default="")
    # Who added it; none for status from before Horatio.
    added_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    # The Play View game it was given at, which does not count toward its end.
    game_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("play_games.id", ondelete="SET NULL")
    )


class StatusBanMark(Record):
    """Staff saying whether one of the sect's status bans applies to a character
    (MET: VTM p. 312): exempt from one the sheet shows, or under one it cannot
    show (no boons registered with the Harpy), with their reason."""

    __tablename__ = "status_ban_marks"
    __table_args__ = (UniqueConstraint("character_id", "sect", "ban"),)

    character_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    sect: Mapped[str]
    # The ban, by who it applies to, as the rules word it.
    ban: Mapped[str]
    # True: it applies; False: the character is exempt.
    applies: Mapped[bool]
    reason: Mapped[str]
    marked_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
