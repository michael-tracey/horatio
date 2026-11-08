"""status ban clans: a troupe names the clans the sects' status bans on clans name,
the Camarilla's pillar clans among them, and staff marks on those bans are kept by
the ban's key, not its words, which now name the troupe's clans (issue #553)

Revision ID: 0156
Revises: 0155
Create Date: 2026-11-08 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0156"
down_revision: str | None = "0155"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Each ban on clans: its words before, which marks were kept under, and its key.
RENAMED = {
    "Not Embraced into a pillar clan (Assamite, Brujah, Malkavian, Nosferatu, Toreador,"
    " Tremere, Ventrue); the Gangrel are not one again yet.": "pillar_clans",
    "A known Caitiff.": "known_caitiff",
    "Assamite or Toreador antitribu.": "lesser_antitribu",
    "Tremere antitribu.": "greater_antitribu",
}
SECTS = {
    "pillar_clans": "Camarilla",
    "known_caitiff": "Camarilla",
    "lesser_antitribu": "Sabbat",
    "greater_antitribu": "Sabbat",
}


def rename(before: str, after: str, sect: str) -> None:
    op.execute(
        sa.text(
            "update status_ban_marks set ban = :after where ban = :before and sect = :sect"
        ).bindparams(before=before, after=after, sect=sect)
    )


def upgrade() -> None:
    # Every troupe goes by the rule set's clans, now Volume II's pillar clans.
    op.add_column(
        "troupes",
        sa.Column("status_ban_clans", JSONB(), nullable=False, server_default="{}"),
    )
    for words, key in RENAMED.items():
        rename(words, key, SECTS[key])


def downgrade() -> None:
    for words, key in RENAMED.items():
        rename(key, words, SECTS[key])
    op.drop_column("troupes", "status_ban_clans")
