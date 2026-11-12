"""The Harpy and the troupe's boon ledger (#688; MET: VTM p. 379).

The Harpy keeps the boon registry in play. In Horatio, the Harpy is whoever holds
the Harpy title in the troupe, under any of its names (a Master Harpy is a Harpy);
with several holders, each has the access. Access goes with the title: a character
who stops holding it, or retires, stops having it at once.

The troupe says how far the Harpy reaches into its ledger (`ACCESS`):
- "none": the ledger is its staff's alone;
- "submissions": the review queue (#687), and word of each boon its players report;
- "full": the whole ledger, to register, edit, trade, pass on, settle, void and
  reopen boons as its staff do, and its review queue.

The Harpy works from the Play View, as their character: what they do is logged on
the boon as done by that character. They never see what an edit changed (only the
troupe's storytellers and assistant storytellers do, horatio.boons.sees_changes),
nor a boon's staff note, nor who entered a boon out of game, nor why a character
retired.

`keeper` is the one check of who may work the ledger, and as whom: the troupe's
running staff, a Harpy within the troupe's setting, or a Lesser Harpy (a talon) the
Harpy gave access (horatio.boon_talons, #689). It answers for one `need`:
- "submissions": the review queue (#687);
- "view": seeing the whole ledger;
- "add": registering boons;
- "edit": editing, trading, passing on, settling, voiding and reopening them;
- "audit": auditing a character's boons (#690).
Audits (#690), Gallant's offers (#693) and Boonbreakers (#717) are meant to ask it too.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit, boons, notifications, titles
from horatio.models import Boon, Character, CharacterTitle, Troupe, User
from horatio.sheets import unprocessable

# The title whose holders keep the registry (p. 379), by its main name.
HARPY = "Harpy"
# How far the Harpy reaches into the ledger, least first.
ACCESS = {
    "none": "no access to the ledger",
    "submissions": "the review queue, and word of each boon players report",
    "full": "the full ledger, to register, edit and settle boons",
}
RANK = {level: n for n, level in enumerate(ACCESS)}
# What working the ledger can take (`keeper`'s `need`).
NEEDS = ("submissions", "view", "add", "edit", "audit")
EVERYTHING = frozenset(NEEDS)
# What a Harpy may do, by the troupe's setting.
HARPY_CAN = {
    "none": frozenset[str](),
    "submissions": frozenset({"submissions"}),
    "full": EVERYTHING,
}


@dataclass(frozen=True)
class Keeper:
    """Someone who may work the troupe's ledger: its running staff (no character), a
    Harpy, or a Lesser Harpy, as their character, with what they may do (`can`)."""

    character: Character | None
    can: frozenset[str] = EVERYTHING
    # "staff", "harpy" or "talon".
    role: str = "staff"

    @property
    def staff(self) -> bool:
        return self.character is None


def access(troupe: Troupe) -> str:
    return troupe.boon_harpy


def set_access(db: Session, user: User, troupe: Troupe, level: str) -> None:
    """How far the Harpy reaches into the troupe's ledger. Logged if it changes."""
    if level not in ACCESS:
        raise unprocessable(f"The Harpy has one of {', '.join(ACCESS)}.")
    if troupe.boon_harpy == level:
        return
    troupe.boon_harpy = level
    audit.record(db, user, "house.boon_harpy", troupe_id=troupe.id, setting=ACCESS[level])


def harpies(db: Session, troupe: Troupe) -> list[Character]:
    """The characters holding the Harpy title in the troupe, under any of its names,
    who are still in play there."""
    names = titles.office_names(titles.title_data(db, troupe.id), HARPY)
    found: dict[object, Character] = {}
    for character, _ in titles.holders_of(db, troupe.id, names):
        if character.status != "retired" and boons.in_troupe(db, troupe, character):
            found.setdefault(character.id, character)
    return list(found.values())


def harpy_of(db: Session, user: User, troupe: Troupe) -> Character | None:
    """The user's own character that is a Harpy in the troupe, if any (the first by
    name, should they play two)."""
    return next((c for c in harpies(db, troupe) if c.player_id == user.id), None)


def offices_of(db: Session, character: Character) -> list[Troupe]:
    """The troupes keeping a ledger the Harpy reaches into, where the character holds
    the Harpy title and is in play: where its player works the ledger as it."""
    if character.status == "retired":
        return []
    found: list[Troupe] = []
    held = db.execute(
        select(CharacterTitle.troupe_id, CharacterTitle.name).where(
            CharacterTitle.character_id == character.id
        )
    ).all()
    for troupe_id in dict.fromkeys(t for t, _ in held):
        troupe = db.get(Troupe, troupe_id)
        if troupe is None or not boons.tracked(troupe) or troupe.archived_at is not None:
            continue
        if troupe.boon_harpy == "none" or not boons.in_troupe(db, troupe, character):
            continue
        names = titles.office_names(titles.title_data(db, troupe.id), HARPY)
        if any(n in names for t, n in held if t == troupe_id):
            found.append(troupe)
    return sorted(found, key=lambda t: t.name)


def reaches(troupe: Troupe, need: str) -> bool:
    """Whether the troupe's setting gives the Harpy `need`: "submissions" or "full"."""
    return RANK[troupe.boon_harpy] >= RANK[need]


def keeper(db: Session, user: User, troupe: Troupe, need: str = "view") -> Keeper | None:
    """Who `user` works the troupe's ledger as, for `need` (one of `NEEDS`): its
    running staff; one of their characters that holds the Harpy title, where the
    troupe's setting reaches that far; or one of their characters the Harpy gave
    access (a Lesser Harpy, horatio.boon_talons), for what that access allows. None
    for anyone else, or while the troupe keeps no ledger."""
    if need not in NEEDS:
        raise ValueError(f"No such need: {need}")
    if boons.can_manage(db, user, troupe):
        return Keeper(None)
    if not boons.tracked(troupe) or troupe.archived_at is not None:
        return None
    harpy = harpy_of(db, user, troupe)
    if harpy is not None and need in HARPY_CAN[troupe.boon_harpy]:
        return Keeper(harpy, HARPY_CAN[troupe.boon_harpy], "harpy")
    from horatio import boon_talons  # imports this module

    found = boon_talons.talon_of(db, user, troupe)
    if found is not None and need in boon_talons.can(found[1]):
        return Keeper(found[0], boon_talons.can(found[1]), "talon")
    return None


def tell(db: Session, troupe: Troupe, made: Sequence[Boon], reporter: Character) -> None:
    """Word to each Harpy's player of boons a player just reported, where the troupe
    gives the Harpy the review queue or more. Not to the reporter's own player."""
    if not made or not boons.tracked(troupe) or troupe.boon_harpy == "none":
        return
    first = made[0]
    debtor, creditor = boons.parties(db, first)
    waits = " It waits for review." if first.state == "pending" else ""
    what = boons.a_boon(first.kind, len(made))
    for harpy in harpies(db, troupe):
        if harpy.kind != "pc" or harpy.player_id is None or harpy.player_id == reporter.player_id:
            continue
        notifications.notify(
            db,
            [harpy.player_id],
            "boon.reported",
            f"{reporter.name} reported {what} to the ledger: {debtor.shown} owes"
            f" {creditor.shown} ({boons.when(first.made_on)}).{waits}",
            f"/play/characters/{harpy.id}/ledger",
            troupe_id=troupe.id,
            character_id=harpy.id,
        )
