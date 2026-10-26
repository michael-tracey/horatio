"""NPCs: characters a troupe's staff make and keep for the troupe (CONTEXT.md: NPC).

An NPC belongs to its troupe: it is approved there from the start, plays by
the troupe's house rules, needs no approval and never takes part in
downtimes. Staff can build one through the creation wizard, or quickly by
setting ratings directly; either way no experience is spent, and a running
tally shows what the build would be worth under the troupe's rules.

Every NPC has a kind (horatio.rules.npc_kinds), such as a vampire, a mortal or a
werewolf, all on the Vampire rule set, and a form: sheeted, with a full sheet as
above, or stock, with only an NPC rating and specializations (horatio.rules.stock).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit
from horatio.creation import grant_starting_traits
from horatio.models import (
    Character,
    CharacterTrait,
    StockNpc,
    Troupe,
    TroupeMembership,
    User,
)
from horatio.rules import stock
from horatio.rules.npc_kinds import NpcKind, Resource, custom_kind, npc_kinds
from horatio.rules.pricing import NotAllowed, PricingError, trait_cost
from horatio.rules.store import read_troupe_rules
from horatio.sheets import (
    conflict,
    find_definition,
    held_at,
    replace_choice,
    rules_for,
    sheet_rows,
    unprocessable,
)

Form = Literal["sheeted", "stock"]


def resolve_kind(key: str, custom: Mapping[str, Any] | None) -> NpcKind:
    """The kind with `key`, and for the custom kind, as `custom` sets it up:
    {"name", "nature", "resource": {"name", "size", "per_turn", "regains"?}}."""
    kind = npc_kinds().get(key)
    if kind is None:
        raise unprocessable(f"There is no NPC kind {key!r}.")
    if not kind.custom:
        if custom is not None:
            raise unprocessable(f"Only a custom kind is set up by hand, not {kind.name}.")
        return kind
    if custom is None:
        raise unprocessable(
            "A custom kind needs a name, whether it is mortal, and its resource's name and size."
        )
    return custom_kind(kind, custom["name"], custom["nature"], Resource(**custom["resource"]))


def kind_of(npc: Character) -> NpcKind:
    """The NPC's kind, with a custom kind as staff set it up for it."""
    if npc.npc_kind is None:
        raise conflict("Only an NPC has a kind.")
    return resolve_kind(npc.npc_kind, npc.npc_custom_kind)


def splat_for(kind: str) -> str:
    """The rule set an NPC of `kind` is built on: a ghoul's, for a ghoul; the
    Vampire rule set for every other kind (MET: VTM p. 490)."""
    return "ghoul" if kind == "ghoul" else "vampire"


def create_npc(
    db: Session,
    staff: User,
    troupe: Troupe,
    splat: str,
    name: str,
    wizard: bool,
    npc_kind: str = "vampire",
    npc_form: Form = "sheeted",
    custom: Mapping[str, Any] | None = None,
) -> Character:
    """A new NPC in `troupe`. A sheeted one, with `wizard`, starts in character
    creation; without, it is ready for its ratings to be set directly. A Stock NPC
    starts at rating 1 with no specializations, for `set_stock` to fill in."""
    resolve_kind(npc_kind, custom)
    if npc_form == "stock" and wizard:
        raise unprocessable("A Stock NPC has no sheet to build in the creation wizard.")
    npc = Character(
        player_id=staff.id,
        splat=splat,
        name=name,
        kind="npc",
        npc_kind=npc_kind,
        npc_form=npc_form,
        npc_custom_kind=dict(custom) if custom is not None else None,
        owner_troupe_id=troupe.id,
        home_troupe_id=troupe.id,
        creation_completed_at=None if wizard else datetime.now(UTC),
    )
    db.add(npc)
    db.flush()
    db.add(TroupeMembership(troupe_id=troupe.id, character_id=npc.id))
    if npc_form == "stock":
        db.add(StockNpc(character_id=npc.id, rating=1))
    else:
        grant_starting_traits(db, rules_for(db, npc), npc)
    db.flush()
    audit.record(
        db,
        staff,
        "npc.created",
        troupe_id=troupe.id,
        character_id=npc.id,
        npc_kind=npc_kind,
        npc_form=npc_form,
    )
    return npc


def stock_of(db: Session, npc: Character) -> StockNpc:
    found = db.scalar(select(StockNpc).where(StockNpc.character_id == npc.id))
    if npc.npc_form != "stock" or found is None:
        raise conflict(f"{npc.name} is not a Stock NPC.")
    return found


def specializations_of(row: StockNpc) -> list[stock.Specialization]:
    return [stock.Specialization(s["type"], s["name"]) for s in row.specializations]


def stat_block(db: Session, npc: Character) -> tuple[StockNpc, stock.StatBlock]:
    row = stock_of(db, npc)
    return row, stock.stat_block(kind_of(npc), row.rating, specializations_of(row))


def set_stock(
    db: Session,
    staff: User,
    npc: Character,
    npc_kind: str,
    custom: Mapping[str, Any] | None,
    rating: int,
    specializations: Sequence[stock.Specialization],
    notes: str,
) -> None:
    """Change a Stock NPC: its kind, rating, specializations and notes, as the
    Stock NPC rules allow them (horatio.rules.stock). Its skills, disciplines and
    paths are the Vampire rule set's, under its troupe's house rules."""
    row = stock_of(db, npc)
    kind = resolve_kind(npc_kind, custom)
    rule_set = read_troupe_rules(db, "vampire", npc.owner_troupe_id).rule_set
    names = {
        category: {name for (c, name) in rule_set.traits if c == category}
        for category in ("skills", "disciplines")
    }
    try:
        stock.check(kind, rating, specializations, names["skills"], names["disciplines"])
    except stock.StockError as error:
        raise unprocessable(str(error)) from error
    npc.npc_kind = npc_kind
    npc.npc_custom_kind = dict(custom) if custom is not None else None
    npc.splat = splat_for(npc_kind)
    row.rating = rating
    row.specializations = [{"type": s.type, "name": s.name} for s in specializations]
    row.notes = notes
    db.flush()
    audit.record(db, staff, "npc.stock_changed", troupe_id=npc.owner_troupe_id, character_id=npc.id)


def set_rating(
    db: Session,
    staff: User,
    npc: Character,
    category_key: str,
    name: str,
    detail: str,
    rating: int | None,
) -> None:
    """Set an NPC's trait straight to `rating` (0 removes it), with no experience spent.
    Unrated traits replace the category's choice, and so does a new trait in a
    category that holds one (a focus, or its Morality): the new one takes the old
    one's place, starting dots and all."""
    if npc.kind != "npc":
        raise conflict("Only an NPC's ratings can be set directly.")
    if npc.npc_form == "stock":
        raise conflict("A Stock NPC has no sheet: change its rating and specializations instead.")
    definition, category = find_definition(db, npc, category_key, name)
    if not category.rated:
        if rating is not None:
            raise unprocessable(f"{category.name} has no rating.")
        replace_choice(db, npc, definition, category, detail)
        db.flush()
        return
    if rating is None or rating < 0:
        raise unprocessable(f"{category.name} needs a rating.")
    if category.max_rating is not None and rating > category.max_rating:
        raise unprocessable(f"{category.name} cannot go above {category.max_rating}.")
    fixed = held_at(db, npc, category.key, definition.name)
    if fixed is not None and rating not in (0, fixed):
        raise unprocessable(f"{name} is always rated {fixed}.")

    trait = db.scalar(
        select(CharacterTrait).where(
            CharacterTrait.character_id == npc.id,
            CharacterTrait.trait_definition_id == definition.id,
            CharacterTrait.detail == detail,
        )
    )
    if rating == 0:
        if trait is not None:
            db.delete(trait)
        db.flush()
        return
    if trait is None and category.max_held == 1:
        # A choice such as a focus or a Path: the new one takes the place of the one
        # chosen before, as a PC's swap does (one a merit grants stays).
        held = [
            r.trait
            for r in sheet_rows(db, npc)
            if r.category.key == category.key and not r.trait.granted_rating
        ]
        for extra in held[1:]:
            db.delete(extra)
        if held:
            trait = held[0]
            trait.trait_definition_id = definition.id
            trait.detail = detail
        db.flush()
    if trait is None:
        trait = CharacterTrait(
            character_id=npc.id, trait_definition_id=definition.id, detail=detail
        )
        db.add(trait)
    trait.rating = rating
    trait.free_rating = min(trait.free_rating or 0, rating)
    if trait.creation_pick is not None and trait.creation_pick > trait.free_rating:
        trait.creation_pick = None
    db.flush()


@dataclass
class TallyLine:
    category: str
    name: str
    detail: str
    rating: int
    cost: int | None  # None: this troupe's rules do not allow it
    note: str = ""


def tally(db: Session, npc: Character) -> tuple[int, list[TallyLine]]:
    """What the NPC's sheet would cost in experience under its troupe's rules, trait
    by trait. Starting traits and creation picks count as free, as for a PC."""
    rules = rules_for(db, npc)
    rows = sheet_rows(db, npc)
    sheet = [r.as_rules_trait() for r in rows]
    lines: list[TallyLine] = []
    for row in rows:
        if not row.category.rated or not row.trait.rating:
            continue
        line = TallyLine(
            row.category.key, row.definition.name, row.trait.detail, row.trait.rating, None
        )
        try:
            line.cost = trait_cost(rules, sheet, row.as_rules_trait()).cost
        except NotAllowed:
            line.note = "not allowed in this troupe"
        except PricingError as error:
            line.note = str(error)
        lines.append(line)
    return sum(line.cost or 0 for line in lines), lines
