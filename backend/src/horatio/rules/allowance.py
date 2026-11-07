"""Working out a character's action allowance from its sheet (CONTEXT.md: Action Allowance)."""

from collections.abc import Sequence
from dataclasses import dataclass

from horatio.rules.model import AllowanceRuleData, SheetTrait, TroupeRules


@dataclass(frozen=True)
class AllowanceLine:
    """One line of the breakdown shown to the player: where some actions came from."""

    action_kind: str
    source: str
    amount: int
    # What the actions mean, from the rule (Hunted's are owed to staying hidden).
    note: str = ""
    # What the actions may only be spent on: a Science's field, "Chemistry" (p. 97).
    only: str = ""


def held(trait: SheetTrait, min_rating: int) -> bool:
    """A trait with no rating (a ritual) counts while it is on the sheet."""
    return trait.rating is None or trait.rating >= min_rating


def field_lines(rule: AllowanceRuleData, sheet: Sequence[SheetTrait]) -> list[AllowanceLine]:
    """One line for each field of the trait the character holds, best first: each
    Science gives one action, spent only on its field (MET: VtM core p. 97). With
    `detail_ratings`, the character's best of the trait needs that rating for each
    further field to count."""
    fields = sorted(
        (
            t
            for t in sheet
            if t.category == rule.category
            and t.name == rule.trait
            and t.detail
            and held(t, rule.min_rating)
        ),
        key=lambda t: (-(t.rating or 0), t.detail),
    )
    best = (fields[0].rating or 0) if fields else 0
    lines: list[AllowanceLine] = []
    for n, trait in enumerate(fields):
        needs = rule.detail_ratings
        if needs and (n >= len(needs) or best < needs[n]):
            break
        lines.append(
            AllowanceLine(rule.action_kind, trait.full_name, rule.amount, rule.note, trait.detail)
        )
    return lines


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
            found = [AllowanceLine(rule.action_kind, "Everyone", rule.amount, rule.note)]
        elif rule.scheme == "per_detail":
            found = field_lines(rule, sheet)
        else:
            trait = next(
                (
                    t
                    for t in sheet
                    if t.category == rule.category
                    and t.name == rule.trait
                    and held(t, rule.min_rating)
                ),
                None,
            )
            if trait is None:
                continue
            rating = trait.rating or 0
            amount = rule.amount * rating if rule.scheme == "per_dot" else rule.amount
            source = f"{trait.name} {rating}" if rule.scheme == "per_dot" else trait.name
            found = [AllowanceLine(rule.action_kind, source, amount, rule.note)]
        for line in found:
            if line.amount:
                totals[rule.action_kind] += line.amount
                lines.append(line)
    return {k: max(0, v) for k, v in totals.items()}, lines
