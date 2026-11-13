"""The Vinculum and the Vaulderie log, for Sabbat troupes (issue #666; MET: VTM pp.
433-435, and the Errata's p. 434). A Vaulderie is a night, its participants (characters
or names, any of them a false Sabbat who gave no blood) and who officiated; Vinculum
ratings are worked out from them. A background tie is two who shared Vaulderies before
Horatio, at a rating on a night. A bond's log gains a line for a Vaulderie lowering it
a step, which sets its level as a drop does.

Revision ID: 0216
Revises: 0215
Create Date: 2026-11-12 23:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0216"
down_revision: str | None = "0215"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def record_columns() -> list[sa.Column]:  # type: ignore[type-arg]
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
    op.create_table(
        "vaulderies",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("night", sa.Date(), nullable=False),
        sa.Column("officiant_id", sa.Uuid(), nullable=True),
        sa.Column("officiant_name", sa.String(), server_default="", nullable=False),
        sa.Column("source", sa.String(), server_default="staff", nullable=False),
        sa.Column("note", sa.String(), server_default="", nullable=False),
        sa.Column("status", sa.String(), server_default="recorded", nullable=False),
        sa.Column("recorded_by", sa.Uuid(), nullable=True),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(), server_default="", nullable=False),
        *record_columns(),
        sa.CheckConstraint(
            "status in ('recorded', 'pending', 'declined', 'withdrawn', 'removed')",
            name=op.f("ck_vaulderies_status"),
        ),
        sa.CheckConstraint(
            "source in ('game', 'downtime', 'staff')", name=op.f("ck_vaulderies_source")
        ),
        sa.CheckConstraint(
            "officiant_id is null or officiant_name = ''", name=op.f("ck_vaulderies_officiant")
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_vaulderies_troupe_id_troupes")
        ),
        sa.ForeignKeyConstraint(
            ["officiant_id"], ["characters.id"], name=op.f("fk_vaulderies_officiant_id_characters")
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by"], ["users.id"], name=op.f("fk_vaulderies_recorded_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"], ["users.id"], name=op.f("fk_vaulderies_decided_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vaulderies")),
    )
    op.create_index(op.f("ix_vaulderies_troupe_id"), "vaulderies", ["troupe_id"])
    op.create_table(
        "vaulderie_participants",
        sa.Column("vaulderie_id", sa.Uuid(), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(), server_default="", nullable=False),
        sa.Column("false_sabbat", sa.Boolean(), server_default="false", nullable=False),
        *record_columns(),
        sa.CheckConstraint(
            "(character_id is null) <> (name = '')", name=op.f("ck_vaulderie_participants_who")
        ),
        sa.ForeignKeyConstraint(
            ["vaulderie_id"],
            ["vaulderies.id"],
            name=op.f("fk_vaulderie_participants_vaulderie_id_vaulderies"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_vaulderie_participants_character_id_characters"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vaulderie_participants")),
    )
    op.create_index(
        op.f("ix_vaulderie_participants_vaulderie_id"), "vaulderie_participants", ["vaulderie_id"]
    )
    op.create_index(
        op.f("ix_vaulderie_participants_character_id"), "vaulderie_participants", ["character_id"]
    )
    op.create_table(
        "vinculum_ties",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("one_id", sa.Uuid(), nullable=True),
        sa.Column("one_name", sa.String(), server_default="", nullable=False),
        sa.Column("other_id", sa.Uuid(), nullable=True),
        sa.Column("other_name", sa.String(), server_default="", nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("night", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(), server_default="", nullable=False),
        sa.Column("recorded_by", sa.Uuid(), nullable=True),
        *record_columns(),
        sa.CheckConstraint(
            "(one_id is null) <> (one_name = '')", name=op.f("ck_vinculum_ties_one")
        ),
        sa.CheckConstraint(
            "(other_id is null) <> (other_name = '')", name=op.f("ck_vinculum_ties_other")
        ),
        sa.CheckConstraint("rating between 1 and 5", name=op.f("ck_vinculum_ties_rating")),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_vinculum_ties_troupe_id_troupes")
        ),
        sa.ForeignKeyConstraint(
            ["one_id"], ["characters.id"], name=op.f("fk_vinculum_ties_one_id_characters")
        ),
        sa.ForeignKeyConstraint(
            ["other_id"], ["characters.id"], name=op.f("fk_vinculum_ties_other_id_characters")
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by"], ["users.id"], name=op.f("fk_vinculum_ties_recorded_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vinculum_ties")),
    )
    op.create_index(op.f("ix_vinculum_ties_troupe_id"), "vinculum_ties", ["troupe_id"])
    op.create_index(op.f("ix_vinculum_ties_one_id"), "vinculum_ties", ["one_id"])
    op.create_index(op.f("ix_vinculum_ties_other_id"), "vinculum_ties", ["other_id"])
    op.drop_constraint("kind", "bond_entries", type_="check")
    op.create_check_constraint(
        "kind",
        "bond_entries",
        "kind in ('drink', 'entered', 'dropped', 'meeting', 'vaulderie')",
    )
    op.drop_constraint("entered_level", "bond_entries", type_="check")
    op.create_check_constraint(
        "entered_level",
        "bond_entries",
        "(kind in ('entered', 'dropped', 'vaulderie')) = (level is not null)",
    )


def downgrade() -> None:
    op.execute("delete from bond_entries where kind = 'vaulderie'")
    op.drop_constraint("entered_level", "bond_entries", type_="check")
    op.create_check_constraint(
        "entered_level", "bond_entries", "(kind in ('entered', 'dropped')) = (level is not null)"
    )
    op.drop_constraint("kind", "bond_entries", type_="check")
    op.create_check_constraint(
        "kind", "bond_entries", "kind in ('drink', 'entered', 'dropped', 'meeting')"
    )
    op.drop_table("vinculum_ties")
    op.drop_table("vaulderie_participants")
    op.drop_table("vaulderies")
