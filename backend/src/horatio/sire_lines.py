"""Sire lines (issue #707): who sired whom, as a family tree for a troupe.

**A character's sire** is on the character (Character.sire_id, sire_name,
sire_clan): a vampire in Horatio, or one known by name and clan only. Its player
gives it, or its home troupe's storytellers and assistant storytellers (an NPC's
troupe staff); an Embrace run in play names it too (horatio.embrace). A sire that
would make a loop, its own sire's sire and so on, is refused. `sire_secret` keeps
it from the troupe's players.

**The tree.** Each character is a node, with its clan, generation (from its sheet),
and how it left if it is retired. A sire known by name only is a node of its own,
and every childe that names the same name and clan shares it. A linked sire outside
the troupe is a node too, by name, for staff.

**Who sees what.** The troupe's storytellers and assistant storytellers see every
character in it, home or visiting, active or retired, NPCs included. Its players
see the lines only if the troupe shows them (Troupe.sire_lines_players), and then
only the characters on its Who's Who (horatio.whos_who), with only the sires
the Who's Who shows: a sire kept secret, or linked to a character not on it, is
left out, never named.
"""

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit, notifications, social_age, whos_who
from horatio.embrace import generation_number
from horatio.models import (
    Character,
    CharacterTrait,
    TraitCategory,
    TraitDefinition,
    Troupe,
    TroupeMembership,
    User,
)
from horatio.permissions import TroupeAction
from horatio.sheets import conflict, unprocessable

VAMPIRE = "vampire"
# The longest a sire's name or clan can be, in characters.
NAME_LENGTH = 100


@dataclass(frozen=True)
class Person:
    """A character as the tree needs it, and the sire it names."""

    id: uuid.UUID
    name: str
    clan: str | None
    generation: int | None
    # final_death, off_field or inactive for a retired character; None while active.
    left_reason: str | None
    retired: bool
    kind: str
    sire_id: uuid.UUID | None = None
    sire_name: str = ""
    sire_clan: str = ""


@dataclass(frozen=True)
class Node:
    # The character's id, or "named:<name>|<clan>" for a sire known by name only.
    key: str
    character_id: uuid.UUID | None
    name: str
    clan: str | None
    generation: int | None
    left_reason: str | None
    retired: bool
    # "pc" or "npc"; "named" for a sire known by name only; "elsewhere" for a linked
    # sire outside the troupe.
    kind: str
    sire_key: str | None


def named_key(name: str, clan: str) -> str:
    """One key for every childe naming the same sire: by name and clan, ignoring case
    and spaces at either end."""
    return f"named:{name.strip().casefold()}|{clan.strip().casefold()}"


def forest(
    people: Sequence[Person], elsewhere: Mapping[uuid.UUID, Person] | None = None
) -> list[Node]:
    """The nodes of the tree, by name, each with its sire's key: a forest, with a
    root for each eldest known. A link that would close a loop is dropped, so the
    tree never cycles even if the records do. `elsewhere` are linked sires outside
    the set, drawn by name; any other linked sire outside it is left out."""
    elsewhere = elsewhere or {}
    inside = {p.id for p in people}
    nodes: dict[str, Node] = {}
    for p in people:
        sire_key: str | None = None
        if p.sire_id is not None and p.sire_id in inside:
            sire_key = str(p.sire_id)
        elif p.sire_id is not None and p.sire_id in elsewhere:
            outside = elsewhere[p.sire_id]
            sire_key = str(outside.id)
            nodes.setdefault(sire_key, node_of(outside, "elsewhere", None))
        elif p.sire_id is None and p.sire_name.strip():
            sire_key = named_key(p.sire_name, p.sire_clan)
            nodes.setdefault(
                sire_key,
                Node(
                    key=sire_key,
                    character_id=None,
                    name=p.sire_name.strip(),
                    clan=p.sire_clan.strip() or None,
                    generation=None,
                    left_reason=None,
                    retired=False,
                    kind="named",
                    sire_key=None,
                ),
            )
        nodes[str(p.id)] = node_of(p, p.kind, sire_key)
    return sorted(unlooped(nodes).values(), key=lambda n: (n.name.casefold(), n.key))


def node_of(p: Person, kind: str, sire_key: str | None) -> Node:
    return Node(
        key=str(p.id),
        character_id=p.id,
        name=p.name,
        clan=p.clan,
        generation=p.generation,
        left_reason=p.left_reason,
        retired=p.retired,
        kind=kind,
        sire_key=sire_key,
    )


def unlooped(nodes: dict[str, Node]) -> dict[str, Node]:
    """The nodes with every link that closes a loop dropped, the loop's first node by
    key losing its sire; links to a node not there are dropped too."""
    found = dict(nodes)
    for key in sorted(found):
        seen = {key}
        at = found[key].sire_key
        while at is not None:
            if at not in found:
                break
            if at in seen:
                found[key] = replace_sire(found[key], None)
                break
            seen.add(at)
            at = found[at].sire_key
    return {
        k: n if n.sire_key is None or n.sire_key in found else replace_sire(n, None)
        for k, n in found.items()
    }


def replace_sire(node: Node, sire_key: str | None) -> Node:
    return Node(**{**node.__dict__, "sire_key": sire_key})


# --- reading the troupe ----------------------------------------------------------------------


def generations(db: Session, ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, int | None]:
    """Each character's generation from its sheet as it stands: its Generation dots
    and any flaw that changes them (horatio.embrace.generation_number)."""
    wanted = list(ids)
    dots: dict[uuid.UUID, int] = {}
    flaws: dict[uuid.UUID, list[str]] = {i: [] for i in wanted}
    for trait, definition, category in db.execute(
        select(CharacterTrait, TraitDefinition, TraitCategory.key)
        .join(TraitDefinition, CharacterTrait.trait_definition_id == TraitDefinition.id)
        .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
        .where(
            CharacterTrait.character_id.in_(wanted),
            TraitCategory.key.in_(("backgrounds", "flaws")),
        )
    ):
        if category == "backgrounds" and definition.name == "Generation":
            dots[trait.character_id] = trait.rating or 0
        elif category == "flaws":
            flaws[trait.character_id].append(definition.name)
    return {i: generation_number(dots.get(i, 0), flaws[i]) for i in wanted}


def people_of(db: Session, characters: Sequence[Character]) -> list[Person]:
    ids = [c.id for c in characters]
    standing = social_age.standings(db, ids)
    generation = generations(db, ids)
    return [
        Person(
            id=c.id,
            name=c.name,
            clan=standing[c.id].clan if c.id in standing else None,
            generation=generation.get(c.id),
            left_reason=c.left_reason,
            retired=c.status == "retired",
            kind=c.kind,
            sire_id=c.sire_id,
            sire_name=c.sire_name,
            sire_clan=c.sire_clan,
        )
        for c in characters
    ]


def is_vampire(c: Character) -> bool:
    return c.splat == VAMPIRE


def staff_forest(db: Session, troupe: Troupe) -> list[Node]:
    """Every vampire in the troupe, home or visiting, active or retired, NPCs included,
    and every sire they name."""
    members = list(
        db.scalars(
            select(Character)
            .join(TroupeMembership, TroupeMembership.character_id == Character.id)
            .where(TroupeMembership.troupe_id == troupe.id, TroupeMembership.left_at.is_(None))
            .order_by(Character.name, Character.id)
        )
    )
    inside = {c.id for c in members}
    sires = {c.sire_id for c in members if c.sire_id is not None}
    # A character in the troupe that is a sire stays, whatever it is now.
    shown = [c for c in members if is_vampire(c) or c.id in sires or c.sire_id or c.sire_name]
    outside = [c for c in db.scalars(select(Character).where(Character.id.in_(sires - inside)))]
    return forest(people_of(db, shown), {p.id: p for p in people_of(db, outside)})


def player_forest(db: Session, troupe: Troupe) -> list[Node]:
    """The characters on the troupe's Who's Who that are vampires, with only the sires
    it shows: none kept secret, and none linked to a character not on it."""
    found = whos_who.whos_who(db, troupe)
    listed = [e.character for e in found.entries if is_vampire(e.character)]
    inside = {c.id for c in listed}
    people = []
    for p in people_of(db, listed):
        character = next(c for c in listed if c.id == p.id)
        hidden = character.sire_secret or (p.sire_id is not None and p.sire_id not in inside)
        if hidden:
            p = Person(**{**p.__dict__, "sire_id": None, "sire_name": "", "sire_clan": ""})
        people.append(p)
    return forest(people)


def clan_counts(nodes: Sequence[Node]) -> dict[str, int]:
    """How many of the tree's characters each clan has, for the chart's colours."""
    counts: dict[str, int] = {}
    for n in nodes:
        if n.character_id is not None and n.kind in ("pc", "npc"):
            counts[n.clan or ""] = counts.get(n.clan or "", 0) + 1
    return counts


# --- setting a sire ------------------------------------------------------------------------


def would_loop(db: Session, childe: Character, sire: Character) -> bool:
    """Whether making `sire` the childe's sire would close a loop: the childe itself,
    or one of its own childer, however far down."""
    at: Character | None = sire
    seen: set[uuid.UUID] = set()
    while at is not None and at.id not in seen:
        if at.id == childe.id:
            return True
        seen.add(at.id)
        at = db.get(Character, at.sire_id) if at.sire_id else None
    return False


def set_sire(
    db: Session,
    user: User,
    childe: Character,
    *,
    sire: Character | None,
    name: str,
    clan: str,
    secret: bool,
    by_player: bool = False,
) -> None:
    """Give the character its sire: a character, or a name with its clan, or none
    (both empty); and whether players see it. Logged on the character; when its
    player made the change (`by_player`), its home troupe's storytellers and
    assistant storytellers are told what it was and what it is now (#747)."""
    name, clan = name.strip(), clan.strip()
    if not is_vampire(childe):
        raise conflict("Only a vampire has a sire.")
    if sire is not None:
        if not is_vampire(sire):
            raise unprocessable(f"{sire.name} isn't a vampire.")
        if would_loop(db, childe, sire):
            raise unprocessable(
                f"{sire.name} can't be {childe.name}'s sire: they descend from {childe.name}."
            )
        name, clan = "", ""
    elif clan and not name:
        raise unprocessable("Give the sire's name.")
    if len(name) > NAME_LENGTH or len(clan) > NAME_LENGTH:
        raise unprocessable(f"Keep the sire's name and clan to {NAME_LENGTH} characters.")
    before = sire_text(db, childe)
    childe.sire_id = sire.id if sire is not None else None
    childe.sire_name = name
    childe.sire_clan = clan
    childe.sire_secret = secret
    db.flush()
    after = sire_text(db, childe)
    if after != before:
        audit.record(
            db,
            user,
            "character.sire",
            troupe_id=childe.home_troupe_id,
            character_id=childe.id,
            sire=after or "no sire",
        )
        if by_player:
            tell_staff(db, user, childe, before, after)


def tell_staff(db: Session, user: User, childe: Character, before: str, after: str) -> None:
    """Tell the home troupe's storytellers and assistant storytellers that the
    player changed the character's sire. They can see a sire kept from players."""
    home = db.get(Troupe, childe.home_troupe_id) if childe.home_troupe_id else None
    if home is None:
        return
    staff = [
        s for s in notifications.staff_for(db, home, TroupeAction.APPROVE_CHANGES) if s != user.id
    ]
    notifications.notify(
        db,
        staff,
        "character.sire",
        f"{childe.name}'s player changed the sire: now {after or 'no sire'}, "
        f"was {before or 'no sire'}.",
        f"/characters/{childe.id}",
        troupe_id=home.id,
        character_id=childe.id,
    )


def sire_text(db: Session, character: Character) -> str:
    """The sire as the log says it: "Elsa", "Elsa (Toreador)", "Elsa, kept secret"."""
    if character.sire_id is not None:
        linked = db.get(Character, character.sire_id)
        text = linked.name if linked else ""
    elif character.sire_name:
        text = character.sire_name + (f" ({character.sire_clan})" if character.sire_clan else "")
    else:
        return ""
    return text + (", kept from players" if character.sire_secret else "")
