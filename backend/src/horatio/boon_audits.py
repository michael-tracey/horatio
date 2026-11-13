"""Audits of a character's boons (#690; MET: VTM p. 379).

In play, characters pay the Harpy for an audit: one character's boons, as the
registry holds them on a night. A troupe's registry made these by hand, a dated
page per character. Here an audit is made from the troupe's ledger and kept as it
was then (`BoonAudit.contents`): later edits, trades and settlings never change it.

**What it holds:** the character's name, standing, clan and age as the troupe shows
them, the date it was made, how many boons they owe and are owed (and what those
weigh, horatio.boon_standings), then each boon they owe and each owed to them: the
other side, its kind, night, reason and conditions, and whether it stands, was
settled, or involves someone departed. Pending and void boons aren't in it, nor a
boon's staff note, its log, or anything else staff-only.

**Standing as the court knows it** (`court_standing`): an audit is something
characters read, so it says only what the court knows. A character is shown as
departed only as the troupe's Who's Who lists them under "No longer with us", with
why only for Final Death or Off-field; an Inactive player's character is never shown
as such (their player stopping says nothing in game), and a retired character the
Who's Who doesn't list is at court as far as anyone knows. The same rule serves the
Harpy's other views (#749).

**Who makes one:** the troupe's running staff, its Harpy with the full ledger, and
Lesser Harpies the Harpy let perform audits (horatio.boon_harpy.keeper, "audit"). A
Harpy or Lesser Harpy makes it as their character. **Given:** whoever made it may
give it to a player character in play in the troupe, once; that character's player
reads it in the Play View's Boons tab, and is told. **Logged:** the troupe's log
says who audited whom, when, as whom, and for whom; staff see every audit, and a
Harpy or Lesser Harpy those made in play (not staff's).
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from horatio import audit, boon_standings, boons, notifications, social_age
from horatio.boon_harpy import Keeper
from horatio.models import Boon, BoonAudit, Character, Troupe, TroupeMembership, User
from horatio.sheets import unprocessable

# A character's standing as the court knows it, as an audit shows it.
COURT = {
    "active": "Active",
    "final_death": "Final Death",
    "off_field": "Off-field",
    "gone": "No longer with us",
}
# Why a listed character left, where the court is told: an Inactive player's
# character only "is no longer with us".
TOLD = ("final_death", "off_field")
# What became of a boon, as an audit lists it.
STATUS = {"standing": "Standing", "settled": "Settled", "departed": "Departed"}


def court_standing(character: Character | None) -> str | None:
    """A character's standing as the court knows it (the troupe's Who's Who): active,
    or departed as listed under "No longer with us", with why only for Final Death
    or Off-field. None for a name only."""
    if character is None:
        return None
    if character.status != "retired" or not character.left_listed:
        return "active"
    return character.left_reason if character.left_reason in TOLD else "gone"


def line(boon: Boon, other: Character | None, other_name: str) -> dict[str, Any]:
    """One boon, as an audit lists it."""
    if boon.state == "settled":
        state = "settled"
    elif court_standing(other) in ("final_death", "off_field", "gone"):
        state = "departed"
    else:
        state = "standing"
    return {
        "other": other.name if other is not None else other_name,
        "kind": boon.kind,
        "made_on": boon.made_on.isoformat(),
        "reason": boon.reason,
        "conditions": boon.conditions,
        "status": state,
        "settled_how": boon.settled_how if boon.state == "settled" else None,
    }


def contents_of(db: Session, troupe: Troupe, character: Character) -> dict[str, Any]:
    """What the troupe's ledger holds of the character's boons now: registered and
    settled boons, owed and owed to them, newest first, with the counts and weights
    of those still standing (departed ones too: a debt is a debt)."""
    found = list(
        db.scalars(
            select(Boon)
            .where(
                Boon.troupe_id == troupe.id,
                Boon.state.in_(("registered", "settled")),
                or_(Boon.debtor_id == character.id, Boon.creditor_id == character.id),
            )
            .order_by(Boon.made_on.desc(), Boon.created_at.desc(), Boon.id.desc())
        )
    )
    ids = {b.debtor_id for b in found} | {b.creditor_id for b in found}
    others = {
        c.id: c
        for c in db.scalars(select(Character).where(Character.id.in_([i for i in ids if i])))
    }
    weights = boon_standings.weights_of(troupe)
    owes = [b for b in found if b.debtor_id == character.id]
    owed = [b for b in found if b.creditor_id == character.id]

    def lines(side: Sequence[Boon], debtor: bool) -> list[dict[str, Any]]:
        out = []
        for b in side:
            other_id, other_name = (
                (b.creditor_id, b.creditor_name) if debtor else (b.debtor_id, b.debtor_name)
            )
            out.append(line(b, others.get(other_id) if other_id else None, other_name))
        return out

    def standing(side: Sequence[Boon]) -> list[Boon]:
        return [b for b in side if b.state == "registered"]

    known = social_age.standings(db, [character.id]).get(character.id)
    return {
        "name": character.name,
        "clan": known.clan if known else None,
        "age": known.age if known else None,
        "standing": court_standing(character),
        "owes_count": len(standing(owes)),
        "owed_count": len(standing(owed)),
        "owes_weight": boon_standings.rounded(sum(weights[b.kind] for b in standing(owes))),
        "owed_weight": boon_standings.rounded(sum(weights[b.kind] for b in standing(owed))),
        "owes": lines(owes, True),
        "owed": lines(owed, False),
    }


def subject_ok(db: Session, troupe: Troupe, character: Character) -> None:
    if not boons.in_troupe(db, troupe, character):
        raise unprocessable(f"{character.name} isn't a character in {troupe.name}.")


def recipient_ok(db: Session, troupe: Troupe, character: Character) -> None:
    """Someone an audit can be given to: a player character in play in the troupe."""
    if (
        character.kind != "pc"
        or character.status == "retired"
        or not boons.in_troupe(db, troupe, character)
    ):
        raise unprocessable(f"{character.name} isn't a player character in play in {troupe.name}.")


def recipients(db: Session, troupe: Troupe) -> list[Character]:
    """The troupe's player characters in play, at home or visiting, by name: who an
    audit can be given to."""
    members = select(TroupeMembership.character_id).where(
        TroupeMembership.troupe_id == troupe.id, TroupeMembership.left_at.is_(None)
    )
    return list(
        db.scalars(
            select(Character)
            .where(Character.id.in_(members), Character.kind == "pc", Character.status != "retired")
            .order_by(Character.name, Character.id)
        )
    )


def seen_by(keeper: Keeper, found: BoonAudit) -> bool:
    """Staff see every audit; a Harpy or Lesser Harpy those made in play."""
    return keeper.staff or found.as_character_id is not None


def may_give(keeper: Keeper, found: BoonAudit) -> bool:
    """Its maker gives it, once: the troupe's staff, or the character who made it."""
    if found.given_to_id is not None:
        return False
    if keeper.staff:
        return True
    return keeper.character is not None and keeper.character.id == found.as_character_id


def make(
    db: Session,
    user: User,
    troupe: Troupe,
    keeper: Keeper,
    character: Character,
    given_to: Character | None = None,
) -> BoonAudit:
    """Audit the character's boons as the ledger holds them now, as `keeper`; given at
    once to `given_to`, if named. Logged."""
    subject_ok(db, troupe, character)
    if given_to is not None:
        recipient_ok(db, troupe, given_to)
    found = BoonAudit(
        troupe_id=troupe.id,
        subject_id=character.id,
        contents=contents_of(db, troupe, character),
        made_by=user.id,
        as_character_id=keeper.character.id if keeper.character is not None else None,
    )
    db.add(found)
    db.flush()
    audit.record(
        db,
        user,
        "boon.audited",
        troupe_id=troupe.id,
        character_id=character.id,
        acting=f" as {keeper.character.name}" if keeper.character is not None else "",
    )
    if given_to is not None:
        give(db, user, troupe, keeper, found, given_to)
    return found


def give(
    db: Session, user: User, troupe: Troupe, keeper: Keeper, found: BoonAudit, to: Character
) -> None:
    """Give the audit to a player character in play in the troupe, whose player is
    told. Once only: for someone else, make another. Logged."""
    if not may_give(keeper, found):
        if found.given_to_id is not None:
            raise unprocessable("It has been given already: make another for someone else.")
        raise unprocessable("Only whoever made it gives it.")
    recipient_ok(db, troupe, to)
    found.given_to_id = to.id
    found.given_at = datetime.now(UTC)
    name = found.contents.get("name", "")
    audit.record(
        db,
        user,
        "boon.audit_given",
        troupe_id=troupe.id,
        character_id=to.id,
        audited=name,
        acting=f" as {keeper.character.name}" if keeper.character is not None else "",
    )
    if to.player_id is not None:
        maker = keeper.character.name if keeper.character is not None else "The troupe's staff"
        notifications.notify(
            db,
            [to.player_id],
            "boon.audit",
            f"{maker} gave {to.name} an audit of {name}'s boons in {troupe.name}.",
            f"/print/boon-audits/{found.id}",
            troupe_id=troupe.id,
            character_id=to.id,
        )


def given_to(db: Session, character: Character) -> list[BoonAudit]:
    """The audits given to the character, in every troupe whose ledger is on, newest
    first."""
    return [
        a
        for a in db.scalars(
            select(BoonAudit)
            .where(BoonAudit.given_to_id == character.id)
            .order_by(BoonAudit.created_at.desc(), BoonAudit.id.desc())
        )
        if (t := db.get(Troupe, a.troupe_id)) is not None and boons.tracked(t)
    ]


def of_troupe(db: Session, troupe: Troupe, keeper: Keeper) -> list[BoonAudit]:
    """The troupe's audits `keeper` sees, newest first."""
    query = select(BoonAudit).where(BoonAudit.troupe_id == troupe.id)
    if not keeper.staff:
        query = query.where(BoonAudit.as_character_id.is_not(None))
    return list(db.scalars(query.order_by(BoonAudit.created_at.desc(), BoonAudit.id.desc())))
