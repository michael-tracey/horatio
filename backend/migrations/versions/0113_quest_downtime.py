"""quests in downtime: a downtime form's Quest action names a quest and spends an
action of the kind the troupe chooses; a scenario's result recorded through a
downtime cycle waits for that cycle's delivery (horatio.quest_actions)

Revision ID: 0112
Revises: 0110
Create Date: 2026-10-30 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0112"
down_revision: str | None = "0110"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("kind", "questions", type_="check")
    op.create_check_constraint("kind", "questions", "kind in ('action', 'custom', 'quest')")
    op.drop_constraint("action_has_kind", "questions", type_="check")
    op.create_check_constraint(
        "action_has_kind", "questions", "(kind in ('action', 'quest')) = (action_kind is not null)"
    )

    op.add_column(
        "quest_scenarios",
        sa.Column(
            "cycle_id",
            sa.Uuid(),
            sa.ForeignKey(
                "downtime_cycles.id",
                name=op.f("fk_quest_scenarios_cycle_id_downtime_cycles"),
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
    )
    op.create_index(op.f("ix_quest_scenarios_cycle_id"), "quest_scenarios", ["cycle_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_quest_scenarios_cycle_id"), table_name="quest_scenarios")
    op.drop_column("quest_scenarios", "cycle_id")

    # A Quest action becomes a plain action of the kind it spent.
    op.execute("update questions set kind = 'action' where kind = 'quest'")
    op.drop_constraint("action_has_kind", "questions", type_="check")
    op.create_check_constraint(
        "action_has_kind", "questions", "(kind = 'action') = (action_kind is not null)"
    )
    op.drop_constraint("kind", "questions", type_="check")
    op.create_check_constraint("kind", "questions", "kind in ('action', 'custom')")
