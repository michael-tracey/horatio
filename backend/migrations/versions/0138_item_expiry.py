"""Items that expire (issue #443): a troupe's setting "Items can expire", and an item's
expiry: on a date, after a number of its holder's games, or when a downtime cycle
closes, with a note on what happens and when its holder was warned.

Revision ID: 0138
Revises: 0127
Create Date: 2026-11-01 23:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0138"
down_revision: str | None = "0127"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "troupes",
        sa.Column("items_expire", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column("equipment_items", sa.Column("expiry_kind", sa.String(), nullable=True))
    op.add_column("equipment_items", sa.Column("expires_on", sa.Date(), nullable=True))
    op.add_column("equipment_items", sa.Column("expires_after_games", sa.Integer(), nullable=True))
    op.add_column("equipment_items", sa.Column("expires_cycle_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_equipment_items_expires_cycle_id_downtime_cycles"),
        "equipment_items",
        "downtime_cycles",
        ["expires_cycle_id"],
        ["id"],
    )
    op.add_column(
        "equipment_items", sa.Column("expiry_from", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "equipment_items",
        sa.Column("expiry_note", sa.String(), server_default="", nullable=False),
    )
    op.add_column(
        "equipment_items",
        sa.Column("expiry_warned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "expiry",
        "equipment_items",
        "expiry_kind is null"
        " or (expiry_kind = 'date' and expires_on is not null)"
        " or (expiry_kind = 'games' and expires_after_games > 0)"
        " or (expiry_kind = 'cycle' and expires_cycle_id is not null)",
    )


def downgrade() -> None:
    op.drop_constraint("expiry", "equipment_items", type_="check")
    op.drop_constraint(
        op.f("fk_equipment_items_expires_cycle_id_downtime_cycles"),
        "equipment_items",
        type_="foreignkey",
    )
    for column in (
        "expiry_warned_at",
        "expiry_note",
        "expiry_from",
        "expires_cycle_id",
        "expires_after_games",
        "expires_on",
        "expiry_kind",
    ):
        op.drop_column("equipment_items", column)
    op.drop_column("troupes", "items_expire")
