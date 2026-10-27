"""Equipment (issue #283): weapons, protective gear and miscellaneous gear, with the
book's qualities (MET: VTM pp. 515-524). The rules are horatio.rules.equipment's;
`check` is what every equipment ticket asks before an item is made or changed.

A troupe's storytellers and assistant storytellers give equipment to the characters
whose home troupe it is, PCs and the troupe's NPCs alike (issue #280), and only to
them: a visiting character carries its own home troupe's equipment, which the
troupe it visits can't change. They can make an item special: any number of
qualities, still keeping the rules between them, and effects of the troupe's own.
They change an item or take it back with a reason, and the holder's player is told.

A character's player, or its home troupe's staff, gives its items to another
character of the same home troupe, or discards them (issue #282). A discarded item
is kept, with its history, and staff restore it. Whoever's character gains or loses
an item is told, unless they did it. On the Play View a give or discard is a tap
("item:<id>"), so it has Undo (horatio.play).

An item belongs to the character, wherever its home is: the staff who see and change
it are those of the holder's home troupe now. Each item keeps its history in
`equipment_events`, and each change goes in the character's log too.
"""

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio import audit, notifications
from horatio.models import (
    Character,
    CharacterTitle,
    EquipmentEvent,
    EquipmentItem,
    EquipmentTemplate,
    RuleSet,
    Troupe,
    User,
)
from horatio.permissions import TroupeAction, allows, troupe_role
from horatio.rules.equipment import (
    WEAPON,
    WEAPON_POOLS,
    Assessment,
    EquipmentRules,
    Facts,
    ItemQuality,
    assess,
    item_qualities,
    item_qualities_to_list,
)
from horatio.rules.store import read_troupe_rules
from horatio.sheets import conflict, unprocessable

__all__ = [
    "Assessment",
    "EquipmentRefused",
    "Facts",
    "ItemFields",
    "ItemQuality",
    "SpecialEffect",
    "assess",
    "check",
    "equipment_rules",
]


class EquipmentRefused(ValueError):
    """An item that breaks the rules between qualities; `problems` says each way."""

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__(" ".join(problems))
        self.problems = tuple(problems)


def equipment_rules(db: Session, splat: str, troupe_id: uuid.UUID | None = None) -> EquipmentRules:
    """The equipment rules a character of `splat` plays by in `troupe_id`."""
    return read_troupe_rules(db, splat, troupe_id).rule_set.equipment


def check(
    rules: EquipmentRules,
    kind: str,
    qualities: Sequence[ItemQuality],
    grade: str,
    *,
    crafted: bool = False,
) -> Facts:
    """The item's facts (hands, damage, shots and range), or EquipmentRefused if it
    breaks a rule: too many qualities for its grade, a quality of another kind or
    taken twice, a missing detail, a two-handed item that is Concealable or Quick
    Draw, or two qualities that exclude each other. `crafted`: its Artisan and
    Masterwork were added while crafting, and take no slot. A special item has no
    limit on its qualities, but keeps every other rule."""
    found = assess(rules, kind, qualities, grade, crafted=crafted)
    if found.problems:
        raise EquipmentRefused(found.problems)
    return found.facts


# --- items ------------------------------------------------------------------------------


@dataclass(frozen=True)
class SpecialEffect:
    """What a special item does that no quality covers, in the troupe's own words."""

    name: str
    effect: str


@dataclass(frozen=True)
class ItemFields:
    """Everything about an item that staff choose, to give it or change it."""

    name: str
    kind: str
    grade: str
    qualities: tuple[ItemQuality, ...] = ()
    crafted: bool = False
    effects: tuple[SpecialEffect, ...] = ()
    description: str = ""
    staff_note: str = ""

    @property
    def special(self) -> bool:
        return self.grade == "special"


def effects_of(raw: Iterable[Mapping[str, str]]) -> tuple[SpecialEffect, ...]:
    return tuple(SpecialEffect(e["name"], e["effect"]) for e in raw)


def effects_to_list(effects: Iterable[SpecialEffect]) -> list[dict[str, str]]:
    return [{"name": e.name, "effect": e.effect} for e in effects]


def fields_of(item: EquipmentItem | EquipmentTemplate) -> ItemFields:
    return ItemFields(
        name=item.name,
        kind=item.kind,
        grade=item.grade,
        qualities=item_qualities(item.qualities),
        crafted=item.crafted,
        effects=effects_of(item.effects),
        description=item.description,
        staff_note=item.staff_note if isinstance(item, EquipmentItem) else "",
    )


@dataclass(frozen=True)
class ItemModifier:
    """What one of an item's qualities does to its holder's test pools while it is
    equipped (issue #306): a modifier, as a player's own is (horatio.pool_modifiers),
    named for the item and quality: "Katana: Accurate"."""

    quality: str
    label: str
    amount: int
    # As a player's own modifier names them, the item's own attack worked out
    # ("pool:attack:Melee"); or "purpose", the challenges it is for.
    pools: str
    when: str
    # It counts only in a situation the Pools tab can't tell (against firearms).
    situational: bool = False


def item_modifiers(rules: EquipmentRules, item: EquipmentItem) -> list[ItemModifier]:
    """The pool modifiers the item's qualities make while it is equipped, from the
    holder's rules. A quality taken again (Superior) adds to its own modifier. A
    special item's own effects are words for the table, not modifiers."""
    found: dict[tuple[str, str, str, bool], ItemModifier] = {}
    for chosen in item_qualities(item.qualities):
        quality = rules.qualities.get((item.kind, chosen.name))
        for effect in quality.pool if quality else ():
            pools = (
                WEAPON_POOLS.get(item.kind, effect.pools)
                if effect.pools == WEAPON
                else effect.pools
            )
            when = effect.when.replace("{detail}", chosen.detail or "its circumstance")
            key = (chosen.name, pools, when, effect.situational)
            if key in found:
                found[key] = replace(found[key], amount=found[key].amount + effect.amount)
            else:
                found[key] = ItemModifier(
                    quality=chosen.name,
                    label=f"{item.name}: {chosen.name}",
                    amount=effect.amount,
                    pools=pools,
                    when=when,
                    situational=effect.situational,
                )
    return list(found.values())


def arrived(
    db: Session, character: Character, items: Sequence[EquipmentItem]
) -> dict[uuid.UUID, datetime]:
    """When each item last came to the character: given by its troupe, passed to it,
    or restored to it."""
    if not items:
        return {}
    return {
        item_id: at
        for item_id, at in db.execute(
            select(EquipmentEvent.item_id, func.max(EquipmentEvent.created_at))
            .where(
                EquipmentEvent.item_id.in_([i.id for i in items]),
                EquipmentEvent.to_character_id == character.id,
            )
            .group_by(EquipmentEvent.item_id)
        )
    }


def home_of(character: Character) -> uuid.UUID | None:
    """The character's home troupe: a PC's, or the troupe an NPC belongs to."""
    return character.home_troupe_id or character.owner_troupe_id


def can_manage(db: Session, user: User, troupe: Troupe) -> bool:
    """The troupe's storytellers and assistant storytellers, and the custodian."""
    if troupe.archived_at is not None and not user.is_custodian:
        return False
    return allows(
        troupe_role(db, user, troupe), TroupeAction.MANAGE_EQUIPMENT, is_custodian=user.is_custodian
    )


def refused(rules: EquipmentRules, fields: ItemFields) -> list[str]:
    """Every way the item breaks the rules, as `check` says, and its effects."""
    problems = list(
        assess(rules, fields.kind, fields.qualities, fields.grade, crafted=fields.crafted).problems
    )
    if not fields.name:
        problems.insert(0, "An item needs a name.")
    if fields.effects and not fields.special:
        problems.append("Only a special item has special effects.")
    if any(not e.name or not e.effect for e in fields.effects):
        problems.append("Each special effect needs a name and what it does.")
    return problems


def checked(rules: EquipmentRules, fields: ItemFields) -> ItemFields:
    """The fields, trimmed, or EquipmentRefused."""
    fields = ItemFields(
        name=fields.name.strip(),
        kind=fields.kind,
        grade=fields.grade,
        qualities=tuple(ItemQuality(q.name, q.detail.strip()) for q in fields.qualities),
        crafted=fields.crafted,
        effects=tuple(SpecialEffect(e.name.strip(), e.effect.strip()) for e in fields.effects),
        description=fields.description.strip(),
        staff_note=fields.staff_note.strip(),
    )
    problems = refused(rules, fields)
    if problems:
        raise EquipmentRefused(problems)
    return fields


def require_home(troupe: Troupe, character: Character) -> None:
    """Only the character's home troupe gives it equipment or changes what it holds."""
    if home_of(character) != troupe.id:
        raise unprocessable(
            f"{troupe.name} is not {character.name}'s home troupe: only its home troupe"
            " gives it equipment or changes what it holds."
        )


def quality_text(quality: ItemQuality) -> str:
    return f"{quality.name}: {quality.detail}" if quality.detail else quality.name


def kind_name(rules: EquipmentRules, kind: str) -> str:
    found = rules.kinds.get(kind)
    return found.name.lower() if found else kind


def describe(rules: EquipmentRules, fields: ItemFields) -> str:
    """What the item is, in a line: "special melee weapon: Accurate, Silver; Drinks
    the Blood"."""
    what = kind_name(rules, fields.kind)
    if fields.grade != "standard":
        what = f"{fields.grade} {what}"
    if fields.crafted:
        what = f"crafted {what}"
    qualities = ", ".join(quality_text(q) for q in fields.qualities)
    effects = ", ".join(e.name for e in fields.effects)
    shown = "; ".join(p for p in (qualities, effects) if p)
    return f"{what}: {shown}" if shown else what


def record(
    db: Session,
    item: EquipmentItem,
    action: str,
    actor: User | None,
    troupe: Troupe | None,
    *,
    before: Character | None = None,
    after: Character | None = None,
    reason: str = "",
    changes: dict[str, Any] | None = None,
) -> EquipmentEvent:
    """A line in the item's history."""
    event = EquipmentEvent(
        item_id=item.id,
        action=action,
        actor_id=actor.id if actor else None,
        troupe_id=troupe.id if troupe else None,
        from_character_id=before.id if before else None,
        to_character_id=after.id if after else None,
        from_name=before.name if before else "",
        to_name=after.name if after else "",
        reason=reason,
        changes=changes or {},
    )
    db.add(event)
    db.flush()
    return event


def tell(db: Session, character: Character, troupe: Troupe, kind: str, summary: str) -> None:
    """The holder's player, for a PC. An NPC's are the troupe's own staff."""
    if character.kind == "pc":
        notifications.notify(
            db,
            [character.player_id],
            kind,
            summary,
            f"/characters/{character.id}",
            troupe_id=troupe.id,
            character_id=character.id,
        )


def apply(item: EquipmentItem, fields: ItemFields) -> None:
    item.name = fields.name
    item.kind = fields.kind
    item.grade = fields.grade
    item.qualities = item_qualities_to_list(fields.qualities)
    item.crafted = fields.crafted
    item.effects = effects_to_list(fields.effects)
    item.description = fields.description
    item.staff_note = fields.staff_note


def give(
    db: Session,
    staff: User,
    troupe: Troupe,
    character: Character,
    fields: ItemFields,
    *,
    template: str | None = None,
) -> EquipmentItem:
    """Give a home character an item, checked by the rules it plays by. `template`:
    the template it was started from, kept in its history."""
    require_home(troupe, character)
    if character.status != "active":
        raise conflict(f"{character.name} is retired.")
    rules = equipment_rules(db, character.splat, troupe.id)
    fields = checked(rules, fields)
    item = EquipmentItem(
        character_id=character.id,
        troupe_id=troupe.id,
        given_by=staff.id,
        given_at=datetime.now(UTC),
        status="held",
        special_troupe_id=troupe.id if fields.special else None,
    )
    apply(item, fields)
    db.add(item)
    db.flush()
    record(
        db,
        item,
        "given",
        staff,
        troupe,
        after=character,
        changes={"template": template} if template else None,
    )
    what = describe(rules, fields)
    audit.record(
        db,
        staff,
        "equipment.given",
        troupe_id=troupe.id,
        character_id=character.id,
        item=item.name,
        what=what,
    )
    tell(
        db,
        character,
        troupe,
        "equipment.given",
        f"{staff.display_name} gave {character.name} {item.name} ({what}).",
    )
    return item


# The fields a change is told for, in this order. The staff note is kept in the
# item's history, but never told to the player.
TOLD = ("name", "kind", "grade", "qualities", "crafted", "effects", "description")


def as_recorded(fields: ItemFields) -> dict[str, Any]:
    return {
        "name": fields.name,
        "kind": fields.kind,
        "grade": fields.grade,
        "qualities": item_qualities_to_list(fields.qualities),
        "crafted": fields.crafted,
        "effects": effects_to_list(fields.effects),
        "description": fields.description,
        "staff_note": fields.staff_note,
    }


def differences(before: ItemFields, after: ItemFields) -> dict[str, Any]:
    """Each field changed, {field: {"from": ..., "to": ...}}, as the history keeps it."""
    old, new = as_recorded(before), as_recorded(after)
    return {k: {"from": old[k], "to": new[k]} for k in old if old[k] != new[k]}


def changes_text(rules: EquipmentRules, changes: Mapping[str, Any], *, staff: bool = False) -> str:
    """The changes, in a phrase each: "qualities now Accurate, Long Range; now
    special". The staff note only for `staff`."""
    told: list[str] = []
    for name in (*TOLD, "staff_note") if staff else TOLD:
        if name not in changes:
            continue
        old, new = changes[name]["from"], changes[name]["to"]
        if name == "name":
            told.append(f"renamed from {old}")
        elif name == "kind":
            told.append(f"now a {kind_name(rules, new)}, not a {kind_name(rules, old)}")
        elif name == "grade":
            told.append(f"now {new}" if new == "special" else f"now {new}, not {old}")
        elif name == "qualities":
            listed = ", ".join(quality_text(q) for q in item_qualities(new))
            told.append(f"qualities now {listed}" if listed else "no qualities now")
        elif name == "crafted":
            told.append("now crafted" if new else "no longer crafted")
        elif name == "effects":
            listed = ", ".join(e["name"] for e in new)
            told.append(f"special effects now {listed}" if listed else "no special effects now")
        elif name == "description":
            told.append("a new description")
        else:
            told.append("a new staff note")
    return "; ".join(told)


def change(
    db: Session,
    staff: User,
    troupe: Troupe,
    item: EquipmentItem,
    fields: ItemFields,
    reason: str,
) -> EquipmentItem:
    """Change a held item, with a reason, checked by the rules its holder plays by.
    Its holder's player is told, unless only the staff note changed."""
    character = db.get_one(Character, item.character_id)
    require_home(troupe, character)
    if item.status != "held":
        raise conflict(f"{item.name} isn't held by {character.name} now.")
    rules = equipment_rules(db, character.splat, troupe.id)
    fields = checked(rules, fields)
    changes = differences(fields_of(item), fields)
    if not changes:
        raise unprocessable("Nothing has changed.")
    reason = reason.strip()
    told = changes_text(rules, changes)
    if told and not reason:
        raise unprocessable("Say why it changes: its holder's player is told.")
    if not fields.special:
        item.special_troupe_id = None
    elif item.special_troupe_id is None:
        item.special_troupe_id = troupe.id
    was = item.name
    apply(item, fields)
    record(
        db,
        item,
        "changed",
        staff,
        troupe,
        before=character,
        after=character,
        reason=reason,
        changes=changes,
    )
    if told:
        audit.record(
            db,
            staff,
            "equipment.changed",
            troupe_id=troupe.id,
            character_id=character.id,
            item=was,
            changes=told,
            reason=reason,
        )
        tell(
            db,
            character,
            troupe,
            "equipment.changed",
            f"{staff.display_name} changed {character.name}'s {was}: {told} ({reason}).",
        )
    db.flush()
    return item


def take_back(
    db: Session, staff: User, troupe: Troupe, item: EquipmentItem, reason: str
) -> EquipmentItem:
    """Take a held item away from its holder, with a reason. It is kept, with its
    history, as taken back."""
    character = db.get_one(Character, item.character_id)
    require_home(troupe, character)
    if item.status != "held":
        raise conflict(f"{item.name} isn't held by {character.name} now.")
    reason = reason.strip()
    if not reason:
        raise unprocessable("Say why it is taken back: its holder's player is told.")
    item.status = "taken_back"
    record(db, item, "taken_back", staff, troupe, before=character, reason=reason)
    audit.record(
        db,
        staff,
        "equipment.taken_back",
        troupe_id=troupe.id,
        character_id=character.id,
        item=item.name,
        reason=reason,
    )
    tell(
        db,
        character,
        troupe,
        "equipment.taken_back",
        f"{staff.display_name} took {item.name} back from {character.name}: {reason}",
    )
    db.flush()
    return item


# --- given between characters, and discarded (issue #282) ---------------------------------


@dataclass(frozen=True)
class Receiver:
    """A character the holder's items can be given to."""

    character: Character
    # The titles it holds in the home troupe: "Prince, Harpy"; empty for none.
    title: str


def is_player(user: User, character: Character) -> bool:
    return character.kind == "pc" and character.player_id == user.id


def can_pass(db: Session, user: User, character: Character) -> bool:
    """Who gives or discards the character's items: its player, and its home troupe's
    staff. Nobody takes an item from another character: theft is played out, and
    staff move the item."""
    home = home_of(character)
    if home is None:
        return False
    return is_player(user, character) or can_manage(db, user, db.get_one(Troupe, home))


def receivers(db: Session, character: Character, *, staff: bool) -> list[Receiver]:
    """Who the character's items can go to: its home troupe's active PCs, and its
    NPCs holding a title there, as the patron list of status has them (#252); for
    staff, every home character. Never the character itself."""
    home = home_of(character)
    if home is None:
        return []
    titles: dict[uuid.UUID, list[str]] = {}
    for who, name in db.execute(
        select(CharacterTitle.character_id, CharacterTitle.name)
        .where(CharacterTitle.troupe_id == home)
        .order_by(CharacterTitle.name)
    ):
        titles.setdefault(who, []).append(name)
    return [
        Receiver(c, ", ".join(titles.get(c.id, [])))
        for c in home_characters(db, home)
        if c.id != character.id and (staff or c.kind == "pc" or c.id in titles)
    ]


def acting_for(db: Session, user: User, character: Character) -> Troupe:
    """The character's home troupe, if `user` may give or discard its items; else 403,
    or 409 for a troupe since archived."""
    if not can_pass(db, user, character):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Only {character.name}'s player, or its home troupe's staff, give or discard"
            " its equipment.",
        )
    troupe = db.get_one(Troupe, home_of(character))
    if troupe.archived_at is not None and not user.is_custodian:
        raise conflict(f"{troupe.name} is archived.")
    return troupe


def by_staff(user: User, character: Character, troupe: Troupe) -> Troupe | None:
    """The troupe whose staff did it, for the item's history; None for a player's own
    doing."""
    return None if is_player(user, character) else troupe


def held_by(db: Session, item: EquipmentItem) -> Character:
    character = db.get_one(Character, item.character_id)
    if item.status != "held":
        raise conflict(f"{item.name} isn't held by {character.name} now.")
    return character


def told(
    db: Session, actor: User, character: Character, troupe: Troupe, kind: str, text: str
) -> None:
    """The character's player, unless they did it themselves."""
    if not is_player(actor, character):
        tell(db, character, troupe, kind, text)


def move(
    db: Session,
    actor: User,
    item: EquipmentItem,
    source: Character,
    to: Character,
    troupe: Troupe,
    *,
    reason: str = "",
    undoes: EquipmentEvent | None = None,
) -> EquipmentEvent:
    """Move the item from `source` to `to`, both of `troupe`'s home characters; both
    characters' logs say so, and both players are told unless they did it."""
    item.character_id = to.id
    event = record(
        db,
        item,
        "passed",
        actor,
        by_staff(actor, source, troupe),
        before=source,
        after=to,
        reason=reason,
        changes={"undoes": str(undoes.id)} if undoes else None,
    )
    # The troupe's log has the give once, under the giver; the receiver's own log
    # has it too.
    audit.record(
        db,
        actor,
        "equipment.passed",
        troupe_id=troupe.id,
        character_id=source.id,
        item=item.name,
        to=to.name,
        reason=reason,
    )
    audit.record(
        db,
        actor,
        "equipment.received",
        character_id=to.id,
        item=item.name,
        source=source.name,
        reason=reason,
    )
    because = f" ({reason})" if reason else ""
    told(
        db,
        actor,
        to,
        troupe,
        "equipment.passed",
        f"{actor.display_name} gave {to.name} {item.name}, from {source.name}{because}.",
    )
    told(
        db,
        actor,
        source,
        troupe,
        "equipment.passed",
        f"{actor.display_name} gave {source.name}'s {item.name} to {to.name}{because}.",
    )
    db.flush()
    return event


def give_to(
    db: Session, actor: User, item: EquipmentItem, to_id: uuid.UUID, note: str = ""
) -> EquipmentEvent:
    """Give a held item to another character of its holder's home troupe, at once:
    there is no acceptance step, as in the game. A player gives only to the troupe's
    PCs and the NPCs holding a title there; staff to any home character."""
    source = held_by(db, item)
    troupe = acting_for(db, actor, source)
    if source.status != "active":
        raise conflict(f"{source.name} is retired.")
    to = db.get(Character, to_id)
    if to is None or home_of(to) != troupe.id or to.status != "active":
        raise unprocessable(
            f"That character isn't one of {troupe.name}'s: equipment passes only between"
            " characters of the same home troupe."
        )
    if to.id == source.id:
        raise unprocessable(f"{source.name} holds {item.name} already.")
    staff = can_manage(db, actor, troupe)
    if not staff and all(r.character.id != to.id for r in receivers(db, source, staff=False)):
        raise unprocessable(
            f"A player gives equipment to {troupe.name}'s PCs, and to the NPCs holding a"
            " title there."
        )
    return move(db, actor, item, source, to, troupe, reason=note.strip())


def discard(db: Session, actor: User, item: EquipmentItem, note: str = "") -> EquipmentEvent:
    """Take a held item off its holder, with a note if they like ("lost in the
    river"). It is kept, with its history, for the home troupe's staff to restore."""
    character = held_by(db, item)
    troupe = acting_for(db, actor, character)
    note = note.strip()
    item.status = "discarded"
    event = record(
        db,
        item,
        "discarded",
        actor,
        by_staff(actor, character, troupe),
        before=character,
        reason=note,
    )
    audit.record(
        db,
        actor,
        "equipment.discarded",
        troupe_id=troupe.id,
        character_id=character.id,
        item=item.name,
        reason=note,
    )
    because = f": {note}" if note else "."
    told(
        db,
        actor,
        character,
        troupe,
        "equipment.discarded",
        f"{actor.display_name} discarded {character.name}'s {item.name}{because}",
    )
    db.flush()
    return event


def restore(
    db: Session,
    actor: User,
    troupe: Troupe,
    item: EquipmentItem,
    *,
    reason: str = "",
    undoes: EquipmentEvent | None = None,
) -> EquipmentEvent:
    """Give a discarded item back to the character that discarded it."""
    character = db.get_one(Character, item.character_id)
    require_home(troupe, character)
    if item.status != "discarded":
        raise conflict(f"{item.name} isn't discarded.")
    if character.status != "active":
        raise conflict(f"{character.name} is retired.")
    item.status = "held"
    event = record(
        db,
        item,
        "restored",
        actor,
        by_staff(actor, character, troupe),
        after=character,
        reason=reason,
        changes={"undoes": str(undoes.id)} if undoes else None,
    )
    audit.record(
        db,
        actor,
        "equipment.restored",
        troupe_id=troupe.id,
        character_id=character.id,
        item=item.name,
        reason=reason,
    )
    told(
        db,
        actor,
        character,
        troupe,
        "equipment.restored",
        f"{actor.display_name} gave {character.name} {item.name} back.",
    )
    db.flush()
    return event


# --- from the Play View, with Undo ---------------------------------------------------------

# A tap giving or discarding an item: "item:<id>", −1 (horatio.play).
ITEM = "item:"
UNDONE = "undone in the Play View"


def item_key(item_id: uuid.UUID) -> str:
    return f"{ITEM}{item_id}"


def tapped_item(tracker: str) -> uuid.UUID | None:
    """The item a tap names, or None for another tracker."""
    if not tracker.startswith(ITEM):
        return None
    try:
        return uuid.UUID(tracker.removeprefix(ITEM))
    except ValueError:
        return None


def by_tap(
    db: Session,
    character: Character,
    actor: User,
    tracker: str,
    to_id: uuid.UUID | None,
    note: str,
) -> dict[str, Any]:
    """Give (to `to_id`) or discard an item from a Play View tap, which may arrive
    late. What the tap keeps, for its log line and its Undo: the item's name, who it
    went to, and the history's event; or why it was refused, and then the tap changes
    nothing."""
    item = db.get(EquipmentItem, tapped_item(tracker))
    kept: dict[str, Any] = {"name": item.name if item else "an item", "to_name": None}
    if to_id is not None:
        to = db.get(Character, to_id)
        kept["to_name"] = to.name if to else "another character"
    try:
        if item is None or item.character_id != character.id:
            raise conflict(f"{character.name} doesn't hold it now.")
        event = (
            give_to(db, actor, item, to_id, note)
            if to_id is not None
            else discard(db, actor, item, note)
        )
    except HTTPException as refused:
        return {**kept, "refused": str(refused.detail)}
    return {**kept, "event_id": str(event.id)}


def undo_tap(db: Session, actor: User, kept: Mapping[str, Any]) -> dict[str, Any] | None:
    """Undo a give or discard made by a tap: the item goes back, if nothing has
    happened to it since. None if it did; else why it stays where it is."""
    if "event_id" not in kept:
        return None
    event = db.get(EquipmentEvent, uuid.UUID(kept["event_id"]))
    item = db.get(EquipmentItem, event.item_id) if event else None
    if event is None or item is None:
        return {"refused": "It's gone."}
    if history(db, item)[-1].id != event.id:
        return {"refused": f"{item.name} has moved on since, so it stays where it is."}
    source = db.get(Character, event.from_character_id) if event.from_character_id else None
    try:
        if source is None:
            raise conflict(f"{event.from_name} is gone.")
        if event.action == "discarded":
            troupe = acting_for(db, actor, source)
            restore(db, actor, troupe, item, reason=UNDONE, undoes=event)
        else:
            to = held_by(db, item)
            troupe = acting_for(db, actor, source)
            if home_of(source) != home_of(to) or source.status != "active":
                raise conflict(f"{source.name} can't hold it now.")
            move(db, actor, item, to, source, troupe, reason=UNDONE, undoes=event)
    except HTTPException as refused:
        return {"refused": str(refused.detail)}
    return None


def tap_text(kept: Mapping[str, Any]) -> str:
    """The tap as the log reads it: "Gave Silver Dagger to Bram"."""
    name, to = kept.get("name", "an item"), kept.get("to_name")
    if "refused" in kept:
        did = f"give {name} to {to}" if to else f"discard {name}"
        return f"Couldn't {did}: {kept['refused']}"
    return f"Gave {name} to {to}" if to else f"Discarded {name}"


def event_summary(rules: EquipmentRules, event: EquipmentEvent, troupe: str | None) -> str:
    """A line of an item's history, for staff: "Given to Agnes by Lords of the
    Night, from the template Silver Dagger"."""
    if event.action == "given":
        template = event.changes.get("template")
        source = f", from the template {template}" if template else ""
        return f"Given to {event.to_name} by {troupe or 'a troupe'}{source}"
    if event.action == "changed":
        return f"Changed: {changes_text(rules, event.changes, staff=True)}"
    if event.action == "taken_back":
        return f"Taken back from {event.from_name}"
    undone = bool(event.changes.get("undoes"))
    if event.action == "passed":
        if undone:
            return f"Back from {event.from_name} to {event.to_name}"
        return f"Given by {event.from_name} to {event.to_name}"
    if event.action == "discarded":
        return f"Discarded by {event.from_name}"
    return f"Back with {event.to_name}" if undone else f"Restored to {event.to_name}"


def home_characters(db: Session, troupe_id: uuid.UUID) -> list[Character]:
    """The troupe's active home characters, PCs and NPCs, by name: those it gives
    equipment to."""
    return list(
        db.scalars(
            select(Character)
            .where(
                func.coalesce(Character.home_troupe_id, Character.owner_troupe_id) == troupe_id,
                Character.status == "active",
            )
            .order_by(func.lower(Character.name), Character.id)
        )
    )


# --- searching items (issue #284) --------------------------------------------------------


@dataclass(frozen=True)
class ItemMatch:
    """What a search asks of an item: the troupe's Equipment tab, and the Characters
    filter's equipment condition (horatio.character_filter). A field left empty
    matches anything."""

    kind: str | None = None
    # A quality it has, by name, with these words in its detail ("hacking" for
    # Customized: hacking).
    quality: str | None = None
    detail: str = ""
    grade: str | None = None
    special: bool = False
    # Words in its name.
    name: str = ""
    # Words anywhere in it: its name, description, qualities and their details,
    # special effects and staff note.
    text: str = ""

    def matches(self, item: EquipmentItem) -> bool:
        if self.kind and item.kind != self.kind:
            return False
        if self.grade and item.grade != self.grade:
            return False
        if self.special and item.grade != "special":
            return False
        if self.quality and not any(
            q.name == self.quality and has_words(q.detail, self.detail)
            for q in item_qualities(item.qualities)
        ):
            return False
        return has_words(item.name, self.name) and has_words(searched_text(item), self.text)


def has_words(text: str, words: str) -> bool:
    """Every word of `words` is somewhere in `text`, whatever the case."""
    found = text.casefold()
    return all(word in found for word in words.casefold().split())


def searched_text(item: EquipmentItem) -> str:
    qualities = (quality_text(q) for q in item_qualities(item.qualities))
    effects = (f"{e.get('name', '')}: {e.get('effect', '')}" for e in item.effects)
    return "\n".join([item.name, item.description, *qualities, *effects, item.staff_note])


SORTS = {
    "holder": (func.lower(Character.name), Character.id),
    "name": (func.lower(EquipmentItem.name),),
    "date": (EquipmentItem.given_at.desc(),),
}


def troupe_items(
    db: Session,
    troupe_id: uuid.UUID,
    *,
    character_ids: Sequence[uuid.UUID] = (),
    match: ItemMatch | None = None,
    statuses: Sequence[str] = ("held",),
    given_by: uuid.UUID | None = None,
    given_after: datetime | None = None,
    given_before: datetime | None = None,
    retired: bool = False,
    sort: str = "holder",
) -> list[tuple[EquipmentItem, Character]]:
    """Items of the troupe's active home characters (and retired ones too, if
    asked), whichever troupe gave them, that match: of those characters, given by
    that person between those times. By holder and then name, unless sorted by name
    or by when they were given, newest first."""
    query = (
        select(EquipmentItem, Character)
        .join(Character, EquipmentItem.character_id == Character.id)
        .where(
            func.coalesce(Character.home_troupe_id, Character.owner_troupe_id) == troupe_id,
            Character.status.in_(["active", "retired"] if retired else ["active"]),
            EquipmentItem.status.in_(list(statuses)),
        )
        .order_by(
            *SORTS[sort],
            func.lower(Character.name),
            func.lower(EquipmentItem.name),
            EquipmentItem.id,
        )
    )
    match = match or ItemMatch()
    if character_ids:
        query = query.where(EquipmentItem.character_id.in_(list(character_ids)))
    if match.kind is not None:
        query = query.where(EquipmentItem.kind == match.kind)
    if match.grade is not None:
        query = query.where(EquipmentItem.grade == match.grade)
    if given_by is not None:
        query = query.where(EquipmentItem.given_by == given_by)
    if given_after is not None:
        query = query.where(EquipmentItem.given_at >= given_after)
    if given_before is not None:
        query = query.where(EquipmentItem.given_at < given_before)
    return [(item, character) for item, character in db.execute(query) if match.matches(item)]


def givers(db: Session, troupe_id: uuid.UUID) -> list[User]:
    """Everyone who gave an item the troupe's home characters hold or held, by name,
    for searching by who gave it."""
    given = (
        select(EquipmentItem.given_by)
        .join(Character, EquipmentItem.character_id == Character.id)
        .where(func.coalesce(Character.home_troupe_id, Character.owner_troupe_id) == troupe_id)
    )
    return list(
        db.scalars(
            select(User).where(User.id.in_(given)).order_by(func.lower(User.display_name), User.id)
        )
    )


def items_of(
    db: Session, character: Character, statuses: Sequence[str] = ("held",)
) -> list[EquipmentItem]:
    """The character's items, by name."""
    return list(
        db.scalars(
            select(EquipmentItem)
            .where(
                EquipmentItem.character_id == character.id,
                EquipmentItem.status.in_(list(statuses)),
            )
            .order_by(func.lower(EquipmentItem.name), EquipmentItem.id)
        )
    )


def history(db: Session, item: EquipmentItem) -> list[EquipmentEvent]:
    """Where it came from, and every change since, oldest first."""
    return list(
        db.scalars(
            select(EquipmentEvent)
            .where(EquipmentEvent.item_id == item.id)
            .order_by(EquipmentEvent.created_at, EquipmentEvent.id)
        )
    )


# --- a troupe's own templates -------------------------------------------------------------


def troupe_templates(db: Session, troupe_id: uuid.UUID) -> list[EquipmentTemplate]:
    """The troupe's own templates, by name, whichever rule set checked them."""
    return list(
        db.scalars(
            select(EquipmentTemplate)
            .where(EquipmentTemplate.troupe_id == troupe_id)
            .order_by(func.lower(EquipmentTemplate.name), EquipmentTemplate.id)
        )
    )


def save_template(
    db: Session, staff: User, troupe: Troupe, splat: str, fields: ItemFields
) -> EquipmentTemplate:
    """Keep an item as one of the troupe's templates, such as "Sheriff's issue
    pistol", checked by `splat`'s rules in the troupe. Its staff note is not kept."""
    rules = equipment_rules(db, splat, troupe.id)
    fields = checked(rules, fields)
    if any(t.name.lower() == fields.name.lower() for t in troupe_templates(db, troupe.id)):
        raise conflict(f"{troupe.name} already has a template called {fields.name}.")
    rule_set = db.scalars(select(RuleSet).where(RuleSet.splat == splat)).one()
    template = EquipmentTemplate(
        rule_set_id=rule_set.id,
        troupe_id=troupe.id,
        name=fields.name,
        kind=fields.kind,
        grade=fields.grade,
        qualities=item_qualities_to_list(fields.qualities),
        crafted=fields.crafted,
        effects=effects_to_list(fields.effects),
        description=fields.description,
        page=None,
    )
    db.add(template)
    db.flush()
    audit.record(
        db,
        staff,
        "equipment.template_saved",
        troupe_id=troupe.id,
        item=template.name,
        what=describe(rules, fields),
    )
    return template


def delete_template(db: Session, staff: User, troupe: Troupe, template: EquipmentTemplate) -> None:
    audit.record(db, staff, "equipment.template_deleted", troupe_id=troupe.id, item=template.name)
    db.delete(template)
    db.flush()
