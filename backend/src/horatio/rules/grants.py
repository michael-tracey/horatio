"""Grants: traits that give a character other traits, or let others go higher.

A grant names a source (a trait, perhaps at a rating) and what holding it does:

    add          change another trait's rating by `amount` (Rugged: +1 Healthy;
                 Low Pain Threshold: -1 Injured), the dots free
    free_up_to   the first `amount` dots of a trait are free (Personal Cult: 5 in
                 a background); dots already bought there are refunded
    raise_max    the trait can go `amount` higher than its category usually allows
                 (Blood of the Tzimisce: Lore +2)

A grant can also hold only `when` a condition holds, in the vocabulary of
horatio.rules.checks: Fortitude gives a Stamina-focused character a health level
per track, so its grants say `when = { has = { ..., name = "Stamina" } }`.

The target is fixed (`name`, and perhaps `detail`), every trait of some names
(`names`) or of the whole category, or the player's choice: with `choose`, the
source trait's detail says which, as "Resources" or "Performance: Singing".
`choose = "any"` allows any trait in the target's categories.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from horatio.rules.checks import matches
from horatio.rules.model import RuleSetData, SheetTrait

Kind = Literal["add", "free_up_to", "raise_max"]
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
        return sorted({n for (c, n) in rule_set.traits if c in grant.categories})
    return list(choose)


def chosen_target(
    grant: GrantData, detail: str, rule_set: RuleSetData
) -> tuple[str, str, str] | None:
    """The trait a source's detail chooses, or None if it chooses nothing valid."""
    name, _, sub = (part.strip() for part in detail.partition(":"))
    if name not in choices(grant, rule_set):
        return None
    category = next((c for c in grant.categories if (c, name) in rule_set.traits), None)
    if category is None:
        return None
    return (category, name, sub)


def effects(
    grants: Sequence[GrantData], sheet: Sequence[SheetTrait], rule_set: RuleSetData
) -> Effects:
    found = Effects()
    for grant in grants:
        for trait in sheet:
            if not holds_source(trait, grant.source):
                continue
            if grant.when is not None and not matches(grant.when, sheet, trait):
                continue
            label = trait.full_name
            if "choose" in grant.target:
                target = chosen_target(grant, trait.detail, rule_set)
                if target is None:
                    found.unchosen.append((trait, grant))
                    continue
                category, name, detail = target
                if grant.kind == "raise_max":
                    found.raises.append((category, name, detail or None, grant.amount))
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
    )


def grant_to_dict(grant: GrantData) -> dict[str, Any]:
    return {k: v for k, v in vars(grant).items() if v is not None}


def validate_grant(
    grant: GrantData, rule_set_traits: set[tuple[str, str]], categories: set[str]
) -> None:
    source = (grant.source["category"], grant.source["name"])
    if source not in rule_set_traits:
        raise ValueError(f"grant {grant.key} comes from an unknown trait {source}")
    if grant.kind not in ("add", "free_up_to", "raise_max"):
        raise ValueError(f"grant {grant.key} has unknown kind {grant.kind!r}")
    for category in grant.categories:
        if category not in categories:
            raise ValueError(f"grant {grant.key} names unknown category {category!r}")
    names = list(grant.target.get("names") or [])
    if grant.target.get("name"):
        names.append(grant.target["name"])
    choose = grant.target.get("choose")
    if isinstance(choose, list):
        names += choose
    for name in names:
        if not any((c, name) in rule_set_traits for c in grant.categories):
            raise ValueError(f"grant {grant.key} names unknown trait {name!r}")
    if grant.kind != "raise_max" and not (grant.target.get("name") or choose):
        raise ValueError(f"grant {grant.key} must name one trait, or let the player choose one")
