"""NPCs: characters a troupe's staff make and keep for the troupe (CONTEXT.md: NPC).

An NPC belongs to its troupe: it is approved there from the start, plays by
the troupe's house rules, needs no approval and never takes part in
downtimes. Staff can build one through the creation wizard, or quickly by
setting ratings directly; either way no experience is spent, and a running
tally shows what the build would be worth under the troupe's rules.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit
from horatio.creation import grant_starting_traits
from horatio.models import Character, CharacterTrait, Troupe, TroupeMembership, User
from horatio.rules.pricing import NotAllowed, PricingError, trait_cost
from horatio.sheets import (
    conflict,
    find_definition,
    held_at,
    replace_choice,
    rules_for,
    sheet_rows,
    unprocessable,
)


def create_npc(
    db: Session, staff: User, troupe: Troupe, splat: str, name: str, wizard: bool
) -> Character:
    """A new NPC in `troupe`. With `wizard`, it starts in character creation; without,
    it is ready for its ratings to be set directly."""
    npc = Character(
        player_id=staff.id,
        splat=splat,
        name=name,
        kind="npc",
        owner_troupe_id=troupe.id,
        home_troupe_id=troupe.id,
        creation_completed_at=None if wizard else datetime.now(UTC),
    )
    db.add(npc)
    db.flush()
    db.add(TroupeMembership(troupe_id=troupe.id, character_id=npc.id))
    grant_starting_traits(db, rules_for(db, npc), npc)
    db.flush()
    audit.record(db, staff, "npc.created", troupe_id=troupe.id, character_id=npc.id)
    return npc


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
    category that holds one (a focus)."""
    if npc.kind != "npc":
        raise conflict("Only an NPC's ratings can be set directly.")
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
    if trait is None:
        if category.max_held == 1:
            # A choice such as a focus: the new one replaces the one chosen before
            # (one a merit grants stays).
            for row in sheet_rows(db, npc):
                if row.category.key == category.key and not row.trait.granted_rating:
                    db.delete(row.trait)
            db.flush()
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
