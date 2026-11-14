import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class DiscordWebhook(Record):
    """The webhook the Horatio bot made in one of a troupe's Discord channels, through
    which it posts under another name and picture: a news agency's (#883), or an
    NPC's (#884). One per channel, reused (horatio.discord_webhooks)."""

    __tablename__ = "discord_webhooks"
    __table_args__ = (UniqueConstraint("troupe_id", "channel"),)

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id", ondelete="CASCADE"))
    channel: Mapped[str]
    webhook_id: Mapped[str]
    # The webhook's secret, which lets whoever holds it post in the channel. Never
    # shown to anyone.
    token: Mapped[str]
