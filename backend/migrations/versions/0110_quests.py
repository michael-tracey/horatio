"""quests: a troupe turns them on and sets a request limit; quest requests wait in a
staff queue; quests have requirements, scenarios, a party and a log; deliveries
carry a quest's news as well as downtime results; influence can be spent meeting a
quest's requirement (horatio.quests)

Revision ID: 0110
Revises: 0108
Create Date: 2026-10-30 18:00:00.000000
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0110"
down_revision: str | None = "0108"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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


def assignment_columns(table: str) -> list[sa.Column[Any]]:
    return [
        sa.Column(
            "assigned_to_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", name=op.f(f"fk_{table}_assigned_to_user_id_users")),
            nullable=True,
        ),
        sa.Column("assigned_to_any_narrator", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "assigned_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", name=op.f(f"fk_{table}_assigned_by_users")),
            nullable=True,
        ),
    ]


def user_column(table: str, name: str, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(
        name,
        sa.Uuid(),
        sa.ForeignKey("users.id", name=op.f(f"fk_{table}_{name}_users")),
        nullable=nullable,
    )


def upgrade() -> None:
    op.add_column(
        "troupes",
        sa.Column("quests_enabled", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "troupes",
        sa.Column("quest_requests_per_cycle", sa.Integer(), server_default="1", nullable=False),
    )

    op.create_table(
        "quests",
        *record_columns(),
        sa.Column(
            "troupe_id",
            sa.Uuid(),
            sa.ForeignKey("troupes.id", name=op.f("fk_quests_troupe_id_troupes")),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("objective", sa.String(), server_default="", nullable=False),
        sa.Column("category", sa.String(), server_default="simple", nullable=False),
        sa.Column("difficulty", sa.Integer(), server_default="1", nullable=False),
        sa.Column("downtime_only", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("staff_notes", sa.String(), server_default="", nullable=False),
        sa.Column("status", sa.String(), server_default="draft", nullable=False),
        sa.Column(
            "leader_id",
            sa.Uuid(),
            sa.ForeignKey(
                "characters.id", name=op.f("fk_quests_leader_id_characters"), ondelete="SET NULL"
            ),
            nullable=True,
        ),
        sa.Column("offer", sa.String(), server_default="character", nullable=False),
        sa.Column(
            "unlock_quest_id",
            sa.Uuid(),
            sa.ForeignKey(
                "quests.id", name=op.f("fk_quests_unlock_quest_id_quests"), ondelete="SET NULL"
            ),
            nullable=True,
        ),
        sa.Column("unlock_scenario", sa.Integer(), nullable=True),
        *assignment_columns("quests"),
        sa.Column("read_by", JSONB(), server_default="{}", nullable=False),
        user_column("quests", "created_by", nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        user_column("quests", "sent_by"),
        sa.Column("ended_on", sa.Date(), nullable=True),
        user_column("quests", "ended_by"),
        sa.Column("finished_by", JSONB(), server_default="[]", nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        user_column("quests", "closed_by"),
        sa.Column("close_note", sa.String(), server_default="", nullable=False),
        sa.Column("tale", sa.String(), server_default="", nullable=False),
        user_column("quests", "tale_by"),
        sa.Column("tale_at", sa.DateTime(timezone=True), nullable=True),
        user_column("quests", "tale_approved_by"),
        sa.Column("tale_approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quests")),
        sa.CheckConstraint(
            "category in ('simple', 'complex', 'epic')", name=op.f("ck_quests_category")
        ),
        sa.CheckConstraint("difficulty between 1 and 5", name=op.f("ck_quests_difficulty")),
        sa.CheckConstraint(
            "status in ('draft', 'active', 'completed', 'failed', 'closed')",
            name=op.f("ck_quests_status"),
        ),
        sa.CheckConstraint(
            "offer in ('character', 'chosen', 'unlocked', 'troupe')", name=op.f("ck_quests_offer")
        ),
        sa.CheckConstraint(
            "(offer = 'unlocked') = (unlock_quest_id is not null and unlock_scenario is not null)",
            name=op.f("ck_quests_unlock_names_a_scenario"),
        ),
        sa.CheckConstraint(
            "not (assigned_to_any_narrator and assigned_to_user_id is not null)",
            name=op.f("ck_quests_one_assignee"),
        ),
    )
    for column in ("troupe_id", "status", "leader_id", "unlock_quest_id", "assigned_to_user_id"):
        op.create_index(op.f(f"ix_quests_{column}"), "quests", [column])

    op.create_table(
        "quest_requests",
        *record_columns(),
        sa.Column(
            "troupe_id",
            sa.Uuid(),
            sa.ForeignKey("troupes.id", name=op.f("fk_quest_requests_troupe_id_troupes")),
            nullable=False,
        ),
        sa.Column(
            "character_id",
            sa.Uuid(),
            sa.ForeignKey(
                "characters.id",
                name=op.f("fk_quest_requests_character_id_characters"),
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        user_column("quest_requests", "requested_by", nullable=False),
        sa.Column("kind", sa.String(), server_default="custom", nullable=False),
        sa.Column("objective", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), server_default="", nullable=False),
        sa.Column("companions", sa.String(), server_default="", nullable=False),
        sa.Column("details", JSONB(), server_default="{}", nullable=False),
        sa.Column(
            "cycle_id",
            sa.Uuid(),
            sa.ForeignKey(
                "downtime_cycles.id",
                name=op.f("fk_quest_requests_cycle_id_downtime_cycles"),
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column("status", sa.String(), server_default="new", nullable=False),
        *assignment_columns("quest_requests"),
        sa.Column("outcome", sa.String(), nullable=True),
        sa.Column("note", sa.String(), server_default="", nullable=False),
        user_column("quest_requests", "answered_by"),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "quest_id",
            sa.Uuid(),
            sa.ForeignKey(
                "quests.id", name=op.f("fk_quest_requests_quest_id_quests"), ondelete="SET NULL"
            ),
            nullable=True,
        ),
        sa.Column("read_by", JSONB(), server_default="{}", nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quest_requests")),
        sa.CheckConstraint("kind in ('custom')", name=op.f("ck_quest_requests_kind")),
        sa.CheckConstraint(
            "status in ('new', 'working', 'answered', 'withdrawn')",
            name=op.f("ck_quest_requests_status"),
        ),
        sa.CheckConstraint(
            "outcome is null or outcome in ('quest', 'not_needed', 'refused')",
            name=op.f("ck_quest_requests_outcome"),
        ),
        sa.CheckConstraint(
            "not (assigned_to_any_narrator and assigned_to_user_id is not null)",
            name=op.f("ck_quest_requests_one_assignee"),
        ),
    )
    for column in ("troupe_id", "character_id", "cycle_id", "status", "assigned_to_user_id"):
        op.create_index(op.f(f"ix_quest_requests_{column}"), "quest_requests", [column])

    op.create_table(
        "quest_members",
        *record_columns(),
        sa.Column(
            "quest_id",
            sa.Uuid(),
            sa.ForeignKey(
                "quests.id", name=op.f("fk_quest_members_quest_id_quests"), ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column(
            "character_id",
            sa.Uuid(),
            sa.ForeignKey(
                "characters.id",
                name=op.f("fk_quest_members_character_id_characters"),
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("status", sa.String(), server_default="invited", nullable=False),
        user_column("quest_members", "added_by", nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quest_members")),
        sa.UniqueConstraint("quest_id", "character_id", name=op.f("uq_quest_members_quest_id")),
        sa.CheckConstraint(
            "status in ('invited', 'joined', 'left')", name=op.f("ck_quest_members_status")
        ),
    )
    op.create_index(op.f("ix_quest_members_quest_id"), "quest_members", ["quest_id"])
    op.create_index(op.f("ix_quest_members_character_id"), "quest_members", ["character_id"])

    op.create_table(
        "quest_requirements",
        *record_columns(),
        sa.Column(
            "quest_id",
            sa.Uuid(),
            sa.ForeignKey(
                "quests.id", name=op.f("fk_quest_requirements_quest_id_quests"), ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("options", JSONB(), nullable=False),
        sa.Column(
            "met_by_character_id",
            sa.Uuid(),
            sa.ForeignKey(
                "characters.id",
                name=op.f("fk_quest_requirements_met_by_character_id_characters"),
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column("met_by_name", sa.String(), server_default="", nullable=False),
        sa.Column("met_option", sa.Integer(), nullable=True),
        sa.Column("met_patron", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("met_at", sa.DateTime(timezone=True), nullable=True),
        user_column("quest_requirements", "met_marked_by"),
        sa.Column("spent", JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quest_requirements")),
    )
    op.create_index(op.f("ix_quest_requirements_quest_id"), "quest_requirements", ["quest_id"])

    op.create_table(
        "quest_scenarios",
        *record_columns(),
        sa.Column(
            "quest_id",
            sa.Uuid(),
            sa.ForeignKey(
                "quests.id", name=op.f("fk_quest_scenarios_quest_id_quests"), ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("success_text", sa.String(), server_default="", nullable=False),
        sa.Column("fail_text", sa.String(), server_default="", nullable=False),
        sa.Column("result", sa.String(), nullable=True),
        sa.Column("result_text", sa.String(), server_default="", nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        user_column("quest_scenarios", "sent_by"),
        sa.Column("party", JSONB(), server_default="[]", nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quest_scenarios")),
        sa.UniqueConstraint("quest_id", "number", name=op.f("uq_quest_scenarios_quest_id")),
        sa.CheckConstraint(
            "result is null or result in ('passed', 'failed')",
            name=op.f("ck_quest_scenarios_result"),
        ),
    )
    op.create_index(op.f("ix_quest_scenarios_quest_id"), "quest_scenarios", ["quest_id"])

    op.create_table(
        "quest_log_entries",
        *record_columns(),
        sa.Column(
            "quest_id",
            sa.Uuid(),
            sa.ForeignKey(
                "quests.id", name=op.f("fk_quest_log_entries_quest_id_quests"), ondelete="CASCADE"
            ),
            nullable=False,
        ),
        user_column("quest_log_entries", "actor_id"),
        sa.Column("text", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quest_log_entries")),
    )
    op.create_index(op.f("ix_quest_log_entries_quest_id"), "quest_log_entries", ["quest_id"])

    # Deliveries carry a quest's news to one of its characters, as well as results.
    op.alter_column("deliveries", "submission_id", nullable=True)
    op.add_column(
        "deliveries",
        sa.Column(
            "quest_id",
            sa.Uuid(),
            sa.ForeignKey(
                "quests.id", name=op.f("fk_deliveries_quest_id_quests"), ondelete="CASCADE"
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "deliveries",
        sa.Column(
            "character_id",
            sa.Uuid(),
            sa.ForeignKey(
                "characters.id",
                name=op.f("fk_deliveries_character_id_characters"),
                ondelete="CASCADE",
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "deliveries", sa.Column("subject", sa.String(), server_default="", nullable=False)
    )
    op.create_index(op.f("ix_deliveries_quest_id"), "deliveries", ["quest_id"])
    op.create_check_constraint(
        "one_subject",
        "deliveries",
        "(submission_id is not null and quest_id is null and character_id is null)"
        " or (submission_id is null and quest_id is not null and character_id is not null)",
    )

    op.drop_constraint("source", "influence_entries", type_="check")
    op.create_check_constraint(
        "source",
        "influence_entries",
        "source in ('downtime', 'game', 'hand', 'import', 'quest')",
    )


def downgrade() -> None:
    op.execute("delete from influence_entries where source = 'quest'")
    op.drop_constraint("source", "influence_entries", type_="check")
    op.create_check_constraint(
        "source", "influence_entries", "source in ('downtime', 'game', 'hand', 'import')"
    )
    op.execute("delete from deliveries where submission_id is null")
    op.drop_constraint("one_subject", "deliveries", type_="check")
    op.drop_index(op.f("ix_deliveries_quest_id"), table_name="deliveries")
    op.drop_column("deliveries", "subject")
    op.drop_column("deliveries", "character_id")
    op.drop_column("deliveries", "quest_id")
    op.alter_column("deliveries", "submission_id", nullable=False)
    op.drop_table("quest_log_entries")
    op.drop_table("quest_scenarios")
    op.drop_table("quest_requirements")
    op.drop_table("quest_members")
    op.drop_table("quest_requests")
    op.drop_table("quests")
    op.drop_column("troupes", "quest_requests_per_cycle")
    op.drop_column("troupes", "quests_enabled")
