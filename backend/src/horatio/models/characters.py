import uuid

from sqlalchemy import CheckConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Imported, Record


class Character(Imported, Record):
    """A persona a player plays. Belongs to its player, never deleted, only retired."""

    __tablename__ = "characters"
    __table_args__ = (CheckConstraint("status in ('draft', 'active', 'retired')", name="status"),)

    player_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    # Checked against the rule sets by the application, not by the database,
    # so adding a splat is a data change rather than a migration.
    splat: Mapped[str]
    name: Mapped[str]
    status: Mapped[str] = mapped_column(default="draft", server_default="draft")
    home_troupe_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("troupes.id"), index=True)
