"""Status the book ties to boons, read from the boon ledger (#694; MET: VTM p. 316).

- **Disgraced**: boons owed to a Disgraced character need not be repaid. While a
  boon's creditor holds Disgraced, the ledger and the Play View say so beside it
  (`disgraced`). Nothing is settled or changed: the note goes when the status does.
- **Warned** and **Disgraced**: an apology and a boon put a slip right, a minor
  boon under Warned and a major one under Disgraced (`APOLOGY`). Horatio doesn't
  record slips, so staff are offered the boon from the status itself: registered
  in the ledger, owed by the character to whoever was wronged (`register_apology`).
- **Praised**, spent: help worth a trivial boon from an Accepted member of the
  character's sect not already in its debt. The Play View lists who that is in the
  ledger's troupe (`not_in_debt`): its members of the same sect who owe the
  character no boon still standing.

Nothing here happens by itself: notes and offers only.
"""

import uuid
from collections.abc import Iterable
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import boons, sect_status
from horatio.models import Boon, Character, HeldStatus, Troupe, TroupeMembership, User
from horatio.sheets import rules_for, unprocessable

DISGRACED = sect_status.DISGRACED
WARNED = "Warned"
PRAISED = "Praised"
# The boon an apology puts a slip right with, by the status the slip was under (p. 316).
APOLOGY = {WARNED: "minor", DISGRACED: "major"}


def held_now(db: Session, character: Character, name: str) -> bool:
    """Whether the character holds the status and it isn't over."""
    return any(
        h.name == name and not (h.ending and h.ending.over) for h in sect_status.held(db, character)
    )


def disgraced(db: Session, ids: Iterable[uuid.UUID | None]) -> set[uuid.UUID]:
    """Of these characters, those holding Disgraced now (p. 316)."""
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return set()
    holders = set(
        db.scalars(
            select(HeldStatus.character_id).where(
                HeldStatus.character_id.in_(wanted), HeldStatus.name == DISGRACED
            )
        )
    )
    found: set[uuid.UUID] = set()
    for character_id in holders:
        character = db.get(Character, character_id)
        if character is not None and held_now(db, character, DISGRACED):
            found.add(character_id)
    return found


# --- Warned and Disgraced: the apology's boon --------------------------------------------------


def apology_status(db: Session, character: Character, held_id: uuid.UUID) -> HeldStatus:
    """The Warned or Disgraced the character holds, whose slip the boon puts right."""
    row = db.get(HeldStatus, held_id)
    if row is None or row.character_id != character.id:
        raise unprocessable("The character does not hold that status.")
    if row.name not in APOLOGY:
        raise unprocessable(
            "Only a slip under Warned or Disgraced is put right with a boon (p. 316)."
        )
    return row


def register_apology(
    db: Session,
    user: User,
    troupe: Troupe,
    character: Character,
    row: HeldStatus,
    wronged: boons.Party,
    made_on: date,
    reason: str = "",
) -> Boon:
    """Register the boon an apology owes for a slip under `row` (p. 316): minor under
    Warned, major under Disgraced, owed by the character to whoever was wronged."""
    if not boons.in_troupe(db, troupe, character):
        raise unprocessable(f"{character.name} isn't in {troupe.name}.")
    kind = APOLOGY[row.name]
    terms = boons.Terms(
        kind=kind,
        made_on=made_on,
        reason=reason.strip() or f"An apology for a slip while {row.name}",
    )
    made = boons.register(
        db,
        user,
        troupe,
        boons.Party(character, ""),
        wronged,
        terms,
        note=f"Puts right a slip while {row.name} (p. 316).",
    )
    return made[0]


# --- Praised: who is not already in the character's debt ---------------------------------------


def in_sect(db: Session, character: Character) -> str | None:
    """The sect that has Accepted the character: one with status rules; None if none has."""
    sect = sect_status.sect_of(db, character)
    if sect is None or sect not in rules_for(db, character).rule_set.status_rules.sects:
        return None
    return sect


def not_in_debt(
    db: Session, troupe: Troupe, character: Character, players_only: bool
) -> tuple[str | None, list[Character]]:
    """The sect, and the troupe's characters in play Accepted by it, who owe the
    character no boon still standing: whom it may claim a trivial boon's worth of help
    from by spending Praised (p. 316). Its player gets player characters only; staff
    get the troupe's NPCs too."""
    sect = in_sect(db, character)
    if sect is None:
        return None, []
    members = select(TroupeMembership.character_id).where(
        TroupeMembership.troupe_id == troupe.id, TroupeMembership.left_at.is_(None)
    )
    in_play = Character.id.in_(members) & (Character.kind == "pc")
    if not players_only:
        in_play = in_play | ((Character.kind == "npc") & (Character.owner_troupe_id == troupe.id))
    candidates = db.scalars(
        select(Character)
        .where(in_play, Character.status == "active", Character.id != character.id)
        .order_by(Character.name)
    )
    owing = set(
        db.scalars(
            select(Boon.debtor_id).where(
                Boon.troupe_id == troupe.id,
                Boon.creditor_id == character.id,
                Boon.state == "registered",
            )
        )
    )
    return sect, [c for c in candidates if c.id not in owing and in_sect(db, c) == sect]
