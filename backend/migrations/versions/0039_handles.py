"""handles: what people find and see each other by, instead of their email

Every existing account gets a handle made from its display name, as
horatio.handles.suggest makes them: lowercased, only letters, numbers, _ and -,
and numbered when two would be the same. Each person can change theirs.

Revision ID: 0039
Revises: 0038
Create Date: 2026-10-20 20:00:00.000000
"""

import re
import unicodedata
from collections.abc import Sequence
from itertools import count

import sqlalchemy as sa
from alembic import op

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def from_name(name: str) -> str:
    """horatio.handles.from_name, as it was when this migration was written."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    made = re.sub(r"[^a-z0-9_-]+", "_", plain).strip("_-")[:30]
    return made if len(made) >= 3 else "player"


def free(base: str, taken: set[str]) -> str:
    """The base, or the base numbered from 2, whichever is not taken yet."""
    for n in count(1):
        number = str(n) if n > 1 else ""
        handle = base[: 30 - len(number)] + number
        if handle not in taken:
            return handle
    raise AssertionError("unreachable")


def upgrade() -> None:
    op.add_column("users", sa.Column("handle", sa.String(), nullable=True))
    op.add_column(
        "users", sa.Column("handle_changed_at", sa.DateTime(timezone=True), nullable=True)
    )
    # The longest-standing account gets the plainest handle.
    bind = op.get_bind()
    taken: set[str] = set()
    users = bind.execute(sa.text("select id, display_name from users order by created_at, id"))
    for user_id, display_name in list(users):
        handle = free(from_name(display_name), taken)
        taken.add(handle)
        bind.execute(
            sa.text("update users set handle = :handle where id = :id"),
            {"handle": handle, "id": user_id},
        )
    op.alter_column("users", "handle", nullable=False)
    op.create_index(
        "uq_users_handle_lower", "users", [sa.literal_column("lower(handle)")], unique=True
    )
    op.create_table(
        "former_handles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("handle", sa.String(), nullable=False),
        sa.Column("held_until", sa.DateTime(timezone=True), nullable=False),
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
            ["user_id"], ["users.id"], name=op.f("fk_former_handles_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_former_handles")),
    )
    op.create_index(op.f("ix_former_handles_user_id"), "former_handles", ["user_id"], unique=False)
    op.create_index(
        "ix_former_handles_handle_lower",
        "former_handles",
        [sa.literal_column("lower(handle)")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_former_handles_handle_lower", table_name="former_handles")
    op.drop_index(op.f("ix_former_handles_user_id"), table_name="former_handles")
    op.drop_table("former_handles")
    op.drop_index("uq_users_handle_lower", table_name="users")
    op.drop_column("users", "handle_changed_at")
    op.drop_column("users", "handle")
