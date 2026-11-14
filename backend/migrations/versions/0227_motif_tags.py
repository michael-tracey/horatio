"""Theme and mood tags on scenes and quests (issue #880): staff tag a scene or a quest
with the troupe's themes and moods from its Setting Style Document, to see which the
chronicle touches. A tag goes with its theme or mood, scene or quest.

Revision ID: 0227
Revises: 0225
Create Date: 2026-11-14 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0227"
down_revision: str | None = "0225"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "motif_tags",
        sa.Column("motif_id", sa.Uuid(), nullable=False),
        sa.Column("scene_id", sa.Uuid(), nullable=True),
        sa.Column("quest_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "num_nonnulls(scene_id, quest_id) = 1", name=op.f("ck_motif_tags_one_tagged")
        ),
        sa.ForeignKeyConstraint(
            ["motif_id"],
            ["chronicle_motifs.id"],
            name=op.f("fk_motif_tags_motif_id_chronicle_motifs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["scene_id"],
            ["scenes.id"],
            name=op.f("fk_motif_tags_scene_id_scenes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["quest_id"],
            ["quests.id"],
            name=op.f("fk_motif_tags_quest_id_quests"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_motif_tags")),
        sa.UniqueConstraint("motif_id", "scene_id", name="uq_motif_tags_scene"),
        sa.UniqueConstraint("motif_id", "quest_id", name="uq_motif_tags_quest"),
    )
    for column in ("motif_id", "scene_id", "quest_id"):
        op.create_index(op.f(f"ix_motif_tags_{column}"), "motif_tags", [column])


def downgrade() -> None:
    op.drop_table("motif_tags")
