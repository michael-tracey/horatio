"""Equipment (issue #283): weapons, protective gear and miscellaneous gear, with the
book's qualities (MET: VTM pp. 515-524). The rules are horatio.rules.equipment's;
`check` is what every equipment ticket asks before an item is made or changed.

A troupe's storytellers and assistant storytellers give equipment to the characters
whose home troupe it is, PCs and the troupe's NPCs alike (issue #280), and only to
them: a visiting character carries its own home troupe's equipment, which the
troupe it visits can't change. They can make an item special: any number of
qualities, still keeping the rules between them, and effects of the troupe's own.
They change an item or take it back with a reason, and the holder's player is told.

An item belongs to the character, wherever its home is: the staff who see and change
it are those of the holder's home troupe now. Each item keeps its history in
`equipment_events`, and each change goes in the character's log too.
"""

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio import audit, notifications
from horatio.models import (
    Character,
    EquipmentEvent,
    EquipmentItem,
    EquipmentTemplate,
    RuleSet,
    Troupe,
    User,
)
from horatio.permissions import TroupeAction, allows, troupe_role
from horatio.rules.equipment import (
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
    if event.action == "passed":
        return f"Given by {event.from_name} to {event.to_name}"
    if event.action == "discarded":
        return f"Discarded by {event.from_name}"
    return f"Restored to {event.to_name}"


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


def troupe_items(
    db: Session,
    troupe_id: uuid.UUID,
    *,
    character_id: uuid.UUID | None = None,
    kind: str | None = None,
    statuses: Sequence[str] = ("held",),
) -> list[tuple[EquipmentItem, Character]]:
    """Items of the troupe's active home characters, whichever troupe gave them, by
    holder and then name."""
    query = (
        select(EquipmentItem, Character)
        .join(Character, EquipmentItem.character_id == Character.id)
        .where(
            func.coalesce(Character.home_troupe_id, Character.owner_troupe_id) == troupe_id,
            Character.status == "active",
            EquipmentItem.status.in_(list(statuses)),
        )
        .order_by(
            func.lower(Character.name),
            Character.id,
            func.lower(EquipmentItem.name),
            EquipmentItem.id,
        )
    )
    if character_id is not None:
        query = query.where(EquipmentItem.character_id == character_id)
    if kind is not None:
        query = query.where(EquipmentItem.kind == kind)
    return [(item, character) for item, character in db.execute(query)]


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
