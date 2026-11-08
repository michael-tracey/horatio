"""retired give up titles: characters retired before retiring gave up titles give up
the ones they still hold, with an entry in each troupe's log (issue #550)

Revision ID: 0158
Revises: 0157
Create Date: 2026-11-08 18:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0158"
down_revision: str | None = "0157"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # One entry per character and troupe, as retiring now records (horatio.titles.
    # give_up_on_retiring), with no one as its actor. Its titles are named
    # alphabetically: the court order needs the rules, which a migration doesn't load.
    op.execute(
        """
        insert into audit_events (actor_id, troupe_id, character_id, action, data)
        select null, t.troupe_id, t.character_id, 'title.given_up',
          jsonb_build_object(
            'kind', 'retired',
            'titles', case when count(*) = 1 then min(t.name)
              else array_to_string(
                (array_agg(t.name order by t.name))[1:(count(*) - 1)::int], ', '
              ) || ' and ' || max(t.name) end,
            'character_name', c.name
          )
        from character_titles t join characters c on c.id = t.character_id
        where c.status = 'retired'
        group by t.troupe_id, t.character_id, c.name
        """
    )
    op.execute(
        """
        delete from character_titles t using characters c
        where c.id = t.character_id and c.status = 'retired'
        """
    )


def downgrade() -> None:
    # The titles given up stay given up: the log says which they were.
    pass
