import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class YorickImport(Record):
    """A troupe's import from Yorick, which the custodian runs (horatio.yorick_imports):
    the Print Characters page uploaded last, the troupe's own names for what the
    printout says, the choices made about characters already here under a printed
    name, and the last dry run or import. One for each troupe, kept between uploads, as
    a troupe may come across over months."""

    __tablename__ = "yorick_imports"
    __table_args__ = (
        CheckConstraint("job in ('dry_run', 'import')", name="job"),
        CheckConstraint("report_kind in ('dry_run', 'import')", name="report_kind"),
    )

    troupe_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("troupes.id", ondelete="CASCADE"), unique=True
    )
    # Who the NPCs are made by: one of the troupe's storytellers, or its lead (null).
    staff_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    # The page uploaded, kept under the upload directory until it is imported, deleted,
    # or `yorick_imports.KEPT_FOR` has passed. It holds real names and emails.
    page_name: Mapped[str | None]
    page_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    page_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    # The troupe's own names over the bundled table (horatio.yorick_names), in its
    # shape: {"names": {category: {Yorick's: Horatio's}}, "values": {...}, "paths": {...}}.
    names: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    # Printed lines ("Merits: Arcane (1)") staff will put right by hand, so the report
    # no longer counts them as waiting for a name.
    by_hand: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    # By Yorick id, what to do with a printed character whose name a character here
    # has: {"choice": "overwrite" | "skip" | "new", "character_id": ...}.
    decisions: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")

    # The dry run or import running now, and when and by whom it was started.
    job: Mapped[str | None]
    job_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    job_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    # The last dry run's or import's report: its summary and each character.
    report: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    report_text: Mapped[str | None] = mapped_column(Text)
    report_kind: Mapped[str | None]
    report_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Something changed since that would change the report: a name, a choice.
    report_stale: Mapped[bool] = mapped_column(default=False, server_default="false")
    # Why the last run stopped short, if it did.
    error: Mapped[str | None]
