"""Grants: traits that give a character other traits, or let others go higher.

A grant names a source (a trait, perhaps at a rating) and what holding it does:

    add          change another trait's rating by `amount` (Rugged: +1 Healthy;
                 Low Pain Threshold: -1 Injured), the dots free
    free_up_to   the first `amount` dots of a trait are free (Personal Cult: 5 in
                 a background); dots already bought there are refunded. A merit
                 is given this way, whole and at its value, whatever `amount`
                 says (Extrasensory Perceptions: Acute Sense)
    raise_max    the trait can go `amount` higher than its category usually allows
                 (Blood of the Tzimisce: Lore +2)
    price_in_clan  the trait is priced as in-clan without being in-clan
                 (Thaumaturgic Expertise: another path)
    replace_in_clan  the character's in-clan disciplines are the target's `names`
                 instead of their clan's (Shadows of the Past, Blight of the
                 Ever-Hungry). Extra in-clan disciplines still come on top, and the
                 names need not be in the catalogue. It changes no trait, so it is
                 read by splats.vampire_in_clan_disciplines, not by `effects`
    cost_percent the trait costs `amount` percent of its price, rounded up
                 (Supernatural Aria: Performance: Singing at 50)
    convert      the trait named in `from` becomes the target, keeping its rating
                 (a Path merit turns Humanity into that Path); undone with the merit.
                 The target can be the player's choice (Path Adherent)

A grant can also hold only `when` a condition holds, in the vocabulary of
horatio.rules.checks: Fortitude gives a Stamina-focused character a health level
per track, so its grants say `when = { has = { ..., name = "Stamina" } }`.

The target is fixed (`name`, and perhaps `detail`), every trait of some names
(`names`) or of the whole category, or the player's choice: with `choose`, the
source trait's detail says which, as "Resources" or "Performance: Singing".
`choose = "any"` allows any trait in the target's categories.
"""

from collections.abc import Mapping, Sequence, Set
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal

from horatio.rules.checks import matches
from horatio.rules.model import RuleSetData, SheetTrait

Kind = Literal[
    "add", "free_up_to", "raise_max", "price_in_clan", "replace_in_clan", "cost_percent", "convert"
]
KINDS = (
    "add",
    "free_up_to",
    "raise_max",
    "price_in_clan",
    "replace_in_clan",
    "cost_percent",
    "convert",
)
TraitKey = tuple[str, str, str]  # category, name, detail


@dataclass(frozen=True)
class GrantData:
    key: str
    source: Mapping[str, Any]
    kind: Kind
    target: Mapping[str, Any]
    amount: int
    page: str | None = None
    # A condition (horatio.rules.checks) the sheet must meet as well.
    when: Mapping[str, Any] | None = None
    # For a conversion: the trait that becomes the target.
    convert_from: Mapping[str, str] | None = None

    @property
    def categories(self) -> list[str]:
        return list(self.target.get("categories") or [self.target["category"]])


@dataclass
class Effects:
    """What the sheet's grants do, worked out from the sheet."""

    # Dots added (or taken away) by `add` grants.
    added: dict[TraitKey, int] = field(default_factory=dict)
    # The most dots `free_up_to` grants make free.
    free_up_to: dict[TraitKey, int] = field(default_factory=dict)
    # Raises: (category, name or None for the whole category, detail or None, amount).
    raises: list[tuple[str, str | None, str | None, int]] = field(default_factory=list)
    # Traits priced as in-clan, and price percentages, by (category, name, detail
    # or None for any).
    in_clan_priced: set[tuple[str, str, str | None]] = field(default_factory=set)
    cost_percent: dict[tuple[str, str, str | None], int] = field(default_factory=dict)
    # Conversions the sheet's grants want: (category, from name) -> to name.
    converts: dict[tuple[str, str], str] = field(default_factory=dict)
    # Which source traits each granted trait owes its dots to.
    sources: dict[TraitKey, list[str]] = field(default_factory=dict)
    # Source traits whose detail does not say what they grant.
    unchosen: list[tuple[SheetTrait, GrantData]] = field(default_factory=list)


def holds_source(trait: SheetTrait, source: Mapping[str, Any]) -> bool:
    if trait.category != source["category"] or trait.name != source["name"]:
        return False
    return trait.rating is None or trait.rating >= source.get("rating", 1)


def choices(grant: GrantData, rule_set: RuleSetData) -> list[str]:
    """The names a player can choose from, for a grant that lets them choose."""
    choose = grant.target.get("choose")
    if choose is None:
        return []
    if choose == "any":
        prefix = grant.target.get("choose_prefix", "")
        excluded = set(grant.target.get("except", []))
        return sorted(
            {
                n
                for (c, n) in rule_set.traits
                if c in grant.categories and n.startswith(prefix) and n not in excluded
            }
        )
    return list(choose)


def chosen_target(
    grant: GrantData, detail: str, rule_set: RuleSetData
) -> tuple[str, str, str] | None:
    """The trait a source's detail chooses, or None if it chooses nothing valid."""
    options = choices(grant, rule_set)
    if detail.strip() in options:
        name, sub = detail.strip(), ""
    else:
        name, _, sub = (part.strip() for part in detail.partition(":"))
    if name not in options:
        return None
    category = next((c for c in grant.categories if (c, name) in rule_set.traits), None)
    if category is None:
        return None
    return (category, name, sub)


def effects(
    grants: Sequence[GrantData], sheet: Sequence[SheetTrait], rule_set: RuleSetData
) -> Effects:
    found = Effects()
    # Each grant is only held through its source trait.
    by_name: dict[tuple[str, str], list[SheetTrait]] = {}
    for trait in sheet:
        by_name.setdefault((trait.category, trait.name), []).append(trait)
    for grant in grants:
        for trait in by_name.get((grant.source["category"], grant.source["name"]), ()):
            if not holds_source(trait, grant.source):
                continue
            if grant.when is not None and not matches(grant.when, sheet, trait):
                continue
            label = trait.full_name
            if grant.kind == "replace_in_clan":
                continue
            if grant.kind == "convert":
                assert grant.convert_from is not None
                if "choose" in grant.target:
                    chosen = chosen_target(grant, trait.detail, rule_set)
                    if chosen is None:
                        found.unchosen.append((trait, grant))
                        continue
                    to = chosen[1]
                else:
                    to = grant.target["name"]
                found.converts[(grant.convert_from["category"], grant.convert_from["name"])] = to
                continue
            if "choose" in grant.target:
                target = chosen_target(grant, trait.detail, rule_set)
                if target is None:
                    found.unchosen.append((trait, grant))
                    continue
                category, name, detail = target
                if grant.kind == "raise_max":
                    found.raises.append((category, name, detail or None, grant.amount))
                    continue
                if grant.kind == "price_in_clan":
                    found.in_clan_priced.add((category, name, detail or None))
                    continue
                if grant.kind == "cost_percent":
                    found.cost_percent[(category, name, detail or None)] = grant.amount
                    continue
            elif grant.kind in ("price_in_clan", "cost_percent"):
                targets: list[str] = grant.target.get("names") or [grant.target["name"]]
                for category in grant.categories:
                    for name in targets:
                        key3: tuple[str, str, str | None] = (
                            category,
                            name,
                            grant.target.get("detail"),
                        )
                        if grant.kind == "price_in_clan":
                            found.in_clan_priced.add(key3)
                        else:
                            found.cost_percent[key3] = grant.amount
                continue
            elif grant.kind == "raise_max":
                names = grant.target.get("names") or [grant.target.get("name")]
                for category in grant.categories:
                    for name in names:
                        found.raises.append(
                            (category, name, grant.target.get("detail"), grant.amount)
                        )
                continue
            else:
                category = grant.target["category"]
                name = grant.target["name"]
                detail = grant.target.get("detail", "")
            key = (category, name, detail)
            if grant.kind == "add":
                found.added[key] = found.added.get(key, 0) + grant.amount
            else:
                found.free_up_to[key] = max(found.free_up_to.get(key, 0), grant.amount)
            found.sources.setdefault(key, []).append(label)
    return found


@dataclass(frozen=True)
class Priced:
    """What a sheet's grants do to prices."""

    in_clan: Set[tuple[str, str, str | None]]
    cost_percent: Mapping[tuple[str, str, str | None], int]


def priced(rule_set: RuleSetData, sheet: Sequence[SheetTrait]) -> Priced:
    """What the sheet's grants price as in-clan, and at what percent: worked out
    once for each sheet, as pricing asks it of every trait it prices."""

    def work_out() -> Priced:
        found = effects(rule_set.grants, sheet, rule_set)
        return Priced(frozenset(found.in_clan_priced), MappingProxyType(dict(found.cost_percent)))

    return rule_set.remembered(("priced", tuple(sheet)), work_out)


def in_clan_replaced(rule_set: RuleSetData, sheet: Sequence[SheetTrait]) -> list[str] | None:
    """The in-clan disciplines a `replace_in_clan` grant sets in place of the clan's,
    or None if the sheet holds none. Asked for every sheet a trial tries, so it
    looks only at the few grants of that kind."""
    replacing = rule_set.remembered(
        ("replacing_in_clan",),
        lambda: tuple(g for g in rule_set.grants if g.kind == "replace_in_clan"),
    )
    for grant in replacing:
        for trait in sheet:
            if holds_source(trait, grant.source) and (
                grant.when is None or matches(grant.when, sheet, trait)
            ):
                return list(grant.target["names"])
    return None


def matching(
    keys: Mapping[tuple[str, str, str | None], Any] | Set[tuple[str, str, str | None]],
    trait: SheetTrait,
) -> tuple[str, str, str | None] | None:
    """The entry for `trait`: its detail exactly, or any detail."""
    for key in (
        (trait.category, trait.name, trait.detail or None),
        (trait.category, trait.name, None),
    ):
        if key in keys:
            return key
    return None


def raised_by(effects: Effects, category: str, name: str, detail: str) -> int:
    """How much higher than usual the grants let a trait go."""
    return sum(
        amount
        for c, n, d, amount in effects.raises
        if c == category and (n is None or n == name) and (d is None or d == detail)
    )


def grant_from_dict(raw: Mapping[str, Any]) -> GrantData:
    return GrantData(
        key=raw["key"],
        source=raw["source"],
        kind=raw["kind"],
        target=raw["target"],
        amount=raw["amount"],
        page=raw.get("page"),
        when=raw.get("when"),
        convert_from=raw.get("from"),
    )


def grant_to_dict(grant: GrantData) -> dict[str, Any]:
    found = {k: v for k, v in vars(grant).items() if v is not None and k != "convert_from"}
    if grant.convert_from is not None:
        found["from"] = grant.convert_from
    return found


def validate_grant(
    grant: GrantData, rule_set_traits: set[tuple[str, str]], categories: set[str]
) -> None:
    source = (grant.source["category"], grant.source["name"])
    if source not in rule_set_traits:
        raise ValueError(f"grant {grant.key} comes from an unknown trait {source}")
    if grant.kind not in KINDS:
        raise ValueError(f"grant {grant.key} has unknown kind {grant.kind!r}")
    for category in grant.categories:
        if category not in categories:
            raise ValueError(f"grant {grant.key} names unknown category {category!r}")
    names = list(grant.target.get("names") or [])
    if grant.kind == "replace_in_clan":
        # The names are disciplines to be in-clan, which the catalogue may lack
        # (the Graveborne path of Blight of the Ever-Hungry).
        if not names:
            raise ValueError(f"grant {grant.key} must name the in-clan disciplines")
        return
    if grant.target.get("name"):
        names.append(grant.target["name"])
    choose = grant.target.get("choose")
    if isinstance(choose, list):
        names += choose
    for name in names:
        if not any((c, name) in rule_set_traits for c in grant.categories):
            raise ValueError(f"grant {grant.key} names unknown trait {name!r}")
    if grant.kind == "convert" and not (
        grant.convert_from and (grant.target.get("name") or choose)
    ):
        raise ValueError(
            f"grant {grant.key} must convert `from` one trait to a named or chosen one"
        )
    if grant.kind in ("add", "free_up_to") and not (grant.target.get("name") or choose):
        raise ValueError(f"grant {grant.key} must name one trait, or let the player choose one")
