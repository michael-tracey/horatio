"""Player Nominations (issue #470): a troupe's setting, off by default; the notes
players write in their downtimes praising others' roleplaying, with staff's review
of them; and when each cycle's were published.

Revision ID: 0145
Revises: 0144
Create Date: 2026-11-06 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0145"
down_revision: str | None = "0144"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "troupes",
        sa.Column("player_nominations", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "downtime_cycles",
        sa.Column("nominations_published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "nominations",
        sa.Column("cycle_id", sa.Uuid(), nullable=False),
        sa.Column("participant_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("about_character_id", sa.Uuid(), nullable=True),
        sa.Column("about_user_id", sa.Uuid(), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("removed_by", sa.Uuid(), nullable=True),
        sa.Column("removed_reason", sa.String(), server_default="", nullable=False),
        sa.Column("starred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("starred_by", sa.Uuid(), nullable=True),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("edited_by", sa.Uuid(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shuffle_key", sa.Float(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "about_character_id is null or about_user_id is null",
            name=op.f("ck_nominations_one_about"),
        ),
        sa.ForeignKeyConstraint(
            ["about_character_id"],
            ["characters.id"],
            name=op.f("fk_nominations_about_character_id_characters"),
        ),
        sa.ForeignKeyConstraint(
            ["about_user_id"], ["users.id"], name=op.f("fk_nominations_about_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["cycle_id"],
            ["downtime_cycles.id"],
            name=op.f("fk_nominations_cycle_id_downtime_cycles"),
        ),
        sa.ForeignKeyConstraint(
            ["edited_by"], ["users.id"], name=op.f("fk_nominations_edited_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["participant_id"],
            ["cycle_participants.id"],
            name=op.f("fk_nominations_participant_id_cycle_participants"),
        ),
        sa.ForeignKeyConstraint(
            ["removed_by"], ["users.id"], name=op.f("fk_nominations_removed_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["starred_by"], ["users.id"], name=op.f("fk_nominations_starred_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_nominations")),
    )
    op.create_index(
        op.f("ix_nominations_about_character_id"), "nominations", ["about_character_id"]
    )
    op.create_index(op.f("ix_nominations_cycle_id"), "nominations", ["cycle_id"])
    op.create_index(op.f("ix_nominations_participant_id"), "nominations", ["participant_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_nominations_participant_id"), table_name="nominations")
    op.drop_index(op.f("ix_nominations_cycle_id"), table_name="nominations")
    op.drop_index(op.f("ix_nominations_about_character_id"), table_name="nominations")
    op.drop_table("nominations")
    op.drop_column("downtime_cycles", "nominations_published_at")
    op.drop_column("troupes", "player_nominations")
