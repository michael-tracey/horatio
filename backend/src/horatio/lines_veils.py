"""A player's lines and veils (issue #266): their content boundaries, in their own
words. A **line** is something that must not happen in play around them at all; a
**veil** may happen in the story, but off-screen.

They belong to the player, not a character, so they hold whichever character they
play. They are never public, never printed and never on a troupe's public profile:
the player sees their own, and the staff of every troupe they play in always see
them, to run games. Other players there see them on the Who's Who only if the player
shares them, which is off until they turn it on (horatio.permissions). Changing them
is not logged: they are the player's private settings.

Staff also see every line and veil across the troupe's players on one list, to
plan games, which names whose they are only for players who share them.
"""

from dataclasses import dataclass, field

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import Character, Troupe, TroupeMembership, User

# The most of each a player keeps, and the longest one.
MAX_ITEMS = 20
MAX_LENGTH = 100


def clean(items: list[str], what: str) -> list[str]:
    """`items` trimmed, without blanks or the same one twice (in any case)."""
    kept: list[str] = []
    for item in items:
        item = " ".join(item.split())
        if not item or item.lower() in (k.lower() for k in kept):
            continue
        if len(item) > MAX_LENGTH:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"Keep each of your {what} to {MAX_LENGTH} characters.",
            )
        kept.append(item)
    if len(kept) > MAX_ITEMS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Give at most {MAX_ITEMS} {what}."
        )
    return kept


def players(db: Session, troupe: Troupe) -> list[User]:
    """The troupe's players: those with an active character in it now, home or
    visiting, by name."""
    playing = (
        select(Character.player_id)
        .join(TroupeMembership, TroupeMembership.character_id == Character.id)
        .where(
            TroupeMembership.troupe_id == troupe.id,
            TroupeMembership.left_at.is_(None),
            Character.kind == "pc",
            Character.status == "active",
        )
    )
    return list(
        db.scalars(select(User).where(User.id.in_(playing)).order_by(User.display_name, User.id))
    )


@dataclass
class Gathered:
    """One line or veil as the troupe's list shows it: the words, how many players
    gave it, and those of them who share theirs."""

    text: str
    count: int = 0
    shared_by: list[User] = field(default_factory=list[User])


@dataclass
class TroupeList:
    lines: list[Gathered]
    veils: list[Gathered]
    # The players who gave any, for staff to open.
    players: list[User]


def gather(found: list[User], which: str) -> list[Gathered]:
    """Everyone's lines (or veils), the same words once, most often given first."""
    by_text: dict[str, Gathered] = {}
    for player in found:
        for item in getattr(player, which):
            g = by_text.setdefault(item.lower(), Gathered(text=item))
            g.count += 1
            if player.share_lines_veils:
                g.shared_by.append(player)
    return sorted(by_text.values(), key=lambda g: (-g.count, g.text.lower()))


def troupe_list(db: Session, troupe: Troupe) -> TroupeList:
    found = [p for p in players(db, troupe) if p.lines or p.veils]
    return TroupeList(lines=gather(found, "lines"), veils=gather(found, "veils"), players=found)
