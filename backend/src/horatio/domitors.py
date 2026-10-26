"""A ghoul's domitor: the vampire it is bound to (MET: VTM pp. 296–297).

A ghoul has no clan of its own. It takes its domitor's clan and bloodline, which
its sheet holds as its clan trait, and its disciplines are its domitor's in-clan
ones, in powers the domitor has. The domitor can be a vampire PC or NPC in
Horatio, linked, or one that is not, by name: then the player names its clan
and bloodline, and staff check the powers at approval.

Before a home troupe accepts the ghoul, its player sets the domitor; after, the
home troupe's running staff do, when the old bond has faded and the ghoul is
fully bound to a new one (p. 297). Its player then keeps the discipline dots, or
moves all of them to the new domitor's in-clan disciplines.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from horatio import audit
from horatio.models import Character, CharacterTrait, TraitCategory, TraitDefinition, User
from horatio.rules.model import SheetTrait
from horatio.rules.splats import SPLATS
from horatio.sheets import (
    Domitor,
    as_domitor,
    conflict,
    ensure_unlocked,
    find_definition,
    rules_for,
    sheet_rows,
    unprocessable,
)

# Never more dots of disciplines than this (p. 297).
GHOUL_DISCIPLINE_DOTS = 5


@dataclass(frozen=True)
class Placed:
    """Dots of one discipline, where a ghoul's player moves them."""

    name: str
    rating: int
    detail: str = ""


@dataclass(frozen=True)
class DomitorInfo:
    # The linked domitor, or None for one known by name only.
    character: Character | None
    name: str
    # The ghoul's clan and bloodline, which are the domitor's.
    clan: str | None


def has_domitor(character: Character) -> bool:
    return SPLATS[character.splat].has_domitor


def domitor_info(db: Session, ghoul: Character) -> DomitorInfo | None:
    """The ghoul's domitor, or None while it has none (or for a vampire)."""
    linked = db.get(Character, ghoul.domitor_id) if ghoul.domitor_id is not None else None
    if linked is None and not ghoul.domitor_name:
        return None
    clan = next(
        (r.definition.name for r in sheet_rows(db, ghoul) if r.category.key == "clan"), None
    )
    return DomitorInfo(linked, linked.name if linked is not None else ghoul.domitor_name, clan)


def set_domitor(
    db: Session,
    user: User,
    ghoul: Character,
    *,
    domitor: Character | None,
    name: str = "",
    clan: str | None = None,
    disciplines: Literal["keep", "move"] = "keep",
    moved: Sequence[Placed] = (),
) -> None:
    """Bind the ghoul to `domitor`, or to one not in Horatio called `name`, of `clan`.
    Its clan becomes the domitor's. Its discipline dots stay where they are, or with
    `disciplines` "move" go where `moved` says: all of them, and only to the new
    domitor's in-clan disciplines, in powers a linked domitor has."""
    if not has_domitor(ghoul):
        raise conflict("Only a ghoul has a domitor.")
    ensure_unlocked(db, ghoul)
    if domitor is not None:
        if domitor.id == ghoul.id or has_domitor(domitor):
            raise unprocessable("A domitor is a vampire.")
        if domitor.status == "retired":
            raise conflict(f"{domitor.name} is retired.")
        clan = next(
            (r.definition.name for r in sheet_rows(db, domitor) if r.category.key == "clan"), None
        )
        if clan is None:
            raise conflict(f"{domitor.name} has no clan yet, so a ghoul cannot take it.")
        name = ""
    else:
        name = name.strip()
        if not name:
            raise unprocessable("Name the domitor, or choose one in Horatio.")
        if clan is None:
            raise unprocessable("Choose the domitor's clan and bloodline.")
    definition, _ = find_definition(db, ghoul, "clan", clan)
    placing: list[tuple[TraitDefinition, Placed]] = []
    if disciplines == "move":
        powers = as_domitor(db, domitor) if domitor is not None else None
        placing = planned_moves(db, ghoul, clan, powers, moved)
    elif moved:
        raise unprocessable("Say to move the discipline dots, or leave out where they go.")

    clan_ids = select(TraitDefinition.id).join(TraitCategory).where(TraitCategory.key == "clan")
    db.execute(
        delete(CharacterTrait).where(
            CharacterTrait.character_id == ghoul.id,
            CharacterTrait.trait_definition_id.in_(clan_ids),
        )
    )
    db.add(CharacterTrait(character_id=ghoul.id, trait_definition_id=definition.id))
    ghoul.domitor_id = domitor.id if domitor is not None else None
    ghoul.domitor_name = name
    db.flush()
    if disciplines == "move":
        move_disciplines(db, ghoul, placing)
    audit.record(
        db,
        user,
        "character.domitor",
        character_id=ghoul.id,
        domitor=domitor.name if domitor is not None else name,
        linked=domitor is not None,
        clan=clan,
        disciplines="moved" if disciplines == "move" else "kept",
    )


def planned_moves(
    db: Session, ghoul: Character, clan: str, domitor: Domitor | None, moved: Sequence[Placed]
) -> list[tuple[TraitDefinition, Placed]]:
    """Where the ghoul's discipline dots go, checked against its new domitor (p. 297):
    as many as it has, in the domitor's clan's in-clan disciplines, none above what a
    linked domitor has."""
    rows = [r for r in sheet_rows(db, ghoul) if r.category.key == "disciplines"]
    held = sum(r.trait.rating or 0 for r in rows)
    if sum(p.rating for p in moved) != held:
        raise unprocessable(
            f"Move all {held} discipline dots, no more and no fewer;"
            f" that is {sum(p.rating for p in moved)}."
        )
    if len({(p.name, p.detail) for p in moved}) != len(moved):
        raise unprocessable("Each discipline once.")
    rules = rules_for(db, ghoul)
    # The sheet as the new domitor leaves it, before the dots are placed.
    sheet = [
        r.as_rules_trait()
        for r in sheet_rows(db, ghoul)
        if r.category.key not in ("disciplines", "clan")
    ] + [SheetTrait("clan", clan)]
    facts = SPLATS[ghoul.splat].facts
    placing: list[tuple[TraitDefinition, Placed]] = []
    for place in moved:
        definition, _ = find_definition(db, ghoul, "disciplines", place.name)
        trait = SheetTrait("disciplines", definition.name, place.rating, detail=place.detail)
        if not 1 <= place.rating <= GHOUL_DISCIPLINE_DOTS:
            raise unprocessable(f"{place.name} at {place.rating}: from 1 to 5 dots.")
        if not facts(rules, sheet, trait)["in_clan"]:
            raise unprocessable(
                f"{place.name} is not one of the new domitor's in-clan disciplines."
            )
        if domitor is not None and place.rating > max(
            domitor.powers.get(trait.full_name, 0), domitor.powers.get(trait.name, 0)
        ):
            raise unprocessable(f"The domitor does not have {trait.full_name} at {place.rating}.")
        placing.append((definition, place))
    return placing


def move_disciplines(
    db: Session, ghoul: Character, placing: Sequence[tuple[TraitDefinition, Placed]]
) -> None:
    """Take every discipline dot off the ghoul and place them as planned. The dots
    stay free."""
    for row in sheet_rows(db, ghoul):
        if row.category.key == "disciplines":
            db.delete(row.trait)
    db.flush()
    creating = ghoul.creation_completed_at is None
    for definition, place in placing:
        db.add(
            CharacterTrait(
                character_id=ghoul.id,
                trait_definition_id=definition.id,
                detail=place.detail,
                rating=place.rating,
                free_rating=place.rating,
                creation_pick=place.rating if creating else None,
            )
        )
    db.flush()
