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
    price_out_of_clan  the trait is priced as out-of-clan, and takes no free
                 starting dot, though the checks still count it native (Inept: the
                 in-clan discipline its detail names)
    no_free_dot  the extra in-clan discipline the target names takes no free
                 starting dot (Additional Common Discipline, p. 248). It is for the
                 extra disciplines (`extra_in_clan_disciplines`), and never for one
                 the clan itself has in-clan
    convert      the trait named in `from` becomes the target, keeping its rating
                 (a Path merit turns Humanity into that Path); undone with the merit.
                 The target can be the player's choice (Path Adherent)
    free_choices the player chooses several free traits, kept on the merit held
                 (CharacterTrait.choices), until a home troupe accepts the character
                 (Ventrue Royalty: three backgrounds, placed 4, 3 and 2). The target
                 names one `category` and what can be chosen: `choose` (names, or
                 "any" as below) or a `pool` of that category's catalogue:
                     types           the catalogue types (Clan, Sabbat, General…)
                     requirement     the requirement is one of these
                     other_clan      the requirement names a clan family other than
                                     the character's own
                     max_rating      a merit worth at most this
                     except_prefix   names not starting with this
                     except          names not to offer
                     except_granting leave out merits that grant a discipline, an
                                     in-clan one or the price of one
                     not_held        leave out merits the character holds
                 `picks` says how many and how much: `places` (amounts, each used
                 once on a different trait: 4, 3, 2), `count` (at most this many
                 picks) and `points` (the picked merits' values add up to at most
                 this). Each pick is given free like `free_up_to`: dots placed free,
                 a merit given whole and at its value (so it is not counted against
                 the merit limit, which is for merits bought), a specialisation
                 named free. A specialisation named "Custom" takes the player's
                 words as its detail. Removing the merit removes what it gave

A grant can also hold only `when` a condition holds, in the vocabulary of
horatio.rules.checks: Fortitude gives a Stamina-focused character a health level
per track, so its grants say `when = { has = { ..., name = "Stamina" } }`.

The target is fixed (`name`, and perhaps `detail`), every trait of some names
(`names`) or of the whole category, or the player's choice: with `choose`, the
source trait's detail says which, as "Resources" or "Performance: Singing".
`choose = "any"` allows any trait in the target's categories.

A `cost_percent` grant with no name in its target prices every trait of the
category at that percent (Chosen of Cappadocius: rituals at half, ×1 XP a dot).
"""

from collections import Counter
from collections.abc import Mapping, Sequence, Set
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal

from horatio.rules.checks import matches
from horatio.rules.model import FreeChoice, RuleSetData, SheetTrait

Kind = Literal[
    "add",
    "free_up_to",
    "raise_max",
    "price_in_clan",
    "replace_in_clan",
    "cost_percent",
    "convert",
    "free_choices",
    "price_out_of_clan",
    "no_free_dot",
]
KINDS = (
    "add",
    "free_up_to",
    "raise_max",
    "price_in_clan",
    "replace_in_clan",
    "cost_percent",
    "convert",
    "free_choices",
    "price_out_of_clan",
    "no_free_dot",
)
TraitKey = tuple[str, str, str]  # category, name, detail
# A trait a grant looks at: its detail, or None for any detail.
LooseKey = tuple[str, str, str | None]
# In a price entry, the name that stands for every trait of the category.
WHOLE_CATEGORY = "*"
# The specialisation a player names in their own words.
CUSTOM = "Custom"


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
    # For free_choices: how many the player chooses and how much (places, count, points).
    picks: Mapping[str, Any] | None = None

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
    # Traits priced as out-of-clan, and extra in-clan disciplines that take no free dot,
    # with the source traits (category, name) each is because of.
    out_of_clan_priced: dict[LooseKey, list[tuple[str, str]]] = field(default_factory=dict)
    no_free_dot: dict[LooseKey, list[tuple[str, str]]] = field(default_factory=dict)
    # Conversions the sheet's grants want: (category, from name) -> to name.
    converts: dict[tuple[str, str], str] = field(default_factory=dict)
    # The source trait of each conversion: (category, from name) -> (category, name).
    converted_by: dict[tuple[str, str], tuple[str, str]] = field(default_factory=dict)
    # Which source traits each granted trait owes its dots to: their names with details,
    # and as (category, name).
    sources: dict[TraitKey, list[str]] = field(default_factory=dict)
    givers: dict[TraitKey, list[tuple[str, str]]] = field(default_factory=dict)
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


@dataclass(frozen=True)
class Option:
    """A trait a free_choices grant lets the player choose."""

    category: str
    name: str
    # A merit's value; None for any other trait.
    rating: int | None = None
    # The player says more: a "Custom" specialisation's words.
    needs_detail: bool = False


def clan_family(sheet: Sequence[SheetTrait]) -> str | None:
    clan = next((t.name for t in sheet if t.category == "clan"), None)
    return clan.split(":")[0].strip() if clan else None


def clan_families(rule_set: RuleSetData) -> frozenset[str]:
    return rule_set.remembered(
        ("clan_families",),
        lambda: frozenset(n.split(":")[0].strip() for (c, n) in rule_set.traits if c == "clan"),
    )


def grants_disciplines(rule_set: RuleSetData) -> frozenset[str]:
    """The merits that give a discipline, an in-clan one or the price of one."""
    return rule_set.remembered(
        ("grants_disciplines",),
        lambda: frozenset(
            g.source["name"]
            for g in rule_set.grants
            if g.kind in ("replace_in_clan", "price_in_clan")
            or g.target.get("category") == "extra_in_clan_disciplines"
        ),
    )


def options(
    grant: GrantData,
    rule_set: RuleSetData,
    sheet: Sequence[SheetTrait] = (),
    *,
    choosing: bool = True,
) -> list[Option]:
    """What a free_choices grant lets the player choose, in name order. With
    `choosing` False, the filters that depend on the sheet (a clan other than
    theirs, a merit not already held) are left out: what the grant may give, not
    what can still be picked."""
    category = grant.target["category"]
    pool = grant.target.get("pool")
    if pool is None:
        names = choices(grant, rule_set)
    else:
        own = clan_family(sheet) if choosing else None
        held = (
            {t.name for t in sheet if t.category == category and not t.granted}
            if choosing and pool.get("not_held")
            else set()
        )
        unwanted = grants_disciplines(rule_set) if pool.get("except_granting") else frozenset()
        names = []
        for (c, name), trait in rule_set.traits.items():
            if c != category:
                continue
            props = trait.properties
            # A troupe's house merit no player can pick (horatio.house_traits).
            if props.get("offered") is False:
                continue
            requirement = props.get("requirement")
            if "types" in pool and props.get("type") not in pool["types"]:
                continue
            if "requirement" in pool and requirement not in pool["requirement"]:
                continue
            if pool.get("other_clan"):
                family = str(requirement or "").split(":")[0].strip()
                if family not in clan_families(rule_set) or family == own:
                    continue
            if "max_rating" in pool and not 0 < props.get("rating", 99) <= pool["max_rating"]:
                continue
            if name.startswith(pool.get("except_prefix", "\0")) or name in pool.get("except", ()):
                continue
            if name in unwanted or name in held:
                continue
            if "rating" not in props and category == "merits":
                continue
            names.append(name)
    return [
        Option(
            category,
            name,
            rule_set.trait_properties(category, name).get("rating")
            if category == "merits"
            else None,
            needs_detail=name == CUSTOM
            or rule_set.trait_properties(category, name).get("requirement")
            == "requires_specialization",
        )
        for name in sorted(names)
        if (category, name) in rule_set.traits
    ]


def chosen_options(grant: GrantData, trait: SheetTrait, rule_set: RuleSetData) -> list[FreeChoice]:
    """The free traits the player chose for `trait` under this grant that still
    stand: those it may give (judged without the sheet, which may have moved on)."""
    mine = [c for c in trait.choices if c.grant == grant.key]
    if not mine:
        return []
    allowed = {o.name for o in options(grant, rule_set, choosing=False)}
    return [c for c in mine if c.name in allowed]


def check_picks(
    grant: GrantData,
    picks: Sequence[FreeChoice],
    rule_set: RuleSetData,
    sheet: Sequence[SheetTrait],
) -> str | None:
    """Why `picks` cannot answer a free_choices grant, or None if they can."""
    assert grant.picks is not None
    offered = {o.name: o for o in options(grant, rule_set, sheet)}
    seen: set[tuple[str, str]] = set()
    for pick in picks:
        option = offered.get(pick.name)
        if option is None:
            return f"{pick.name} is not one of the traits {grant.source['name']} can give."
        detail = pick.detail.strip()
        if option.needs_detail and not detail:
            return f"Say what the {pick.name} is."
        if (pick.name, detail) in seen:
            return f"{pick.name} is chosen twice."
        seen.add((pick.name, detail))
    places = grant.picks.get("places")
    if places is not None:
        if len({p.name for p in picks}) < len(picks):
            return "Each of the traits is chosen once, with its own amount."
        left = Counter(places)
        for pick in picks:
            if left[pick.amount] <= 0:
                return f"Place {', '.join(map(str, places))}, each once."
            left[pick.amount] -= 1
    count = grant.picks.get("count")
    if count is not None and len(picks) > count:
        return f"{grant.source['name']} gives {count}, not {len(picks)}."
    points = grant.picks.get("points")
    if points is not None:
        worth = sum(offered[p.name].rating or 0 for p in picks)
        if worth > points:
            return f"{grant.source['name']} gives up to {points} points; these are {worth}."
    return None


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
            if grant.kind == "free_choices":
                given = chosen_options(grant, trait, rule_set)
                for pick in given:
                    key = (grant.target["category"], pick.name, pick.detail)
                    amount = pick.amount if "places" in (grant.picks or {}) else 1
                    found.free_up_to[key] = max(found.free_up_to.get(key, 0), amount)
                    found.sources.setdefault(key, []).append(label)
                    found.givers.setdefault(key, []).append((trait.category, trait.name))
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
                origin = (grant.convert_from["category"], grant.convert_from["name"])
                found.converts[origin] = to
                found.converted_by[origin] = (trait.category, trait.name)
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
                if grant.kind in ("price_out_of_clan", "no_free_dot"):
                    held = (
                        found.out_of_clan_priced
                        if grant.kind == "price_out_of_clan"
                        else found.no_free_dot
                    )
                    held.setdefault((category, name, detail or None), []).append(
                        (trait.category, trait.name)
                    )
                    continue
            elif grant.kind in (
                "price_in_clan",
                "cost_percent",
                "price_out_of_clan",
                "no_free_dot",
            ):
                targets: list[str] = grant.target.get("names") or [
                    grant.target.get("name", WHOLE_CATEGORY)
                ]
                for category in grant.categories:
                    for name in targets:
                        key3: tuple[str, str, str | None] = (
                            category,
                            name,
                            grant.target.get("detail"),
                        )
                        if grant.kind == "price_in_clan":
                            found.in_clan_priced.add(key3)
                        elif grant.kind == "cost_percent":
                            found.cost_percent[key3] = grant.amount
                        else:
                            held = (
                                found.out_of_clan_priced
                                if grant.kind == "price_out_of_clan"
                                else found.no_free_dot
                            )
                            held.setdefault(key3, []).append((trait.category, trait.name))
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
            found.givers.setdefault(key, []).append((trait.category, trait.name))
    return found


@dataclass(frozen=True)
class Priced:
    """What a sheet's grants do to prices."""

    in_clan: Set[LooseKey]
    cost_percent: Mapping[LooseKey, int]
    # Priced as out-of-clan, and extra in-clan disciplines without a free dot: the
    # traits (category, name) each is because of.
    out_of_clan: Mapping[LooseKey, tuple[tuple[str, str], ...]]
    no_free_dot: Mapping[LooseKey, tuple[tuple[str, str], ...]]


def priced(rule_set: RuleSetData, sheet: Sequence[SheetTrait]) -> Priced:
    """What the sheet's grants price as in-clan or out-of-clan, and at what percent:
    worked out once for each sheet, as pricing asks it of every trait it prices."""

    def work_out() -> Priced:
        found = effects(rule_set.grants, sheet, rule_set)
        return Priced(
            frozenset(found.in_clan_priced),
            MappingProxyType(dict(found.cost_percent)),
            MappingProxyType({k: tuple(v) for k, v in found.out_of_clan_priced.items()}),
            MappingProxyType({k: tuple(v) for k, v in found.no_free_dot.items()}),
        )

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
    """The entry for `trait`: its detail exactly, any detail, or its whole category."""
    for key in (
        (trait.category, trait.name, trait.detail or None),
        (trait.category, trait.name, None),
        (trait.category, WHOLE_CATEGORY, None),
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
        picks=raw.get("picks"),
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
    if grant.kind == "free_choices":
        validate_free_choices(grant)
        for name in (grant.target.get("pool") or {}).get("except", ()):
            if (grant.categories[0], name) not in rule_set_traits:
                raise ValueError(f"grant {grant.key} leaves out unknown trait {name!r}")


def validate_free_choices(grant: GrantData) -> None:
    if "category" not in grant.target or not (
        grant.target.get("choose") or grant.target.get("pool") is not None
    ):
        raise ValueError(f"grant {grant.key} must name one category and what can be chosen in it")
    shape = grant.picks or {}
    if not set(shape) & {"places", "count", "points"} or set(shape) - {"places", "count", "points"}:
        raise ValueError(f"grant {grant.key} must say its picks: places, count or points")
    pool = grant.target.get("pool") or {}
    unknown = set(pool) - {
        "types", "requirement", "other_clan", "max_rating", "except_prefix", "except",
        "except_granting", "not_held",
    }  # fmt: skip
    if unknown:
        raise ValueError(f"grant {grant.key} has unknown pool filters {sorted(unknown)}")
