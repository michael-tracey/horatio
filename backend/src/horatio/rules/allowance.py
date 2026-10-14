"""Working out a character's action allowance from its sheet (CONTEXT.md: Action Allowance)."""

from collections.abc import Sequence
from dataclasses import dataclass

from horatio.rules.model import SheetTrait, TroupeRules


@dataclass(frozen=True)
class AllowanceLine:
    """One line of the breakdown shown to the player: where some actions came from."""

    action_kind: str
    source: str
    amount: int


def allowance(
    rules: TroupeRules, sheet: Sequence[SheetTrait]
) -> tuple[dict[str, int], list[AllowanceLine]]:
    """Actions of each kind, and the breakdown that produced them. A kind never
    goes below zero, however many flaws take from it."""
    totals = {key: 0 for key in rules.action_kinds()}
    lines: list[AllowanceLine] = []
    for rule in rules.allowance_rules():
        if rule.action_kind not in totals:
            continue
        if rule.trait is None:
            amount, source = rule.amount, "Everyone"
        else:
            trait = next(
                (
                    t
                    for t in sheet
                    if t.category == rule.category
                    and t.name == rule.trait
                    and (t.rating or 0) >= rule.min_rating
                ),
                None,
            )
            if trait is None:
                continue
            rating = trait.rating or 0
            amount = rule.amount * rating if rule.scheme == "per_dot" else rule.amount
            source = f"{trait.name} {rating}" if rule.scheme == "per_dot" else trait.name
        if amount:
            totals[rule.action_kind] += amount
            lines.append(AllowanceLine(rule.action_kind, source, amount))
    return {k: max(0, v) for k, v in totals.items()}, lines
