"""Lesser Harpies, or talons (#689; MET: VTM p. 379): characters the troupe's Harpy
gives access to the boon ledger.

A troupe lets its Harpy do this (`boon_talons`) only while the Harpy has the full
ledger (horatio.boon_harpy), and calls them "Lesser Harpies" or "Talons"
(`boon_talon_word`). For each one, the Harpy chooses whether they may:
- add boons (register them);
- edit boons: edit, trade, pass on, settle, void and reopen them, and review what
  players report;
- perform audits of a character's boons (#690).
Everyone given access sees the ledger, as a Harpy does: never what an edit changed,
nor a boon's staff note, nor who entered a boon, nor why a character retired.

The access belongs to the office, not to the Harpy who gave it: a new Harpy finds the
list and keeps or removes each one. The holders of the Lesser Harpy title are offered
first, but the Harpy may choose anyone in play in the troupe. Giving, changing and
taking away access is logged; staff see who has what, and may take it away. A Lesser
Harpy who retires or leaves the troupe loses the access at once; it comes back if
they return while the Harpy hasn't removed it.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit, boon_harpy, boons, titles
from horatio.models import BoonTalon, Character, Troupe, TroupeMembership, User
from horatio.sheets import unprocessable

WORDS = ("Lesser Harpies", "Talons")
# One of them, as "Lesser Harpy of …".
ONE = {"Lesser Harpies": "Lesser Harpy", "Talons": "Talon"}
# The title the Harpy appoints (p. 379), offered first.
LESSER_HARPY = "Lesser Harpy"


def enabled(troupe: Troupe) -> bool:
    """Whether the troupe's Harpy may give others access to its ledger now: the troupe
    keeps a ledger, lets the Harpy give access, and gives the Harpy the full ledger."""
    return boons.tracked(troupe) and troupe.boon_talons and troupe.boon_harpy == "full"


def can(talon: BoonTalon) -> frozenset[str]:
    """What a Lesser Harpy may do, as horatio.boon_harpy.keeper's needs."""
    found = {"view"}
    if talon.can_add:
        found.add("add")
    if talon.can_edit:
        found |= {"edit", "submissions"}
    if talon.can_audit:
        found.add("audit")
    return frozenset(found)


def describe(talon: BoonTalon) -> str:
    """What they may do, in words: "see the ledger, add boons and edit them"."""
    parts = ["see the ledger"]
    if talon.can_add:
        parts.append("add boons")
    if talon.can_edit:
        parts.append("edit them" if talon.can_add else "edit boons")
    if talon.can_audit:
        parts.append("perform audits")
    return parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}"


def set_setting(db: Session, user: User, troupe: Troupe, on: bool, word: str) -> None:
    """Whether the Harpy may give others access, and what the troupe calls them.
    Logged if either changes. Switched off, the access given is kept, unused, for
    when it is switched on again."""
    if word not in WORDS:
        raise unprocessable(f"Call them {' or '.join(WORDS)}.")
    if troupe.boon_talons == on and troupe.boon_talon_word == word:
        return
    troupe.boon_talons = on
    troupe.boon_talon_word = word
    audit.record(
        db,
        user,
        "house.boon_talons",
        troupe_id=troupe.id,
        setting=f"may give others access to the ledger, as {word}"
        if on
        else "may give no one access",
    )


def in_play(db: Session, troupe: Troupe, character: Character) -> bool:
    return character.status != "retired" and boons.in_troupe(db, troupe, character)


def rows(db: Session, troupe: Troupe) -> list[tuple[BoonTalon, Character]]:
    """Everyone given access in the troupe, by name: in play or not."""
    found = db.execute(
        select(BoonTalon, Character)
        .join(Character, Character.id == BoonTalon.character_id)
        .where(BoonTalon.troupe_id == troupe.id)
        .order_by(Character.name, BoonTalon.id)
    ).all()
    return [(t, c) for t, c in found]


def talon_of(db: Session, user: User, troupe: Troupe) -> tuple[Character, BoonTalon] | None:
    """The user's own character given access in the troupe, while the Harpy may give
    it and the character is in play there (the first by name, should they play two)."""
    if not enabled(troupe):
        return None
    for talon, character in rows(db, troupe):
        if character.player_id == user.id and in_play(db, troupe, character):
            return character, talon
    return None


def offices_of(db: Session, character: Character) -> list[tuple[Troupe, BoonTalon]]:
    """The troupes where the character has access to the ledger as a Lesser Harpy, and
    is in play: where its player works the ledger as it."""
    if character.status == "retired":
        return []
    found: list[tuple[Troupe, BoonTalon]] = []
    for talon in db.scalars(select(BoonTalon).where(BoonTalon.character_id == character.id)):
        troupe = db.get(Troupe, talon.troupe_id)
        if troupe is None or troupe.archived_at is not None or not enabled(troupe):
            continue
        if boons.in_troupe(db, troupe, character):
            found.append((troupe, talon))
    return sorted(found, key=lambda f: f[0].name)


def giver(db: Session, user: User, troupe: Troupe) -> Character | None:
    """The user's own Harpy in the troupe who may give access now, if any."""
    if not enabled(troupe):
        return None
    return boon_harpy.harpy_of(db, user, troupe)


def candidates(db: Session, troupe: Troupe) -> list[tuple[Character, bool]]:
    """Who the Harpy may give access: the troupe's player characters in play, not its
    Harpies (who have the ledger already), each with whether they hold the Lesser
    Harpy title. Title holders first, then by name."""
    harpies = {c.id for c in boon_harpy.harpies(db, troupe)}
    names = titles.office_names(titles.title_data(db, troupe.id), LESSER_HARPY)
    lesser = {c.id for c, _ in titles.holders_of(db, troupe.id, names)}
    members = select(TroupeMembership.character_id).where(
        TroupeMembership.troupe_id == troupe.id, TroupeMembership.left_at.is_(None)
    )
    found = [
        c
        for c in db.scalars(
            select(Character).where(
                Character.id.in_(members), Character.kind == "pc", Character.status != "retired"
            )
        )
        if c.id not in harpies
    ]
    return sorted(((c, c.id in lesser) for c in found), key=lambda f: (not f[1], f[0].name))


def give(
    db: Session,
    user: User,
    troupe: Troupe,
    character: Character,
    *,
    add: bool,
    edit: bool,
    audits: bool,
    by: Character | None,
) -> BoonTalon:
    """Give the character access to the ledger, or change what it allows. Logged."""
    if character.kind != "pc" or not in_play(db, troupe, character):
        raise unprocessable(f"{character.name} isn't a player character in play in {troupe.name}.")
    if character.id in {c.id for c in boon_harpy.harpies(db, troupe)}:
        raise unprocessable(f"{character.name} is the Harpy: they have the ledger already.")
    talon = db.scalar(
        select(BoonTalon).where(
            BoonTalon.troupe_id == troupe.id, BoonTalon.character_id == character.id
        )
    )
    new = talon is None
    if talon is None:
        talon = BoonTalon(
            troupe_id=troupe.id,
            character_id=character.id,
            given_by_id=by.id if by is not None else None,
        )
        db.add(talon)
    elif (talon.can_add, talon.can_edit, talon.can_audit) == (add, edit, audits):
        return talon
    talon.can_add, talon.can_edit, talon.can_audit = add, edit, audits
    if by is not None:
        talon.given_by_id = by.id
    db.flush()
    audit.record(
        db,
        user,
        "boon.talon_given" if new else "boon.talon_changed",
        troupe_id=troupe.id,
        character_id=character.id,
        word=ONE[troupe.boon_talon_word],
        acting=f" as {by.name}" if by is not None else "",
        can=describe(talon),
    )
    return talon


def take_away(
    db: Session, user: User, troupe: Troupe, character_id: uuid.UUID, by: Character | None
) -> None:
    """Take the character's access away. Logged."""
    talon = db.scalar(
        select(BoonTalon).where(
            BoonTalon.troupe_id == troupe.id, BoonTalon.character_id == character_id
        )
    )
    if talon is None:
        return
    character = db.get(Character, character_id)
    db.delete(talon)
    audit.record(
        db,
        user,
        "boon.talon_removed",
        troupe_id=troupe.id,
        character_id=character_id,
        character_name=character.name if character else "",
        word=ONE[troupe.boon_talon_word],
        acting=f" as {by.name}" if by is not None else "",
    )


@dataclass(frozen=True)
class Listed:
    talon: BoonTalon
    character: Character
    given_by: str
    in_play: bool


def listed(db: Session, troupe: Troupe) -> list[Listed]:
    """Everyone given access, with who gave it and whether they are in play now."""
    out: list[Listed] = []
    for talon, character in rows(db, troupe):
        by = db.get(Character, talon.given_by_id) if talon.given_by_id else None
        out.append(Listed(talon, character, by.name if by else "", in_play(db, troupe, character)))
    return out
