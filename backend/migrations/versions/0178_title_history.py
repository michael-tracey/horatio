"""title history: each holding of a title, from when it began to when it ended, for the
court over time (issue #712); those from before are recovered from the audit log. And a
troupe setting for whether its players see it.

Revision ID: 0178
Revises: 0172
Create Date: 2026-11-12 18:00:00.000000
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0178"
down_revision: str | None = "0172"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


BEGAN = ("given", "chosen", "unknown")
ENDED = ("taken", "given_up", "retired", "left", "removed", "deleted", "unknown")


def upgrade() -> None:
    op.add_column(
        "troupes",
        sa.Column("court_history_players", sa.Boolean(), server_default="false", nullable=False),
    )
    op.create_table(
        "title_holdings",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=True),
        sa.Column("character_name", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("began_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("began_how", sa.String(), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_how", sa.String(), nullable=True),
        sa.Column("began_in_game", sa.Date(), nullable=True),
        sa.Column("ended_in_game", sa.Date(), nullable=True),
        sa.Column("backfilled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "began_how in (" + ", ".join(f"'{h}'" for h in BEGAN) + ")",
            name=op.f("ck_title_holdings_began_how"),
        ),
        sa.CheckConstraint(
            "ended_how is null or ended_how in (" + ", ".join(f"'{h}'" for h in ENDED) + ")",
            name=op.f("ck_title_holdings_ended_how"),
        ),
        sa.CheckConstraint(
            "(ended_at is null) = (ended_how is null)", name=op.f("ck_title_holdings_ended")
        ),
        sa.CheckConstraint(
            "ended_at is null or ended_at >= began_at", name=op.f("ck_title_holdings_in_order")
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_title_holdings_character_id_characters"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"],
            ["troupes.id"],
            name=op.f("fk_title_holdings_troupe_id_troupes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_title_holdings")),
    )
    op.create_index(op.f("ix_title_holdings_character_id"), "title_holdings", ["character_id"])
    op.create_index(op.f("ix_title_holdings_troupe_id"), "title_holdings", ["troupe_id"])
    op.create_index(
        "uq_title_holdings_open",
        "title_holdings",
        ["troupe_id", "character_id", "name"],
        unique=True,
        postgresql_where=sa.text("ended_at is null"),
    )
    backfill(op.get_bind())


def downgrade() -> None:
    op.drop_index("uq_title_holdings_open", table_name="title_holdings")
    op.drop_index(op.f("ix_title_holdings_troupe_id"), table_name="title_holdings")
    op.drop_index(op.f("ix_title_holdings_character_id"), table_name="title_holdings")
    op.drop_table("title_holdings")
    op.drop_column("troupes", "court_history_players")


# --- recovering the history from the log ---------------------------------------------------------
#
# Kept here, not in horatio: a migration runs against the schema as it was, and must not
# change when the app's code does. tests/test_title_history.py loads it to test `replay`.


@dataclass(frozen=True)
class Event:
    """One change from the audit log that starts or ends a holding."""

    at: datetime
    action: str
    troupe_id: uuid.UUID | None
    # None for a character since deleted: then `character_name` stands for it.
    character_id: uuid.UUID | None
    character_name: str
    data: dict[str, Any]


@dataclass(frozen=True)
class Held:
    """A title held now (a character_titles row), with when its row was made."""

    troupe_id: uuid.UUID
    character_id: uuid.UUID
    character_name: str
    name: str
    since: datetime


@dataclass
class Tenure:
    troupe_id: uuid.UUID
    character_id: uuid.UUID | None
    character_name: str
    name: str
    began_at: datetime
    began_how: str
    ended_at: datetime | None = None
    ended_how: str | None = None


@dataclass
class Replayed:
    tenures: list[Tenure] = field(default_factory=list[Tenure])
    # How much the log could say, for the report.
    begun_from_log: int = 0
    begun_from_rows: int = 0
    ends_without_start: int = 0
    closed_as_unknown: int = 0


# The ends of a holding the log records by title, and what each is.
ENDING = {"title.taken": "taken", "title.given_up": "given_up"}
# Leaving a troupe, or the troupe closing, ends every title held there.
LEFT = ("troupe.leave", "troupe.settled")
ACTIONS = (
    "title.given",
    "title.chosen",
    "title.taken",
    "title.given_up",
    "title.removed_from_troupe",
    *LEFT,
)


def names_in(listed: str, known: Sequence[str]) -> list[str]:
    """The titles in "Prince, Harpy and Whip", as horatio.titles.and_list wrote them.
    A name with " and " or a comma of its own is found by matching `known` (the
    titles the character held there) first."""
    found: list[str] = []
    rest = listed
    for name in sorted(known, key=len, reverse=True):
        if name and name in rest:
            found.append(name)
            rest = rest.replace(name, ",")
    found += [part.strip() for part in rest.replace(" and ", ",").split(",") if part.strip()]
    return found


def replay(events: Sequence[Event], held: Sequence[Held]) -> Replayed:
    """The holdings the log shows, oldest event first: each given or chosen title
    opens one, and its taking, giving up, retiring, leaving, or removal from the
    troupe closes it. A title held now that the log never opened began when its row
    was made, how unknown. One the log opened, no longer held, with nothing to close
    it, closes at the last thing the log says of that character there: as deleted
    if the character was, else how unknown."""
    out = Replayed()
    open_: dict[tuple[uuid.UUID, object, str], Tenure] = {}
    last_seen: dict[tuple[uuid.UUID, object], datetime] = {}

    def close(key: tuple[uuid.UUID, object, str], at: datetime, how: str) -> None:
        tenure = open_.pop(key)
        tenure.ended_at, tenure.ended_how = max(at, tenure.began_at), how

    for e in sorted(events, key=lambda e: e.at):
        if e.troupe_id is None:
            continue
        person: object = e.character_id or ("name", e.character_name)
        here = (e.troupe_id, person)
        last_seen[here] = e.at
        title = str(e.data.get("title") or "")
        if e.action in ("title.given", "title.chosen") and title:
            key = (*here, title)
            if key not in open_:
                how = "chosen" if e.action == "title.chosen" else "given"
                tenure = Tenure(e.troupe_id, e.character_id, e.character_name, title, e.at, how)
                open_[key] = tenure
                out.tenures.append(tenure)
                out.begun_from_log += 1
        elif e.action == "title.given_up" and e.data.get("kind") in ("retiring", "retired"):
            mine = [k for k in open_ if k[:2] == here]
            listed = names_in(str(e.data.get("titles") or ""), [k[2] for k in mine])
            for key in mine:
                close(key, e.at, "retired")
            out.ends_without_start += len(set(listed) - {k[2] for k in mine})
        elif e.action in ENDING and title:
            key = (*here, title)
            if key in open_:
                close(key, e.at, ENDING[e.action])
            else:
                out.ends_without_start += 1
        elif e.action == "title.removed_from_troupe" and title:
            for key in [k for k in open_ if k[0] == e.troupe_id and k[2] == title]:
                close(key, e.at, "removed")
        elif e.action in LEFT:
            for key in [k for k in open_ if k[:2] == here]:
                close(key, e.at, "left")

    for row in held:
        key = (row.troupe_id, row.character_id, row.name)
        if key in open_:
            del open_[key]  # held still, as the log says
            continue
        out.tenures.append(
            Tenure(
                row.troupe_id, row.character_id, row.character_name, row.name, row.since, "unknown"
            )
        )
        out.begun_from_rows += 1
    for key, tenure in list(open_.items()):
        how = "deleted" if tenure.character_id is None else "unknown"
        close(key, last_seen.get(key[:2], tenure.began_at), how)
        out.closed_as_unknown += 1
    return out


def backfill(connection: sa.Connection) -> Replayed:
    events = [
        Event(
            at=row.created_at,
            action=row.action,
            troupe_id=row.troupe_id,
            character_id=row.character_id,
            character_name=str((row.data or {}).get("character_name") or ""),
            data=dict(row.data or {}),
        )
        for row in connection.execute(
            sa.text(
                "select created_at, action, troupe_id, character_id, data from audit_events"
                " where action in :actions order by created_at, id"
            ).bindparams(sa.bindparam("actions", expanding=True)),
            {"actions": list(ACTIONS)},
        )
    ]
    held = [
        Held(row.troupe_id, row.character_id, row.character_name, row.name, row.created_at)
        for row in connection.execute(
            sa.text(
                "select t.troupe_id, t.character_id, c.name as character_name, t.name,"
                " t.created_at from character_titles t join characters c on c.id = t.character_id"
            )
        )
    ]
    found = replay(events, held)
    # A character deleted since: its holding goes under its name; its id is gone.
    existing = {row.id for row in connection.execute(sa.text("select id from characters"))}
    rows = [
        {
            "troupe_id": t.troupe_id,
            "character_id": t.character_id if t.character_id in existing else None,
            "character_name": t.character_name or "Unknown",
            "name": t.name,
            "began_at": t.began_at,
            "began_how": t.began_how,
            "ended_at": t.ended_at,
            "ended_how": t.ended_how,
        }
        for t in found.tenures
    ]
    if rows:
        connection.execute(
            sa.text(
                "insert into title_holdings (troupe_id, character_id, character_name, name,"
                " began_at, began_how, ended_at, ended_how, backfilled) values (:troupe_id,"
                " :character_id, :character_name, :name, :began_at, :began_how, :ended_at,"
                " :ended_how, true)"
            ),
            rows,
        )
    return found
