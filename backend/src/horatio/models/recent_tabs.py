import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class RecentTroupeTabs(Record):
    """The tabs of a troupe's page one person opened last there (horatio.recent_tabs,
    #1048), newest first, kept on their account so they follow them between devices.
    The troupe's page shows them at the top of its tab list on a phone. One row for
    each person and troupe; it goes with either."""

    __tablename__ = "recent_troupe_tabs"
    __table_args__ = (UniqueConstraint("user_id", "troupe_id", name="uq_recent_troupe_tabs_one"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    troupe_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("troupes.id", ondelete="CASCADE"), index=True
    )
    # Each tab's address under the troupe's ("/approvals"; "" for the Overview).
    tabs: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
