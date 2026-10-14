"""audit survives character deletion

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-14 08:45:05.240957
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("fk_audit_events_character_id_characters"), "audit_events", type_="foreignkey"
    )
    op.create_foreign_key(
        op.f("fk_audit_events_character_id_characters"),
        "audit_events",
        "characters",
        ["character_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_audit_events_character_id_characters"), "audit_events", type_="foreignkey"
    )
    op.create_foreign_key(
        op.f("fk_audit_events_character_id_characters"),
        "audit_events",
        "characters",
        ["character_id"],
        ["id"],
    )
