import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class BoonAudit(Record):
    """An audit of one character's boons (horatio.boon_audits, #690): what the
    troupe's ledger held of them when it was made (its `created_at`), kept as it was
    then in `contents`, so later edits never change it. Made by the troupe's running
    staff, its Harpy, or a Lesser Harpy allowed to; given, if its maker chooses, to a
    character, whose player reads it in the Play View."""

    __tablename__ = "boon_audits"

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    # Whose boons: kept by name in `contents` should the character be deleted.
    subject_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), index=True
    )
    # What the ledger held then (horatio.boon_audits.contents_of).
    contents: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    # Who made it, and the character they made it as (a Harpy or a Lesser Harpy); no
    # character when the troupe's staff made it.
    made_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    as_character_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL")
    )
    # Who it was given to, and when; none until it is.
    given_to_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), index=True
    )
    given_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
