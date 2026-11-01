"""The optional feeding rules Feeding Territories and Advanced Feeding, the Rack
(issue #416; MET: VTM Vol. 2, pp. 298-307): a troupe's switches, its territories,
each cycle's Feeding Cards, a character's feeding restriction, and the patrols that
caught a poacher.

Revision ID: 0124
Revises: 0123
Create Date: 2026-11-01 22:00:00.000000
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0124"
down_revision: str | None = "0123"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

HUMORS = "('choleric', 'melancholic', 'phlegmatic', 'sanguine')"


def record_columns() -> list[sa.Column[Any]]:
    return [
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    for name in ("feeding_territories", "feeding_rack"):
        op.add_column(
            "troupes", sa.Column(name, sa.Boolean(), server_default="false", nullable=False)
        )
    op.add_column("characters", sa.Column("feeding_numbers", JSONB(), nullable=True))
    op.add_column(
        "submissions",
        sa.Column("feeding_caught_by", JSONB(), server_default="[]", nullable=False),
    )
    op.create_table(
        "feeding_territories",
        *record_columns(),
        sa.Column(
            "troupe_id",
            sa.Uuid(),
            sa.ForeignKey("troupes.id", name=op.f("fk_feeding_territories_troupe_id_troupes")),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("size", sa.String(), server_default="small", nullable=False),
        sa.Column("area", sa.String(), server_default="", nullable=False),
        sa.Column("held_by", sa.String(), server_default="", nullable=False),
        sa.Column("holder_ids", JSONB(), server_default="[]", nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "size in ('small', 'moderate', 'notable', 'significant', 'large')",
            name=op.f("ck_feeding_territories_size"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feeding_territories")),
    )
    op.create_index(op.f("ix_feeding_territories_troupe_id"), "feeding_territories", ["troupe_id"])
    op.create_table(
        "feeding_cards",
        *record_columns(),
        sa.Column(
            "cycle_id",
            sa.Uuid(),
            sa.ForeignKey(
                "downtime_cycles.id", name=op.f("fk_feeding_cards_cycle_id_downtime_cycles")
            ),
            nullable=False,
        ),
        sa.Column("source", sa.String(), server_default="rack", nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("resonance", sa.String(), nullable=False),
        sa.Column("dyscrasia", sa.String(), server_default="", nullable=False),
        sa.Column("descriptor", sa.String(), server_default="", nullable=False),
        sa.Column(
            "territory_id",
            sa.Uuid(),
            sa.ForeignKey(
                "feeding_territories.id",
                name=op.f("fk_feeding_cards_territory_id_feeding_territories"),
            ),
            nullable=True,
        ),
        sa.Column(
            "dealt_to",
            sa.Uuid(),
            sa.ForeignKey(
                "cycle_participants.id", name=op.f("fk_feeding_cards_dealt_to_cycle_participants")
            ),
            nullable=True,
        ),
        sa.Column(
            "taken_by",
            sa.Uuid(),
            sa.ForeignKey(
                "cycle_participants.id", name=op.f("fk_feeding_cards_taken_by_cycle_participants")
            ),
            nullable=True,
        ),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "source in ('rack', 'territory', 'herd', 'hunt')", name=op.f("ck_feeding_cards_source")
        ),
        sa.CheckConstraint(f"resonance in {HUMORS}", name=op.f("ck_feeding_cards_resonance")),
        sa.CheckConstraint(
            "(source = 'territory') = (territory_id is not null)",
            name=op.f("ck_feeding_cards_territory"),
        ),
        sa.CheckConstraint(
            "(source in ('herd', 'hunt')) = (dealt_to is not null)",
            name=op.f("ck_feeding_cards_dealt_to"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feeding_cards")),
    )
    op.create_index(op.f("ix_feeding_cards_cycle_id"), "feeding_cards", ["cycle_id"])
    op.create_index(op.f("ix_feeding_cards_taken_by"), "feeding_cards", ["taken_by"])


def downgrade() -> None:
    op.drop_table("feeding_cards")
    op.drop_table("feeding_territories")
    op.drop_column("submissions", "feeding_caught_by")
    op.drop_column("characters", "feeding_numbers")
    op.drop_column("troupes", "feeding_rack")
    op.drop_column("troupes", "feeding_territories")
