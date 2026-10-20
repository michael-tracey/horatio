"""Renaming a character.

Its player can rename it at most once every three months, counted in calendar
months from the last time they did (renamed on 19 October, they can again from
19 January). The custodian can rename any character at any time, and that does
not start the player's three months.

The new name cannot be one a character already has in any of the character's
troupes (its home troupe and those it visits), ignoring case and surrounding
spaces. The staff of those troupes are told of a player's rename; a
custodian's is told to the player and the staff of every troupe they play in.

A character in no troupe yet is the player's own business: it can be renamed
at will, with no limit, no name check and no one told, and those renames do
not count towards the three months. Archived troupes are closed, so they do
not count as the character's troupes.

The audit log keeps "renamed from … to …" in each of the character's troupes.
Past entries, XP and downtime results keep the name they were written with.
"""

import calendar
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit
from horatio.models import Character, Troupe, TroupeMembership, TroupeStaff, User
from horatio.notifications import notify
from horatio.permissions import TROUPE_POLICY, TroupeAction
from horatio.sheets import conflict, unprocessable

# How often a player can rename a character that is in a troupe.
MONTHS_BETWEEN_RENAMES = 3


def add_months(day: date, months: int) -> date:
    """The same day `months` calendar months on, or the month's last day if it is
    shorter: 30 November and three months is 28 (or 29) February."""
    month = day.month - 1 + months
    year, month = day.year + month // 12, month % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def troupes_of(db: Session, character: Character) -> list[Troupe]:
    """The running troupes the character is in now, home first."""
    troupes = db.scalars(
        select(Troupe)
        .join(TroupeMembership, TroupeMembership.troupe_id == Troupe.id)
        .where(
            TroupeMembership.character_id == character.id,
            TroupeMembership.left_at.is_(None),
            Troupe.archived_at.is_(None),
        )
        .order_by(TroupeMembership.joined_at)
    )
    return sorted(troupes, key=lambda t: t.id != character.home_troupe_id)


def next_rename_on(db: Session, character: Character, today: date | None = None) -> date | None:
    """The first day its player can rename the character again; None if they can now."""
    if character.renamed_at is None:
        return None
    allowed = add_months(character.renamed_at.astimezone(UTC).date(), MONTHS_BETWEEN_RENAMES)
    if allowed <= (today or datetime.now(UTC).date()) or not troupes_of(db, character):
        return None
    return allowed


def running_staff(db: Session, troupes: list[Troupe]) -> dict[Troupe, list[User]]:
    """Each troupe's lead, storytellers and assistant storytellers."""
    roles = [r.value for r in TROUPE_POLICY[TroupeAction.VIEW_MEMBER_CHARACTERS]]
    staff: dict[Troupe, list[User]] = {}
    for troupe in troupes:
        people = db.scalars(
            select(User)
            .join(TroupeStaff, TroupeStaff.user_id == User.id)
            .where(TroupeStaff.troupe_id == troupe.id, TroupeStaff.role.in_(roles))
        )
        staff[troupe] = [db.get_one(User, troupe.lead_user_id), *people]
    return staff


def players_troupes(db: Session, character: Character) -> list[Troupe]:
    """The character's troupes, then the other running troupes its player has a
    character in."""
    others = db.scalars(
        select(Troupe)
        .join(TroupeMembership, TroupeMembership.troupe_id == Troupe.id)
        .join(Character, TroupeMembership.character_id == Character.id)
        .where(
            Character.player_id == character.player_id,
            Character.kind == "pc",
            TroupeMembership.left_at.is_(None),
            Troupe.archived_at.is_(None),
        )
        .order_by(Troupe.name)
    )
    return list(dict.fromkeys([*troupes_of(db, character), *others]))


def check_name_is_free(db: Session, character: Character, troupes: list[Troupe], name: str) -> None:
    """Refuse a name another character already has in any of `troupes`."""
    wanted = name.strip().casefold()
    for troupe in troupes:
        names = db.scalars(
            select(Character.name)
            .join(TroupeMembership, TroupeMembership.character_id == Character.id)
            .where(
                TroupeMembership.troupe_id == troupe.id,
                TroupeMembership.left_at.is_(None),
                Character.id != character.id,
            )
        )
        if any(n.strip().casefold() == wanted for n in names):
            raise conflict(f"A character in {troupe.name} is already called {name}.")


def rename(db: Session, user: User, character: Character, name: str) -> None:
    """Rename the character, as its player (or, for an NPC, its troupe's staff) or as
    the custodian. Callers check that `user` may change the character at all."""
    name = name.strip()
    if not name:
        raise unprocessable("A character needs a name.")
    old = character.name
    if name == old:
        return
    troupes = troupes_of(db, character)
    by_custodian = user.is_custodian
    by_player = not by_custodian and character.kind == "pc"
    if troupes:
        if by_player:
            allowed = next_rename_on(db, character)
            if allowed is not None:
                raise conflict(
                    f"{old} was renamed less than {MONTHS_BETWEEN_RENAMES} months ago;"
                    f" you can rename it again on {allowed.day} {allowed:%B %Y}."
                )
        check_name_is_free(db, character, troupes, name)

    character.name = name
    if troupes and by_player:
        character.renamed_at = datetime.now(UTC)
    db.flush()

    for troupe_id in [t.id for t in troupes] or [None]:
        audit.record(
            db,
            user,
            "character.renamed",
            troupe_id=troupe_id,
            character_id=character.id,
            character_name=name,
            from_name=old,
            name=name,
            by_custodian=by_custodian,
        )
    if not troupes:
        return

    told = {user.id}
    link = f"/characters/{character.id}"
    if by_custodian and character.kind == "pc" and character.player_id not in told:
        notify(
            db,
            [character.player_id],
            "character.renamed",
            f"The custodian renamed {old} to {name}",
            link,
            troupe_id=character.home_troupe_id,
            character_id=character.id,
        )
        told.add(character.player_id)
    if not (by_player or by_custodian):
        return  # an NPC renamed by its own troupe's staff
    pc = character.kind == "pc"
    staffed = players_troupes(db, character) if by_custodian and pc else troupes
    for troupe, staff in running_staff(db, staffed).items():
        new = [s.id for s in staff if s.id not in told]
        if troupe in troupes:
            summary, where = f"{old} is now called {name}", link
        else:
            # Staff of the player's other troupes cannot see the character itself.
            player = db.get_one(User, character.player_id).display_name
            summary = f"{player}'s character {old} is now called {name}"
            where = f"/troupes/{troupe.id}"
        notify(
            db,
            new,
            "character.renamed",
            summary,
            where,
            troupe_id=troupe.id,
            character_id=character.id,
        )
        told.update(new)
