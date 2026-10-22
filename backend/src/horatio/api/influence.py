"""How influence actions and a character's reach with them go out (horatio.influence)."""

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from horatio import influence
from horatio.influence import InfluenceType
from horatio.rules.model import TroupeRules


class InfluenceActionOut(BaseModel):
    key: str
    name: str
    # As players and staff say it: "5: Lockdown", or "Attack".
    label: str
    # None for a conflict action.
    level: int | None
    # A targeted action: Attack, Block, Boost, Defend or a discovery block.
    conflict: bool


class InfluenceStandingOut(BaseModel):
    """What a character can do with one type of influence, for the downtime form."""

    action_kind: str
    type: InfluenceType
    rating: int
    # The character's own specialisations of this type: an action using one counts
    # the rating one higher.
    held: list[str]
    # Every specialisation of this type the troupe allows, held ones included.
    options: list[str]
    actions: list[InfluenceActionOut]


class InfluenceAnswerOut(BaseModel):
    """What an influence answer names, for staff."""

    type: InfluenceType
    specialization: str | None
    # None when the answer names no action the rules know.
    action_key: str | None
    action: str | None
    level: int | None
    conflict: bool


def action_out(action: influence.InfluenceAction) -> InfluenceActionOut:
    return InfluenceActionOut(
        key=action.key,
        name=action.name,
        label=action.label,
        level=action.level,
        conflict=action.conflict,
    )


def standing_out(standing: influence.Standing) -> InfluenceStandingOut:
    return InfluenceStandingOut(
        action_kind=influence.ACTION_KINDS[standing.influence_type],
        type=standing.influence_type,
        rating=standing.rating,
        held=standing.held,
        options=standing.options,
        actions=[action_out(a) for a in standing.actions],
    )


def answer_out(
    rules: TroupeRules, action_kind: str | None, structured: Mapping[str, Any]
) -> InfluenceAnswerOut | None:
    """An influence answer's action and specialisation, or None for any other answer."""
    influence_type = influence.type_of(action_kind)
    if influence_type is None:
        return None
    action = influence.answer_action(rules, influence_type, structured)
    specialization = structured.get("specialization")
    return InfluenceAnswerOut(
        type=influence_type,
        specialization=specialization or None if isinstance(specialization, str) else None,
        action_key=action.key if action else None,
        action=action.label if action else None,
        level=action.level if action else None,
        conflict=action.conflict if action else False,
    )
