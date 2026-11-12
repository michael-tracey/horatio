"""merits and flaws in XP: a merit taken in creation costs initial XP and a flaw adds
to it, at most the flaws' budget in all, as the book has it (MET: VTM pp. 85, 106;
issue #657), where they came from free budgets of points before

Characters still in creation are recalculated: each merit and flaw they hold gets its
"creation" line in the XP history, as if taken now. A merit costs its points here
(Horatio reprices it at the next change, for the few that cost less, such as a Path
merit for its own clan); flaws give XP in the order they were taken, up to the
budget. Every other character keeps its numbers: `merits_flaws_xp` is false for them.

Revision ID: 0165
Revises: 0164
Create Date: 2026-11-11 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0165"
down_revision: str | None = "0164"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS = (
    "'award', 'purchase', 'settlement', 'fee', 'correction', 'self_entered', 'cap', 'reprice',"
    " 'debt', 'lost'"
)


def upgrade() -> None:
    op.drop_constraint("kind", "xp_entries", type_="check")
    op.create_check_constraint("kind", "xp_entries", f"kind in ({KINDS}, 'creation')")
    op.add_column(
        "characters",
        sa.Column("merits_flaws_xp", sa.Boolean(), server_default="false", nullable=False),
    )
    # Player characters still in creation that no home troupe has ever accepted.
    op.execute(
        """
        update characters set merits_flaws_xp = true
        where kind = 'pc' and creation_completed_at is null and home_troupe_id is null
          and not exists (select 1 from sheet_versions v where v.character_id = characters.id)
        """
    )
    op.alter_column("characters", "merits_flaws_xp", server_default="true")
    # Their merits and flaws, in XP. The flaws' budget is the troupe's they are built
    # for, where it has its own creation rules for flaws, else the rule set's.
    op.execute(
        """
        with picks as (
          select t.id, t.character_id, t.trait_definition_id, t.detail,
                 t.creation_pick as points, k.key as category, k.id as category_id,
                 case when t.detail = '' then d.name else d.name || ': ' || t.detail end
                   as label,
                 c.player_id, c.building_troupe_id
          from character_traits t
          join characters c on c.id = t.character_id
          join trait_definitions d on d.id = t.trait_definition_id
          join trait_categories k on k.id = d.category_id
          where c.merits_flaws_xp and t.creation_pick > 0
            and k.key in ('merits', 'flaws')
        ),
        limited as (
          select p.*,
                 case when exists (
                   select 1 from creation_rules r
                   where r.troupe_id = p.building_troupe_id and r.category_id = p.category_id
                 ) then coalesce((
                   select max(r.points) from creation_rules r
                   where r.troupe_id = p.building_troupe_id and r.category_id = p.category_id
                 ), 0)
                 else coalesce((
                   select max(r.points) from creation_rules r
                   where r.troupe_id is null and r.category_id = p.category_id
                 ), 0) end as budget,
                 sum(p.points) over (
                   partition by p.character_id, p.category order by p.id
                 ) as upto
          from picks p
        )
        insert into xp_entries (
          character_id, kind, amount, reason, entered_by, trait_definition_id, detail,
          from_rating, to_rating
        )
        select character_id, 'creation',
               case when category = 'merits' then -points
                    else least(points, greatest(0, budget - (upto - points))) end,
               label || ' 0 → ' || points || ', taken in creation: '
                 || case when category = 'merits' then 'merits now cost XP (p. 106)'
                         else 'flaws now give XP (p. 106)' end,
               player_id, trait_definition_id, nullif(detail, ''), 0, points
        from limited
        order by character_id, id
        """
    )


def downgrade() -> None:
    op.execute("delete from xp_entries where kind = 'creation'")
    op.drop_column("characters", "merits_flaws_xp")
    op.drop_constraint("kind", "xp_entries", type_="check")
    op.create_check_constraint("kind", "xp_entries", f"kind in ({KINDS})")
