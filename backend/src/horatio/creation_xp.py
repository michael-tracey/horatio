"""Merits and flaws taken in creation, in XP, as the book has it (MET: VTM p. 85,
Steps Eight and Nine; p. 106; issue #657).

A merit is bought with the character's initial XP: the troupe's starting XP, or the
rule set's. A flaw adds its points to it, at most 7 XP from flaws in all (the troupe's
budget for flaws, where it sets one); flaws past that need the Storyteller's OK and
add nothing (p. 85, the `flaws/past-limit` check). The merits' budget of points stays
their cap, the clan's rarity and bloodline merits within it (p. 235), and those cost
XP as any merit does. Ghouls the same: the ghoul pages change which merits a ghoul may
take, not how they are paid for, and a ghoul pays for its domitor's rarity and
bloodline merits (p. 296). The rest of the initial XP is spent once creation is
finished (Step Nine).

Merits and flaws stay creation picks, so their budgets, the clan's merits and
reconciliation work as they did. What each costs or gives is a line of its own in the
XP history, of the kind "creation", naming the trait, one for each change. `sync`
brings those lines into line with the picks after any change to a sheet in creation
(horatio.sheets.checked, finishing creation, a ghoul's domitor, a troupe's house
rules or setting changing). Taking one back refunds its XP, or takes back what a flaw
gave. Until a home troupe has accepted the character, a merit is priced by the rules
as they stand (a Path merit costs its own clan less, pp. 254-259); in creation
reopened after one has (horatio.reconciliation), only the picks that change are.

Flaws give XP in the order they were taken, the first filling the budget first; one
taken off makes room for the next, whose line says so.

A change that would leave the character with less than nothing is refused, saying
why: a merit it can't pay for, or a flaw taken off whose XP is spent already (undo
spends first).

Characters finished before this (`Character.merits_flaws_xp` false) keep their
numbers: their merits and flaws came from free budgets, and nothing here touches them.
NPCs spend no XP; what an NPC's merits and flaws would come to as a player
character's is `due`, for its tally (horatio.npcs) and for giving it to a player
(horatio.npc_gifts).
"""

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio.creation import pools_for
from horatio.models import Character, TraitCategory, TraitDefinition, XpEntry
from horatio.rules.model import SheetTrait, TroupeRules
from horatio.rules.pricing import PricingError, trait_cost
from horatio.sheets import SheetRow, conflict, ever_accepted, rules_for, sheet_rows, xp_balance

CREATION = "creation"
CATEGORIES = ("merits", "flaws")
# Where the book says so.
PAGE = "p. 106"
FLAWS_PAGE = "p. 85"

# A trait, as the XP history names it: (definition, detail).
Key = tuple[uuid.UUID, str]


@dataclass
class Held:
    """What the XP history has for one trait's creation lines: the points it holds
    by them, and the XP they come to (negative for a merit)."""

    category: str
    name: str
    points: int = 0
    xp: int = 0


@dataclass
class Line:
    """One trait's change in XP: what it held and comes to, and what it now does."""

    category: str
    name: str
    detail: str
    definition_id: uuid.UUID
    before: int
    after: int
    # XP gained (negative for XP spent).
    amount: int
    # What the trait comes to in all now, and the flaws' budget, for the line's reason.
    worth: int
    budget: int

    @property
    def label(self) -> str:
        return f"{self.name}: {self.detail}" if self.detail else self.name

    @property
    def reason(self) -> str:
        if self.before == self.after:
            if self.category == "merits":
                return f"{self.label}: repriced in creation, now {-self.worth} XP"
            return (
                f"{self.label}: now gives {self.worth} XP, flaws giving at most"
                f" {self.budget} ({FLAWS_PAGE})"
            )
        verb = "taken back" if self.after < self.before else "taken"
        said = f"{self.label} {self.before} → {self.after}, {verb} in creation"
        if self.category == "flaws" and self.after and self.worth < self.after:
            said += (
                f": {self.worth} XP of its {points(self.after)}, flaws giving at most"
                f" {self.budget} ({FLAWS_PAGE})"
            )
        return said


def points(n: int) -> str:
    return f"{n} point" if n == 1 else f"{n} points"


def keeps_xp(character: Character) -> bool:
    """Whether the character's merits and flaws from creation cost and give XP."""
    return character.kind == "pc" and character.merits_flaws_xp


def merit_cost(rules: TroupeRules, sheet: Sequence[SheetTrait], row: SheetRow) -> int:
    """What a merit costs at its pick's points, bought outright; its points where the
    rules can't price it."""
    pick = row.trait.creation_pick or 0
    try:
        bought = SheetTrait(row.category.key, row.definition.name, pick, 0, row.trait.detail)
        return trait_cost(rules, sheet, bought).cost
    except PricingError:
        return pick


def flaw_budget(rules: TroupeRules, rows: Sequence[SheetRow]) -> int:
    """The most XP flaws give: the creation budget for flaws (p. 85)."""
    pool = pools_for(rules.creation_rules(), rows).get(("flaws", 0))
    return pool.allowed if pool is not None and pool.kind == "points" else 0


def held(db: Session, character: Character) -> dict[Key, Held]:
    """What the character's creation lines come to, trait by trait."""
    found = db.execute(
        select(
            XpEntry.trait_definition_id,
            XpEntry.detail,
            TraitCategory.key,
            TraitDefinition.name,
            func.sum(XpEntry.to_rating - XpEntry.from_rating),
            func.sum(XpEntry.amount),
        )
        .join(TraitDefinition, XpEntry.trait_definition_id == TraitDefinition.id)
        .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
        .where(XpEntry.character_id == character.id, XpEntry.kind == CREATION)
        .group_by(
            XpEntry.trait_definition_id, XpEntry.detail, TraitCategory.key, TraitDefinition.name
        )
    )
    # A creation line names its trait, and its detail where it has one (`write`).
    return {
        (definition, detail or ""): Held(category, name, int(points or 0), int(xp or 0))
        for definition, detail, category, name, points, xp in found
        if definition is not None
    }


def due(db: Session, character: Character, *, reprice: bool = True) -> list[Line]:
    """The lines that bring the character's creation lines into line with its merit
    and flaw picks. With `reprice` false, only the picks that changed are priced."""
    rules = rules_for(db, character)
    rows = sheet_rows(db, character)
    sheet = [r.as_rules_trait() for r in rows]
    recorded = held(db, character)
    budget = flaw_budget(rules, rows)

    def key(row: SheetRow) -> Key:
        return (row.definition.id, row.trait.detail)

    picked = [r for r in rows if r.category.key in CATEGORIES and (r.trait.creation_pick or 0) > 0]
    target: dict[Key, tuple[SheetRow, int]] = {}
    for row in picked:
        if row.category.key != "merits":
            continue
        was = recorded.get(key(row))
        kept = not reprice and was is not None and was.points == row.trait.creation_pick
        target[key(row)] = (row, was.xp if kept and was else -merit_cost(rules, sheet, row))
    # Flaws in the order taken (ids follow it), each giving what is left of the budget.
    flaws = sorted((r for r in picked if r.category.key == "flaws"), key=lambda r: r.trait.id)
    room = budget
    if not reprice:
        for row in flaws:
            was = recorded.get(key(row))
            if was is not None and was.points == row.trait.creation_pick:
                target[key(row)] = (row, was.xp)
                room -= was.xp
    for row in flaws:
        if key(row) in target:
            continue
        gives = min(row.trait.creation_pick or 0, max(0, room))
        room -= gives
        target[key(row)] = (row, gives)

    lines: list[Line] = []
    for found, (row, worth) in target.items():
        was = recorded.get(found, Held(row.category.key, row.definition.name))
        after = row.trait.creation_pick or 0
        if was.points == after and was.xp == worth:
            continue
        lines.append(
            Line(
                row.category.key,
                row.definition.name,
                row.trait.detail,
                row.definition.id,
                was.points,
                after,
                worth - was.xp,
                worth,
                budget,
            )
        )
    # Those taken back come first: their XP back, or taken back.
    gone = [
        Line(was.category, was.name, detail, definition, was.points, 0, -was.xp, 0, budget)
        for (definition, detail), was in recorded.items()
        if (definition, detail) not in target and (was.points or was.xp)
    ]
    return gone + lines


def write(db: Session, character: Character, lines: Iterable[Line], actor: uuid.UUID) -> None:
    for line in lines:
        db.add(
            XpEntry(
                character_id=character.id,
                kind=CREATION,
                amount=line.amount,
                reason=line.reason,
                entered_by=actor,
                trait_definition_id=line.definition_id,
                detail=line.detail or None,
                from_rating=line.before,
                to_rating=line.after,
            )
        )
    db.flush()


def sync(db: Session, character: Character, actor: uuid.UUID | None = None) -> list[Line]:
    """Bring a character in creation's creation lines into line with its merit and flaw
    picks, as `actor` (its player, if None). The lines written."""
    if not keeps_xp(character) or character.creation_completed_at is not None:
        return []
    lines = due(db, character, reprice=not ever_accepted(db, character))
    write(db, character, lines, actor or character.player_id)
    return lines


def resync(db: Session, characters: Iterable[Character]) -> None:
    """`sync` for each, after their rules change: a troupe's flaws budget, say."""
    for character in characters:
        sync(db, character)


def xp_text(n: int) -> str:
    return "none" if n <= 0 else f"only {n} XP"


def short(db: Session, character: Character, lines: Sequence[Line]) -> str | None:
    """Why the lines just written leave the character less XP than nothing, if they
    lowered its XP and do: a merit it can't pay for, or a flaw taken off whose XP it has
    spent."""
    change = sum(line.amount for line in lines)
    if change >= 0:
        return None
    after = xp_balance(db, character)
    if after >= 0:
        return None
    left = after - change
    back = [line for line in lines if line.category == "flaws" and line.amount < 0]
    costs = [line for line in lines if line.category == "merits" and line.amount < 0]
    if back and not costs:
        names = " and ".join(line.label for line in back)
        taken = -sum(line.amount for line in back)
        gave = "it gave" if len(back) == 1 else "they gave"
        return (
            f"Taking {names} off takes back the {taken} XP {gave}, and {xp_text(left)}"
            " is unspent. Undo some spends first."
        )
    return f"That costs {-change} XP, and {xp_text(left)} is left ({PAGE})."


def settle(db: Session, character: Character, actor: uuid.UUID | None = None) -> str | None:
    """`sync`, and why the change is refused if it leaves less XP than nothing."""
    return short(db, character, sync(db, character, actor))


def refuse(message: str | None) -> None:
    if message is not None:
        raise conflict(message)


@dataclass(frozen=True)
class Totals:
    """A character in creation's XP, the book's way: what it starts with, what its
    merits cost and its flaws gave, and what is left (pp. 85, 106)."""

    starting: int
    merits: int
    flaws: int
    flaw_budget: int
    left: int


def totals(db: Session, character: Character) -> Totals | None:
    """The character's XP from merits and flaws taken in creation, while it is in
    creation; None once finished (its XP is then spent from the sheet), for one whose
    merits and flaws came from free budgets, and for an NPC."""
    if not keeps_xp(character) or character.creation_completed_at is not None:
        return None
    recorded = held(db, character).values()
    merits = -sum(h.xp for h in recorded if h.category == "merits")
    flaws = sum(h.xp for h in recorded if h.category == "flaws")
    left = xp_balance(db, character)
    rows = sheet_rows(db, character)
    budget = flaw_budget(rules_for(db, character), rows)
    return Totals(left + merits - flaws, merits, flaws, budget, left)


def finish_refusal(db: Session, character: Character) -> str | None:
    """Why creation can't finish for the XP: merits that cost more than it has."""
    if not keeps_xp(character):
        return None
    balance = xp_balance(db, character)
    if balance >= 0:
        return None
    return (
        f"The merits cost {-balance} XP more than {character.name} has. Take some off,"
        f" or take a flaw, first ({PAGE})."
    )
