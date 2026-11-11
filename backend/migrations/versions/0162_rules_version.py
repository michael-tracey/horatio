"""rules version: what a rule set's and a troupe's rules were read at, changed by the
database whenever anything they are read from changes, so each process can keep the
rules in memory (issue #641)

Revision ID: 0162
Revises: 0161
Create Date: 2026-11-10 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0162"
down_revision: str | None = "0161"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The tables a troupe's rules are read from, beside its own row, and its written and
# teacher rules: a row with a troupe is that troupe's, one without the book's.
TROUPE_TABLES = (
    "action_kinds",
    "allowance_rules",
    "check_overrides",
    "cost_rules",
    "creation_rules",
    "equipment_templates",
    "house_checks",
    "house_traits",
    "starting_traits",
    "teacher_rules",
    "trait_definitions",
    "trait_overrides",
    "written_rules",
)
# The book's alone, with no troupe.
BOOK_TABLES = ("equipment_qualities", "trait_categories")
# Their own row holds the version.
VERSIONED = ("rule_sets", "troupes")


def upgrade() -> None:
    for table in VERSIONED:
        op.add_column(
            table,
            sa.Column(
                "rules_version",
                sa.Uuid(),
                server_default=sa.text("gen_random_uuid()"),
                nullable=False,
            ),
        )
    # A change to the row itself, other than to the version, gives it a new one. One
    # that sets the version (below) is left as it is.
    op.execute(
        """
        create function row_rules_changed() returns trigger language plpgsql as $$
        begin
            if new.rules_version is not distinct from old.rules_version
                and (to_jsonb(new) - 'rules_version' - 'updated_at')
                is distinct from (to_jsonb(old) - 'rules_version' - 'updated_at') then
                new.rules_version := gen_random_uuid();
            end if;
            return new;
        end $$
        """
    )
    # A row of a troupe's rules: that troupe's version; a row of the book's: the
    # rule sets'.
    op.execute(
        """
        create function troupe_rules_changed() returns trigger language plpgsql as $$
        begin
            if tg_op <> 'INSERT' then
                if old.troupe_id is null then
                    update rule_sets set rules_version = gen_random_uuid();
                else
                    update troupes set rules_version = gen_random_uuid()
                    where id = old.troupe_id;
                end if;
            end if;
            if tg_op = 'INSERT'
                or (tg_op = 'UPDATE' and new.troupe_id is distinct from old.troupe_id) then
                if new.troupe_id is null then
                    update rule_sets set rules_version = gen_random_uuid();
                else
                    update troupes set rules_version = gen_random_uuid()
                    where id = new.troupe_id;
                end if;
            end if;
            return null;
        end $$
        """
    )
    op.execute(
        """
        create function book_rules_changed() returns trigger language plpgsql as $$
        begin
            update rule_sets set rules_version = gen_random_uuid();
            return null;
        end $$
        """
    )
    for table in VERSIONED:
        op.execute(
            f"create trigger rules_changed before update on {table} "
            "for each row execute function row_rules_changed()"
        )
    for table in TROUPE_TABLES:
        op.execute(
            f"create trigger rules_changed after insert or update or delete on {table} "
            "for each row execute function troupe_rules_changed()"
        )
    for table in BOOK_TABLES:
        op.execute(
            f"create trigger rules_changed after insert or update or delete on {table} "
            "for each statement execute function book_rules_changed()"
        )


def downgrade() -> None:
    for table in (*VERSIONED, *TROUPE_TABLES, *BOOK_TABLES):
        op.execute(f"drop trigger rules_changed on {table}")
    for function in ("row_rules_changed", "troupe_rules_changed", "book_rules_changed"):
        op.execute(f"drop function {function}()")
    for table in VERSIONED:
        op.drop_column(table, "rules_version")
