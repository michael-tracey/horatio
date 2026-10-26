"""scenes: a troupe's named scenes, kept on the server, and who is pinned to each

Revision ID: 0072
Revises: 0071
Create Date: 2026-10-26 20:00:00.000000
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0072"
down_revision: str | None = "0071"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _record_columns() -> list[sa.Column[Any]]:
    return [
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "scenes",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        *_record_columns(),
        sa.CheckConstraint(
            "char_length(name) between 1 and 80", name=op.f("ck_scenes_name_length")
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_scenes_troupe_id_troupes")
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], name=op.f("fk_scenes_created_by_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scenes")),
    )
    op.create_index(op.f("ix_scenes_troupe_id"), "scenes", ["troupe_id"], unique=False)
    op.create_table(
        "scene_characters",
        sa.Column("scene_id", sa.Uuid(), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        *_record_columns(),
        sa.ForeignKeyConstraint(
            ["scene_id"],
            ["scenes.id"],
            name=op.f("fk_scene_characters_scene_id_scenes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_scene_characters_character_id_characters"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scene_characters")),
        sa.UniqueConstraint("scene_id", "character_id", name=op.f("uq_scene_characters_scene_id")),
    )
    op.create_index(
        op.f("ix_scene_characters_scene_id"), "scene_characters", ["scene_id"], unique=False
    )
    op.create_index(
        op.f("ix_scene_characters_character_id"),
        "scene_characters",
        ["character_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_scene_characters_character_id"), table_name="scene_characters")
    op.drop_index(op.f("ix_scene_characters_scene_id"), table_name="scene_characters")
    op.drop_table("scene_characters")
    op.drop_index(op.f("ix_scenes_troupe_id"), table_name="scenes")
    op.drop_table("scenes")
