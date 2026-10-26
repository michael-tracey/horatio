"""What each splat's cost-rule conditions can test, and how those facts are worked out."""

from collections.abc import Callable, Mapping, Sequence, Set
from dataclasses import dataclass, field
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
    # How each fact reads in plain words (horatio.rules.conditions.describe).
    fact_words: Mapping[str, Any] = field(default_factory=dict)


# --- Vampire ---------------------------------------------------------------


def vampire_generation(sheet: Sequence[SheetTrait]) -> int:
    """The Generation background's rating, or 1 without one. A rating of 0 also
    counts as 1, as it did in Yorick."""
    for trait in sheet:
        if trait.category == "backgrounds" and trait.name == "Generation":
            return trait.rating or 1
    return 1


def vampire_in_clan_disciplines(rules: TroupeRules, sheet: Sequence[SheetTrait]) -> list[str]:
    """The clan's in-clan disciplines (or the ones a merit sets in their place)
    plus any extra in-clan disciplines on the sheet."""
    from horatio.rules.grants import in_clan_replaced

    replaced = in_clan_replaced(rules.rule_set, sheet)
    disciplines: list[str] = []
    for trait in sheet:
        if trait.category == "clan" and replaced is None:
            disciplines.extend(
                rules.rule_set.trait_properties("clan", trait.name).get("in_clan", [])
            )
    disciplines.extend(replaced or [])
    disciplines.extend(t.name for t in sheet if t.category == "extra_in_clan_disciplines")
    return disciplines


# Powers named after their discipline ("Celerity: Projectile"), in-clan when it is.
VAMPIRE_ELDER_POWERS = frozenset({"elder_disciplines", "luminary_disciplines"})


@dataclass(frozen=True)
class VampireSheet:
    """What a vampire's sheet says for every trait priced on it."""

    generation: int
    # The clan or bloodline exactly ("Brujah: True Brujah").
    clan: str
    in_clan: frozenset[str]
    # What its grants price as in-clan (Thaumaturgic Expertise's extra path).
    priced_in_clan: Set[tuple[str, str, str | None]]


def vampire_sheet(rules: TroupeRules, sheet: Sequence[SheetTrait]) -> VampireSheet:
    """Worked out once for each sheet, as pricing asks it of every trait it prices."""
    from horatio.rules.grants import priced

    def work_out() -> VampireSheet:
        return VampireSheet(
            generation=vampire_generation(sheet),
            clan=next((t.name for t in sheet if t.category == "clan"), ""),
            in_clan=frozenset(vampire_in_clan_disciplines(rules, sheet)),
            priced_in_clan=priced(rules.rule_set, sheet).in_clan,
        )

    return rules.rule_set.remembered(("vampire", tuple(sheet)), work_out)


def in_clan_names(trait: SheetTrait) -> set[str]:
    """An in-clan entry matches the trait's name, or its name with its detail: so
    "Celerity" matches any Celerity, but "Thaumaturgy: Path of Blood" only that path.
    An elder or luminary power matches its discipline."""
    names = {trait.name, trait.full_name}
    if trait.category in VAMPIRE_ELDER_POWERS:
        names.add(trait.name.split(":")[0].strip())
    return names


def vampire_facts(rules: TroupeRules, sheet: Sequence[SheetTrait], trait: SheetTrait) -> Facts:
    from horatio.rules.grants import matching

    found = vampire_sheet(rules, sheet)
    return {
        "generation": found.generation,
        "in_clan": not in_clan_names(trait).isdisjoint(found.in_clan)
        or matching(found.priced_in_clan, trait) is not None,
        # The clan or bloodline exactly ("Brujah: True Brujah"), and its clan ("Brujah").
        "clan": found.clan,
        "clan_family": found.clan.split(":")[0].strip(),
    }


SPLATS: dict[str, Splat] = {
    "vampire": Splat(
        fact_names=frozenset({"generation", "in_clan", "clan", "clan_family"}),
        facts=vampire_facts,
        in_clan=vampire_in_clan_disciplines,
        fact_words={
            "generation": "Generation {}",
            "in_clan": ("in-clan", "out-of-clan"),
            "clan": "{}",
            "clan_family": "{} clan",
        },
    ),
}
