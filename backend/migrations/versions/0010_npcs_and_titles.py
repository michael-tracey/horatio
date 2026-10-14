"""npcs and titles

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-14 09:05:09.675685
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "troupe_titles",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
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
            ["troupe_id"], ["troupes.id"], name=op.f("fk_troupe_titles_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_troupe_titles")),
        sa.UniqueConstraint("troupe_id", "name", name=op.f("uq_troupe_titles_troupe_id")),
    )
    op.create_index(
        op.f("ix_troupe_titles_troupe_id"), "troupe_titles", ["troupe_id"], unique=False
    )
    op.create_table(
        "character_titles",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
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
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_character_titles_character_id_characters"),
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_character_titles_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_character_titles")),
        sa.UniqueConstraint(
            "troupe_id", "character_id", "name", name=op.f("uq_character_titles_troupe_id")
        ),
    )
    op.create_index(
        op.f("ix_character_titles_character_id"), "character_titles", ["character_id"], unique=False
    )
    op.create_index(
        op.f("ix_character_titles_troupe_id"), "character_titles", ["troupe_id"], unique=False
    )
    op.add_column("characters", sa.Column("kind", sa.String(), server_default="pc", nullable=False))
    op.add_column("characters", sa.Column("owner_troupe_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_characters_owner_troupe_id"), "characters", ["owner_troupe_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_characters_owner_troupe_id_troupes"),
        "characters",
        "troupes",
        ["owner_troupe_id"],
        ["id"],
    )
    op.add_column(
        "rule_sets",
        sa.Column(
            "titles", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
    )
    op.create_check_constraint(op.f("ck_characters_kind"), "characters", "kind in ('pc', 'npc')")
    op.create_check_constraint(
        op.f("ck_characters_npc_has_troupe"),
        "characters",
        "(kind = 'npc') = (owner_troupe_id is not null)",
    )

    # Antecedence is now whether a character is a PC or an NPC, and titles are
    # given by troupes: neither is a trait a player chooses any more.
    gone = """
        select d.id from trait_definitions d join trait_categories c on c.id = d.category_id
        where c.key in ('title', 'antecedence')
    """
    op.execute(f"delete from character_traits where trait_definition_id in ({gone})")
    op.execute(
        """
        update sheet_versions set snapshot = (
            select coalesce(jsonb_agg(e), '[]'::jsonb) from jsonb_array_elements(snapshot) e
            where e->>'category' not in ('title', 'antecedence')
        )
        """
    )
    op.execute(f"delete from trait_definitions where id in ({gone})")
    op.execute("delete from trait_categories where key in ('title', 'antecedence')")


def downgrade() -> None:
    # Removed titles and antecedence choices are not restored.
    op.drop_constraint(op.f("ck_characters_npc_has_troupe"), "characters", type_="check")
    op.drop_constraint(op.f("ck_characters_kind"), "characters", type_="check")
    op.drop_column("rule_sets", "titles")
    op.drop_constraint(
        op.f("fk_characters_owner_troupe_id_troupes"), "characters", type_="foreignkey"
    )
    op.drop_index(op.f("ix_characters_owner_troupe_id"), table_name="characters")
    op.drop_column("characters", "owner_troupe_id")
    op.drop_column("characters", "kind")
    op.drop_index(op.f("ix_character_titles_troupe_id"), table_name="character_titles")
    op.drop_index(op.f("ix_character_titles_character_id"), table_name="character_titles")
    op.drop_table("character_titles")
    op.drop_index(op.f("ix_troupe_titles_troupe_id"), table_name="troupe_titles")
    op.drop_table("troupe_titles")
