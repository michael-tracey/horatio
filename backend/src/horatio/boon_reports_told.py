"""Who is told of each boon a player reports to the troupe's ledger (#1018), each by
their own choice, which only they change:
- its storytellers and assistant storytellers (its running staff), if they ask: off
  to start with (`BoonReportStaff`). Staff choose in the Boons settings;
- each Harpy, while the troupe gives the Harpy the review queue or more: on whenever
  someone takes the title (`CharacterTitle.boon_reports_told`);
- each Lesser Harpy the Harpy lets approve reported boons (horatio.boon_talons): on
  when given access, and again when given that right (`BoonTalon.told_of_reports`).
  One who may not approve them is never told.
The Harpy and a Lesser Harpy choose on their ledger in the Play View. Nobody is told
of their own report, and each person once (horatio.boon_harpy.tell). Account ›
Notifications lists every one of a person's choices (`choices_of`, #1053) and changes
them here, so each is kept in one place.
"""

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from horatio import boon_harpy, boon_talons, boons, notifications, titles
from horatio.models import BoonReportStaff, BoonTalon, Character, CharacterTitle, Troupe, User
from horatio.permissions import TroupeAction, allows, member_troupe_ids, troupe_role


@dataclass(frozen=True)
class Told:
    """One person told of a report: where its word links, and as which character."""

    user_id: uuid.UUID
    link: str
    character_id: uuid.UUID | None = None


def is_staff(db: Session, user: User, troupe: Troupe) -> bool:
    """Whether `user` is among the troupe's running staff, who may ask to be told. The
    custodian alone is not: they aren't sent every troupe's word."""
    return troupe.archived_at is None and allows(
        troupe_role(db, user, troupe), TroupeAction.MANAGE_BOONS
    )


def staff_told(db: Session, user: User, troupe: Troupe) -> bool | None:
    """Whether the staff member asked to be told; None for anyone not running staff."""
    if not is_staff(db, user, troupe):
        return None
    return (
        db.scalar(
            select(BoonReportStaff.id).where(
                BoonReportStaff.troupe_id == troupe.id, BoonReportStaff.user_id == user.id
            )
        )
        is not None
    )


def set_staff(db: Session, user: User, troupe: Troupe, on: bool) -> None:
    if staff_told(db, user, troupe) == on:
        return
    if on:
        db.add(BoonReportStaff(troupe_id=troupe.id, user_id=user.id))
    else:
        db.execute(
            delete(BoonReportStaff).where(
                BoonReportStaff.troupe_id == troupe.id, BoonReportStaff.user_id == user.id
            )
        )
    db.flush()


def harpy_titles(db: Session, troupe: Troupe, character: Character) -> list[CharacterTitle]:
    """The character's holdings of the Harpy title in the troupe, under any of its names."""
    names = titles.office_names(titles.title_data(db, troupe.id), boon_harpy.HARPY)
    return list(
        db.scalars(
            select(CharacterTitle).where(
                CharacterTitle.troupe_id == troupe.id,
                CharacterTitle.character_id == character.id,
                CharacterTitle.name.in_(names),
            )
        )
    )


def harpy_told(db: Session, troupe: Troupe, character: Character) -> bool:
    """Whether the Harpy is told: not if they turned it off while holding the title."""
    return all(t.boon_reports_told for t in harpy_titles(db, troupe, character))


def keeper_of(db: Session, user: User, troupe: Troupe) -> tuple[Character, BoonTalon | None] | None:
    """The user's own character that may be told as the Harpy (where the troupe gives
    the Harpy the review queue or more), or else as a Lesser Harpy who approves
    reported boons, with its access; None if they have neither."""
    if not boons.tracked(troupe) or troupe.archived_at is not None:
        return None
    if troupe.boon_harpy != "none":
        harpy = boon_harpy.harpy_of(db, user, troupe)
        if harpy is not None:
            return harpy, None
    found = boon_talons.talon_of(db, user, troupe)
    if found is not None and found[1].can_review:
        return found
    return None


def keeper_told(db: Session, user: User, troupe: Troupe) -> bool | None:
    """Whether the user's Harpy or Lesser Harpy is told; None if they have neither."""
    found = keeper_of(db, user, troupe)
    if found is None:
        return None
    character, talon = found
    return talon.told_of_reports if talon is not None else harpy_told(db, troupe, character)


def set_keeper(db: Session, user: User, troupe: Troupe, on: bool) -> bool:
    """Set the choice of the user's Harpy or Lesser Harpy; False if they have neither."""
    found = keeper_of(db, user, troupe)
    if found is None:
        return False
    character, talon = found
    if talon is not None:
        talon.told_of_reports = on
    else:
        db.execute(
            update(CharacterTitle)
            .where(CharacterTitle.id.in_([t.id for t in harpy_titles(db, troupe, character)]))
            .values(boon_reports_told=on)
        )
    db.flush()
    return True


@dataclass(frozen=True)
class Choice:
    """One of a person's choices to be told, in one troupe: as staff, or as its Harpy or
    a Lesser Harpy (`keeper`), playing `character`."""

    troupe: Troupe
    role: Literal["staff", "keeper"]
    on: bool
    character: Character | None = None
    # A keeper's office, as the troupe names it: "Harpy", "Lesser Harpy" or "Talon".
    office: str | None = None


def choices_of(db: Session, user: User) -> list[Choice]:
    """Every choice the person has, in the troupes they run or play in that keep a
    ledger, by troupe name."""
    found: list[Choice] = []
    troupes = db.scalars(select(Troupe).where(Troupe.id.in_(member_troupe_ids(db, user))))
    for troupe in sorted(troupes, key=lambda t: t.name.casefold()):
        if not boons.tracked(troupe):
            continue
        staff = staff_told(db, user, troupe)
        if staff is not None:
            found.append(Choice(troupe, "staff", staff))
        keeper = keeper_of(db, user, troupe)
        if keeper is not None:
            character, talon = keeper
            office = boon_talons.ONE[troupe.boon_talon_word] if talon else "Harpy"
            on = talon.told_of_reports if talon else harpy_told(db, troupe, character)
            found.append(Choice(troupe, "keeper", on, character, office))
    return found


def told(db: Session, troupe: Troupe, waits: bool) -> list[Told]:
    """Everyone told of a report, once each: the Harpy, then Lesser Harpies, then staff.
    Their word links to the To review tab while the boons wait (#1011), else to the
    ledger. A Harpy's or Lesser Harpy's ledger opens on To review when it is the only
    tab: with the review queue alone (HarpyLedgerPage)."""
    found: dict[uuid.UUID, Told] = {}
    if troupe.boon_harpy != "none":
        tab = "/review" if waits and boon_harpy.reaches(troupe, "full") else ""
        for harpy in boon_harpy.harpies(db, troupe):
            if harpy.kind != "pc" or harpy.player_id is None:
                continue
            if harpy_told(db, troupe, harpy):
                link = f"/play/characters/{harpy.id}/ledger{tab}"
                found.setdefault(harpy.player_id, Told(harpy.player_id, link, harpy.id))
    if boon_talons.enabled(troupe):
        tab = "/review" if waits else ""
        for talon, character in boon_talons.rows(db, troupe):
            if not (talon.can_review and talon.told_of_reports) or character.player_id is None:
                continue
            if boon_talons.in_play(db, troupe, character):
                link = f"/play/characters/{character.id}/ledger{tab}"
                found.setdefault(character.player_id, Told(character.player_id, link, character.id))
    asked = set(
        db.scalars(select(BoonReportStaff.user_id).where(BoonReportStaff.troupe_id == troupe.id))
    )
    link = f"/troupes/{troupe.id}/boons{'/review' if waits else ''}"
    for user_id in notifications.staff_for(db, troupe, TroupeAction.MANAGE_BOONS):
        if user_id in asked:
            found.setdefault(user_id, Told(user_id, link))
    return list(found.values())
