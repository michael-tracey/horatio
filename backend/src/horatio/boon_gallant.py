"""Gallant for repaying a boon (#693; MET: VTM pp. 402, 405).

Gallant is fleeting Camarilla status (p. 402). A character earns it two ways the
ledger can see:

- **Social Nobility** (p. 405): when someone satisfactorily repays a boon owed to a
  character with the merit, that character may give them Gallant. Any kind of boon.
- **A great boon repaid to someone of significance** (p. 402): a great boon-debt
  "such as a blood boon or a life boon", repaid to "an individual of significance
  within the Camarilla (such as an elder of the Camarilla, a Prince, or even a
  Justicar)". Here: a Blood or Life boon, to a Camarilla character who holds an
  active title or is an Elder by social age. The book gives examples, not a test, so
  this is only ever a suggestion for staff and the Harpy.

Neither is ever automatic. When a boon is settled as called in, the ledger *offers*
Gallant for its debtor; whoever may answer the offer gives it or declines it, and
either way the answer goes in the boon's own log, so the offer is answered once.
Reopening and settling the boon again makes a new offer.

Who answers:
- Whoever may settle the boon in the ledger (horatio.boon_harpy.keeper, "edit"): the
  troupe's running staff, a Harpy with the full ledger (#688), or a Lesser Harpy the
  Harpy let edit it (#689), either offer, as their character for a Harpy.
- The creditor's player, a Social Nobility offer only, from the Play View's Boons tab,
  where the troupe shows creditors their boons and lets players keep their own status.
  Where only staff add or remove status, staff and the Harpy answer it.

Giving Gallant goes through horatio.sect_status, as any fleeting status does, with
the creditor as its patron: the debtor's sheet and log show it, and its rules hold
(the debtor must be Camarilla, not Disgraced, and have room under the fleeting cap).
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import boons, sect_status, social_age
from horatio.boon_harpy import Keeper
from horatio.models import Boon, BoonEvent, Character, Troupe, User
from horatio.sheets import conflict, sheet_rows

GALLANT = "Gallant"
SOCIAL_NOBILITY = "Social Nobility"
CAMARILLA = "Camarilla"
# Great boon-debts (p. 402): "such as a blood boon or a life boon".
GREAT = ("blood", "life")
# How a boon repaid is settled (horatio.boons.SETTLED).
REPAID = "called_in"
ANSWERS = ("gallant_given", "gallant_declined")
# Why Gallant is offered, as the ledger says it.
REASONS = {
    "nobility": "its creditor has Social Nobility (p. 405)",
    "great": "a great boon repaid to someone of significance (p. 402)",
}


@dataclass(frozen=True)
class Offer:
    """Gallant offered for a repaid boon's debtor: why, and the two characters."""

    debtor: Character
    creditor: Character
    # "nobility", "great", or both.
    reasons: tuple[str, ...]

    @property
    def nobility(self) -> bool:
        return "nobility" in self.reasons


def has_social_nobility(db: Session, character: Character) -> bool:
    return any(
        r.category.key == "merits" and r.definition.name == SOCIAL_NOBILITY
        for r in sheet_rows(db, character)
    )


def of_significance(db: Session, character: Character) -> bool:
    """Of significance in the Camarilla (p. 402): Camarilla, holding an active title,
    or an Elder by social age."""
    if sect_status.sect_of(db, character) != CAMARILLA:
        return False
    if sect_status.active_titles(db, character):
        return True
    return social_age.standings(db, [character.id])[character.id].age == "Elder"


def answered(db: Session, boon: Boon) -> bool:
    """Whether the offer made when the boon was last settled has had its answer."""
    lines = list(
        db.scalars(
            select(BoonEvent.kind)
            .where(BoonEvent.boon_id == boon.id)
            .order_by(BoonEvent.created_at, BoonEvent.id)
        )
    )
    last_settled = max((i for i, k in enumerate(lines) if k == "settled"), default=-1)
    return any(k in ANSWERS for k in lines[last_settled + 1 :])


def offer(db: Session, boon: Boon) -> Offer | None:
    """Gallant offered for the boon's debtor, if it is: a boon repaid by a Camarilla
    character to a character with Social Nobility, or a great boon to someone of
    significance, and not answered yet."""
    if boon.state != "settled" or boon.settled_how != REPAID:
        return None
    if boon.debtor_id is None or boon.creditor_id is None:
        return None
    debtor = db.get(Character, boon.debtor_id)
    creditor = db.get(Character, boon.creditor_id)
    if debtor is None or creditor is None or debtor.status == "retired":
        return None
    if sect_status.sect_of(db, debtor) != CAMARILLA:
        return None
    reasons: list[str] = []
    if has_social_nobility(db, creditor):
        reasons.append("nobility")
    if boon.kind in GREAT and of_significance(db, creditor):
        reasons.append("great")
    if not reasons or answered(db, boon):
        return None
    return Offer(debtor, creditor, tuple(reasons))


def keeper_answers(keeper: Keeper | None) -> bool:
    """Whoever may settle boons in the ledger answers any offer: its running staff
    (None, or a staff `Keeper`), or a Harpy or Lesser Harpy who may edit it."""
    return keeper is None or "edit" in keeper.can


def player_answers(troupe: Troupe, found: Offer, user: User) -> bool:
    """The creditor's player answers a Social Nobility offer, where the troupe shows
    creditors their boons and lets players keep their own status."""
    return (
        found.nobility
        and found.creditor.kind == "pc"
        and found.creditor.player_id == user.id
        and troupe.boon_players_see == "owed"
        and sect_status.setting_of(troupe) == "players"
    )


def story(boon: Boon, found: Offer) -> str:
    kind = boons.KINDS[boon.kind]
    why = " and ".join(REASONS[r] for r in found.reasons)
    return f"Repaid a {kind} boon to {found.creditor.name}: {why}."


def give(
    db: Session,
    user: User,
    troupe: Troupe,
    boon: Boon,
    found: Offer,
    acting: sect_status.Acting,
    note: str = "",
    as_character: Character | None = None,
) -> None:
    """Give the debtor Gallant, with the creditor as its patron, and log it on the
    boon. The caller has checked who may (`keeper_answers`, `player_answers`), and
    says as whom: "staff" for staff and the Harpy, as for a Boonbreaker (#717);
    "player" for the creditor's player."""
    debtor, creditor = found.debtor, found.creditor
    standing = sect_status.standing(db, debtor)
    if len(standing.fleeting) >= standing.fleeting_cap > 0:
        raise conflict(
            f"{debtor.name} holds as much fleeting status as they can"
            f" ({standing.fleeting_cap}). Their player or staff can give one up first;"
            " the offer stays open until then."
        )
    patron = next((c for c in sect_status.patron_choices(db, debtor) if c.id == creditor.id), None)
    sect_status.add(
        db,
        user,
        debtor,
        troupe,
        name=GALLANT,
        patron_id=patron.id if patron is not None else None,
        patron_text="" if patron is not None else creditor.name,
        story=story(boon, found),
        reason=note.strip() or f"Repaid a boon to {creditor.name}.",
        acting=acting,
    )
    answer(db, user, boon, found, "gallant_given", note, as_character)


def decline(
    db: Session,
    user: User,
    boon: Boon,
    found: Offer,
    note: str = "",
    as_character: Character | None = None,
) -> None:
    """No Gallant this time: the offer is answered, and the boon's log says so."""
    answer(db, user, boon, found, "gallant_declined", note, as_character)


def answer(
    db: Session,
    user: User,
    boon: Boon,
    found: Offer,
    kind: str,
    note: str,
    as_character: Character | None,
) -> None:
    note = note.strip()
    given = kind == "gallant_given"
    boons.event(
        db,
        user,
        boon,
        kind,
        note,
        {"gallant": ("Offered", f"Given to {found.debtor.name}" if given else "Not given")},
        as_character,
    )
    boons.log(db, user, f"boon.{kind}", boon, reason=note)
    db.flush()
