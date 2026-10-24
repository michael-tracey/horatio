"""Repricing earlier XP buys when Generation changes before acceptance.

Until a first home troupe accepts the character, its build is still creation
(MET: VTM pp. 99, 106): Generation, a creation-only trait kept open until then
(`until = "accepted"` in the rules data), can go up or down with XP. What the
character has bought since creation is then priced as if it had been bought at
the new Generation. Each purchase whose price changes gets its own `reprice`
line in the XP history, naming it, for the difference.

A purchase is priced on the sheet as it was before the change and as it is
after, with only that trait different, so the line is what the change itself
does to it, whatever else has changed since it was bought. Changing Generation
back and forth comes out even.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import TraitCategory, TraitDefinition, User, XpEntry
from horatio.rules.model import SheetTrait, TroupeRules
from horatio.rules.pricing import PricingError, purchase_cost

TraitKey = tuple[str, str, str]  # category, name, detail


@dataclass(frozen=True)
class Repriced:
    """One earlier purchase, and what it costs more (negative: less) repriced."""

    purchase_id: uuid.UUID
    trait_definition_id: uuid.UUID
    name: str
    detail: str
    from_rating: int
    to_rating: int
    cost: int

    @property
    def label(self) -> str:
        """The purchase, as the XP history names it: "Brawl 0 → 2"."""
        named = f"{self.name}: {self.detail}" if self.detail else self.name
        return f"{named} {self.from_rating} → {self.to_rating}"


def with_rating(
    sheet: Sequence[SheetTrait], category: str, name: str, detail: str, rating: int
) -> list[SheetTrait]:
    """The sheet with one trait at `rating`, added if it is not held."""
    changed = [
        replace(t, rating=rating)
        if (t.category, t.name, t.detail) == (category, name, detail)
        else t
        for t in sheet
    ]
    if not any((t.category, t.name, t.detail) == (category, name, detail) for t in sheet):
        changed.append(SheetTrait(category=category, name=name, rating=rating, detail=detail))
    return changed


def repricing(
    db: Session,
    rules: TroupeRules,
    character_id: uuid.UUID,
    before: Sequence[SheetTrait],
    after: Sequence[SheetTrait],
    free: Mapping[TraitKey, int],
    changing: uuid.UUID,
) -> list[Repriced]:
    """Each earlier purchase whose price differs on the sheet `after` from the
    sheet `before`, and by how much. Only purchases a cost rule priced count:
    not those given free, nor refunds of granted or declined dots, nor buys of the
    trait `changing` itself. One the rules cannot price on either sheet, such as a
    technique a Master cannot learn, is left as it is: holding it is for the
    checks to refuse. `free` is each trait's free dots now."""
    purchases = db.execute(
        select(XpEntry, TraitDefinition.name, TraitCategory.key)
        .join(TraitDefinition, XpEntry.trait_definition_id == TraitDefinition.id)
        .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
        .where(
            XpEntry.character_id == character_id,
            XpEntry.kind == "purchase",
            XpEntry.trait_definition_id != changing,
        )
        .order_by(XpEntry.id)
    )
    found: list[Repriced] = []
    for entry, name, category in purchases:
        if "scheme" not in (entry.cost_basis or {}):
            continue
        assert entry.trait_definition_id is not None
        assert entry.from_rating is not None and entry.to_rating is not None
        detail = entry.detail or ""
        held_free = free.get((category, name, detail), 0)
        trait = SheetTrait(
            category=category,
            name=name,
            rating=entry.from_rating,
            free_rating=min(held_free, entry.from_rating, entry.to_rating),
            detail=detail,
        )
        try:
            was = purchase_cost(rules, before, trait, entry.to_rating).cost
            now = purchase_cost(rules, after, trait, entry.to_rating).cost
        except PricingError:
            continue
        if now != was:
            found.append(
                Repriced(
                    purchase_id=entry.id,
                    trait_definition_id=entry.trait_definition_id,
                    name=name,
                    detail=detail,
                    from_rating=entry.from_rating,
                    to_rating=entry.to_rating,
                    cost=now - was,
                )
            )
    return found


def record(
    db: Session, user: User, character_id: uuid.UUID, found: Sequence[Repriced], change: str
) -> None:
    """A `reprice` line in the XP history for each, naming the purchase it reprices
    and the `change` that reprices it: "Generation 1 → 2: Brawl 0 → 2 repriced"."""
    for repriced in found:
        db.add(
            XpEntry(
                character_id=character_id,
                kind="reprice",
                amount=-repriced.cost,
                reason=f"{change}: {repriced.label} repriced",
                entered_by=user.id,
                trait_definition_id=repriced.trait_definition_id,
                detail=repriced.detail or None,
                from_rating=repriced.from_rating,
                to_rating=repriced.to_rating,
                corrects_id=repriced.purchase_id,
            )
        )
    db.flush()
