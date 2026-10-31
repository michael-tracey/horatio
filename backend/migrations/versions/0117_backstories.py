"""A character's backstory (issue #343): its Markdown text, the thread of staff
feedback on it, a troupe's backstory questions and the answers given to them, and
the troupe's settings for how backstories are written and whether one must be
approved before a character is accepted (on, for every troupe)

Revision ID: 0117
Revises: 0115
Create Date: 2026-10-31 18:00:00.000000
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0117"
down_revision: str | None = "0115"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def record() -> list[sa.Column[Any]]:
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
    op.add_column(
        "troupes", sa.Column("backstory_mode", sa.String(), server_default="free", nullable=False)
    )
    op.add_column(
        "troupes",
        sa.Column("backstory_required", sa.Boolean(), server_default="true", nullable=False),
    )
    op.create_check_constraint(
        "backstory_mode", "troupes", "backstory_mode in ('free', 'either', 'wizard')"
    )

    op.create_table(
        "backstories",
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.Text(), server_default="", nullable=False),
        sa.Column("version", sa.Integer(), server_default="0", nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("changed_by", sa.Uuid(), nullable=True),
        sa.Column(
            "built", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("review", sa.String(), server_default="none", nullable=False),
        sa.Column("review_troupe_id", sa.Uuid(), nullable=True),
        sa.Column("approved_text", sa.Text(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        *record(),
        sa.CheckConstraint(
            "review in ('none', 'returned', 'resubmitted', 'approved')",
            name=op.f("ck_backstories_review"),
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_backstories_character_id_characters"),
        ),
        sa.ForeignKeyConstraint(
            ["changed_by"], ["users.id"], name=op.f("fk_backstories_changed_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["review_troupe_id"],
            ["troupes.id"],
            name=op.f("fk_backstories_review_troupe_id_troupes"),
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"], ["users.id"], name=op.f("fk_backstories_approved_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_backstories")),
        sa.UniqueConstraint("character_id", name=op.f("uq_backstories_character_id")),
    )

    op.create_table(
        "backstory_feedback",
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("troupe_id", sa.Uuid(), nullable=True),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("section", sa.String(), server_default="", nullable=False),
        sa.Column("body", sa.Text(), server_default="", nullable=False),
        *record(),
        sa.CheckConstraint(
            "kind in ('feedback', 'reply', 'approved')", name=op.f("ck_backstory_feedback_kind")
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_backstory_feedback_character_id_characters"),
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_backstory_feedback_troupe_id_troupes")
        ),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], name=op.f("fk_backstory_feedback_author_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_backstory_feedback")),
    )
    op.create_index(
        op.f("ix_backstory_feedback_character_id"),
        "backstory_feedback",
        ["character_id"],
        unique=False,
    )

    op.create_table(
        "backstory_question_sets",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        *record(),
        sa.ForeignKeyConstraint(
            ["troupe_id"],
            ["troupes.id"],
            name=op.f("fk_backstory_question_sets_troupe_id_troupes"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_backstory_question_sets")),
    )
    op.create_index(
        op.f("ix_backstory_question_sets_troupe_id"),
        "backstory_question_sets",
        ["troupe_id"],
        unique=False,
    )

    op.create_table(
        "backstory_questions",
        sa.Column("set_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("title", sa.String(), server_default="", nullable=False),
        sa.Column("hint", sa.Text(), server_default="", nullable=False),
        sa.Column("optional", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "options", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
        sa.Column("condition", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        *record(),
        sa.CheckConstraint(
            "kind in ('long', 'short', 'year', 'choice', 'scale', 'heading')",
            name=op.f("ck_backstory_questions_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["set_id"],
            ["backstory_question_sets.id"],
            name=op.f("fk_backstory_questions_set_id_backstory_question_sets"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_backstory_questions")),
    )
    op.create_index(
        op.f("ix_backstory_questions_set_id"), "backstory_questions", ["set_id"], unique=False
    )

    op.create_table(
        "backstory_answers",
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("answer", sa.Text(), server_default="", nullable=False),
        *record(),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_backstory_answers_character_id_characters"),
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["backstory_questions.id"],
            name=op.f("fk_backstory_answers_question_id_backstory_questions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_backstory_answers")),
        sa.UniqueConstraint(
            "character_id", "question_id", name=op.f("uq_backstory_answers_character_id")
        ),
    )
    op.create_index(
        op.f("ix_backstory_answers_character_id"),
        "backstory_answers",
        ["character_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("backstory_answers")
    op.drop_table("backstory_questions")
    op.drop_table("backstory_question_sets")
    op.drop_table("backstory_feedback")
    op.drop_table("backstories")
    op.drop_constraint("backstory_mode", "troupes", type_="check")
    op.drop_column("troupes", "backstory_required")
    op.drop_column("troupes", "backstory_mode")
