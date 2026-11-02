"""A ghoul's Embrace (MET: VTM pp. 297–299): a ghoul PC is Embraced in play, and its
player chooses whether it dies in the attempt or becomes a vampire.

The home troupe's lead storyteller, storytellers and assistant storytellers run it
from the ghoul's sheet. Dying retires the character, with a note in its log.
Becoming a vampire converts the sheet, step by step, in one go:

1. Clan and rarity. If the sire was the ghoul's domitor, its clan and rarity
   merits are already right. If not, they are stripped and their XP refunded, an
   exception to the rule that such merits are never refunded, and the new vampire
   buys the ones its sire's clan and rarity need in the setting. Over the 7-point
   merit limit, merits are stripped until it is within it; if it cannot be, the
   character dies in the Embrace.
2. Generation: one weaker than the sire, bought at a background's price (1 × the
   level a dot as a Neonate, 2 × at any other Generation), an exception to the
   rule that Generation is never bought in play. A weaker Generation than the
   background gives comes with the Lesser Generation flaw (p. 263), free.
3. Disciplines: every ghoul dot is lost. The new vampire has 2 dots, free, in one
   in-clan discipline and 1 in each of the others (a Caitiff first chooses its
   three, p. 246).
4. Skills and backgrounds bought in play are repriced at the new Generation, each
   difference a `reprice` line naming the purchase.
5. Finishing touches: the vampire's starting traits it lacks (Humanity), and a
   note of the clan weakness (a Malkavian's derangement, say). Blood, Blood a
   turn and the attribute bonus follow from Generation. The Storyteller may let
   merits and flaws change: a merit taken off refunds its XP, a flaw taken off
   takes back the XP it gave.
6. XP debt. The refunds and saved XP pay the costs first; what they cannot pay is
   XP debt (horatio.xp_debt), which all the XP earned after pays off. What is left
   over can buy back up to 2 lost discipline dots, at what they now cost, with no
   teacher; the Storyteller may let them be bought into debt, now or later from
   the cart.

Horatio gives merits and flaws at creation from a budget of points where the book
spends initial XP on them (p. 106), so a merit or flaw taken off here is worth its
points from that budget as well as the XP it cost or gave.

The character is then a vampire, by the vampire rule set, with no domitor. Every
step is in its log, the sheet as it now stands is the one its home troupe has
approved, and the Embrace is kept with what each step did.
"""

import uuid
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio import audit, clan_merits, notifications, repricing, sheets, xp_debt
from horatio.models import (
    AppliedHouseTrait,
    Character,
    CharacterTrait,
    Embrace,
    HouseTrait,
    SheetVersion,
    TraitCategory,
    TraitDefinition,
    User,
    XpEntry,
)
from horatio.rules.model import SheetTrait, TroupeRules
from horatio.rules.pricing import PricingError, fixed_rating, points, purchase_cost
from horatio.rules.splats import DOMITOR_IN_CLAN, SPLATS
from horatio.rules.store import read_troupe_rules
from horatio.sheets import conflict, unprocessable

VAMPIRE = "vampire"
GENERATION = "Generation"
# The merits that pay for a clan's rarity in the setting (p. 237), and those that
# make a vampire of a bloodline.
RARITY = ("Uncommon Clan", "Rare Clan", "Restricted Clan")
BLOODLINE = "Bloodline:"
LESSER = ("Lesser Generation 1", "Lesser Generation 2")
THIN_BLOODED = "Thin Blooded"
# Lost discipline dots that can be bought back (p. 298).
BUY_BACK_DOTS = 2

# Each generation a character can be Embraced into, by its number: the dots of
# Generation it buys, and the flaw that makes it weaker than they give (pp. 100–101,
# 263). A weaker one than 13th is thin-blooded, which this does not make.
GENERATIONS: dict[int, tuple[int, str | None]] = {
    6: (5, None),
    7: (4, None),
    8: (3, None),
    9: (2, None),
    10: (2, "Lesser Generation 1"),
    11: (1, None),
    12: (1, "Lesser Generation 1"),
    13: (1, "Lesser Generation 2"),
}
STRONGEST, WEAKEST = min(GENERATIONS), max(GENERATIONS)
# By dots of Generation (p. 101): the title, Blood pool, Blood a turn and attribute bonus.
CHART: dict[int, tuple[str, int, int, int]] = {
    1: ("Neonate", 10, 1, 1),
    2: ("Ancilla", 12, 2, 2),
    3: ("Pretender Elder", 15, 3, 3),
    4: ("Master Elder", 20, 4, 4),
    5: ("Luminary Elder", 30, 5, 5),
}


def ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def generation_number(dots: int, flaws: Sequence[str]) -> int | None:
    """A vampire's generation from its sheet: its Generation dots, less what a Lesser
    Generation flaw takes away (p. 263). None for one with no dots, or thin-blooded."""
    if THIN_BLOODED in flaws or dots not in CHART:
        return None
    number = {1: 11, 2: 9, 3: 8, 4: 7, 5: 6}[dots]
    if "Lesser Generation 2" in flaws and dots == 1:
        return 13
    if "Lesser Generation 1" in flaws and dots <= 2:
        return number + 1
    return number


def generation_cost(dots: int) -> int:
    """What Generation costs bought at the Embrace, as any other background (p. 298):
    the new level × 1 a dot as a Neonate, × 2 at any other Generation."""
    rate = 1 if dots == 1 else 2
    return rate * dots * (dots + 1) // 2


# --- what staff choose ------------------------------------------------------------


@dataclass(frozen=True)
class SireIn:
    """A vampire PC or NPC in Horatio, or one known by name, clan and generation."""

    character_id: uuid.UUID | None = None
    name: str = ""
    clan: str = ""
    generation: int | None = None


@dataclass(frozen=True)
class Named:
    category: str
    name: str
    detail: str = ""


@dataclass(frozen=True)
class Dots:
    """A lost discipline, bought back to `rating`."""

    name: str
    rating: int


@dataclass(frozen=True)
class Choices:
    sire: SireIn
    # Whether the sire was the domitor; None works it out where both are linked, and
    # otherwise goes by their names.
    sire_is_domitor: bool | None = None
    # The merits the sire's clan and rarity need; None suggests them.
    clan_merits: tuple[str, ...] | None = None
    # The in-clan discipline with 2 dots; None takes the first.
    two_dots: str | None = None
    # A Caitiff's three in-clan disciplines.
    caitiff_three: tuple[str, ...] = ()
    # Merits and flaws taken off: to come within the merit limit, or as the
    # Storyteller lets them change.
    remove: tuple[Named, ...] = ()
    buy_back: tuple[Dots, ...] = ()
    buy_back_into_debt: bool = False
    weakness: str = ""


# --- what it does -------------------------------------------------------------------


@dataclass
class Line:
    """One thing a step does, and its XP: positive for XP back, negative for XP spent."""

    text: str
    xp: int = 0


@dataclass
class Step:
    key: str
    title: str
    lines: list[Line] = field(default_factory=list[Line])

    @property
    def xp(self) -> int:
        return sum(line.xp for line in self.lines)

    def add(self, text: str, xp: int = 0) -> None:
        self.lines.append(Line(text, xp))


@dataclass(frozen=True)
class Rated:
    name: str
    rating: int
    detail: str = ""


@dataclass(frozen=True)
class Removable:
    """A merit or flaw that could come off, and the XP that would mean."""

    category: str
    name: str
    detail: str
    rating: int
    xp: int


@dataclass
class Plan:
    """What the Embrace would do to the sheet, or did."""

    sire_id: uuid.UUID | None = None
    sire_name: str = ""
    sire_clan: str = ""
    sire_generation: int | None = None
    sire_is_domitor: bool = False
    generation: int | None = None
    generation_dots: int = 0
    lesser_flaw: str | None = None
    title: str = ""
    blood: int = 0
    blood_per_turn: int = 0
    attribute_bonus: int = 0
    clan: str = ""
    caitiff: bool = False
    in_clan: list[str] = field(default_factory=list[str])
    two_dots: str | None = None
    # The merits a clan's rarity or bloodline can need, to choose from.
    clan_merit_choices: list[str] = field(default_factory=list[str])
    clan_merits: list[str] = field(default_factory=list[str])
    merit_points: int = 0
    merit_limit: int = 7
    # The character cannot come within the merit limit, and dies in the Embrace.
    dies: bool = False
    removable: list[Removable] = field(default_factory=list[Removable])
    lost: list[Rated] = field(default_factory=list[Rated])
    disciplines: list[Rated] = field(default_factory=list[Rated])
    bought_back: list[Rated] = field(default_factory=list[Rated])
    buy_back_into_debt: bool = False
    weakness: str = ""
    steps: list[Step] = field(default_factory=list[Step])
    balance_before: int = 0
    balance_after: int = 0
    debt: int = 0
    # What the sheet then holds against the rules, not stopping it.
    notes: list[str] = field(default_factory=list[str])
    refused: str | None = None

    def step(self, key: str, title: str) -> Step:
        found = Step(key, title)
        self.steps.append(found)
        return found

    def as_dict(self) -> dict[str, Any]:
        found = asdict(self)
        for step, data in zip(self.steps, found["steps"], strict=True):
            data["xp"] = step.xp
        return found

    def as_outcome(self) -> dict[str, Any]:
        found = self.as_dict()
        for key in ("refused", "removable", "clan_merit_choices", "dies"):
            del found[key]
        found["sire_id"] = str(self.sire_id) if self.sire_id else None
        return found


# --- who may be Embraced, and by whom -------------------------------------------------


def can_embrace(db: Session, character: Character) -> str | None:
    """Why this character cannot be Embraced here, if it cannot."""
    if not SPLATS[character.splat].has_domitor:
        return "Only a ghoul is Embraced this way."
    if character.kind != "pc":
        return "An NPC is its staff's to build as they like; make a vampire NPC instead."
    if character.status == "retired":
        return "This character is retired."
    if character.home_troupe_id is None:
        return "A ghoul is Embraced on the sheet its home troupe has accepted."
    if character.creation_completed_at is None:
        return "Its player has not finished creating it."
    if sheets.pending_approvals(db, character):
        return "Decide what is waiting on the storytellers first."
    return None


@dataclass(frozen=True)
class Sire:
    character: Character | None
    name: str
    clan: str
    generation: int


def vampire_rules(db: Session, character: Character) -> TroupeRules:
    return read_troupe_rules(db, VAMPIRE, sheets.rules_troupe(character))


def sire_generation(db: Session, vampire: Character) -> int | None:
    """A vampire's generation as its sheet has it."""
    return generation_of(sheets.sheet_rows(db, vampire))


def generation_of(rows: Sequence[sheets.SheetRow]) -> int | None:
    """The generation sheet rows give: their Generation dots and any Lesser
    Generation flaw. None without a dot, or thin-blooded."""
    dots = next(
        (
            r.trait.rating or 0
            for r in rows
            if r.category.key == "backgrounds" and r.definition.name == GENERATION
        ),
        0,
    )
    flaws = [r.definition.name for r in rows if r.category.key == "flaws"]
    return generation_number(dots, flaws)


def sire_of(db: Session, ghoul: Character, given: SireIn) -> Sire:
    """The sire as staff gave it: refused unless the childe can be one generation
    weaker, between 6th and 13th."""
    if given.character_id is not None:
        vampire = db.get(Character, given.character_id)
        if vampire is None:
            raise unprocessable("There is no such vampire.")
        if vampire.id == ghoul.id or vampire.splat != VAMPIRE:
            raise unprocessable(f"{vampire.name} is not a vampire.")
        clan = next(
            (r.definition.name for r in sheets.sheet_rows(db, vampire) if r.category.key == "clan"),
            None,
        )
        if clan is None:
            raise conflict(f"{vampire.name} has no clan on its sheet.")
        generation = sire_generation(db, vampire)
        if generation is None:
            raise conflict(
                f"{vampire.name}'s sheet gives no generation to be one weaker than;"
                " name the sire instead, with its generation."
            )
        sire = Sire(vampire, vampire.name, clan, generation)
    else:
        name = given.name.strip()
        if not name:
            raise unprocessable("Choose the sire, or name it.")
        if not given.clan:
            raise unprocessable("Choose the sire's clan and bloodline.")
        if ("clan", given.clan) not in vampire_rules(db, ghoul).rule_set.traits:
            raise unprocessable(f"{given.clan} is not a clan or bloodline.")
        if given.generation is None:
            raise unprocessable("Give the sire's generation.")
        sire = Sire(None, name, given.clan, given.generation)
    childe = sire.generation + 1
    if childe < STRONGEST:
        raise conflict(
            f"A sire of the {ordinal(sire.generation)} generation would make a childe"
            f" stronger than the {ordinal(STRONGEST)}, the strongest a character can be."
        )
    if childe > WEAKEST:
        raise conflict(
            f"A sire of the {ordinal(sire.generation)} generation makes a thin-blooded childe,"
            f" weaker than the {ordinal(WEAKEST)}: staff build that by hand."
        )
    return sire


def is_domitor(ghoul: Character, sire: Sire, said: bool | None) -> bool:
    if sire.character is not None and ghoul.domitor_id is not None:
        return sire.character.id == ghoul.domitor_id
    if said is not None:
        return said
    domitor = ghoul.domitor_name.strip().casefold()
    return bool(domitor) and domitor == sire.name.strip().casefold()


def clan_merit_names(rules: TroupeRules) -> list[str]:
    """The merits that pay for a clan's rarity or make a vampire of a bloodline."""
    return [
        name
        for category, name in rules.rule_set.traits
        if category == "merits" and (name in RARITY or name.startswith(BLOODLINE))
    ]


def is_clan_merit(name: str) -> bool:
    return name in RARITY or name.startswith(BLOODLINE)


def suggested_clan_merits(rules: TroupeRules, clan: str, default: str | None = None) -> list[str]:
    """The bloodline merit a bloodline's clan trait points to, but for the bloodline
    the setting plays as its clan's `default`, which needs none (p. 238); the rarity
    is the setting's, for staff to choose."""
    if ":" not in clan or clan == default:
        return []
    merit = f"{BLOODLINE} {clan.split(':', 1)[1].strip()}"
    return [merit] if ("merits", merit) in rules.rule_set.traits else []


# --- the XP history ---------------------------------------------------------------------


def net_spent(db: Session, character: Character, category: str, name: str, detail: str) -> int:
    """The XP spent on a trait, net of what came back (negative for a flaw that paid),
    by its name: the ghoul's purchases and the vampire's are of different rule sets."""
    return -(
        db.scalar(
            select(func.coalesce(func.sum(XpEntry.amount), 0))
            .join(TraitDefinition, XpEntry.trait_definition_id == TraitDefinition.id)
            .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
            .where(
                XpEntry.character_id == character.id,
                XpEntry.kind.in_(("purchase", "reprice")),
                TraitCategory.key == category,
                TraitDefinition.name == name,
                func.coalesce(XpEntry.detail, "") == detail,
            )
        )
        or 0
    )


def worth(db: Session, character: Character, row: sheets.SheetRow) -> int:
    """What taking a merit off gives back, or a flaw off takes back: the XP it cost
    or gave, and the points it took of the creation budget."""
    spent = net_spent(db, character, row.category.key, row.definition.name, row.trait.detail)
    budget = row.trait.creation_pick or 0
    if row.category.key == "flaws":
        return max(0, -spent) + budget
    return max(0, spent) + budget


def entered_play(db: Session, character: Character) -> uuid.UUID | None:
    """The first sheet a home troupe approved: what was bought after it was bought in
    play. Ids are UUID v7, so they follow the order things were written in."""
    return db.scalar(
        select(SheetVersion.id)
        .where(SheetVersion.character_id == character.id)
        .order_by(SheetVersion.id)
        .limit(1)
    )


def refund(
    db: Session,
    actor: User,
    character: Character,
    row: sheets.SheetRow,
    amount: int,
    why: str,
) -> None:
    """Take a merit or flaw off, `amount` XP back (negative: taken back)."""
    rating = row.trait.rating or 0
    if amount:
        db.add(
            XpEntry(
                character_id=character.id,
                kind="purchase",
                amount=amount,
                reason=f"{label(row)} {rating} → 0 ({why})",
                entered_by=actor.id,
                trait_definition_id=row.definition.id,
                detail=row.trait.detail or None,
                from_rating=rating,
                to_rating=0,
                cost_basis={"refund": "embrace"},
            )
        )
    db.delete(row.trait)
    db.flush()


def buy(
    db: Session,
    actor: User,
    character: Character,
    category: str,
    name: str,
    detail: str,
    rating: int,
    cost: int,
    why: str,
    basis: dict[str, Any],
    *,
    free: int = 0,
) -> None:
    """Add a trait at `rating`, `free` of its dots free, for `cost` XP."""
    definition, _ = sheets.find_definition(db, character, category, name)
    db.add(
        CharacterTrait(
            character_id=character.id,
            trait_definition_id=definition.id,
            rating=rating,
            free_rating=free,
            detail=detail,
        )
    )
    db.add(
        XpEntry(
            character_id=character.id,
            kind="purchase",
            amount=-cost,
            reason=f"{name}: {detail} 0 → {rating} ({why})"
            if detail
            else f"{name} 0 → {rating} ({why})",
            entered_by=actor.id,
            trait_definition_id=definition.id,
            detail=detail or None,
            from_rating=0,
            to_rating=rating,
            cost_basis=basis,
        )
    )
    db.flush()


def label(row: sheets.SheetRow) -> str:
    return f"{row.definition.name}: {row.trait.detail}" if row.trait.detail else row.definition.name


def plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


# --- making the change --------------------------------------------------------------------


def become_vampire(db: Session, character: Character, sire: Sire) -> None:
    """Switch the sheet to the vampire rule set: the same traits, held by its
    definitions, with the sire's clan for the domitor's, and no domitor. A house merit
    or flaw goes to the troupe's vampire one of the same name."""
    rows = sheets.sheet_rows(db, character)
    character.splat = VAMPIRE
    character.domitor_id = None
    character.domitor_name = ""
    db.flush()
    for row in rows:
        if row.category.key == "clan":
            db.delete(row.trait)
            continue
        try:
            definition, _ = sheets.find_definition(
                db, character, row.category.key, row.definition.name
            )
        except HTTPException as error:
            raise conflict(
                f"{label(row)} has no vampire trait of that name: take it off first."
            ) from error
        if row.definition.troupe_id is not None and definition.troupe_id is None:
            raise conflict(f"★ {label(row)} is the troupe's ghoul one: take it off first.")
        row.trait.trait_definition_id = definition.id
        applied = db.scalar(
            select(AppliedHouseTrait).where(AppliedHouseTrait.character_trait_id == row.trait.id)
        )
        if applied is not None:
            twin = db.scalar(
                select(HouseTrait.id).where(
                    HouseTrait.troupe_id == definition.troupe_id,
                    HouseTrait.splat == VAMPIRE,
                    HouseTrait.category == row.category.key,
                    HouseTrait.name == row.definition.name,
                )
            )
            if twin is None:
                raise conflict(f"★ {label(row)} is the troupe's ghoul one: take it off first.")
            applied.house_trait_id = twin
    clan, _ = sheets.find_definition(db, character, "clan", sire.clan)
    db.add(CharacterTrait(character_id=character.id, trait_definition_id=clan.id))
    db.flush()
    held = {(r.category.key, r.definition.name) for r in sheets.sheet_rows(db, character)}
    for starting in sheets.rules_for(db, character).starting_traits():
        if (starting.category, starting.name) in held:
            continue
        definition, _ = sheets.find_definition(db, character, starting.category, starting.name)
        db.add(
            CharacterTrait(
                character_id=character.id,
                trait_definition_id=definition.id,
                rating=starting.rating,
                free_rating=starting.rating or 0,
            )
        )
    db.flush()


@dataclass(frozen=True)
class Purchase:
    """A skill or background bought in play, priced by the ghoul's rules."""

    entry: XpEntry
    category: str
    name: str
    trait: SheetTrait
    was: int


def bought_in_play(db: Session, character: Character) -> list[Purchase]:
    """The skills and backgrounds bought since the ghoul entered play, each with what
    the ghoul's rules price it at (p. 298: what was bought at creation stays)."""
    started = entered_play(db, character)
    if started is None:
        return []
    rules = sheets.rules_for(db, character)
    rows = sheets.sheet_rows(db, character)
    sheet = [r.as_rules_trait() for r in rows]
    free = {r.key: r.trait.free_rating for r in rows}
    found: list[Purchase] = []
    for entry, name, category in db.execute(
        select(XpEntry, TraitDefinition.name, TraitCategory.key)
        .join(TraitDefinition, XpEntry.trait_definition_id == TraitDefinition.id)
        .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
        .where(
            XpEntry.character_id == character.id,
            XpEntry.kind == "purchase",
            XpEntry.id > started,
            TraitCategory.key.in_(("skills", "backgrounds")),
        )
        .order_by(XpEntry.id)
    ):
        if "scheme" not in (entry.cost_basis or {}):
            continue
        assert entry.from_rating is not None and entry.to_rating is not None
        detail = entry.detail or ""
        trait = SheetTrait(
            category=category,
            name=name,
            rating=entry.from_rating,
            free_rating=min(
                free.get((category, name, detail), 0), entry.from_rating, entry.to_rating
            ),
            detail=detail,
        )
        try:
            was = purchase_cost(rules, sheet, trait, entry.to_rating).cost
        except PricingError:
            continue
        found.append(Purchase(entry, category, name, trait, was))
    return found


def change(
    db: Session, staff: User | None, character: Character, choices: Choices, plan: Plan
) -> None:
    """Make the Embrace's changes, filling `plan` in as it goes. `staff` is None for a
    trial, whose history is taken back. The caller holds the character's lock, and
    takes the changes back if this raises."""
    actor = staff or db.get_one(User, character.player_id)
    run = Run(db, actor, character, choices, plan, sire_of(db, character, choices.sire))
    run.start()
    clan = run.strip_clan_merits()
    run.lose_disciplines()
    # What the ghoul's rules priced its skills and backgrounds at, before they go.
    purchases = bought_in_play(db, character)
    become_vampire(db, character, run.sire)
    run.buy_clan_merits(clan)
    run.buy_generation()
    run.starting_disciplines()
    run.reprice(purchases)
    run.finishing_touches()
    run.within_merit_limit()
    run.buy_back()
    run.judge()


@dataclass
class Run:
    """One Embrace being made: each step a method, in the order they are taken."""

    db: Session
    actor: User
    character: Character
    choices: Choices
    plan: Plan
    sire: Sire

    def rows(self) -> list[sheets.SheetRow]:
        return sheets.sheet_rows(self.db, self.character)

    def sheet(self) -> list[SheetTrait]:
        return [r.as_rules_trait() for r in self.rows()]

    @property
    def rules(self) -> TroupeRules:
        return sheets.rules_for(self.db, self.character)

    @property
    def balance(self) -> int:
        return sheets.xp_balance(self.db, self.character)

    def start(self) -> None:
        plan, sire = self.plan, self.sire
        plan.sire_id = sire.character.id if sire.character else None
        plan.sire_name, plan.sire_clan, plan.sire_generation = sire.name, sire.clan, sire.generation
        plan.sire_is_domitor = is_domitor(self.character, sire, self.choices.sire_is_domitor)
        plan.balance_before = self.balance
        plan.weakness = self.choices.weakness.strip()
        plan.buy_back_into_debt = self.choices.buy_back_into_debt
        rules = vampire_rules(self.db, self.character)
        plan.clan_merit_choices = clan_merit_names(rules)
        merits = rules.rule_set.categories.get("merits")
        plan.merit_limit = (merits.points_limit if merits else None) or 7
        plan.clan = sire.clan
        plan.caitiff = sire.clan == "Caitiff"

    def strip_clan_merits(self) -> Step:
        """1. The ghoul's clan and rarity merits go, refunded, unless the sire was its
        domitor."""
        step = self.plan.step("clan", "Clan and rarity")
        for row in self.rows():
            if row.category.key != "merits" or not is_clan_merit(row.definition.name):
                continue
            if self.plan.sire_is_domitor:
                step.add(f"{label(row)} stays: the sire was the domitor.")
                continue
            back = worth(self.db, self.character, row)
            step.add(f"{label(row)} stripped, its XP refunded", back)
            refund(
                self.db,
                self.actor,
                self.character,
                row,
                back,
                "the ghoul's, refunded at the Embrace",
            )
        return step

    def lose_disciplines(self) -> None:
        """3. The ghoul's discipline dots are lost, free as they were, with nothing back."""
        self.plan.lost = [
            Rated(r.definition.name, r.trait.rating or 0, r.trait.detail)
            for r in self.rows()
            if r.category.key == "disciplines" and (r.trait.rating or 0) > 0
        ]
        for row in self.rows():
            if row.category.key in ("disciplines", DOMITOR_IN_CLAN):
                self.db.delete(row.trait)
        self.db.flush()

    def default_bloodline(self) -> str | None:
        """The bloodline the character's setting plays as its sire's clan's default."""
        setting = clan_merits.setting_of(self.db, self.character)
        family = clan_merits.family_of(self.sire.clan)
        rule_set = vampire_rules(self.db, self.character).rule_set
        return clan_merits.default_bloodline(rule_set, family, setting)

    def buy_clan_merits(self, step: Step) -> None:
        """1, once a vampire: the merits its sire's clan and rarity need."""
        rules = self.rules
        wanted = (
            []
            if self.plan.sire_is_domitor
            else list(
                self.choices.clan_merits
                if self.choices.clan_merits is not None
                else suggested_clan_merits(rules, self.sire.clan, self.default_bloodline())
            )
        )
        held = {r.definition.name for r in self.rows()}
        for name in dict.fromkeys(wanted):
            if not is_clan_merit(name) or ("merits", name) not in rules.rule_set.traits:
                raise unprocessable(f"{name} is not a rarity or bloodline merit.")
            if name in held:
                continue
            sheet = self.sheet()
            value = fixed_rating(rules, sheet, "merits", name) or 1
            quote = purchase_cost(rules, sheet, SheetTrait("merits", name, 0), value)
            step.add(f"{name} bought for the sire's {self.sire.clan}", -quote.cost)
            buy(
                self.db,
                self.actor,
                self.character,
                "merits",
                name,
                "",
                value,
                quote.cost,
                "the sire's clan and rarity, at the Embrace",
                quote.rule.describe(),
            )
            self.plan.clan_merits.append(name)

    def buy_generation(self) -> None:
        """2. One generation weaker than the sire, at a background's price, and the
        Lesser Generation flaw, free, where the dots alone would make it stronger."""
        plan = self.plan
        generation = self.sire.generation + 1
        dots, flaw = GENERATIONS[generation]
        plan.generation, plan.generation_dots, plan.lesser_flaw = generation, dots, flaw
        plan.title, plan.blood, plan.blood_per_turn, plan.attribute_bonus = CHART[dots]
        step = plan.step("generation", "Generation")
        cost = generation_cost(dots)
        step.add(
            f"Generation {dots}, the {ordinal(generation)} generation: one weaker than the"
            f" {ordinal(self.sire.generation)}, at a background's price",
            -cost,
        )
        for row in self.rows():
            if row.category.key == "flaws" and row.definition.name in (*LESSER, THIN_BLOODED):
                self.db.delete(row.trait)
        self.db.flush()
        buy(
            self.db,
            self.actor,
            self.character,
            "backgrounds",
            GENERATION,
            "",
            dots,
            cost,
            f"the Embrace, {ordinal(generation)} generation",
            {"embrace": "Generation at a background's price", "rate": 1 if dots == 1 else 2},
        )
        if flaw is not None:
            value = self.rules.fixed_rating("flaws", flaw) or 1
            step.add(f"{flaw}, free: the {ordinal(generation)} generation")
            buy(
                self.db,
                self.actor,
                self.character,
                "flaws",
                flaw,
                "",
                value,
                0,
                f"free at the Embrace, {ordinal(generation)} generation",
                {"free": "the Embrace"},
                free=value,
            )

    def starting_disciplines(self) -> None:
        """3, once a vampire: 2 dots, free, in one in-clan discipline and 1 in each of
        the others; a Caitiff first chooses its three."""
        plan, db = self.plan, self.db
        step = plan.step("disciplines", "Disciplines")
        for gone in plan.lost:
            step.add(f"{gone.name} {gone.rating} lost, as every ghoul dot is")
        if plan.caitiff:
            three = list(dict.fromkeys(self.choices.caitiff_three))
            if len(three) != 3:
                raise unprocessable("Choose the Caitiff's three in-clan disciplines.")
            for name in three:
                self.add_free("extra_in_clan_disciplines", name, 1)
        plan.in_clan = list(dict.fromkeys(SPLATS[VAMPIRE].in_clan(self.rules, self.sheet())))
        if not plan.in_clan:
            raise unprocessable("Choose the in-clan disciplines first.")
        two = self.choices.two_dots or plan.in_clan[0]
        if two not in plan.in_clan:
            raise unprocessable(f"{two} is not one of {self.sire.clan}'s in-clan disciplines.")
        plan.two_dots = two
        for name in plan.in_clan:
            rating = 2 if name == two else 1
            self.add_free("disciplines", name, rating)
            plan.disciplines.append(Rated(name, rating))
            step.add(f"{name} {rating}, free")
        db.flush()

    def add_free(self, category: str, name: str, rating: int) -> None:
        definition, _ = sheets.find_definition(self.db, self.character, category, name)
        self.db.add(
            CharacterTrait(
                character_id=self.character.id,
                trait_definition_id=definition.id,
                rating=rating,
                free_rating=rating,
            )
        )
        self.db.flush()

    def reprice(self, purchases: Sequence[Purchase]) -> None:
        """4. Skills and backgrounds bought in play, priced again at the new Generation,
        each difference a `reprice` line naming the purchase."""
        step = self.plan.step("reprice", "Skills and backgrounds")
        rules, sheet = self.rules, self.sheet()
        found: list[repricing.Repriced] = []
        for purchase in purchases:
            entry = purchase.entry
            try:
                now = purchase_cost(rules, sheet, purchase.trait, entry.to_rating or 0).cost
            except PricingError:
                continue
            if now == purchase.was:
                continue
            assert entry.trait_definition_id is not None
            repriced = repricing.Repriced(
                purchase_id=entry.id,
                trait_definition_id=entry.trait_definition_id,
                name=purchase.name,
                detail=purchase.trait.detail,
                from_rating=entry.from_rating or 0,
                to_rating=entry.to_rating or 0,
                cost=now - purchase.was,
            )
            found.append(repriced)
            step.add(f"{repriced.label}, bought in play, repriced", -repriced.cost)
        if not found:
            step.add(
                "Nothing bought in play costs more or less at the new Generation."
                if purchases
                else "Nothing was bought in play."
            )
        repricing.record(
            self.db,
            self.actor,
            self.character.id,
            found,
            f"The Embrace, {ordinal(self.plan.generation or 0)} generation",
        )

    def finishing_touches(self) -> None:
        """5. What the new Generation gives, the clan weakness, and the merits and
        flaws the Storyteller lets change."""
        plan, db = self.plan, self.db
        step = plan.step("finishing", "Finishing touches")
        step.add(
            f"As a {plan.title}: Blood {plan.blood}, {plan.blood_per_turn} a turn, and"
            f" {plural(plan.attribute_bonus, 'attribute bonus point')} to place when wanted"
        )
        if any(r.definition.name == "Humanity" for r in self.rows()):
            step.add("Humanity 5, as every new vampire starts")
        step.add(
            f"The {self.sire.clan} clan weakness: {plan.weakness}"
            if plan.weakness
            else f"The {self.sire.clan} clan weakness, as the clan's write-up has it"
        )
        removing = {(r.category, r.name, r.detail) for r in self.choices.remove}
        for row in self.rows():
            if row.key not in removing:
                continue
            removing.discard(row.key)
            if row.trait.granted_rating:
                raise unprocessable(
                    f"{label(row)} comes from another trait; it cannot come off alone."
                )
            value = worth(db, self.character, row)
            if row.category.key == "flaws":
                step.add(f"{label(row)} taken off, the XP it gave taken back", -value)
                refund(db, self.actor, self.character, row, -value, "taken off at the Embrace")
            else:
                step.add(f"{label(row)} taken off, its XP refunded", value)
                refund(db, self.actor, self.character, row, value, "taken off at the Embrace")
        if removing:
            raise unprocessable(f"The sheet has no {next(iter(removing))[1]} to take off.")
        before = self.balance
        sheets.apply_grants(db, self.actor, self.character)
        db.expire_all()
        if self.balance != before:
            step.add("Dots the vampire's merits now give, refunded", self.balance - before)

    def within_merit_limit(self) -> None:
        """1, again: within the merit limit, or merits must come off; and if the sire's
        clan and rarity alone go over it, the character dies in the Embrace."""
        plan, db = self.plan, self.db
        plan.merit_points = sheets.held_points(db, self.character, "merits")
        rows = self.rows()
        plan.removable = [
            Removable(
                r.category.key,
                r.definition.name,
                r.trait.detail,
                r.trait.rating or 0,
                worth(db, self.character, r) * (-1 if r.category.key == "flaws" else 1),
            )
            for r in rows
            if r.category.key in ("merits", "flaws")
            and not r.trait.granted_rating
            and r.definition.name not in plan.clan_merits
            and r.definition.name not in (*LESSER, THIN_BLOODED)
        ]
        if plan.merit_points <= plan.merit_limit:
            return
        sheet = [r.as_rules_trait() for r in rows]
        needed = sum(
            points(self.rules, sheet, r.as_rules_trait())
            for r in rows
            if r.category.key == "merits" and r.definition.name in plan.clan_merits
        )
        plan.dies = needed > plan.merit_limit
        raise conflict(
            f"The sire's clan and rarity merits alone come to {needed} points, over the"
            f" limit of {plan.merit_limit}: the character cannot conform, and dies in the"
            " Embrace (p. 297)."
            if plan.dies
            else f"Merits come to {plan.merit_points} points, over the limit of"
            f" {plan.merit_limit}: take merits off until they are within it (p. 297)."
        )

    def buy_back(self) -> None:
        """6. Refunds and saved XP pay the costs, and what they cannot is debt; then up
        to 2 lost dots bought back with what is left over, or into debt where the
        Storyteller allows it."""
        plan, choices = self.plan, self.choices
        step = plan.step("debt", "XP debt")
        left = self.balance
        step.add(
            f"Refunds and saved XP pay the costs: {left} XP left over"
            if left >= 0
            else f"Refunds and saved XP pay what they can: {-left} XP owed"
        )
        lost = {d.name: d.rating for d in plan.lost}
        asked = sum(max(0, d.rating - self.rating_of(d.name)) for d in choices.buy_back)
        if asked > BUY_BACK_DOTS:
            raise unprocessable(f"At most {BUY_BACK_DOTS} lost discipline dots can be bought back.")
        for wish in choices.buy_back:
            if wish.name not in lost:
                raise unprocessable(f"{wish.name} was not lost in the Embrace.")
            if wish.rating > lost[wish.name]:
                raise unprocessable(
                    f"{wish.name} was {lost[wish.name]}; it can be bought back that far."
                )
            self.buy_back_one(step, wish)
        plan.balance_after = self.balance
        plan.debt = xp_debt.owed(plan.balance_after)
        if plan.debt:
            step.add(
                f"XP debt of {plan.debt}: all the XP it earns goes to it until it is paid off,"
                " and nothing new is bought till then"
            )

    def buy_back_one(self, step: Step, wish: Dots) -> None:
        now = self.rating_of(wish.name)
        if wish.rating <= now:
            return
        held = next(
            (
                r
                for r in self.rows()
                if r.category.key == "disciplines" and r.definition.name == wish.name
            ),
            None,
        )
        before = SheetTrait("disciplines", wish.name, now, held.trait.free_rating if held else 0)
        try:
            quote = purchase_cost(self.rules, self.sheet(), before, wish.rating)
        except PricingError as error:
            raise unprocessable(f"{wish.name} cannot be bought back: {error}") from error
        left = max(0, self.balance)
        if not self.choices.buy_back_into_debt and quote.cost > left:
            raise conflict(
                f"{wish.name} {wish.rating} costs {quote.cost} XP, and {left} is left over:"
                " the Storyteller can let lost dots be bought back into XP debt (p. 298)."
            )
        step.add(f"{wish.name} {now} → {wish.rating} bought back, no teacher needed", -quote.cost)
        self.plan.bought_back.append(Rated(wish.name, wish.rating))
        definition, _ = sheets.find_definition(self.db, self.character, "disciplines", wish.name)
        if held is None:
            trait = CharacterTrait(
                character_id=self.character.id, trait_definition_id=definition.id, rating=0
            )
            self.db.add(trait)
        else:
            trait = held.trait
        trait.rating = wish.rating
        self.db.add(
            XpEntry(
                character_id=self.character.id,
                kind="purchase",
                amount=-quote.cost,
                reason=f"{wish.name} {now} → {wish.rating} (bought back after the Embrace)",
                entered_by=self.actor.id,
                trait_definition_id=definition.id,
                from_rating=now,
                to_rating=wish.rating,
                cost_basis=quote.rule.describe(),
            )
        )
        self.db.flush()

    def rating_of(self, discipline: str) -> int:
        return next(
            (
                r.trait.rating or 0
                for r in self.rows()
                if r.category.key == "disciplines" and r.definition.name == discipline
            ),
            0,
        )

    def judge(self) -> None:
        """The sheet as it now stands: what the rules refuse stops it; the rest is noted."""
        self.db.expire_all()
        refusals: list[sheets.Problem] = []
        for violation in sheets.sheet_violations(self.db, self.character):
            if sheets.blocking(violation, self.character):
                refusals.append(sheets.problem(violation))
            else:
                self.plan.notes.append(violation.message)
        if refusals:
            raise conflict(sheets.refusal(refusals))


def plan_for(db: Session, character: Character, choices: Choices) -> Plan:
    """What the Embrace would do, worked out by making it and taking it back."""
    plan = Plan()
    plan.refused = can_embrace(db, character)
    if plan.refused is not None:
        return plan
    savepoint = db.begin_nested()
    try:
        change(db, None, character, choices, plan)
    except HTTPException as error:
        plan.refused = str(error.detail)
    finally:
        savepoint.rollback()
        db.expire_all()
    return plan


def embrace(
    db: Session,
    staff: User,
    character: Character,
    choices: Choices,
    embraced_on: date,
    note: str,
) -> Plan:
    """Make the Embrace: refused, changing nothing, if any step is. The caller holds
    the character's lock."""
    refused = can_embrace(db, character)
    if refused is not None:
        raise conflict(refused)
    assert character.home_troupe_id is not None
    plan = Plan()
    savepoint = db.begin_nested()
    try:
        change(db, staff, character, choices, plan)
    except BaseException:
        savepoint.rollback()
        db.expire_all()
        raise
    savepoint.commit()
    db.add(
        Embrace(
            character_id=character.id,
            troupe_id=character.home_troupe_id,
            result="vampire",
            embraced_on=embraced_on,
            sire_id=plan.sire_id,
            sire_name=plan.sire_name,
            sire_clan=plan.sire_clan,
            sire_generation=plan.sire_generation,
            note=note.strip(),
            buy_back_into_debt=plan.buy_back_into_debt,
            outcome=plan.as_outcome(),
            recorded_by=staff.id,
        )
    )
    sheets.freeze_sheet(db, staff, character, character.home_troupe_id)
    db.flush()
    for step in plan.steps:
        audit.record(
            db,
            staff,
            "embrace.step",
            troupe_id=character.home_troupe_id,
            character_id=character.id,
            step=step.title,
            summary="; ".join(line.text for line in step.lines) or "nothing",
            xp=signed(step.xp),
        )
    audit.record(
        db,
        staff,
        "embrace.vampire",
        troupe_id=character.home_troupe_id,
        character_id=character.id,
        sire=plan.sire_name,
        clan=plan.clan,
        generation=ordinal(plan.generation or 0),
        debt=plan.debt,
    )
    notifications.notify(
        db,
        [character.player_id],
        "sheet.embrace",
        f"{character.name} was Embraced by {plan.sire_name}: a vampire of {plan.clan},"
        f" {ordinal(plan.generation or 0)} generation"
        + (f", with an XP debt of {plan.debt}." if plan.debt else "."),
        f"/characters/{character.id}",
        troupe_id=character.home_troupe_id,
        character_id=character.id,
    )
    return plan


def signed(xp: int) -> str:
    return f"+{xp}" if xp > 0 else str(xp)


def died(
    db: Session,
    staff: User,
    character: Character,
    embraced_on: date,
    sire_name: str,
    note: str,
) -> Embrace:
    """The character died in the attempted Embrace: retired, with a note in its log."""
    refused = can_embrace(db, character)
    if refused is not None:
        raise conflict(refused)
    assert character.home_troupe_id is not None
    record = Embrace(
        character_id=character.id,
        troupe_id=character.home_troupe_id,
        result="died",
        embraced_on=embraced_on,
        sire_name=sire_name.strip(),
        note=note.strip(),
        recorded_by=staff.id,
    )
    db.add(record)
    character.status = "retired"
    # Final Death, listed on the Who's Who until its player says otherwise
    # (horatio.leaving).
    character.left_reason = "final_death"
    character.left_listed = True
    db.flush()
    audit.record(
        db,
        staff,
        "embrace.died",
        troupe_id=character.home_troupe_id,
        character_id=character.id,
        note=note.strip() or "no note",
    )
    notifications.notify(
        db,
        [character.player_id],
        "sheet.embrace",
        f"{character.name} died in the Embrace, and is retired.",
        f"/characters/{character.id}",
        troupe_id=character.home_troupe_id,
        character_id=character.id,
    )
    return record


def embraces(db: Session, character: Character) -> list[Embrace]:
    return list(
        db.scalars(
            select(Embrace)
            .where(Embrace.character_id == character.id)
            .order_by(Embrace.embraced_on, Embrace.id)
        )
    )


# --- buying lost dots back later, from the cart ------------------------------------------


def buys_back_into_debt(
    db: Session, character: Character, category: str, name: str, from_rating: int, to_rating: int
) -> bool:
    """Whether raising a discipline is buying back dots the character's Embrace took,
    which the Storyteller let be bought into XP debt (p. 298): no higher than it was,
    and with the purchases of lost disciplines since, no more than 2 dots in all."""
    if category != "disciplines" or to_rating <= from_rating:
        return False
    found = db.scalar(
        select(Embrace)
        .where(
            Embrace.character_id == character.id,
            Embrace.result == "vampire",
            Embrace.buy_back_into_debt.is_(True),
        )
        .order_by(Embrace.id.desc())
        .limit(1)
    )
    if found is None:
        return False
    lost = {d["name"]: d["rating"] for d in found.outcome.get("lost", [])}
    if name not in lost or to_rating > lost[name]:
        return False
    names = list(lost)
    since = db.scalars(
        select(XpEntry)
        .join(TraitDefinition, XpEntry.trait_definition_id == TraitDefinition.id)
        .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
        .where(
            XpEntry.character_id == character.id,
            XpEntry.kind == "purchase",
            TraitCategory.key == "disciplines",
            TraitDefinition.name.in_(names),
            XpEntry.created_at >= found.created_at,
        )
    )
    used = sum((e.to_rating or 0) - (e.from_rating or 0) for e in since)
    return used + to_rating - from_rating <= BUY_BACK_DOTS
