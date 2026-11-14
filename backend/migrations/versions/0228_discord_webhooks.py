"""News agencies' portraits, and the Discord webhooks Horatio posts through (issue
#883): a story posts as its agency, under its name and portrait, through a webhook
the bot makes in the channel and reuses. One per troupe and channel.

Revision ID: 0228
Revises: 0225
Create Date: 2026-11-14 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0228"
down_revision: str | None = "0225"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("news_agencies", sa.Column("portrait_id", sa.Uuid(), nullable=True))
    op.add_column(
        "news_agencies",
        sa.Column("portrait_crop", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_table(
        "discord_webhooks",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("webhook_id", sa.String(), nullable=False),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"],
            ["troupes.id"],
            name=op.f("fk_discord_webhooks_troupe_id_troupes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_discord_webhooks")),
        sa.UniqueConstraint("troupe_id", "channel", name=op.f("uq_discord_webhooks_troupe_id")),
    )


def downgrade() -> None:
    op.drop_table("discord_webhooks")
    op.drop_column("news_agencies", "portrait_crop")
    op.drop_column("news_agencies", "portrait_id")
