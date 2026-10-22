"""What a targeted influence action is aimed at (MET: VtM core, pp. 510-511).

Attack, Defend, Boost and Block are logged with a target:

- **Attack:** a character's influence, or the influence behind another log entry
  ("the actions behind UW268"), since an attacker need not know whose it is. It
  aims at one type, its own or the other; the other costs more (p. 510);
- **Defend:** the defender's own influence of the same type, unless staff name
  another character;
- **Boost:** another character's influence of the same type, never the booster's own;
- **Block:** an activity, such as "acquiring firearms", in one type. The actions
  paying for it can be of either type (p. 511).

An entry still waiting on its details, or an imported one, can go without.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy.orm import Session

from horatio import influence
from horatio.influence import InfluenceType
from horatio.models import Character, InfluenceEntry
from horatio.sheets import unprocessable

TARGETED = frozenset({influence.ATTACK, influence.BLOCK, influence.BOOST, influence.DEFEND})


@dataclass(frozen=True)
class Target:
    """A targeted entry's target, checked, as the entry keeps it."""

    character_id: uuid.UUID | None = None
    name: str = ""
    entry_id: uuid.UUID | None = None
    influence_type: InfluenceType | None = None
    activity: str = ""


NONE = Target()


def checked(
    db: Session,
    troupe_id: uuid.UUID,
    *,
    influence_type: InfluenceType,
    action_key: str | None,
    character_id: uuid.UUID | None,
    wanted: Target,
    required: bool,
    keep: InfluenceEntry | None,
    in_troupe: Callable[[Character], bool],
) -> Target:
    """The target an entry keeps: checked against its action, or none for an action
    that takes none. `required` is false for an entry still needing details."""
    if action_key not in TARGETED:
        return NONE
    type_name = influence.TYPE_NAMES[influence_type]
    aimed = wanted.influence_type
    if aimed is not None and aimed not in influence.TYPES:
        raise unprocessable("Influence is Elite or Underworld.")
    if action_key == influence.BLOCK:
        activity = " ".join(wanted.activity.split())
        if not activity and required:
            raise unprocessable("Say what the Block is on, such as acquiring firearms.")
        return Target(influence_type=aimed or influence_type, activity=activity)
    if aimed is not None and aimed != influence_type and action_key != influence.ATTACK:
        verb = "raises" if action_key == influence.BOOST else "protects"
        raise unprocessable(
            f"A {action_key.capitalize()} {verb} influence of its own type only: "
            f"{type_name} for {type_name}."
        )

    entry_id = wanted.entry_id if action_key == influence.ATTACK else None
    target_entry = db.get(InfluenceEntry, entry_id) if entry_id else None
    if entry_id is not None:
        if target_entry is None or target_entry.troupe_id != troupe_id:
            raise unprocessable("That entry is not in this troupe's log.")
        if keep is not None and target_entry.id == keep.id:
            raise unprocessable("An Attack cannot target its own entry.")
    target_id = wanted.character_id
    if target_id is None and action_key == influence.DEFEND:
        target_id = character_id  # one's own influence
    name = ""
    if target_id is not None:
        target = db.get(Character, target_id)
        if keep is not None and keep.target_character_id == target_id:
            name = keep.target_name  # as it was logged, whatever it is called now
        elif target is None or not in_troupe(target):
            raise unprocessable("The target is not in this troupe.")
        else:
            name = target.name
    if action_key == influence.BOOST and target_id is not None and target_id == character_id:
        raise unprocessable("A Boost is for someone else: boosting yourself does nothing (p. 512).")
    if required and target_id is None and target_entry is None:
        raise unprocessable(
            "Choose who the Attack is on, or the entry it targets."
            if action_key == influence.ATTACK
            else f"Choose who the {action_key.capitalize()} is for."
        )
    if aimed is None and target_entry is not None and target_id is None:
        aimed = cast(InfluenceType, target_entry.type)  # the influence behind that entry
    return Target(
        character_id=target_id, name=name, entry_id=entry_id, influence_type=aimed or influence_type
    )


def columns(target: Target) -> dict[str, Any]:
    """The entry's columns for a target."""
    return {
        "target_character_id": target.character_id,
        "target_name": target.name,
        "target_entry_id": target.entry_id,
        "target_type": target.influence_type,
        "target_activity": target.activity,
    }


def of(entry: InfluenceEntry) -> Target:
    return Target(
        character_id=entry.target_character_id,
        name=entry.target_name,
        entry_id=entry.target_entry_id,
        influence_type=entry.target_type,  # type: ignore[arg-type]  # checked by the database
        activity=entry.target_activity,
    )
