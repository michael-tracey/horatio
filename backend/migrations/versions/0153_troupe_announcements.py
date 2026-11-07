"""troupe announcements: posts of a second kind, with a byline, pinning, banners
dismissed per person, and important emails that go to everyone (issue #511)

Revision ID: 0153
Revises: 0152
Create Date: 2026-11-07 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0153"
down_revision: str | None = "0152"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_posts_kind"), "posts", type_="check")
    op.create_check_constraint(op.f("ck_posts_kind"), "posts", "kind in ('news', 'announcement')")
    op.add_column("posts", sa.Column("byline", sa.String(), server_default="", nullable=False))
    op.add_column("posts", sa.Column("pinned_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "posts", sa.Column("important", sa.Boolean(), server_default="false", nullable=False)
    )
    op.add_column(
        "email_notices",
        sa.Column("forced", sa.Boolean(), server_default="false", nullable=False),
    )
    op.create_table(
        "post_dismissals",
        sa.Column("post_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
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
            ["post_id"],
            ["posts.id"],
            name=op.f("fk_post_dismissals_post_id_posts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_post_dismissals_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_post_dismissals")),
        sa.UniqueConstraint("post_id", "user_id", name=op.f("uq_post_dismissals_post_id")),
    )
    op.create_index(
        op.f("ix_post_dismissals_user_id"), "post_dismissals", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_post_dismissals_user_id"), table_name="post_dismissals")
    op.drop_table("post_dismissals")
    op.drop_column("email_notices", "forced")
    op.drop_column("posts", "important")
    op.drop_column("posts", "pinned_until")
    op.drop_column("posts", "byline")
    op.execute("delete from posts where kind = 'announcement'")
    op.drop_constraint(op.f("ck_posts_kind"), "posts", type_="check")
    op.create_check_constraint(op.f("ck_posts_kind"), "posts", "kind in ('news')")
