"""Influence: the named actions Elite and Underworld influence can take (CONTEXT.md:
Influence Action), and what a character can reach with them.

The actions are rules data, on the `influence_elite` and `influence_underworld`
action kinds, so a troupe can rename or add them with a house action kind. Each
has a key, which answers and the influence log store, and a name:

- a **general** action has a level, 1 to 10. It needs an influence rating at
  least its level, or one less when it uses one of the character's own
  specialisations of that type (MET: VtM core, p. 512);
- a **conflict** action (Attack, Block, Boost, Defend, and a discovery block) is
  a targeted action, with no level (p. 510). A Block, discovery blocks included,
  can be paid with actions of either type (p. 511).

Each type has its own list, and a general action is spent from its own type
only. An answer from before actions had names holds only a level; it reads as
the general action at that level.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, get_args

from sqlalchemy.orm import Session

from horatio import specializations
from horatio.models import Character
from horatio.rules.model import TroupeRules
from horatio.sheets import rules_for, unprocessable

InfluenceType = Literal["elite", "underworld"]
TYPES: tuple[InfluenceType, ...] = get_args(InfluenceType)

# The action kind each type's downtime actions are, and the background behind it.
ACTION_KINDS: dict[InfluenceType, str] = {
    "elite": "influence_elite",
    "underworld": "influence_underworld",
}
TRAITS: dict[InfluenceType, str] = {
    "elite": "Influences: The Elite",
    "underworld": "Influences: The Underworld",
}
SPECIALIZATIONS: dict[InfluenceType, str] = {
    "elite": "influence_elite_specializations",
    "underworld": "influence_underworld_specializations",
}
TYPE_NAMES: dict[InfluenceType, str] = {"elite": "Elite", "underworld": "Underworld"}

# The targeted actions' keys, the same in both types.
ATTACK = "attack"
BLOCK = "block"
BOOST = "boost"
DEFEND = "defend"
DISCOVERY_BLOCK = "discovery_block"


@dataclass(frozen=True)
class InfluenceAction:
    key: str
    name: str
    # None for a conflict action.
    level: int | None = None
    conflict: bool = False

    @property
    def general(self) -> bool:
        return not self.conflict

    @property
    def label(self) -> str:
        """As players and staff say it: "5: Lockdown", or "Attack"."""
        return f"{self.level}: {self.name}" if self.level is not None else self.name

    def reachable(self, rating: int, with_specialization: bool) -> bool:
        """Whether a character with this rating can take it (p. 512)."""
        return self.level is None or self.level <= rating + (1 if with_specialization else 0)


def type_of(action_kind: str | None) -> InfluenceType | None:
    """The influence type of an action kind, or None for any other kind."""
    return next((t for t, kind in ACTION_KINDS.items() if kind == action_kind), None)


def action_from(data: Mapping[str, Any]) -> InfluenceAction:
    level = data.get("level")
    return InfluenceAction(
        key=data["key"],
        name=data["name"],
        level=None if data.get("conflict") else level,
        conflict=bool(data.get("conflict")),
    )


def actions(rules: TroupeRules, influence_type: InfluenceType) -> list[InfluenceAction]:
    """The type's actions under these troupe rules, in the rules' order."""
    kind = rules.action_kinds().get(ACTION_KINDS[influence_type])
    return [action_from(a) for a in kind.actions] if kind else []


def find(rules: TroupeRules, influence_type: InfluenceType, key: str) -> InfluenceAction | None:
    return next((a for a in actions(rules, influence_type) if a.key == key), None)


def at_level(
    rules: TroupeRules, influence_type: InfluenceType, level: int
) -> InfluenceAction | None:
    """The general action at a level, for answers from before actions had names."""
    return next((a for a in actions(rules, influence_type) if a.general and a.level == level), None)


def label(rules: TroupeRules, influence_type: InfluenceType, key: str) -> str:
    """An action's label, or its key made readable when the rules no longer have it."""
    found = find(rules, influence_type, key)
    return found.label if found else key.replace("_", " ").capitalize()


def named_in(
    found: Sequence[InfluenceAction], structured: Mapping[str, Any]
) -> InfluenceAction | None:
    """The action an influence answer's fields name, out of `found`: by its key, or
    by its level alone for an answer from before actions had names."""
    key = structured.get("action")
    if isinstance(key, str) and key:
        return next((a for a in found if a.key == key), None)
    level = structured.get("level")
    if isinstance(level, int) and not isinstance(level, bool):
        return next((a for a in found if a.general and a.level == level), None)
    return None


def answer_action(
    rules: TroupeRules, influence_type: InfluenceType, structured: Mapping[str, Any]
) -> InfluenceAction | None:
    """The action an influence answer names, under these troupe rules."""
    return named_in(actions(rules, influence_type), structured)


def specialization_name(name: str, detail: str) -> str:
    """A specialisation as it is written down: its name, or a custom one's text."""
    return detail if name == specializations.CUSTOM else name


@dataclass
class Standing:
    """What one character can do with one type of influence."""

    influence_type: InfluenceType
    rating: int
    # The character's own specialisations of this type, as written down.
    held: list[str]
    # Every specialisation of this type the character's troupe allows.
    options: list[str]
    actions: list[InfluenceAction]

    def reachable(self, action: InfluenceAction, specialization: str | None) -> bool:
        return action.reachable(self.rating, bool(specialization) and specialization in self.held)


def standings(db: Session, character: Character) -> dict[InfluenceType, Standing]:
    """The character's rating, specialisations and actions in each type, under its
    own troupe rules. The rating is the sheet's as it stands."""
    rules = rules_for(db, character)
    kinds = {k.category: k for k in specializations.kinds(db, character)}
    found: dict[InfluenceType, Standing] = {}
    for influence_type in TYPES:
        kind = kinds.get(SPECIALIZATIONS[influence_type])
        held = [specialization_name(n, d) for n, d in kind.held] if kind else []
        found[influence_type] = Standing(
            influence_type=influence_type,
            rating=kind.parent_rating if kind else 0,
            held=held,
            options=sorted(set(kind.options if kind else []) | set(held)),
            actions=actions(rules, influence_type),
        )
    return found


def check_answer(
    standing: Standing, prompt: str, structured: Mapping[str, Any]
) -> InfluenceAction | None:
    """Refuse an influence answer that names no action of its type, or one the
    character cannot reach. Returns the action, or None for a troupe's own kind
    with no named actions."""
    if not standing.actions:
        return None
    type_name = TYPE_NAMES[standing.influence_type]
    specialization = structured.get("specialization")
    if specialization is not None and not isinstance(specialization, str):
        raise unprocessable(f"{prompt!r}: the specialisation is a name.")
    chosen = named_in(standing.actions, structured)
    if chosen is None:
        raise unprocessable(f"{prompt!r}: choose one of the {type_name} actions.")
    if not standing.reachable(chosen, specialization):
        raise unprocessable(
            f"{prompt!r}: {chosen.label} needs {type_name} {chosen.level}, or "
            f"{(chosen.level or 1) - 1} with one of your {type_name} specialisations."
        )
    return chosen
