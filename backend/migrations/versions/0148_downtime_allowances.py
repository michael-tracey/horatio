"""downtime allowances the book gives and takes: Science's one action a field, Quick
Hands, Quick Work, rare disciplines at two actions, owed actions applied from a
response, and backgrounds raised or lowered for a while (issue #506)

Revision ID: 0148
Revises: 0147
Create Date: 2026-11-07 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0148"
down_revision: str | None = "0147"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("scheme", "allowance_rules", type_="check")
    op.create_check_constraint(
        "scheme", "allowance_rules", "scheme in ('fixed', 'per_dot', 'per_detail')"
    )
    op.add_column(
        "allowance_rules",
        sa.Column(
            "detail_ratings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )
    op.add_column(
        "submissions",
        sa.Column("quick_hands", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "troupes",
        sa.Column(
            "rare_disciplines_two_actions", sa.Boolean(), server_default="false", nullable=False
        ),
    )
    op.add_column("owed_actions", sa.Column("source", sa.String(), nullable=True))
    op.add_column("owed_actions", sa.Column("response_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_owed_actions_response_id"), "owed_actions", ["response_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_owed_actions_response_id_responses"),
        "owed_actions",
        "responses",
        ["response_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_table(
        "background_changes",
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("trait", sa.String(), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("response_id", sa.Uuid(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("games", sa.Integer(), server_default="0", nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("halved_by_response_id", sa.Uuid(), nullable=True),
        sa.Column("added_by", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint(
            "source in ('crafts', 'performance', 'overtaxed')",
            name=op.f("ck_background_changes_source"),
        ),
        sa.ForeignKeyConstraint(
            ["added_by"], ["users.id"], name=op.f("fk_background_changes_added_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_background_changes_character_id_characters"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["halved_by_response_id"],
            ["responses.id"],
            name=op.f("fk_background_changes_halved_by_response_id_responses"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["response_id"],
            ["responses.id"],
            name=op.f("fk_background_changes_response_id_responses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_background_changes_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_background_changes")),
    )
    op.create_index(
        op.f("ix_background_changes_character_id"),
        "background_changes",
        ["character_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_background_changes_response_id"),
        "background_changes",
        ["response_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_background_changes_response_id"), table_name="background_changes")
    op.drop_index(op.f("ix_background_changes_character_id"), table_name="background_changes")
    op.drop_table("background_changes")
    op.drop_constraint(
        op.f("fk_owed_actions_response_id_responses"), "owed_actions", type_="foreignkey"
    )
    op.drop_index(op.f("ix_owed_actions_response_id"), table_name="owed_actions")
    op.drop_column("owed_actions", "response_id")
    op.drop_column("owed_actions", "source")
    op.drop_column("troupes", "rare_disciplines_two_actions")
    op.drop_column("submissions", "quick_hands")
    op.drop_column("allowance_rules", "detail_ratings")
    op.execute("delete from allowance_rules where scheme = 'per_detail'")
    op.drop_constraint("scheme", "allowance_rules", type_="check")
    op.create_check_constraint("scheme", "allowance_rules", "scheme in ('fixed', 'per_dot')")
