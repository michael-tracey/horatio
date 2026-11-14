"""The story bible's staff-only notes (issue #879): a troupe's running staff keep
notes of their own beside the Setting Style Document (MET: VTM p. 336), which
players never read.

Revision ID: 0226
Revises: 0225
Create Date: 2026-11-14 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0226"
down_revision: str | None = "0225"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "story_bible_notes",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("body", sa.Text(), server_default="", nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_story_bible_notes_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_story_bible_notes")),
        sa.UniqueConstraint(
            "troupe_id",
            "position",
            name="uq_story_bible_notes_place",
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    op.create_index(op.f("ix_story_bible_notes_troupe_id"), "story_bible_notes", ["troupe_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_story_bible_notes_troupe_id"), table_name="story_bible_notes")
    op.drop_table("story_bible_notes")
