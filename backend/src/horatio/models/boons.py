import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class Boon(Record):
    """A boon (CONTEXT.md: Boon): a debt its debtor owes its creditor, registered in
    one troupe's boon ledger (horatio.boons; MET: VTM pp. 395-397). Either side is a
    character (a PC or an NPC) or, for someone not in Horatio, a name only. What
    happens to it is kept in its own log (BoonEvent)."""

    __tablename__ = "boons"
    __table_args__ = (
        CheckConstraint("kind in ('trivial', 'minor', 'major', 'blood', 'life')", name="kind"),
        CheckConstraint("state in ('pending', 'registered', 'settled', 'void')", name="state"),
        CheckConstraint("(debtor_id is null) <> (debtor_name = '')", name="debtor"),
        CheckConstraint("(creditor_id is null) <> (creditor_name = '')", name="creditor"),
        CheckConstraint("debtor_id <> creditor_id", name="not_own_creditor"),
        CheckConstraint(
            "settled_how is null or settled_how in ('called_in', 'forgiven', 'ignored')",
            name="settled_how",
        ),
        CheckConstraint("(state = 'settled') = (settled_how is not null)", name="settled"),
        CheckConstraint("(state in ('settled', 'void')) = (closed_at is not null)", name="closed"),
        CheckConstraint(
            "status_loss is null or status_loss in ('due', 'taken', 'waived')",
            name="status_loss",
        ),
        Index("ix_boons_troupe_id_state", "troupe_id", "state"),
    )

    # The troupe whose ledger it is in, and whose Boons setting says whether it shows.
    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"))
    # Who owes it: a character, or a name only.
    debtor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("characters.id"), index=True)
    debtor_name: Mapped[str] = mapped_column(default="", server_default="")
    # Who holds it, and may call it in: a character, or a name only.
    creditor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("characters.id"), index=True)
    creditor_name: Mapped[str] = mapped_column(default="", server_default="")
    # trivial | minor | major | blood | life (pp. 396-397).
    kind: Mapped[str]
    # The in-game night it was made.
    made_on: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(default="", server_default="")
    # Its stipulations, as recorded with it (p. 395): "Cannot be traded".
    conditions: Mapped[str] = mapped_column(default="", server_default="")
    # Its debtor's player is told when it is traded.
    notify_on_trade: Mapped[bool] = mapped_column(default=False, server_default="false")
    # pending, submitted and waiting for review (#687); registered, standing; settled,
    # called in, forgiven or formally ignored; or void, entered by mistake or undone.
    state: Mapped[str] = mapped_column(default="registered", server_default="registered")
    # For a settled boon: called_in, forgiven, or ignored by its debtor (p. 397).
    settled_how: Mapped[str | None]
    # When it was settled or made void, and the note given then.
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_note: Mapped[str] = mapped_column(default="", server_default="")
    # For the troupe's running staff only.
    staff_note: Mapped[str] = mapped_column(default="", server_default="")
    # Who put it in the ledger.
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    # The game it was registered at, when staff say so (#702): the Harpy's boons from
    # one game, entered days later. None away from a game, or for one entered before.
    # A major, blood or life boon its debtor formally ignored costs them status (p. 395):
    # "due" until staff or the Harpy say they took it ("taken") or chose not to
    # ("waived"). None for any other boon.
    status_loss: Mapped[str | None]
    game_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("scheduled_games.id", ondelete="SET NULL"), index=True
    )


class BoonEvent(Record):
    """A line of a boon's own log: its registering (or submitting, to wait for review),
    each edit, trade, passing on, settling, voiding and reopening, its review (#687:
    accepted or rejected, flags raised and cleared, a name linked to a character), and
    Gallant given for repaying it or not (#693),
    with who did it, when, and their note. `changes`
    says what it changed: for an edit, each field before and after, which only the
    troupe's storytellers and assistant storytellers see (anyone else who sees the
    boon sees that it was edited, when, and the note); for the rest, what it did."""

    __tablename__ = "boon_events"
    __table_args__ = (
        CheckConstraint(
            "kind in ('registered', 'edited', 'traded', 'passed_on', 'settled', 'voided',"
            " 'reopened', 'submitted', 'accepted', 'rejected', 'flagged', 'flag_cleared',"
            " 'linked', 'gallant_given', 'gallant_declined')",
            name="kind",
        ),
    )

    boon_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("boons.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str]
    note: Mapped[str] = mapped_column(default="", server_default="")
    # Each field changed, by name: [before, after], as shown (a party by its name).
    changes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    # The character it was done as, for a Harpy or a Lesser Harpy (#688, #689); none
    # for staff.
    as_character_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("characters.id"))
