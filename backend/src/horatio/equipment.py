"""Equipment (issue #283): weapons, protective gear and miscellaneous gear, with the
book's qualities (MET: VTM pp. 515-524). The rules are horatio.rules.equipment's;
this is the check every equipment ticket uses before an item is made or changed.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

from horatio.rules.equipment import (
    Assessment,
    EquipmentRules,
    Facts,
    ItemQuality,
    assess,
)
from horatio.rules.store import read_troupe_rules

__all__ = [
    "Assessment",
    "EquipmentRefused",
    "Facts",
    "ItemQuality",
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
