"""Equipment qualities (issue #279): the four kinds of item, their grades, every
quality of each kind, and the book's sample items (MET: VTM 2013, Chapter Thirteen,
pp. 515-524, with the Ballistic and Hardened errata in the Vol. II Issue 1 update,
p. 23). The rules are written in `bns_met_vampire_equipment.toml`; see the top of
that file for its shape.

A quality is per kind: the same name can mean different things on different kinds
(a ranged Deadly weapon needs two hands, a melee one does not), so each is keyed by
(kind, name). What it does to an item is in its properties:

    two_handed            the item needs both hands (Brutal, Reach, Long Range...)
    needs_one_hand        it can't go on a two-handed item (Concealable, Quick Draw)
    no_slot_when_crafted  added while crafting, it takes no slot (Artisan, Masterwork)
    repeatable            it can be taken more than once (Superior)
    needs_detail          it says something of its own, asked with `detail_prompt`
                          (Customized: the circumstance). `detail_prompt` without
                          `needs_detail` is a detail that may be left out
                          (Masterwork: its story effect)
    ammo                  it is the weapon's ammunition, which can be swapped for
                          other ammunition (p. 516); swapping isn't modelled
    excludes              qualities of its kind it can't go with
    shots                 the shots it holds instead of the kind's (Ammo Capacity)
    max_shots             the most it can hold, unless a quality with `shots` says
                          more (Spread: 6 unless it has Ammo Capacity)
    range                 its range instead of the kind's (Long Range: half a mile)
    aggravated_against    whom it does aggravated damage to; "{detail}" is the detail
    pool                  what it does to the character's test pools while its item
                          is equipped (issue #306), each a `PoolEffect`; the file
                          gives every quality one, with `pool = []` for a quality
                          that changes no pool (damage, range, a story effect)

`assess` checks an item's qualities against these rules and works out its facts:
hands, damage, shots and range. `horatio.equipment.check` refuses what it finds.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, cast

KINDS = ("melee", "ranged", "protective", "miscellaneous")
GRADES = ("cheap", "standard", "special")

QUALITY_PROPERTIES = (
    "two_handed",
    "needs_one_hand",
    "no_slot_when_crafted",
    "repeatable",
    "needs_detail",
    "detail_prompt",
    "ammo",
    "excludes",
    "shots",
    "max_shots",
    "range",
    "aggravated_against",
    "pool",
)

# What a pool effect applies to, besides the pools a player's own modifier names
# (horatio.pool_modifiers): the item's own attack, and the challenges a piece of
# miscellaneous gear is for, which no pool on the Pools tab is.
WEAPON = "weapon"
PURPOSE = "purpose"
# The attack each kind of weapon makes: a ranged weapon's is Firearms (MET: VTM
# p. 517), though an archaic one may use Athletics instead.
WEAPON_POOLS = {"melee": "pool:attack:Melee", "ranged": "pool:attack:Firearms"}
MODIFIER_POOLS = ("all", "attack", "defense", "Physical", "Social", "Mental")


@dataclass(frozen=True)
class PoolEffect:
    """What a quality does to a test pool while its item is equipped: a modifier,
    as a player's own is, made by the item (issue #306)."""

    amount: int
    # As a player's own modifier names them ("pool:dodge", "attack"), or WEAPON or
    # PURPOSE.
    pools: str
    # When it counts, in a few words of our own: "against firearms". "{detail}" is
    # the quality's detail (Customized's circumstance).
    when: str
    # It counts only in a situation the Pools tab can't tell (against firearms, for
    # an exceptional success), so the pool shows it on a line of its own rather
    # than in its total.
    situational: bool = False

    def to_dict(self) -> dict[str, Any]:
        found: dict[str, Any] = {"amount": self.amount, "pools": self.pools, "when": self.when}
        if self.situational:
            found["situational"] = True
        return found


def pool_effect(kind: str, raw: Mapping[str, Any]) -> PoolEffect:
    """A pool effect as the rules data writes it, checked."""
    unknown = set(raw) - {"amount", "pools", "when", "situational"}
    if unknown:
        raise ValueError(f"unknown pool effect properties {sorted(unknown)}")
    amount, pools, when = raw.get("amount"), raw.get("pools"), raw.get("when")
    if not isinstance(amount, int) or isinstance(amount, bool) or not amount:
        raise ValueError("a pool effect needs an amount other than 0")
    if not isinstance(pools, str) or not (
        pools in MODIFIER_POOLS
        or pools.startswith("pool:")
        or (pools == WEAPON and kind in WEAPON_POOLS)
        or (pools == PURPOSE and kind == "miscellaneous")
    ):
        raise ValueError(f"a {kind} pool effect can't apply to {pools!r}")
    if not isinstance(when, str) or not when:
        raise ValueError("a pool effect needs its when")
    return PoolEffect(amount, pools, when, bool(raw.get("situational", False)))


@dataclass(frozen=True)
class KindData:
    """A kind of item, and what one is with no qualities (its defaults)."""

    key: str
    name: str
    description: str = ""
    hands: int | None = None
    # Points of normal damage, for a weapon.
    damage: int | None = None
    shots: int | None = None
    range: str | None = None
    # A rule about the kind as a whole, in words (one worn at a time).
    note: str = ""
    page: str | None = None


@dataclass(frozen=True)
class GradeData:
    key: str
    name: str
    description: str = ""
    # The most qualities an item of the grade has; None for no limit (special).
    max_qualities: int | None = None
    page: str | None = None


@dataclass(frozen=True)
class QualityData:
    kind: str
    name: str
    # What it does, in a line of our own words.
    effect: str
    page: str | None = None
    # What it does at the table, in a few words, for the Play View: "+3 initiative".
    play: str = ""
    two_handed: bool = False
    needs_one_hand: bool = False
    no_slot_when_crafted: bool = False
    repeatable: bool = False
    needs_detail: bool = False
    detail_prompt: str | None = None
    ammo: bool = False
    excludes: tuple[str, ...] = ()
    shots: int | None = None
    max_shots: int | None = None
    range: str | None = None
    aggravated_against: str | None = None
    pool: tuple[PoolEffect, ...] = ()

    @property
    def takes_detail(self) -> bool:
        return self.needs_detail or self.detail_prompt is not None

    @property
    def properties(self) -> dict[str, Any]:
        """Its properties as written in the rules data, leaving out those it lacks."""
        found: dict[str, Any] = {}
        for name in QUALITY_PROPERTIES:
            value = getattr(self, name)
            if value and name == "pool":
                found[name] = [e.to_dict() for e in self.pool]
            elif value:
                found[name] = list(value) if isinstance(value, tuple) else value
        return found


@dataclass(frozen=True)
class ItemQuality:
    """A quality on an item, with its detail where it takes one."""

    name: str
    detail: str = ""


@dataclass(frozen=True)
class TemplateData:
    """One of the book's sample items, to start an item from."""

    name: str
    kind: str
    grade: str
    qualities: tuple[ItemQuality, ...]
    page: str | None = None


@dataclass(frozen=True)
class Facts:
    """What an item is, worked out from its kind and qualities. None where it
    doesn't apply: no shots for a melee weapon, no hands for armour."""

    hands: int | None = None
    damage: int | None = None
    shots: int | None = None
    range: str | None = None
    aggravated_against: tuple[str, ...] = ()


@dataclass(frozen=True)
class Assessment:
    facts: Facts
    # Why the item breaks the rules, each a sentence; empty when it doesn't.
    problems: tuple[str, ...] = ()


@dataclass(frozen=True)
class EquipmentRules:
    kinds: Mapping[str, KindData] = field(default_factory=dict[str, KindData])
    grades: Mapping[str, GradeData] = field(default_factory=dict[str, GradeData])
    # In the rules data's order, keyed by (kind, name).
    qualities: Mapping[tuple[str, str], QualityData] = field(
        default_factory=dict[tuple[str, str], QualityData]
    )
    templates: Sequence[TemplateData] = ()

    def qualities_of(self, kind: str) -> list[QualityData]:
        return [q for (k, _), q in self.qualities.items() if k == kind]


NO_EQUIPMENT = EquipmentRules()


def assess(
    rules: EquipmentRules,
    kind: str,
    qualities: Sequence[ItemQuality],
    grade: str,
    *,
    crafted: bool = False,
) -> Assessment:
    """Check an item against the rules between qualities, and work out its facts.
    `crafted`: its Artisan and Masterwork were added while crafting it, so they take
    no slot (pp. 516-517)."""
    kind_data = rules.kinds.get(kind)
    if kind_data is None:
        return Assessment(Facts(), (f"There's no kind of equipment called {kind!r}.",))
    problems: list[str] = []
    grade_data = rules.grades.get(grade)
    if grade_data is None:
        problems.append(f"There's no grade of equipment called {grade!r}.")

    known: list[tuple[QualityData, str]] = []
    seen: set[str] = set()
    for chosen in qualities:
        detail = chosen.detail.strip()
        quality = rules.qualities.get((kind, chosen.name))
        if quality is None:
            problems.append(f"{chosen.name} isn't a {kind_data.name.lower()} quality.")
            continue
        if chosen.name in seen and not quality.repeatable:
            problems.append(f"{chosen.name} can only be taken once.")
            continue
        seen.add(chosen.name)
        if quality.needs_detail and not detail:
            problems.append(f"{chosen.name} needs a detail: {quality.detail_prompt}.")
        elif detail and not quality.takes_detail:
            problems.append(f"{chosen.name} takes no detail.")
        known.append((quality, detail))

    counted = [q for q, _ in known if not (crafted and q.no_slot_when_crafted)]
    limit = grade_data.max_qualities if grade_data else None
    if grade_data and limit is not None and len(counted) > limit:
        problems.append(
            f"{grade_data.name} gear has at most {limit}"
            f" {'quality' if limit == 1 else 'qualities'}, not {len(counted)}."
        )

    names = [q.name for q, _ in known]
    two_handed = [q.name for q, _ in known if q.two_handed]
    if two_handed:
        for q, _ in known:
            if q.needs_one_hand:
                problems.append(f"{two_handed[0]} needs two hands, so it can't be {q.name}.")
    reported: set[frozenset[str]] = set()
    for q, _ in known:
        for other in q.excludes:
            pair = frozenset((q.name, other))
            if other in names and pair not in reported:
                reported.add(pair)
                problems.append(f"An item can't be both {q.name} and {other}.")

    return Assessment(facts_of(kind_data, known), tuple(problems))


def facts_of(kind: KindData, known: Sequence[tuple[QualityData, str]]) -> Facts:
    hands = kind.hands
    if hands is not None and any(q.two_handed for q, _ in known):
        hands = 2
    shots = kind.shots
    if shots is not None:
        more = [q.shots for q, _ in known if q.shots is not None]
        fewer = [q.max_shots for q, _ in known if q.max_shots is not None]
        shots = max(more) if more else min([shots, *fewer])
    ranges = [q.range for q, _ in known if q.range]
    against: list[str] = []
    for q, detail in known:
        if q.aggravated_against:
            text = q.aggravated_against.replace("{detail}", detail or "its material")
            if text not in against:
                against.append(text)
    return Facts(
        hands=hands,
        damage=kind.damage,
        shots=shots,
        range=ranges[-1] if ranges else kind.range,
        aggravated_against=tuple(against),
    )


def item_qualities(raw: Iterable[str | Mapping[str, str]]) -> tuple[ItemQuality, ...]:
    """Qualities as the rules data and the database write them: a name, or a table
    of `name` and `detail`."""
    return tuple(
        ItemQuality(q)
        if isinstance(q, str)
        else ItemQuality(str(q["name"]), str(q.get("detail", "")))
        for q in raw
    )


def item_qualities_to_list(qualities: Iterable[ItemQuality]) -> list[dict[str, str]]:
    return [{"name": q.name, **({"detail": q.detail} if q.detail else {})} for q in qualities]


def quality_from_dict(kind: str, name: str, raw: Mapping[str, Any]) -> QualityData:
    """A quality from its properties, as the rules data or the database has them."""
    unknown = set(raw) - set(QUALITY_PROPERTIES)
    if unknown:
        raise ValueError(f"{kind} quality {name!r}: unknown properties {sorted(unknown)}")
    found: dict[str, Any] = dict(raw)
    if "excludes" in found:
        found["excludes"] = tuple(cast(list[str], found["excludes"]))
    if "pool" in found:
        try:
            found["pool"] = tuple(
                pool_effect(kind, e) for e in cast(list[Mapping[str, Any]], found["pool"])
            )
        except ValueError as error:
            raise ValueError(f"{kind} quality {name!r}: {error}") from error
    return QualityData(kind=kind, name=name, effect="", **found)


def equipment_from(raw: Mapping[str, Any], *, source: str = "") -> EquipmentRules:
    """The equipment rules from a rules data file's `kinds`, `grades`, `qualities` and
    `templates`, checked: every exclusion goes both ways, and every template keeps
    the rules."""
    where = f"{source}: " if source else ""
    kinds = {
        k["key"]: KindData(
            key=k["key"],
            name=k["name"],
            description=k.get("description", ""),
            hands=k.get("hands"),
            damage=k.get("damage"),
            shots=k.get("shots"),
            range=k.get("range"),
            note=k.get("note", ""),
            page=k.get("page"),
        )
        for k in raw.get("kinds", [])
    }
    if kinds and tuple(kinds) != KINDS:
        raise ValueError(f"{where}the kinds of equipment are {', '.join(KINDS)}, in that order")
    grades = {
        g["key"]: GradeData(
            key=g["key"],
            name=g["name"],
            description=g.get("description", ""),
            max_qualities=g.get("max_qualities"),
            page=g.get("page"),
        )
        for g in raw.get("grades", [])
    }
    if grades and tuple(grades) != GRADES:
        raise ValueError(f"{where}the grades of equipment are {', '.join(GRADES)}, in that order")

    qualities: dict[tuple[str, str], QualityData] = {}
    for q in raw.get("qualities", []):
        kind, name = q["kind"], q["name"]
        if kind not in kinds:
            raise ValueError(f"{where}quality {name!r} is of unknown kind {kind!r}")
        if (kind, name) in qualities:
            raise ValueError(f"{where}{kind} quality {name!r} is written twice")
        if not q.get("effect"):
            raise ValueError(f"{where}{kind} quality {name!r} needs its effect")
        if not q.get("play"):
            raise ValueError(f"{where}{kind} quality {name!r} needs its play line")
        if "pool" not in q:
            raise ValueError(
                f"{where}{kind} quality {name!r} needs its pool effect, or pool = [] for none"
            )
        properties = {
            k: v for k, v in q.items() if k not in ("kind", "name", "effect", "play", "page")
        }
        try:
            quality = quality_from_dict(kind, name, properties)
        except ValueError as error:
            raise ValueError(f"{where}{error}") from error
        if quality.needs_detail and not quality.detail_prompt:
            raise ValueError(f"{where}{kind} quality {name!r} needs a detail_prompt")
        qualities[(kind, name)] = replace(
            quality, effect=q["effect"], play=q["play"], page=q.get("page")
        )
    for (kind, name), quality in qualities.items():
        for other in quality.excludes:
            if (kind, other) not in qualities:
                raise ValueError(f"{where}{kind} quality {name!r} excludes unknown {other!r}")
            if name not in qualities[(kind, other)].excludes:
                raise ValueError(
                    f"{where}{kind} quality {name!r} excludes {other!r}, but not the other way"
                )

    rules = EquipmentRules(kinds=kinds, grades=grades, qualities=qualities)
    templates: list[TemplateData] = []
    for t in raw.get("templates", []):
        template = TemplateData(
            name=t["name"],
            kind=t["kind"],
            grade=t.get("grade", "standard"),
            qualities=item_qualities(t["qualities"]),
            page=t.get("page"),
        )
        problems = assess(rules, template.kind, template.qualities, template.grade).problems
        if problems:
            raise ValueError(f"{where}template {template.name!r}: {' '.join(problems)}")
        templates.append(template)
    if len({t.name for t in templates}) != len(templates):
        raise ValueError(f"{where}two templates share a name")
    return EquipmentRules(
        kinds=kinds, grades=grades, qualities=qualities, templates=tuple(templates)
    )


def kind_to_dict(kind: KindData) -> dict[str, Any]:
    return {k: v for k, v in kind.__dict__.items() if v not in (None, "")}


def grade_to_dict(grade: GradeData) -> dict[str, Any]:
    return {k: v for k, v in grade.__dict__.items() if v not in (None, "")}


def equipment_to_dict(rules: EquipmentRules) -> dict[str, Any]:
    """The kinds and grades, as `rule_sets.equipment` keeps them; the qualities and
    templates have tables of their own."""
    return {
        "kinds": [kind_to_dict(k) for k in rules.kinds.values()],
        "grades": [grade_to_dict(g) for g in rules.grades.values()],
    }
