"""A troupe's own changes to book traits: its storytellers ban a merit, flaw, power,
ritual, technique, path, background, clan or bloodline in the troupe, with a reason
its players see (issue #431), give any of them wording of the troupe's own
(issue #433), added to the book's summary or in its place, and move a merit or flaw
to another category (issue #436), such as a sect flaw made a general one.

The changes are kept one row per troupe and trait (`TraitOverride`), and read into
the troupe's rules where they are put together (horatio.rules.store), so whatever
reads the rules follows them. A ban is a check of its own there
(horatio.rules.checks.ban_check), refusing the trait as any refusing check does: it
cannot be bought or picked, at creation or after, and lists show it greyed with the
reason. Characters who already hold it keep it; their sheet lists it under "Against
the rules", staff see who holds a banned trait (`holders`), and an exception can
still let one character have it. Staff building an NPC may use a banned trait.

House wording is the troupe's own text, in Markdown, never the book's: players read
it wherever they read the trait, marked as the troupe's, with the book's page still
shown. A character plays by its home troupe's rules, so it reads that troupe's.

A merit or flaw's category is its catalogue type, which every rule tied to the type
reads: `kind` checks, the clan merit values and the grants that ask for a type. The
troupe's rules read it swapped, so all of those follow. A clan merit moved out of
Clan leaves its clan requirement behind; its own checks stay. Characters who hold it
keep it, and a check it newly breaks is flagged on their sheet, not enforced.
"""

import uuid
from dataclasses import dataclass
from typing import NoReturn

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit
from horatio.models import (
    Character,
    CharacterTrait,
    RuleSet,
    TraitCategory,
    TraitDefinition,
    TraitException,
    TraitOverride,
    Troupe,
    User,
)
from horatio.rules.checks import BAN_KEY
from horatio.rules.model import TraitChangeData
from horatio.rules.splats import SPLATS
from horatio.rules.store import change_book_trait, read_troupe_rules
from horatio.sheets import sheet_rows


def splats_of(troupe: Troupe) -> list[str]:
    """The splats whose traits the troupe can change: Vampire, and the others it takes."""
    return ["vampire", *(s for s in troupe.allowed_splats if s != "vampire" and s in SPLATS)]


def book_definition(db: Session, splat: str, category: str, name: str) -> TraitDefinition:
    """The rule set's own trait of that name, still in its files: never a troupe's
    house merit, which its troupe changes as it likes (horatio.house_traits)."""
    found = db.scalar(
        select(TraitDefinition)
        .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
        .join(RuleSet, TraitCategory.rule_set_id == RuleSet.id)
        .where(
            RuleSet.splat == splat,
            TraitCategory.key == category,
            TraitCategory.derived.is_(False),
            TraitDefinition.name == name,
            TraitDefinition.troupe_id.is_(None),
            TraitDefinition.retired.is_(False),
        )
    )
    if found is None:
        no_such_trait()
    return found


def no_such_trait() -> NoReturn:
    raise HTTPException(status.HTTP_404_NOT_FOUND, "No such trait in the book.")


def changes(db: Session, troupe: Troupe) -> list[tuple[str, TraitChangeData]]:
    """The troupe's changes to book traits, each with its splat, by splat, category
    and name."""
    found: list[tuple[str, TraitChangeData]] = []
    for splat in splats_of(troupe):
        rules = read_troupe_rules(db, splat, troupe.id)
        position = {key: n for n, key in enumerate(rules.rule_set.categories)}
        found += [
            (splat, c)
            for c in sorted(
                rules.trait_changes.values(), key=lambda c: (position[c.category], c.name)
            )
        ]
    return found


def change_of(db: Session, troupe: Troupe, splat: str, category: str, name: str) -> TraitChangeData:
    """The troupe's change to one book trait, as its rules now read it: no change at
    all where it has none."""
    found = read_troupe_rules(db, splat, troupe.id).trait_changes.get((category, name))
    return found or TraitChangeData(category=category, name=name)


def set_ban(
    db: Session,
    user: User,
    troupe: Troupe,
    splat: str,
    definition: TraitDefinition,
    category: str,
    *,
    banned: bool,
    reason: str,
) -> None:
    """Ban a book trait in the troupe, with the reason its players see, or lift the
    ban. Nothing changes on the sheets of those who hold it."""
    before = change_of(db, troupe, splat, category, definition.name)
    reason = reason.strip() if banned else ""
    if (before.banned, before.ban_reason) == (banned, reason):
        return
    change_book_trait(db, troupe.id, definition.id, {"banned": banned, "ban_reason": reason})
    what = for_splat(definition.name, splat)
    if banned:
        audit.record(
            db, user, "house.trait_banned", troupe_id=troupe.id, what=what, reason=reason or "none"
        )
    else:
        audit.record(db, user, "house.trait_unbanned", troupe_id=troupe.id, what=what)


def set_wording(
    db: Session,
    user: User,
    troupe: Troupe,
    splat: str,
    definition: TraitDefinition,
    category: str,
    *,
    wording: str,
    mode: str,
) -> None:
    """Give a book trait the troupe's own wording, added to the book's summary or in
    its place, or (with none) take it away."""
    before = change_of(db, troupe, splat, category, definition.name)
    wording = wording.strip()
    if not wording:
        mode = "added"
    if (before.wording, before.wording_mode) == (wording, mode):
        return
    change_book_trait(db, troupe.id, definition.id, {"wording": wording, "wording_mode": mode})
    what = for_splat(definition.name, splat)
    if not wording:
        audit.record(db, user, "house.trait_wording_removed", troupe_id=troupe.id, what=what)
    else:
        audit.record(
            db,
            user,
            "house.trait_worded",
            troupe_id=troupe.id,
            what=what,
            how="in place of the book's" if mode == "replaces" else "added to the book's",
        )


# The categories whose traits have a catalogue type a troupe can change.
TYPED = ("merits", "flaws")


def book_kinds(db: Session, splat: str, category: str) -> list[str]:
    """The catalogue types the book gives the traits of a category, in order: what a
    troupe can move one of them to."""
    found = db.scalars(
        select(TraitDefinition.properties["type"].astext)
        .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
        .join(RuleSet, TraitCategory.rule_set_id == RuleSet.id)
        .where(
            RuleSet.splat == splat,
            TraitCategory.key == category,
            TraitDefinition.troupe_id.is_(None),
            TraitDefinition.retired.is_(False),
        )
        .distinct()
    )
    return sorted(k for k in found if k)


def set_kind(
    db: Session,
    user: User,
    troupe: Troupe,
    splat: str,
    definition: TraitDefinition,
    category: str,
    *,
    kind: str | None,
) -> None:
    """Move a merit or flaw to another of the book's categories in the troupe, or
    (None, or the book's own) back to the book's."""
    book = definition.properties.get("type")
    if category not in TYPED or not book:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Only a merit or flaw's category changes."
        )
    if kind is not None and kind not in book_kinds(db, splat, category):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"No category {kind!r}.")
    kind = None if kind == book else kind
    if change_of(db, troupe, splat, category, definition.name).kind == kind:
        return
    change_book_trait(db, troupe.id, definition.id, {"kind": kind})
    what = for_splat(definition.name, splat)
    if kind is None:
        audit.record(
            db, user, "house.trait_category_restored", troupe_id=troupe.id, what=what, book=book
        )
    else:
        audit.record(
            db,
            user,
            "house.trait_recategorised",
            troupe_id=troupe.id,
            what=what,
            kind=kind,
            book=book,
        )


def for_splat(name: str, splat: str) -> str:
    """A trait as the troupe log names it: "Passion Play", or for another splat than
    Vampire, "Passion Play for ghouls"."""
    return name if splat == "vampire" else f"{name} for {SPLATS[splat].label.lower()}s"


@dataclass(frozen=True)
class Holder:
    """A character playing by the troupe's rules who holds a trait it bans."""

    character_id: uuid.UUID
    character_name: str
    splat: str
    category: str
    name: str
    detail: str
    # An exception lets this character have it (horatio.trait_exceptions).
    excepted: bool


def holders(db: Session, troupe: Troupe) -> list[Holder]:
    """Every player character playing by the troupe's rules (its own, and those being
    built for it) that holds a trait the troupe bans, by character: for staff to deal
    with one by one, as nothing changes on their sheets by itself."""
    rows = db.execute(
        select(Character, CharacterTrait, TraitDefinition, TraitCategory.key, RuleSet.splat)
        .join(CharacterTrait, CharacterTrait.character_id == Character.id)
        .join(TraitDefinition, CharacterTrait.trait_definition_id == TraitDefinition.id)
        .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
        .join(RuleSet, TraitCategory.rule_set_id == RuleSet.id)
        .join(
            TraitOverride,
            (TraitOverride.trait_definition_id == TraitDefinition.id)
            & (TraitOverride.troupe_id == troupe.id),
        )
        .where(
            TraitOverride.banned.is_(True),
            Character.kind == "pc",
            Character.status == "active",
            (Character.home_troupe_id == troupe.id)
            | (Character.home_troupe_id.is_(None) & (Character.building_troupe_id == troupe.id)),
            CharacterTrait.rating.is_(None) | (CharacterTrait.rating != 0),
        )
        .order_by(Character.name, Character.id, TraitDefinition.name)
    ).all()
    excepted = {
        e.character_trait_id
        for e in db.scalars(
            select(TraitException).where(
                TraitException.character_trait_id.in_([t.id for _, t, _, _, _ in rows])
            )
        )
        if any(c["key"].startswith(BAN_KEY) for c in e.checks)
    }
    return [
        Holder(
            character_id=character.id,
            character_name=character.name,
            splat=splat,
            category=category,
            name=definition.name,
            detail=trait.detail,
            excepted=trait.id in excepted,
        )
        for character, trait, definition, category, splat in rows
    ]


def banned_held(db: Session, troupe_id: uuid.UUID, character: Character) -> list[str]:
    """The traits the character holds that the troupe bans, by name: what accepting it
    as home would bring in, for the approval to flag."""
    rules = read_troupe_rules(db, character.splat, troupe_id)
    return [
        r.as_rules_trait().full_name
        for r in sheet_rows(db, character)
        if r.trait.rating != 0 and rules.banned(r.category.key, r.definition.name)
    ]
