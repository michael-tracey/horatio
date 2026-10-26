"""A ghoul's domitor: the vampire it is bound to (MET: VTM pp. 296–297).

A ghoul has no clan of its own. It takes its domitor's clan and bloodline, which
its sheet holds as its clan trait, and its disciplines are its domitor's in-clan
ones, in powers the domitor has. The domitor can be a vampire PC or NPC in
Horatio, linked, or one that is not, by name: then the player names its clan
and bloodline, and staff check the powers at approval.

A Caitiff has no in-clan disciplines from its clan, but three it chose (p. 246), so
a Caitiff's ghoul has those three. Its sheet holds them, in a category of their
own: a linked domitor's as it chose them, kept in step when it changes them, and
for one not in Horatio the three its player names, which staff check at approval.

Before a home troupe accepts the ghoul, its player sets the domitor; after, the
home troupe's running staff do, when the old bond has faded and the ghoul is
fully bound to a new one (p. 297). Its player then keeps the discipline dots, or
moves all of them to the new domitor's in-clan disciplines.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import delete, event, exists, func, inspect, select
from sqlalchemy.orm import Session

from horatio import audit
from horatio.models import Character, CharacterTrait, TraitCategory, TraitDefinition, User
from horatio.permissions import viewable_characters
from horatio.rules.model import SheetTrait
from horatio.rules.splats import DOMITOR_IN_CLAN, SPLATS
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

# The clan with no in-clan disciplines of its own, and how many each one chooses
# instead (p. 246).
CAITIFF = "Caitiff"
CAITIFF_CHOOSES = 3


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
    # The domitor's in-clan disciplines, which are the ghoul's: its clan's, or a
    # Caitiff's three.
    in_clan: list[str]


def has_domitor(character: Character) -> bool:
    return SPLATS[character.splat].has_domitor


def domitor_info(db: Session, ghoul: Character) -> DomitorInfo | None:
    """The ghoul's domitor, or None while it has none (or for a vampire)."""
    linked = db.get(Character, ghoul.domitor_id) if ghoul.domitor_id is not None else None
    if linked is None and not ghoul.domitor_name:
        return None
    rows = sheet_rows(db, ghoul)
    clan = next((r.definition.name for r in rows if r.category.key == "clan"), None)
    in_clan = SPLATS[ghoul.splat].in_clan(rules_for(db, ghoul), [r.as_rules_trait() for r in rows])
    return DomitorInfo(
        linked, linked.name if linked is not None else ghoul.domitor_name, clan, in_clan
    )


@dataclass(frozen=True)
class Candidate:
    """A vampire a ghoul could be bound to, with what the ghoul would take from it."""

    character: Character
    clan: str
    in_clan: list[str]


# The most vampires one search for a domitor finds.
CANDIDATES = 20


def candidates(db: Session, user: User, ghoul: Character, query: str = "") -> list[Candidate]:
    """The vampires `user` can see whose names hold `query`, that the ghoul could be
    bound to: those with a clan, and not retired. For each, the in-clan disciplines
    the ghoul would have: its clan's, or a Caitiff's three."""
    vampires = [key for key, splat in SPLATS.items() if not splat.has_domitor]
    has_clan = exists(
        select(CharacterTrait.id)
        .join(TraitDefinition, CharacterTrait.trait_definition_id == TraitDefinition.id)
        .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
        .where(CharacterTrait.character_id == Character.id, TraitCategory.key == "clan")
    )
    found = db.scalars(
        select(Character)
        .where(
            viewable_characters(user),
            Character.splat.in_(vampires),
            Character.status != "retired",
            Character.id != ghoul.id,
            func.lower(Character.name).contains(query.strip().lower(), autoescape=True),
            has_clan,
        )
        .order_by(func.lower(Character.name))
        .limit(CANDIDATES)
    )
    rule_set = rules_for(db, ghoul).rule_set
    out: list[Candidate] = []
    for vampire in found:
        clan = next(r.definition.name for r in sheet_rows(db, vampire) if r.category.key == "clan")
        own = rule_set.trait_properties("clan", clan).get("in_clan", [])
        out.append(Candidate(vampire, clan, [*own, *caitiff_three(db, vampire)]))
    return out


def caitiff_three(db: Session, vampire: Character) -> list[str]:
    """A Caitiff's three in-clan disciplines (p. 246), as it chose them among its
    extra in-clan disciplines; none for a vampire of any other clan. Not one another
    trait gives (Web of Knives' Potence), nor the fourth a merit adds (Additional
    Common Discipline, p. 248): with more than three chosen, those beyond the three
    are the ones on a held merit's list, the last chosen first."""
    rows = sheet_rows(db, vampire)
    if not any(r.category.key == "clan" and r.definition.name == CAITIFF for r in rows):
        return []
    chosen = sorted(
        (
            r
            for r in rows
            if r.category.key == "extra_in_clan_disciplines"
            and (r.trait.rating or 0) > 0
            and r.trait.granted_rating < (r.trait.rating or 0)
        ),
        # Ids are UUID v7, so in the order the rows were made.
        key=lambda r: r.trait.id,
    )
    merits = {r.definition.name for r in rows if r.category.key == "merits"}
    # What the merits that add a fourth let it be (their grants say: it takes no free dot).
    from_merits = {
        name
        for g in rules_for(db, vampire).rule_set.grants
        if g.kind == "no_free_dot"
        and g.source.get("category") == "merits"
        and g.source.get("name") in merits
        and g.target.get("category") == "extra_in_clan_disciplines"
        for name in g.target.get("names", [])
    }
    kept = sorted(chosen, key=lambda r: (r.definition.name in from_merits, r.trait.id))[
        :CAITIFF_CHOOSES
    ]
    return [r.definition.name for r in chosen if r in kept]


def named_three(db: Session, ghoul: Character, clan: str, in_clan: Sequence[str]) -> list[str]:
    """The in-clan disciplines a domitor not in Horatio chose: three, named by the
    ghoul's player, for a Caitiff; none for any other clan, whose are its clan's."""
    names = [n.strip() for n in in_clan]
    if clan != CAITIFF:
        if names:
            raise unprocessable(
                "Only a Caitiff domitor's in-clan disciplines are named; a clan's are its own."
            )
        return []
    if len(names) != CAITIFF_CHOOSES or len(set(names)) != CAITIFF_CHOOSES:
        raise unprocessable(
            f"Name the {CAITIFF_CHOOSES} in-clan disciplines the Caitiff domitor chose, each once."
        )
    for name in names:
        try:
            find_definition(db, ghoul, DOMITOR_IN_CLAN, name)
        except HTTPException as error:
            raise unprocessable(f"{name} is not a discipline a Caitiff can choose.") from error
    return names


def set_domitor(
    db: Session,
    user: User,
    ghoul: Character,
    *,
    domitor: Character | None,
    name: str = "",
    clan: str | None = None,
    in_clan: Sequence[str] = (),
    disciplines: Literal["keep", "move"] = "keep",
    moved: Sequence[Placed] = (),
) -> None:
    """Bind the ghoul to `domitor`, or to one not in Horatio called `name`, of `clan`
    (and for a Caitiff, the three disciplines `in_clan` it chose). Its clan and
    in-clan disciplines become the domitor's. Its discipline dots stay where they
    are, or with `disciplines` "move" go where `moved` says: all of them, and only
    to the new domitor's in-clan disciplines, in powers a linked domitor has."""
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
        if in_clan:
            raise unprocessable("A domitor in Horatio has its own in-clan disciplines.")
        name = ""
        three = caitiff_three(db, domitor)
    else:
        name = name.strip()
        if not name:
            raise unprocessable("Name the domitor, or choose one in Horatio.")
        if clan is None:
            raise unprocessable("Choose the domitor's clan and bloodline.")
        three = named_three(db, ghoul, clan, in_clan)
    definition, _ = find_definition(db, ghoul, "clan", clan)
    placing: list[tuple[TraitDefinition, Placed]] = []
    if disciplines == "move":
        powers = as_domitor(db, domitor) if domitor is not None else None
        placing = planned_moves(db, ghoul, clan, three, powers, moved)
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
    place_in_clan(db, ghoul, three)
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
        in_clan=three,
        disciplines="moved" if disciplines == "move" else "kept",
    )


def place_in_clan(db: Session, ghoul: Character, names: Sequence[str]) -> None:
    """Hold these as the domitor's in-clan disciplines on the ghoul's sheet, and no
    others: a dot each, free, as a vampire's extra in-clan disciplines are held."""
    rows = [r for r in sheet_rows(db, ghoul) if r.category.key == DOMITOR_IN_CLAN]
    if sorted(r.definition.name for r in rows) == sorted(names):
        return
    for row in rows:
        if row.definition.name not in names:
            db.delete(row.trait)
    held = {r.definition.name for r in rows}
    for name in names:
        if name not in held:
            found, _ = find_definition(db, ghoul, DOMITOR_IN_CLAN, name)
            db.add(
                CharacterTrait(
                    character_id=ghoul.id, trait_definition_id=found.id, rating=1, free_rating=1
                )
            )
    db.flush()


def follow_domitor(db: Session, ghoul: Character) -> None:
    """Keep a ghoul's in-clan disciplines its linked domitor's, as the domitor's
    player changes the three a Caitiff chose."""
    if ghoul.domitor_id is not None:
        place_in_clan(db, ghoul, caitiff_three(db, db.get_one(Character, ghoul.domitor_id)))


# Which characters' sheets the session has changed since it last committed: when a
# domitor's are among them, its ghouls follow it as the change is committed.
CHANGED_SHEETS = "horatio.domitors.changed"


@event.listens_for(Session, "before_flush")
def note_changed_sheets(session: Session, *_: object) -> None:
    changed: set[uuid.UUID] = session.info.setdefault(CHANGED_SHEETS, set())
    for found in (*session.new, *session.dirty, *session.deleted):
        # Read without loading: a flush cannot load what it is about to write.
        if isinstance(found, CharacterTrait) and (
            character_id := inspect(found).dict.get("character_id")
        ):
            changed.add(character_id)


@event.listens_for(Session, "before_commit")
def follow_domitors(session: Session) -> None:
    session.flush()
    changed = session.info.pop(CHANGED_SHEETS, set())
    if changed:
        for ghoul in session.scalars(select(Character).where(Character.domitor_id.in_(changed))):
            follow_domitor(session, ghoul)
        session.info.pop(CHANGED_SHEETS, None)


@event.listens_for(Session, "after_soft_rollback")
def forget_changed_sheets(session: Session, *_: object) -> None:
    session.info.pop(CHANGED_SHEETS, None)


def planned_moves(
    db: Session,
    ghoul: Character,
    clan: str,
    three: Sequence[str],
    domitor: Domitor | None,
    moved: Sequence[Placed],
) -> list[tuple[TraitDefinition, Placed]]:
    """Where the ghoul's discipline dots go, checked against its new domitor (p. 297):
    as many as it has, in the domitor's in-clan disciplines (its clan's, or the
    `three` a Caitiff chose), none above what a linked domitor has."""
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
    sheet = (
        [
            r.as_rules_trait()
            for r in sheet_rows(db, ghoul)
            if r.category.key not in ("disciplines", "clan", DOMITOR_IN_CLAN)
        ]
        + [SheetTrait("clan", clan)]
        + [SheetTrait(DOMITOR_IN_CLAN, n, 1) for n in three]
    )
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
