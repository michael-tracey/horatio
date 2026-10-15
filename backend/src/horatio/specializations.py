"""Specialisations: the areas of an Influence, the people behind Contacts, the
subjects of Lore. Each kind is a category that `specializes` a skill or
background. A specialisation is a trait in it: a catalogue name, or "Custom"
with the text as its detail.

A troupe can set a list of options for a kind; characters playing by that
troupe's rules (home, or the troupe they are built for) choose from it.
"""

import uuid
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from horatio import audit
from horatio.models import Character, TraitCategory, Troupe, TroupeSpecialization, User
from horatio.sheets import rules_for, rules_troupe, sheet_rows

CUSTOM = "Custom"


@dataclass
class Kind:
    category: str
    name: str
    parent_category: str
    parent_name: str
    # Catalogue options, or the troupe's list where it has one.
    options: list[str]
    from_troupe: bool
    # Whether free text ("Custom") is allowed.
    custom: bool
    held: list[tuple[str, str]]  # name, detail
    parent_rating: int


def troupe_options(db: Session, troupe_id: uuid.UUID | None) -> dict[str, list[str]]:
    if troupe_id is None:
        return {}
    found: dict[str, list[str]] = {}
    for row in db.scalars(
        select(TroupeSpecialization)
        .where(TroupeSpecialization.troupe_id == troupe_id)
        .order_by(TroupeSpecialization.name)
    ):
        found.setdefault(row.category_key, []).append(row.name)
    return found


def kinds(db: Session, character: Character) -> list[Kind]:
    """Every kind of specialisation, with what the character holds and can choose."""
    rules = rules_for(db, character)
    lists = troupe_options(db, rules_troupe(character))
    rows = sheet_rows(db, character)
    found: list[Kind] = []
    for category in rules.rule_set.categories.values():
        if not category.specializes:
            continue
        catalogue = sorted(n for (c, n) in rules.rule_set.traits if c == category.key)
        listed = lists.get(category.key)
        parent = next(
            (
                r
                for r in rows
                if r.category.key == category.specializes["category"]
                and r.definition.name == category.specializes["name"]
            ),
            None,
        )
        found.append(
            Kind(
                category=category.key,
                name=category.name,
                parent_category=category.specializes["category"],
                parent_name=category.specializes["name"],
                options=listed if listed is not None else [n for n in catalogue if n != CUSTOM],
                from_troupe=listed is not None,
                custom=listed is None and CUSTOM in catalogue,
                held=[
                    (r.definition.name, r.trait.detail)
                    for r in rows
                    if r.category.key == category.key and r.trait.rating != 0
                ],
                parent_rating=(parent.trait.rating or 0) if parent else 0,
            )
        )
    return found


def check_choice(
    db: Session, character: Character, category: TraitCategory, name: str, detail: str
) -> None:
    """Where the character's troupe lists a kind's options, only those can be taken."""
    if not category.specializes:
        return
    listed = troupe_options(db, rules_troupe(character)).get(category.key)
    if listed is None:
        if name == CUSTOM and not detail.strip():
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"Say what the {category.name} is."
            )
        return
    chosen = detail.strip() if name == CUSTOM else name
    if chosen not in listed:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"This troupe's {category.name} are: {', '.join(listed)}.",
        )


def set_troupe_options(
    db: Session, user: User, troupe: Troupe, category_key: str, names: list[str]
) -> list[str]:
    """Replace a troupe's list for one kind; an empty list goes back to the catalogue's."""
    known = {
        c.key
        for c in db.scalars(select(TraitCategory).where(TraitCategory.specializes.is_not(None)))
    }
    if category_key not in known:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such kind of specialisation.")
    cleaned = sorted({n.strip() for n in names if n.strip()})
    db.execute(
        delete(TroupeSpecialization).where(
            TroupeSpecialization.troupe_id == troupe.id,
            TroupeSpecialization.category_key == category_key,
        )
    )
    for name in cleaned:
        db.add(TroupeSpecialization(troupe_id=troupe.id, category_key=category_key, name=name))
    db.flush()
    audit.record(
        db,
        user,
        "troupe.specializations",
        troupe_id=troupe.id,
        kind=category_key.replace("_", " "),
        count=len(cleaned),
    )
    return cleaned
