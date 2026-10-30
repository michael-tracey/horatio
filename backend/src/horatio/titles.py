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

**Players choose their characters' titles** from those their home troupe offers
of their sect, on the character's Status & Titles tab, unless the troupe's
"Titles on sheets" setting (Troupe.titles_by) keeps titles to its running staff.
Staff are told of each choice (horatio.notifications). A `unique` title (a Prince)
is one no player can choose while another character in the troupe holds it; staff
can still give it.

**One title is active.** Of the titles a character holds in a troupe, at most one
is active, and only it gives status (horatio.sect_status): a character carries the
status of one abiding source into a game (MET: VTM pp. 311, 313). The first title
it holds there becomes active; another becomes active only when chosen so. When
the active title goes, none is active until one is chosen.
"""

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal, get_args

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from horatio import audit, notifications
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
from horatio.permissions import TroupeAction, allows, troupe_role
from horatio.rules.status import GENERAL, STATUS_CATEGORY, TitleData, titles_from
from horatio.sheets import conflict, membership, unprocessable

# Titles on sheets: who chooses the titles of a troupe's characters.
Setting = Literal["players", "staff"]
SETTINGS: tuple[str, ...] = get_args(Setting)
SETTING_TEXT = {
    "players": "players choose their characters' titles",
    "staff": "only staff give titles",
}
# Who is choosing on the character's tab: its player, or staff.
Acting = Literal["player", "staff"]


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
    return TitleData(
        name=title.name, sect=title.sect, status=tuple(title.status), unique=title.unique
    )


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


def describe(sect: str | None, status: Sequence[str], unique: bool = False) -> str:
    """A troupe's title in words, for the log: "Camarilla, giving Guardian"."""
    gives = f"giving {', '.join(status)}" if status else "giving no status"
    one = ", held by one character at a time" if unique else ""
    return f"{sect or 'any sect'}, {gives}{one}"


def add_title(
    db: Session,
    staff: User,
    troupe: Troupe,
    name: str,
    sect: str | None = None,
    status: Sequence[str] = (),
    unique: bool = False,
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
            unique=unique,
        )
    )
    db.flush()
    audit.record(
        db,
        staff,
        "title.added",
        troupe_id=troupe.id,
        title=name,
        what=describe(sect, status, unique),
    )


def find_house_title(db: Session, troupe: Troupe, name: str) -> TroupeTitle:
    found = db.scalar(
        select(TroupeTitle).where(TroupeTitle.troupe_id == troupe.id, TroupeTitle.name == name)
    )
    if found is None:
        raise conflict("Only titles this troupe added can be changed or removed.")
    return found


def change_title(
    db: Session,
    staff: User,
    troupe: Troupe,
    name: str,
    sect: str | None,
    status: Sequence[str],
    unique: bool = False,
) -> None:
    """Change the sect and status of a title the troupe added, and whether only one
    character holds it. What it gives, it gives everyone who holds it."""
    found = find_house_title(db, troupe, name)
    check_house_title(db, troupe, sect, status)
    if (found.sect, found.status, found.unique) == (sect, list(status), unique):
        return
    found.sect, found.status, found.unique = sect, list(status), unique
    db.flush()
    audit.record(
        db,
        staff,
        "title.changed",
        troupe_id=troupe.id,
        title=name,
        what=describe(sect, status, unique),
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


def active_title(db: Session, troupe_id: uuid.UUID, character_id: uuid.UUID) -> str | None:
    """The title the character holds in the troupe that gives it status, if any."""
    return db.scalar(
        select(CharacterTitle.name).where(
            CharacterTitle.troupe_id == troupe_id,
            CharacterTitle.character_id == character_id,
            CharacterTitle.active,
        )
    )


def active_titles(db: Session, troupe_id: uuid.UUID) -> dict[uuid.UUID, str]:
    """Each character's active title in the troupe, by character."""
    return {
        who: name
        for who, name in db.execute(
            select(CharacterTitle.character_id, CharacterTitle.name).where(
                CharacterTitle.troupe_id == troupe_id, CharacterTitle.active
            )
        )
    }


@dataclass(frozen=True)
class Holding:
    title: str
    character: Character
    # The character's sect, from its sheet; None if it has none.
    sect: str | None
    out_of_sect: bool
    # The one of its titles here that gives it status.
    active: bool = False


def holdings(db: Session, troupe_id: uuid.UUID) -> list[Holding]:
    """Who holds which title in the troupe, by title and then character name."""
    rows = list(
        db.execute(
            select(CharacterTitle.name, CharacterTitle.active, Character)
            .join(Character, CharacterTitle.character_id == Character.id)
            .where(CharacterTitle.troupe_id == troupe_id)
            .order_by(CharacterTitle.name, Character.name)
        )
    )
    known = title_data(db, troupe_id)
    sects = character_sects(db, {c.id for _, _, c in rows})
    return [
        Holding(name, c, sects.get(c.id), out_of_sect(known.get(name), sects.get(c.id)), active)
        for name, active, c in rows
    ]


def make_active(
    db: Session, troupe_id: uuid.UUID, character_id: uuid.UUID, name: str | None
) -> None:
    """Make `name` the character's active title in the troupe; None, none."""
    mine = (CharacterTitle.troupe_id == troupe_id, CharacterTitle.character_id == character_id)
    db.execute(update(CharacterTitle).where(*mine, CharacterTitle.active).values(active=False))
    db.flush()
    if name is not None:
        db.execute(
            update(CharacterTitle).where(*mine, CharacterTitle.name == name).values(active=True)
        )
    db.flush()


def set_titles(
    db: Session, staff: User, troupe: Troupe, character: Character, names: Sequence[str]
) -> list[str]:
    """Give `character` exactly these titles in `troupe`. A new one must be one the
    troupe gives, and of the character's sect if it has a sect. One it holds
    already stays, even out of sect. A character that held none here makes the
    highest of its new titles active; the active one taken leaves none active."""
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
    if after - before and not before & after:
        order = court_order(db, troupe.id)
        make_active(db, troupe.id, character.id, min(after, key=lambda n: court_key(order, n)))
    return sorted(after)


# --- choosing on the character's tab ----------------------------------------------------------


def setting_of(troupe: Troupe | None) -> str:
    return troupe.titles_by if troupe is not None else "players"


def home_of(db: Session, character: Character) -> Troupe | None:
    """The troupe whose titles the character chooses from: a PC's home troupe, or
    the troupe an NPC belongs to."""
    troupe_id = character.home_troupe_id or character.owner_troupe_id
    return db.get(Troupe, troupe_id) if troupe_id else None


def is_player(user: User, character: Character) -> bool:
    return character.kind == "pc" and character.player_id == user.id


def may_choose(
    db: Session,
    user: User,
    character: Character,
    troupe: Troupe | None,
    *,
    setting: str | None = None,
) -> Acting | None:
    """Whether `user` chooses the character's titles in its home troupe, and as whom:
    its player, where players choose their own, or the troupe's running staff."""
    if troupe is None or character.status != "active":
        return None
    if troupe.archived_at is not None or membership(db, character, troupe.id) is None:
        return None
    if is_player(user, character) and (setting or setting_of(troupe)) == "players":
        return "player"
    if allows(
        troupe_role(db, user, troupe), TroupeAction.MANAGE_TITLES, is_custodian=user.is_custodian
    ):
        return "staff"
    return None


def may_switch(
    db: Session, user: User, character: Character, troupe: Troupe | None
) -> Acting | None:
    """Whether `user` chooses which of the character's titles is active, and as
    whom: its player, even where only staff give titles (which source it carries
    into a game is the character's to choose, p. 311), or staff."""
    return may_choose(db, user, character, troupe, setting="players")


def require_choose(
    db: Session, user: User, character: Character, *, switching: bool = False
) -> tuple[Troupe, Acting]:
    troupe = home_of(db, character)
    if troupe is None:
        raise conflict(f"{character.name} has no home troupe: titles are held in a troupe.")
    acting = (may_switch if switching else may_choose)(db, user, character, troupe)
    if acting is None:
        if is_player(user, character) and setting_of(troupe) == "staff":
            raise conflict(f"In {troupe.name}, only staff give titles.")
        raise conflict(f"You cannot change {character.name}'s titles.")
    return troupe, acting


def holders_of(db: Session, troupe_id: uuid.UUID, name: str) -> list[Character]:
    return list(
        db.scalars(
            select(Character)
            .join(CharacterTitle, CharacterTitle.character_id == Character.id)
            .where(CharacterTitle.troupe_id == troupe_id, CharacterTitle.name == name)
            .order_by(Character.name)
        )
    )


def named(title: TitleData | None, name: str) -> str:
    """A title with its sect: "Harpy (Camarilla)"."""
    return f"{name} ({title.sect})" if title is not None and title.sect else name


def gives_words(title: TitleData | None) -> list[str]:
    """The status a title gives, as a line names it: "Noble", "Blessed or Enforcer"."""
    if title is None:
        return []
    found = list(title.status)
    if title.choose_one:
        found.append(" or ".join(title.choose_one))
    for absent in title.while_absent:
        found += [f"{s} while the {absent.title} is away" for s in absent.status]
    return found


def change_words(gained: TitleData | None, lost: TitleData | None) -> str:
    """The status a switch gains and loses: "+Enforcer, −Prominent". Empty for none."""
    new, old = gives_words(gained), gives_words(lost)
    return ", ".join(
        [f"+{s}" for s in new if s not in old] + [f"−{s}" for s in old if s not in new]
    )


def tell_staff(
    db: Session, user: User, troupe: Troupe, character: Character, kind: str, summary: str
) -> None:
    """Tell the troupe's storytellers and assistant storytellers what the player did."""
    staff = [
        s for s in notifications.staff_for(db, troupe, TroupeAction.MANAGE_TITLES) if s != user.id
    ]
    notifications.notify(
        db,
        staff,
        kind,
        summary,
        f"/characters/{character.id}/status",
        troupe_id=troupe.id,
        character_id=character.id,
    )


def choose(
    db: Session, user: User, character: Character, name: str, *, active: bool = False
) -> None:
    """The character takes a title its home troupe offers of its sect, as its player
    (where players choose their own) or staff. The first title it holds becomes
    active; another, only if `active`. A unique title another character holds is
    staff's to give."""
    troupe, acting = require_choose(db, user, character)
    title = offered(db, troupe).get(name)
    if title is None:
        raise unprocessable(f"{troupe.name} does not offer the title {name}.")
    sect = character_sects(db, [character.id]).get(character.id)
    if out_of_sect(title, sect):
        raise conflict(
            f"{name} is a {title.sect} title, and {character.name} "
            + (f"is {sect}." if sect else "has no sect.")
        )
    before = held(db, troupe.id, character.id)
    if name in before:
        raise conflict(f"{character.name} holds {name} already.")
    others = [c for c in holders_of(db, troupe.id, name) if c.id != character.id]
    if title.unique and others and acting == "player":
        raise conflict(
            f"{others[0].name} holds {name}, and only one character holds it at a time:"
            " ask your storytellers."
        )
    was = active_title(db, troupe.id, character.id)
    db.add(CharacterTitle(troupe_id=troupe.id, character_id=character.id, name=name))
    db.flush()
    becomes = active or not before
    if becomes:
        make_active(db, troupe.id, character.id, name)
    data = title_data(db, troupe.id)
    old = data.get(was) if was and becomes else None
    if becomes and was:
        what = f"active, in place of {was}"
    elif becomes:
        what = "active"
    elif was:
        what = f"not active: {was} stays active"
    else:
        what = "not active: no title is"
    audit.record(
        db,
        user,
        "title.chosen" if acting == "player" else "title.given",
        troupe_id=troupe.id,
        character_id=character.id,
        title=name,
        what=what,
    )
    if acting != "player":
        return
    took = f"{character.name} took the title {named(title, name)}"
    change = change_words(title, old) if becomes else ""
    if becomes and was:
        summary = f"{took} and made it active in place of {was}"
    elif becomes:
        summary = took
    elif was:
        summary = f"{took} beside {was}, which stays active"
    else:
        summary = f"{took}; no title is active"
    if becomes:
        summary += f": {change}" if change else ", which gives no status"
    tell_staff(db, user, troupe, character, "title.chosen", summary)


def switch(db: Session, user: User, character: Character, name: str) -> None:
    """Make a title the character holds in its home troupe its active one: its status
    in place of the old one's. Its player can, even where only staff give titles."""
    troupe, acting = require_choose(db, user, character, switching=True)
    if name not in held(db, troupe.id, character.id):
        raise unprocessable(f"{character.name} does not hold {name}.")
    was = active_title(db, troupe.id, character.id)
    if was == name:
        return
    make_active(db, troupe.id, character.id, name)
    audit.record(
        db,
        user,
        "title.made_active",
        troupe_id=troupe.id,
        character_id=character.id,
        title=name,
        what=f"in place of {was}" if was else "none was active",
    )
    if acting != "player":
        return
    data = title_data(db, troupe.id)
    change = change_words(data.get(name), data.get(was) if was else None)
    summary = f"{character.name} made {named(data.get(name), name)} the active title"
    summary += f", in place of {was}" if was else ""
    summary += f": {change}" if change else ""
    tell_staff(db, user, troupe, character, "title.made_active", summary)


def give_up(db: Session, user: User, character: Character, name: str) -> None:
    """The character gives up a title it holds in its home troupe, and the status it
    gave. If it was active, none is active until one is chosen."""
    troupe, acting = require_choose(db, user, character)
    row = db.scalar(
        select(CharacterTitle).where(
            CharacterTitle.troupe_id == troupe.id,
            CharacterTitle.character_id == character.id,
            CharacterTitle.name == name,
        )
    )
    if row is None:
        raise unprocessable(f"{character.name} does not hold {name}.")
    was_active = row.active
    db.delete(row)
    db.flush()
    left = held(db, troupe.id, character.id)
    if was_active:
        what = "it was active; no title is active now" if left else "it was active"
    else:
        what = "it was not active"
    if acting == "player":
        audit.record(
            db,
            user,
            "title.given_up",
            troupe_id=troupe.id,
            character_id=character.id,
            title=name,
            what=what,
        )
    else:
        audit.record(
            db, user, "title.taken", troupe_id=troupe.id, character_id=character.id, title=name
        )
        return
    data = title_data(db, troupe.id)
    summary = f"{character.name} gave up the title {named(data.get(name), name)}"
    if was_active:
        change = change_words(None, data.get(name))
        summary += f": {change}" if change else ""
        summary += "; no title is active" if left else ""
    else:
        summary += ", which was not active"
    tell_staff(db, user, troupe, character, "title.given_up", summary)


def drop_all(db: Session, troupe_id: uuid.UUID, character_id: uuid.UUID) -> None:
    """A character leaving a troupe leaves its titles there."""
    db.execute(
        delete(CharacterTitle).where(
            CharacterTitle.troupe_id == troupe_id, CharacterTitle.character_id == character_id
        )
    )
