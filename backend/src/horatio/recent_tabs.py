"""The tabs of a troupe's page a person opened last there (#1048), kept on their
account so a phone at the game and a laptop at home share them. The page shows
the last three, not counting the open one, at the top of its tab list on a phone.

The page sends the list itself, newest first, a little after the open tab changes,
never on every render: this keeps what it is sent, cut to `KEPT`, and nothing more.
Only a member of the troupe (its staff, its players, the custodian) has one; for
anyone else there is nothing to keep and nothing is kept."""

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from horatio.models import RecentTroupeTabs, Troupe, User
from horatio.permissions import is_member

# The three shown, and the open one, which is left out of them.
KEPT = 4


def read(db: Session, user: User, troupe: Troupe) -> list[str]:
    """The person's last tabs in the troupe, newest first; none for a non-member."""
    if not is_member(db, user, troupe):
        return []
    tabs = db.scalar(
        select(RecentTroupeTabs.tabs).where(
            RecentTroupeTabs.user_id == user.id, RecentTroupeTabs.troupe_id == troupe.id
        )
    )
    return list(tabs or [])


def keep(db: Session, user: User, troupe: Troupe, tabs: list[str]) -> list[str]:
    """Keep `tabs` as the person's last in the troupe, each once, the first `KEPT`:
    one statement, a row made or replaced. Nothing for a non-member."""
    if not is_member(db, user, troupe):
        return []
    kept = list(dict.fromkeys(tabs))[:KEPT]
    db.execute(
        insert(RecentTroupeTabs)
        .values(user_id=user.id, troupe_id=troupe.id, tabs=kept)
        .on_conflict_do_update(
            constraint="uq_recent_troupe_tabs_one",
            set_={"tabs": kept, "updated_at": func.now()},
        )
    )
    return kept
