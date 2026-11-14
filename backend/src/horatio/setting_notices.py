"""A bell notice to a troupe's players when its Setting Style Document changes (issue
#881), saying what changed: a theme added, the teaser rewritten, a clan's rarity
changed. It links to the troupe's Setting tab.

Staff often make several changes in one sitting, so a burst makes one notice: while
a player's notice is unread and its last change came less than `GATHER` ago, the
next change is added to it, and it comes up again as new. Once read, or after a
pause, the next change starts another.

Only the player-facing document counts: the parts staff write
(horatio.setting_style), the chronicle's name and city from the profile, and of
the parts built from the troupe's settings, which sects may join, clan rarity and
the New Character Incentive. Prices, house traits, checks and the other house
rules are left out: players read those on the House rules tab, and staff change
them a step at a time. Staff-only material never makes one. The notice goes to the
players of the troupe's active characters, home or visiting, never to whoever made
the change, and only to the bell: it has no email setting.
"""

from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio import clan_names, lines_veils
from horatio.models import Notification, Troupe, User
from horatio.notifications import notify

KIND = "setting.changed"
# How long after a change the next one still joins its unread notice.
GATHER = timedelta(minutes=30)
# The most changes one notice names; past these it says there are more.
NAMED = 6
OPENING = "The setting changed: "
MORE = "and more"


def link(troupe: Troupe) -> str:
    return f"/troupes/{troupe.id}/setting"


def summary(changes: Sequence[str], more: bool = False) -> str:
    return OPENING + "; ".join([*changes, *([MORE] if more else [])]) + "."


def named(text: str) -> tuple[list[str], bool]:
    """The changes a notice names, and whether it says there are more."""
    parts = text.removeprefix(OPENING).removesuffix(".").split("; ")
    more = parts[-1] == MORE
    return (parts[:-1] if more else parts), more


def changed(db: Session, user: User | None, troupe: Troupe, changes: Sequence[str]) -> None:
    """Tell the troupe's players, but `user`, of `changes` to its document, each a few
    words ("the theme Betrayal added"): in the unread notice from the last few
    minutes if they have one, else in a new one."""
    if not changes or troupe.archived_at is not None:
        return
    players = [p.id for p in lines_veils.players(db, troupe) if user is None or p.id != user.id]
    if not players:
        return
    called = clan_names.troupe_name(troupe)
    changes = list(dict.fromkeys(clan_names.shown(c, called) for c in changes))
    gathering = {
        n.user_id: n
        for n in db.scalars(
            select(Notification)
            .where(
                Notification.user_id.in_(players),
                Notification.kind == KIND,
                Notification.troupe_id == troupe.id,
                Notification.read_at.is_(None),
                Notification.created_at > func.now() - GATHER,
            )
            .order_by(Notification.created_at, Notification.id)
        )
    }
    for notice in gathering.values():
        found, more = named(notice.summary)
        for change in changes:
            if change in found:
                continue
            if len(found) < NAMED:
                found.append(change)
            else:
                more = True
        notice.summary = summary(found, more)
        notice.created_at = func.now()
    fresh = [p for p in players if p not in gathering]
    if fresh:
        notify(
            db,
            fresh,
            KIND,
            summary(changes[:NAMED], len(changes) > NAMED),
            link(troupe),
            troupe_id=troupe.id,
            email=False,
        )
    db.flush()
