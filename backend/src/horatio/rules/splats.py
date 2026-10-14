"""What each splat's cost-rule conditions can test, and how those facts are worked out."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from horatio.rules.model import SheetTrait, TroupeRules

Facts = Mapping[str, Any]
FactsFn = Callable[[TroupeRules, Sequence[SheetTrait], SheetTrait], Facts]


@dataclass(frozen=True)
class Splat:
    fact_names: frozenset[str]
    facts: FactsFn
    # The character's in-clan (native) powers, for checks.
    in_clan: Callable[[TroupeRules, Sequence[SheetTrait]], list[str]] = lambda _r, _s: []


# --- Vampire ---------------------------------------------------------------


def vampire_generation(sheet: Sequence[SheetTrait]) -> int:
    """The Generation background's rating, or 1 without one. A rating of 0 also
    counts as 1, as it did in Yorick."""
    for trait in sheet:
        if trait.category == "backgrounds" and trait.name == "Generation":
            return trait.rating or 1
    return 1


def vampire_in_clan_disciplines(rules: TroupeRules, sheet: Sequence[SheetTrait]) -> list[str]:
    """The clan's in-clan disciplines plus any extra in-clan disciplines on the sheet."""
    disciplines: list[str] = []
    for trait in sheet:
        if trait.category == "clan":
            disciplines.extend(
                rules.rule_set.trait_properties("clan", trait.name).get("in_clan", [])
            )
    disciplines.extend(t.name for t in sheet if t.category == "extra_in_clan_disciplines")
    return disciplines


def vampire_is_in_clan(rules: TroupeRules, sheet: Sequence[SheetTrait], trait: SheetTrait) -> bool:
    """An in-clan entry matches the trait's name, or its name with its detail: so
    "Celerity" matches any Celerity, but "Thaumaturgy: Path of Blood" only that path."""
    return any(
        entry in (trait.name, trait.full_name)
        for entry in vampire_in_clan_disciplines(rules, sheet)
    )


def vampire_facts(rules: TroupeRules, sheet: Sequence[SheetTrait], trait: SheetTrait) -> Facts:
    return {
        "generation": vampire_generation(sheet),
        "in_clan": vampire_is_in_clan(rules, sheet, trait) or priced_in_clan(rules, sheet, trait),
    }


def priced_in_clan(rules: TroupeRules, sheet: Sequence[SheetTrait], trait: SheetTrait) -> bool:
    """A grant prices the trait as in-clan (Thaumaturgic Expertise's extra path)."""
    from horatio.rules.grants import effects, matching

    found = effects(rules.rule_set.grants, sheet, rules.rule_set)
    return matching(found.in_clan_priced, trait) is not None


SPLATS: dict[str, Splat] = {
    "vampire": Splat(
        fact_names=frozenset({"generation", "in_clan"}),
        facts=vampire_facts,
        in_clan=vampire_in_clan_disciplines,
    ),
}
