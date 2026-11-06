"""Remembrances (issue #471): a troupe's setting, off by default; remembrances opened
for a character who left play, with the cycle that asks for them; and each memory,
kept with the Player Nominations (0145) and reviewed and published as they are.

Revision ID: 0146
Revises: 0145
Create Date: 2026-11-06 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0146"
down_revision: str | None = "0145"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "troupes",
        sa.Column("remembrances", sa.Boolean(), server_default="false", nullable=False),
    )
    op.create_table(
        "remembrances",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("cycle_id", sa.Uuid(), nullable=True),
        sa.Column("asked_by", sa.Uuid(), nullable=True),
        sa.Column("asked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_by", sa.Uuid(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["asked_by"], ["users.id"], name=op.f("fk_remembrances_asked_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_remembrances_character_id_characters"),
        ),
        sa.ForeignKeyConstraint(
            ["cycle_id"],
            ["downtime_cycles.id"],
            name=op.f("fk_remembrances_cycle_id_downtime_cycles"),
        ),
        sa.ForeignKeyConstraint(
            ["opened_by"], ["users.id"], name=op.f("fk_remembrances_opened_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_remembrances_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_remembrances")),
        sa.UniqueConstraint("troupe_id", "character_id", name=op.f("uq_remembrances_troupe_id")),
    )
    op.create_index(op.f("ix_remembrances_character_id"), "remembrances", ["character_id"])
    op.create_index(op.f("ix_remembrances_cycle_id"), "remembrances", ["cycle_id"])
    op.create_index(op.f("ix_remembrances_troupe_id"), "remembrances", ["troupe_id"])
    op.add_column("nominations", sa.Column("remembrance_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_nominations_remembrance_id_remembrances"),
        "nominations",
        "remembrances",
        ["remembrance_id"],
        ["id"],
    )
    op.create_index(op.f("ix_nominations_remembrance_id"), "nominations", ["remembrance_id"])
    op.create_unique_constraint(
        op.f("uq_nominations_participant_id"), "nominations", ["participant_id", "remembrance_id"]
    )


def downgrade() -> None:
    op.drop_constraint(op.f("uq_nominations_participant_id"), "nominations", type_="unique")
    op.drop_index(op.f("ix_nominations_remembrance_id"), table_name="nominations")
    op.drop_constraint(
        op.f("fk_nominations_remembrance_id_remembrances"), "nominations", type_="foreignkey"
    )
    op.drop_column("nominations", "remembrance_id")
    op.drop_index(op.f("ix_remembrances_troupe_id"), table_name="remembrances")
    op.drop_index(op.f("ix_remembrances_cycle_id"), table_name="remembrances")
    op.drop_index(op.f("ix_remembrances_character_id"), table_name="remembrances")
    op.drop_table("remembrances")
    op.drop_column("troupes", "remembrances")
