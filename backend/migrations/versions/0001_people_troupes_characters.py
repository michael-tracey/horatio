"""people troupes characters

Revision ID: 0001
Revises:
Create Date: 2026-10-13 23:39:17.993806
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=True),
        sa.Column("is_custodian", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("discord_user_id", sa.String(), nullable=True),
        sa.Column("legacy_id", sa.String(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("discord_user_id", name=op.f("uq_users_discord_user_id")),
        sa.UniqueConstraint("legacy_id", name=op.f("uq_users_legacy_id")),
    )
    op.create_index(
        "uq_users_email_lower", "users", [sa.literal_column("lower(email)")], unique=True
    )
    op.create_table(
        "auth_identities",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
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
            "provider in ('discord', 'google')", name=op.f("ck_auth_identities_provider")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_auth_identities_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_identities")),
        sa.UniqueConstraint("provider", "subject", name=op.f("uq_auth_identities_provider")),
    )
    op.create_index(
        op.f("ix_auth_identities_user_id"), "auth_identities", ["user_id"], unique=False
    )
    op.create_table(
        "sessions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_sessions_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_sessions_token_hash")),
    )
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"], unique=False)
    op.create_table(
        "troupes",
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), server_default="", nullable=False),
        sa.Column("lead_user_id", sa.Uuid(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("legacy_id", sa.String(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["lead_user_id"], ["users.id"], name=op.f("fk_troupes_lead_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_troupes")),
        sa.UniqueConstraint("legacy_id", name=op.f("uq_troupes_legacy_id")),
    )
    op.create_index(op.f("ix_troupes_lead_user_id"), "troupes", ["lead_user_id"], unique=False)
    op.create_table(
        "characters",
        sa.Column("player_id", sa.Uuid(), nullable=False),
        sa.Column("splat", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), server_default="draft", nullable=False),
        sa.Column("home_troupe_id", sa.Uuid(), nullable=True),
        sa.Column("legacy_id", sa.String(), nullable=True),
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
            "status in ('draft', 'active', 'retired')", name=op.f("ck_characters_status")
        ),
        sa.ForeignKeyConstraint(
            ["home_troupe_id"], ["troupes.id"], name=op.f("fk_characters_home_troupe_id_troupes")
        ),
        sa.ForeignKeyConstraint(
            ["player_id"], ["users.id"], name=op.f("fk_characters_player_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_characters")),
        sa.UniqueConstraint("legacy_id", name=op.f("uq_characters_legacy_id")),
    )
    op.create_index(
        op.f("ix_characters_home_troupe_id"), "characters", ["home_troupe_id"], unique=False
    )
    op.create_index(op.f("ix_characters_player_id"), "characters", ["player_id"], unique=False)
    op.create_table(
        "troupe_staff",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
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
            "role in ('storyteller', 'assistant_storyteller', 'narrator')",
            name=op.f("ck_troupe_staff_role"),
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_troupe_staff_troupe_id_troupes")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_troupe_staff_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_troupe_staff")),
        sa.UniqueConstraint("troupe_id", "user_id", name=op.f("uq_troupe_staff_troupe_id")),
    )
    op.create_index(op.f("ix_troupe_staff_troupe_id"), "troupe_staff", ["troupe_id"], unique=False)
    op.create_index(op.f("ix_troupe_staff_user_id"), "troupe_staff", ["user_id"], unique=False)
    op.create_table(
        "troupe_memberships",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
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
            "left_at is null or left_at >= joined_at",
            name=op.f("ck_troupe_memberships_left_after_joined"),
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_troupe_memberships_character_id_characters"),
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_troupe_memberships_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_troupe_memberships")),
    )
    op.create_index(
        op.f("ix_troupe_memberships_character_id"),
        "troupe_memberships",
        ["character_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_troupe_memberships_troupe_id"), "troupe_memberships", ["troupe_id"], unique=False
    )
    op.create_index(
        "uq_troupe_memberships_current",
        "troupe_memberships",
        ["troupe_id", "character_id"],
        unique=True,
        postgresql_where=sa.text("left_at is null"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_troupe_memberships_current",
        table_name="troupe_memberships",
        postgresql_where=sa.text("left_at is null"),
    )
    op.drop_index(op.f("ix_troupe_memberships_troupe_id"), table_name="troupe_memberships")
    op.drop_index(op.f("ix_troupe_memberships_character_id"), table_name="troupe_memberships")
    op.drop_table("troupe_memberships")
    op.drop_index(op.f("ix_troupe_staff_user_id"), table_name="troupe_staff")
    op.drop_index(op.f("ix_troupe_staff_troupe_id"), table_name="troupe_staff")
    op.drop_table("troupe_staff")
    op.drop_index(op.f("ix_characters_player_id"), table_name="characters")
    op.drop_index(op.f("ix_characters_home_troupe_id"), table_name="characters")
    op.drop_table("characters")
    op.drop_index(op.f("ix_troupes_lead_user_id"), table_name="troupes")
    op.drop_table("troupes")
    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_table("sessions")
    op.drop_index(op.f("ix_auth_identities_user_id"), table_name="auth_identities")
    op.drop_table("auth_identities")
    op.drop_index("uq_users_email_lower", table_name="users")
    op.drop_table("users")
