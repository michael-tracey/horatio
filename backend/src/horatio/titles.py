"""Titles: positions characters hold in one troupe (CONTEXT.md: Title).

A troupe's titles are its rule sets' list plus any it added. Its storytellers
and assistant storytellers give them to characters in the troupe; a title
means nothing elsewhere, and goes when the character leaves.

On the troupe's Who's Who, the court is in rank order (`court_order`): the rule
sets' titles as their data ranks them, then those that are only a name, then the
troupe's own, in the order it sets.

A title may belong to a sect and give abiding status (horatio.rules.status): the
rule sets say so for theirs, and a troupe for its own. A troupe that takes only
some sects offers only their titles and those of no sect, and a title of a sect
goes only to a character of that sect. One given before that rule, or held by a
character who has since changed sect, is kept and shown to staff as out of sect.
"""

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from horatio import audit
from horatio.models import (
    Character,
    CharacterTitle,
    CharacterTrait,
    RuleSet,
    TraitCategory,
    TraitDefinition,
    Troupe,
    TroupeTitle,
    User,
)
from horatio.rules.status import GENERAL, STATUS_CATEGORY, TitleData, titles_from
from horatio.sheets import conflict, membership, unprocessable


def rule_set_titles(db: Session) -> dict[str, TitleData]:
    """The titles of every rule set, by name, each with its sect and status."""
    found: dict[str, TitleData] = {}
    for names, rules in db.execute(select(RuleSet.titles, RuleSet.status_rules)):
        for title in titles_from([*names, *rules.get("titles", [])]):
            kept = found.get(title.name)
            # Rule sets that share a title agree on it; one that says more wins.
            if kept is None or ((title.sect or title.gives_status) and not kept.sect):
                found[title.name] = title
    return found


def house_title(title: TroupeTitle) -> TitleData:
    return TitleData(name=title.name, sect=title.sect, status=tuple(title.status))


def house_titles(db: Session, troupe_id: uuid.UUID) -> list[TroupeTitle]:
    return list(
        db.scalars(
            select(TroupeTitle)
            .where(TroupeTitle.troupe_id == troupe_id)
            .order_by(TroupeTitle.position, TroupeTitle.name)
        )
    )


def title_data(db: Session, troupe_id: uuid.UUID) -> dict[str, TitleData]:
    """Every title a troupe can give, by name: its rule sets' titles and its own,
    each with its sect and the status it gives (horatio.rules.status).

    Not narrowed to the troupe's allowed sects (`offered` is), so a title held from
    before is found here too."""
    found = rule_set_titles(db)
    for title in house_titles(db, troupe_id):
        found[title.name] = house_title(title)
    return dict(sorted(found.items()))


def offers(troupe: Troupe, title: TitleData) -> bool:
    """Whether the troupe gives titles of this one's sect: any, if it takes any sect."""
    return title.sect is None or not troupe.allowed_sects or title.sect in troupe.allowed_sects


def offered(db: Session, troupe: Troupe) -> dict[str, TitleData]:
    """The titles the troupe gives now: those of its allowed sects and of none."""
    return {n: t for n, t in title_data(db, troupe.id).items() if offers(troupe, t)}


def sect_names(db: Session) -> list[str]:
    """Every sect in the rule sets."""
    return sorted(
        set(
            db.scalars(
                select(TraitDefinition.name)
                .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
                .where(TraitCategory.key == "sect", TraitDefinition.troupe_id.is_(None))
            )
        )
    )


def troupe_sects(db: Session, troupe: Troupe) -> list[str]:
    """The sects whose titles the troupe gives: its allowed sects, or every sect."""
    return sorted(troupe.allowed_sects) if troupe.allowed_sects else sect_names(db)


def abiding_status(db: Session) -> dict[str, str]:
    """Every abiding status in the rule sets, by name, with its sect (or General)."""
    found: dict[str, str] = {}
    for name, properties in db.execute(
        select(TraitDefinition.name, TraitDefinition.properties)
        .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
        .where(TraitCategory.key == STATUS_CATEGORY, TraitDefinition.troupe_id.is_(None))
    ):
        if properties.get("type") == "Abiding":
            found[name] = properties.get("sect", GENERAL)
    return dict(sorted(found.items()))


def character_sects(db: Session, character_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Each character's sect, from its sheet as it stands. One with none is left out."""
    return {
        who: sect
        for who, sect in db.execute(
            select(CharacterTrait.character_id, TraitDefinition.name)
            .join(TraitDefinition, CharacterTrait.trait_definition_id == TraitDefinition.id)
            .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
            .where(
                TraitCategory.key == "sect", CharacterTrait.character_id.in_(list(character_ids))
            )
        )
    }


def out_of_sect(title: TitleData | None, sect: str | None) -> bool:
    """Whether a character of `sect` (None: no sect) holding `title` is out of its sect."""
    return title is not None and title.sect is not None and title.sect != sect


# --- the troupe's own titles -----------------------------------------------------------------


def check_house_title(db: Session, troupe: Troupe, sect: str | None, status: Sequence[str]) -> None:
    """A troupe's title is of one of its sects, or of none, and gives abiding status
    of that sect or general status."""
    if sect is not None and sect not in troupe_sects(db, troupe):
        raise unprocessable(f"{troupe.name} does not give {sect} titles.")
    statuses = abiding_status(db)
    for name in status:
        of = statuses.get(name)
        if of is None:
            raise unprocessable(f"{name} is not abiding status.")
        if of not in (GENERAL, sect):
            raise unprocessable(f"{name} is {of} status: only a {of} title gives it.")
    if len(set(status)) != len(status):
        raise unprocessable("A title gives each status once.")


def describe(sect: str | None, status: Sequence[str]) -> str:
    """A troupe's title in words, for the log: "Camarilla, giving Guardian"."""
    gives = f"giving {', '.join(status)}" if status else "giving no status"
    return f"{sect or 'any sect'}, {gives}"


def add_title(
    db: Session,
    staff: User,
    troupe: Troupe,
    name: str,
    sect: str | None = None,
    status: Sequence[str] = (),
) -> None:
    name = name.strip()
    if not name:
        raise unprocessable("A title needs a name.")
    if name in title_data(db, troupe.id):
        raise conflict(f"{name} is already a title here.")
    check_house_title(db, troupe, sect, status)
    last = db.scalar(
        select(func.max(TroupeTitle.position)).where(TroupeTitle.troupe_id == troupe.id)
    )
    db.add(
        TroupeTitle(
            troupe_id=troupe.id,
            name=name,
            sect=sect,
            status=list(status),
            position=(last or 0) + 1,
        )
    )
    db.flush()
    audit.record(
        db, staff, "title.added", troupe_id=troupe.id, title=name, what=describe(sect, status)
    )


def find_house_title(db: Session, troupe: Troupe, name: str) -> TroupeTitle:
    found = db.scalar(
        select(TroupeTitle).where(TroupeTitle.troupe_id == troupe.id, TroupeTitle.name == name)
    )
    if found is None:
        raise conflict("Only titles this troupe added can be changed or removed.")
    return found


def change_title(
    db: Session, staff: User, troupe: Troupe, name: str, sect: str | None, status: Sequence[str]
) -> None:
    """Change the sect and status of a title the troupe added. What it gives, it
    gives everyone who holds it."""
    found = find_house_title(db, troupe, name)
    check_house_title(db, troupe, sect, status)
    if (found.sect, found.status) == (sect, list(status)):
        return
    found.sect, found.status = sect, list(status)
    db.flush()
    audit.record(
        db, staff, "title.changed", troupe_id=troupe.id, title=name, what=describe(sect, status)
    )


def remove_title(db: Session, staff: User, troupe: Troupe, name: str) -> None:
    """Remove a title the troupe added, taking it from anyone who holds it."""
    found = find_house_title(db, troupe, name)
    db.execute(
        delete(CharacterTitle).where(
            CharacterTitle.troupe_id == troupe.id, CharacterTitle.name == name
        )
    )
    db.delete(found)
    db.flush()
    audit.record(db, staff, "title.removed_from_troupe", troupe_id=troupe.id, title=name)


# --- the court's order ------------------------------------------------------------------------


def court_order(db: Session, troupe_id: uuid.UUID) -> dict[str, tuple[int, int, str]]:
    """Each title the troupe can give, by name, with the key that puts it in its
    place at court: the rule sets' ranked titles highest first, then those that are
    only a name, by name, then the troupe's own in its order."""
    found: dict[str, tuple[int, int, str]] = {
        name: (0, title.rank, name) if title.rank is not None else (1, 0, name)
        for name, title in rule_set_titles(db).items()
    }
    for title in house_titles(db, troupe_id):
        found[title.name] = (2, title.position, title.name)
    return found


def court_key(order: dict[str, tuple[int, int, str]], name: str) -> tuple[int, int, str]:
    """A title's place at court; one no longer in the rules comes last."""
    return order.get(name, (3, 0, name))


def set_court_order(db: Session, staff: User, troupe: Troupe, names: Sequence[str]) -> None:
    """Put the troupe's own titles in this order at court, after the rule sets'."""
    own = house_titles(db, troupe.id)
    if sorted(names) != sorted(t.name for t in own):
        raise unprocessable("Name each of the troupe's own titles once.")
    if [t.name for t in own] == list(names):
        return
    by_name = {t.name: t for t in own}
    for position, name in enumerate(names, start=1):
        by_name[name].position = position
    db.flush()
    audit.record(db, staff, "title.court_order", troupe_id=troupe.id, order=", ".join(names))


# --- who holds what --------------------------------------------------------------------------


def held(db: Session, troupe_id: uuid.UUID, character_id: uuid.UUID) -> list[str]:
    return list(
        db.scalars(
            select(CharacterTitle.name)
            .where(
                CharacterTitle.troupe_id == troupe_id, CharacterTitle.character_id == character_id
            )
            .order_by(CharacterTitle.name)
        )
    )


@dataclass(frozen=True)
class Holding:
    title: str
    character: Character
    # The character's sect, from its sheet; None if it has none.
    sect: str | None
    out_of_sect: bool


def holdings(db: Session, troupe_id: uuid.UUID) -> list[Holding]:
    """Who holds which title in the troupe, by title and then character name."""
    rows = list(
        db.execute(
            select(CharacterTitle.name, Character)
            .join(Character, CharacterTitle.character_id == Character.id)
            .where(CharacterTitle.troupe_id == troupe_id)
            .order_by(CharacterTitle.name, Character.name)
        )
    )
    known = title_data(db, troupe_id)
    sects = character_sects(db, {c.id for _, c in rows})
    return [
        Holding(name, c, sects.get(c.id), out_of_sect(known.get(name), sects.get(c.id)))
        for name, c in rows
    ]


def set_titles(
    db: Session, staff: User, troupe: Troupe, character: Character, names: Sequence[str]
) -> list[str]:
    """Give `character` exactly these titles in `troupe`. A new one must be one the
    troupe gives, and of the character's sect if it has a sect. One it holds
    already stays, even out of sect."""
    if membership(db, character, troupe.id) is None:
        raise conflict("Titles are only for characters in this troupe.")
    before = set(held(db, troupe.id, character.id))
    after = set(names)
    given = offered(db, troupe)
    unknown = after - before - set(given)
    if unknown:
        raise unprocessable(
            f"Not a title here: {', '.join(sorted(unknown))}. Add it to the troupe first."
        )
    sect = character_sects(db, [character.id]).get(character.id)
    for name in sorted(after - before):
        title = given[name]
        if out_of_sect(title, sect):
            raise conflict(
                f"{name} is a {title.sect} title, and {character.name} "
                + (f"is {sect}." if sect else "has no sect.")
            )
    for name in before - after:
        db.execute(
            delete(CharacterTitle).where(
                CharacterTitle.troupe_id == troupe.id,
                CharacterTitle.character_id == character.id,
                CharacterTitle.name == name,
            )
        )
        audit.record(
            db, staff, "title.taken", troupe_id=troupe.id, character_id=character.id, title=name
        )
    for name in after - before:
        db.add(CharacterTitle(troupe_id=troupe.id, character_id=character.id, name=name))
        audit.record(
            db, staff, "title.given", troupe_id=troupe.id, character_id=character.id, title=name
        )
    db.flush()
    return sorted(after)


def drop_all(db: Session, troupe_id: uuid.UUID, character_id: uuid.UUID) -> None:
    """A character leaving a troupe leaves its titles there."""
    db.execute(
        delete(CharacterTitle).where(
            CharacterTitle.troupe_id == troupe_id, CharacterTitle.character_id == character_id
        )
    )
