"""location quests: requests to acquire, add a quality to, undermine or repair a
location, or to learn whose locations are whose; a quest that changes a location
when it is completed, and the Resources a party spends on its scenarios; the
qualities Damaged has switched off (horatio.location_quests)

Revision ID: 0114
Revises: 0113
Create Date: 2026-10-30 23:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0114"
down_revision: str | None = "0113"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS = "('custom', 'acquire', 'quality', 'undermine', 'repair', 'whose')"


def upgrade() -> None:
    op.drop_constraint("kind", "quest_requests", type_="check")
    op.create_check_constraint("kind", "quest_requests", f"kind in {KINDS}")
    op.drop_constraint("outcome", "quest_requests", type_="check")
    op.create_check_constraint(
        "outcome",
        "quest_requests",
        "outcome is null or outcome in ('quest', 'not_needed', 'refused', 'done')",
    )
    op.add_column(
        "quest_requests",
        sa.Column(
            "location_id",
            sa.Uuid(),
            sa.ForeignKey(
                "locations.id",
                name=op.f("fk_quest_requests_location_id_locations"),
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
    )
    op.create_index(op.f("ix_quest_requests_location_id"), "quest_requests", ["location_id"])

    op.add_column(
        "quests",
        sa.Column(
            "location_id",
            sa.Uuid(),
            sa.ForeignKey(
                "locations.id", name=op.f("fk_quests_location_id_locations"), ondelete="SET NULL"
            ),
            nullable=True,
        ),
    )
    op.create_index(op.f("ix_quests_location_id"), "quests", ["location_id"])
    op.add_column("quests", sa.Column("location_change", postgresql.JSONB(astext_type=sa.Text())))
    # A location's qualities can raise a quest's difficulty past 5 (p. 126).
    op.drop_constraint("difficulty", "quests", type_="check")
    op.create_check_constraint("difficulty", "quests", "difficulty between 1 and 10")

    op.add_column(
        "quest_scenarios",
        sa.Column(
            "resources",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )
    op.add_column(
        "locations",
        sa.Column(
            "damaged_off",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("locations", "damaged_off")
    op.drop_column("quest_scenarios", "resources")
    op.execute("update quests set difficulty = 5 where difficulty > 5")
    op.drop_constraint("difficulty", "quests", type_="check")
    op.create_check_constraint("difficulty", "quests", "difficulty between 1 and 5")
    op.drop_column("quests", "location_change")
    op.drop_index(op.f("ix_quests_location_id"), table_name="quests")
    op.drop_column("quests", "location_id")

    op.drop_index(op.f("ix_quest_requests_location_id"), table_name="quest_requests")
    op.drop_column("quest_requests", "location_id")
    op.execute("update quest_requests set outcome = 'not_needed' where outcome = 'done'")
    op.drop_constraint("outcome", "quest_requests", type_="check")
    op.create_check_constraint(
        "outcome",
        "quest_requests",
        "outcome is null or outcome in ('quest', 'not_needed', 'refused')",
    )
    op.execute("update quest_requests set kind = 'custom' where kind <> 'custom'")
    op.drop_constraint("kind", "quest_requests", type_="check")
    op.create_check_constraint("kind", "quest_requests", "kind in ('custom')")
