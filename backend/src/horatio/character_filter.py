"""Finding a troupe's characters by what is on their sheets: the Characters list's
filter (issue #36).

A filter is a tree. A group matches all, or any, of its items; an item is a
group or a condition. A condition asks about one thing:

    status   which=None       is | is_not            value: a STATUSES key
    trait    which="cat/name" lt lte eq gte gt      value: a rating (a missing trait is 0)
                              has | lacks           value: None
    choice   which=category   is | is_not           value: [names]  (holds any of them)
                              family                value: [clans]  (the clan or its bloodlines)
    title    which=None       has | lacks           value: a title, or None for any title
    player   which=None       is | is_not           value: the player's user id
    xp       which="earned"|"unspent"  lt lte eq gte gt  value: a number
    count    which=category   lt lte eq gte gt      value: how many traits it holds

`which` for a trait may add a detail: "skills/Lore/Kindred".
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import titles
from horatio.models import Approval, Character, XpEntry
from horatio.rules.model import RuleSetData
from horatio.sheets import sheet_rows

STATUSES = {
    "active": "Active",
    "retired": "Retired",
    "home": "Home here",
    "visiting": "Visiting",
    "waiting": "Asking to make this home",
    "creating": "Still in creation",
    "approvals": "Has approvals waiting",
    "pc": "Player character",
    "npc": "NPC",
}
COMPARISONS = {
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
    "eq": lambda a, b: a == b,
    "gte": lambda a, b: a >= b,
    "gt": lambda a, b: a > b,
}
OPS = {
    "status": {"is", "is_not"},
    "trait": {*COMPARISONS, "has", "lacks"},
    "choice": {"is", "is_not", "family"},
    "title": {"has", "lacks"},
    "player": {"is", "is_not"},
    "xp": set(COMPARISONS),
    "count": set(COMPARISONS),
}
# Enough for any filter a person builds; stops a request from asking for millions.
MAX_ITEMS = 100


class FilterError(ValueError):
    """The filter names something that does not exist, or asks nonsense."""


@dataclass
class Facts:
    """What a filter can ask about one character."""

    character_id: uuid.UUID
    player_id: uuid.UUID | None
    statuses: set[str]
    # (category, name, detail) → rating; an unrated choice counts as 1.
    traits: dict[tuple[str, str, str], int]
    titles: set[str]
    xp: dict[str, int] = field(default_factory=dict)


def facts(db: Session, troupe_id: uuid.UUID, character: Character) -> Facts:
    pending = list(
        db.scalars(
            select(Approval).where(
                Approval.character_id == character.id, Approval.status == "pending"
            )
        )
    )
    statuses = {
        "retired" if character.status == "retired" else "active",
        "npc" if character.kind == "npc" else "pc",
        "home" if character.home_troupe_id == troupe_id else "visiting",
    }
    if character.creation_completed_at is None:
        statuses.add("creating")
    if any(a.kind == "home_troupe_change" and a.troupe_id == troupe_id for a in pending):
        statuses.add("waiting")
    if any(a.troupe_id == troupe_id for a in pending):
        statuses.add("approvals")
    traits: dict[tuple[str, str, str], int] = {}
    for row in sheet_rows(db, character):
        if row.trait.rating == 0:
            continue
        key = (row.category.key, row.definition.name, row.trait.detail)
        traits[key] = row.trait.rating if row.trait.rating is not None else 1
    amounts = list(db.scalars(select(XpEntry.amount).where(XpEntry.character_id == character.id)))
    return Facts(
        character_id=character.id,
        player_id=character.player_id if character.kind == "pc" else None,
        statuses=statuses,
        traits=traits,
        titles=set(titles.held(db, troupe_id, character.id)),
        xp={"earned": sum(a for a in amounts if a > 0), "unspent": sum(amounts)},
    )


def is_group(node: Mapping[str, Any]) -> bool:
    return "items" in node


def conditions(node: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Every condition in the tree, in order."""
    if is_group(node):
        return [c for item in node["items"] for c in conditions(item)]
    return [node]


def validate(node: Mapping[str, Any], rules: RuleSetData) -> None:
    """Refuse a filter that names something the troupe's rules do not have."""
    found = conditions(node)
    if len(found) > MAX_ITEMS:
        raise FilterError(f"A filter can have at most {MAX_ITEMS} conditions.")
    for c in found:
        what, which, op, value = c["what"], c.get("which"), c["op"], c.get("value")
        if what not in OPS:
            raise FilterError(f"There is no filter on {what!r}.")
        if op not in OPS[what]:
            raise FilterError(f"{op!r} does not work with {what}.")
        if what == "status" and value not in STATUSES:
            raise FilterError(f"There is no status {value!r}.")
        if what == "trait":
            category, name = trait_key(which)[:2]
            if (category, name) not in rules.traits:
                raise FilterError(f"There is no trait {name!r} in {category!r}.")
        if what in ("choice", "count") and which not in rules.categories:
            raise FilterError(f"There is no category {which!r}.")
        if what == "choice" and not isinstance(value, list):
            raise FilterError("Choose at least one.")
        if what == "xp" and which not in ("earned", "unspent"):
            raise FilterError("Experience is earned or unspent.")
        compares = what in ("xp", "count") or (what == "trait" and op in COMPARISONS)
        if compares and not isinstance(value, int):
            raise FilterError("Give a number to compare with.")


def trait_key(which: Any) -> tuple[str, str, str | None]:
    parts = str(which or "").split("/", 2)
    if len(parts) < 2:
        raise FilterError("Name the trait as category/name.")
    return parts[0], parts[1], parts[2] if len(parts) == 3 else None


def trait_rating(f: Facts, which: str) -> int:
    category, name, detail = trait_key(which)
    return sum(
        rating
        for (c, n, d), rating in f.traits.items()
        if c == category and n == name and (detail is None or d == detail)
    )


def value_of(c: Mapping[str, Any], f: Facts) -> int | None:
    """The number a condition compares, for showing beside the character."""
    if c["what"] == "trait":
        return trait_rating(f, c["which"])
    if c["what"] == "xp":
        return f.xp[c["which"]]
    if c["what"] == "count":
        return sum(1 for (category, _, _) in f.traits if category == c["which"])
    return None


def holds(c: Mapping[str, Any], f: Facts) -> bool:
    what, which, op, value = c["what"], c.get("which"), c["op"], c.get("value")
    if what == "status":
        return (value in f.statuses) == (op == "is")
    if what == "player":
        return (str(f.player_id) == str(value)) == (op == "is")
    if what == "title":
        held = bool(f.titles) if value is None else value in f.titles
        return held == (op == "has")
    if what == "choice":
        chosen = {name for (category, name, _) in f.traits if category == which}
        names: list[str] = value or []
        if op == "family":
            return any(n == v or n.startswith(f"{v}:") for n in chosen for v in names)
        return bool(chosen & set(names)) == (op == "is")
    number = value_of(c, f)
    assert number is not None
    if op in ("has", "lacks"):
        return (number > 0) == (op == "has")
    return COMPARISONS[op](number, value)


def matches(node: Mapping[str, Any], f: Facts) -> bool:
    if is_group(node):
        results = (matches(item, f) for item in node["items"])
        return all(results) if node.get("match", "all") == "all" else any(results)
    return holds(node, f)


def column(c: Mapping[str, Any]) -> str | None:
    """The key a condition's number is shown under, if it compares one."""
    return f"{c['what']}:{c['which']}" if c["what"] in ("trait", "xp", "count") else None


def values(node: Mapping[str, Any], f: Facts) -> dict[str, int]:
    found: dict[str, int] = {}
    for c in conditions(node):
        key = column(c)
        number = value_of(c, f)
        if key is not None and number is not None:
            found[key] = number
    return found


def search(
    db: Session,
    troupe_id: uuid.UUID,
    characters: Sequence[Character],
    node: Mapping[str, Any],
    rules: RuleSetData,
) -> list[tuple[uuid.UUID, dict[str, int]]]:
    """The characters the filter matches, in the order given, each with the numbers
    its conditions compare."""
    validate(node, rules)
    found: list[tuple[uuid.UUID, dict[str, int]]] = []
    for character in characters:
        f = facts(db, troupe_id, character)
        if matches(node, f):
            found.append((character.id, values(node, f)))
    return found
