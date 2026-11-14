"""Messages staff post as an NPC in the troupe's In-Character channel on Discord
(issue #884): who sent each, as which NPC, what it says and where it is on Discord.

Revision ID: 0229
Revises: 0228
Create Date: 2026-11-14 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0229"
down_revision: str | None = "0228"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "in_character_messages",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("sent_by", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("message_id", sa.String(), nullable=False),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("edited_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_in_character_messages_troupe_id_troupes")
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_in_character_messages_character_id_characters"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sent_by"], ["users.id"], name=op.f("fk_in_character_messages_sent_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["edited_by"], ["users.id"], name=op.f("fk_in_character_messages_edited_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_in_character_messages")),
    )
    op.create_index(
        op.f("ix_in_character_messages_troupe_id"), "in_character_messages", ["troupe_id"]
    )
    op.create_index(
        op.f("ix_in_character_messages_character_id"), "in_character_messages", ["character_id"]
    )


def downgrade() -> None:
    op.drop_table("in_character_messages")
