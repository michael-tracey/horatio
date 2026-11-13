"""The Setting Style Document's own entries (issue #770): themes, moods and
storyteller notes as rows of their own, and the chronicle's subtitle, teaser and the
power and agency of its scope (MET: VTM pp. 324-336). The profile's one line on its
tone becomes a mood of the troupe's own, and goes from the profile.

Revision ID: 0220
Revises: 0219
Create Date: 2026-11-13 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0220"
down_revision: str | None = "0219"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# A tone this long or shorter is the mood's name; a longer one is its description,
# under the name "Tone".
NAME_LENGTH = 60


def upgrade() -> None:
    op.create_table(
        "chronicle_motifs",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("name", sa.String(), server_default="", nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("book_key", sa.String(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "kind in ('theme', 'mood', 'note')", name=op.f("ck_chronicle_motifs_kind")
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_chronicle_motifs_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chronicle_motifs")),
        sa.UniqueConstraint(
            "troupe_id",
            "kind",
            "position",
            name="uq_chronicle_motifs_place",
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    op.create_index(op.f("ix_chronicle_motifs_troupe_id"), "chronicle_motifs", ["troupe_id"])
    for column in ("setting_subtitle", "setting_teaser", "setting_power", "setting_agency"):
        kind = sa.String() if column == "setting_subtitle" else sa.Text()
        op.add_column("troupes", sa.Column(column, kind, server_default="", nullable=False))
    op.execute(
        sa.text(
            """
            insert into chronicle_motifs (troupe_id, kind, name, description, position)
            select id, 'mood',
                   case when length(tone) <= :short then tone else 'Tone' end,
                   case when length(tone) <= :short then '' else tone end,
                   1
            from (select id, btrim(profile -> 'setting' ->> 'tone') as tone from troupes) t
            where tone <> ''
            """
        ).bindparams(short=NAME_LENGTH)
    )
    op.execute(
        "update troupes set profile = profile #- '{setting,tone}' "
        "where profile -> 'setting' ? 'tone'"
    )


def downgrade() -> None:
    # The first mood of the troupe's own is its tone again.
    op.execute(
        """
        update troupes set profile = jsonb_set(
            profile,
            '{setting}',
            coalesce(profile -> 'setting', '{}'::jsonb)
                || jsonb_build_object('tone', left(m.tone, 200))
        )
        from (
            select distinct on (troupe_id) troupe_id,
                   case when name = 'Tone' then description else name end as tone
            from chronicle_motifs
            where kind = 'mood' and book_key is null
            order by troupe_id, position, id
        ) m
        where troupes.id = m.troupe_id
        """
    )
    for column in ("setting_agency", "setting_power", "setting_teaser", "setting_subtitle"):
        op.drop_column("troupes", column)
    op.drop_index(op.f("ix_chronicle_motifs_troupe_id"), table_name="chronicle_motifs")
    op.drop_table("chronicle_motifs")
