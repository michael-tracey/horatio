"""The Play View's quick game reference (issue #83): a character's common test
pools, worked out from the sheet, and notes on what each of its powers does.

Pools follow MET: VTM (pp. 271-275): an attack or a static challenge is
attribute + skill; Physical defence is Physical + Dodge; Mental and Social
defence is the attribute + current Willpower, which the Play View's tracker
holds, so those pools are sent without it and the page adds it. Initiative is
the higher of Physical and Mental (p. 271).

Disciplines, focuses, merits and flaws change pools through `pools` entries in
the rules data: on a discipline or power in bns_met_vampire_powers.toml, and on
merits and flaws in the catalogue. See the top of that file for their shape. An
entry with `when` is a variant ("With Celerity active: 12"), not part of the
number shown, since it holds only some of the time.

Each attack pool also carries the damage a hit does (issue #190): the base for its
type (core p. 279) plus what the sheet's powers add through `damage` entries in the
same file, with a note for the extra point of an exceptional success. Weapons are
not counted.

Forms and powers that hold only while they are active (issue #200) are switches,
from `active` in the same file: Shape of the Beast's forms, Celerity, Feral Claws
and the rest. Each pool says what each switch would change in it (`switched`), and
the Play View adds what is on, since being on is a tap in the game
(horatio.play). A switch can also add wound levels, change an attribute, give a
focus or more Blood; `switches` lists those the sheet has, with what they change.

A troupe's house merits and flaws carry `pools` and `active` in their catalogue
properties, as the troupe's rules read them (horatio.rules.house_effects), and are
read here like a book merit's.
"""

import tomllib
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from horatio.rules.model import RuleSetData, SheetTrait
from horatio.sheets import SheetRow

POWERS_FILE = Path(__file__).parent / "rules" / "data" / "bns_met_vampire_powers.toml"
FOCUS_CATEGORIES = ("focus_physicals", "focus_socials", "focus_mentals")
ATTRIBUTES = ("Physical", "Social", "Mental")
# Attacks every character has a pool for, in order; Brawl even at 0.
ATTACKS = (
    ("Brawl", "Unarmed"),
    ("Melee", "Melee"),
    ("Firearms", "Firearms"),
    # Athletics throws a weapon, or shoots a bow or crossbow (MET: VTM p. 279).
    ("Athletics", "Thrown or bow"),
)
# Categories whose traits are powers of a discipline, named "Discipline: Power".
POWER_CATEGORIES = ("elder_disciplines", "luminary_disciplines")
BOOK = "core"
# How the summary of a switch names each pool family.
POOL_WORDS = {
    "initiative": "initiative",
    "dodge": "Dodge",
    "attack": "attacks",
    "defense": "defences",
    "all": "every pool",
}


class PoolPart(BaseModel):
    label: str
    value: int


class SwitchedPart(BaseModel):
    """What a switch adds to a pool while it is on: a part ("Alacrity 4"), or a
    change to the attribute the pool is made on (Physical counts as 3)."""

    switch: str
    label: str
    value: int = 0
    # The attribute it changes, instead of adding a part: `value` is added to it,
    # and it counts as no more than `most`.
    attribute: str | None = None
    most: int | None = None


class SwitchedDamage(BaseModel):
    """What a switch does to an attack's damage while it is on."""

    switch: str
    label: str
    amount: int = 0
    exceptional: int = 0
    type: Literal["normal", "aggravated"] = "normal"


class Damage(BaseModel):
    """What a successful attack does: a base for its type, and what powers add."""

    # unarmed, melee, thrown or firearms.
    kind: str
    type: Literal["normal", "aggravated"] = "normal"
    # The base, then each power's addition: "1 (melee) + 1 (Might)".
    parts: list[PoolPart]
    total: int
    # What an exceptional success adds on top of the total.
    exceptional: int
    # Changes that hold only some of the time: "With Celerity active, …".
    notes: list[str] = []
    # What forms and powers change while they are on.
    switched: list[SwitchedDamage] = []


class PoolVariant(BaseModel):
    # When it applies: "With Celerity active", "In fight form".
    when: str
    total: int
    # What it adds to the pool: "+4 Alacrity".
    parts: list[PoolPart]


class TestPool(BaseModel):
    key: str
    name: str
    group: str
    parts: list[PoolPart]
    total: int
    # What it is tested against, for an attack: "Mental + Willpower".
    versus: str | None = None
    # Mental and Social defence add current Willpower, at least this much.
    adds_willpower: bool = False
    willpower_floor: int = 0
    variants: list[PoolVariant] = []
    notes: list[str] = []
    # For an attack: what a hit does.
    damage: Damage | None = None
    # What forms and powers add while they are on (the Play View knows which are).
    switched: list[SwitchedPart] = []


class PowerNote(BaseModel):
    level: int
    name: str
    note: str
    # What the character's focus adds, if they have the one the book names.
    focus: str | None = None


class DisciplinePowers(BaseModel):
    name: str
    rating: int
    pool: str | None
    versus: str | None
    note: str | None
    focus: str | None
    powers: list[PowerNote]


class OtherPower(BaseModel):
    """A technique, elder or luminary power: named, rated as held."""

    category_name: str
    name: str
    note: str | None


class SwitchLevel(BaseModel):
    level: str
    boxes: int


class AttributeChange(BaseModel):
    """A switch's change to an attribute in the pools made on it."""

    attribute: str
    amount: int = 0
    # The most it counts as: Shape of the Beast's flight form reduces Physical to 3.
    most: int | None = None
    # attack, defense or one pool's key; None for every pool made on it.
    pools: str | None = None


class Switch(BaseModel):
    """A form or power the Play View can switch on while the character has it
    (issue #200). Forms are transformative: only one is on at a time (core
    p. 114), but for those it combines with."""

    key: str
    # "Shape of the Beast: fight form (wolf, Huge)".
    name: str
    # Where it comes from: "Protean 4", "Celerity", "Celerity: Nimble Departure".
    origin: str
    form: bool = False
    combines: list[str] = []
    # Its rules: "p. 155", "Vol. 2, p. 82".
    page: str
    # What it changes, in words: "+2 Brawl attacks", "+2 Healthy".
    changes: list[str] = []
    # What can't be worked out: "Can fly at your normal speed."
    notes: list[str] = []
    # Wound levels it adds while on.
    health: list[SwitchLevel] = []
    attributes: list[AttributeChange] = []
    focuses: list[str] = []
    blood_per_turn: int = 0
    # The Blood pool is half again as big (rounded up) while it is on.
    blood_half: bool = False


class Reference(BaseModel):
    pools: list[TestPool]
    disciplines: list[DisciplinePowers]
    other_powers: list[OtherPower]
    # Modifiers that change no pool shown here: "Tech Junkie: +2 to Computers".
    notes: list[str]
    blood_per_turn: int


@dataclass(frozen=True)
class Catalogue:
    disciplines: Mapping[str, Mapping[str, Any]]
    powers: Mapping[str, Sequence[Mapping[str, Any]]]
    # The default damage of each attack, by the skill its pool is made on.
    attacks: Mapping[str, Mapping[str, Any]]
    # Techniques, elder and luminary powers and merits, by (category, name).
    others: Mapping[tuple[str, str], Mapping[str, Any]] = field(default_factory=dict)
    # Every switch's key: a `when` naming one holds while it is on.
    switch_keys: frozenset[str] = frozenset()

    def power(self, discipline: str, name: str) -> Mapping[str, Any] | None:
        return next((p for p in self.powers.get(discipline, []) if p["name"] == name), None)


def actives(entry: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """An entry's switches: `active` is one table or a list of them."""
    found = entry.get("active", [])
    return [found] if isinstance(found, Mapping) else list(found)  # pyright: ignore[reportUnknownArgumentType]


@lru_cache
def catalogue() -> Catalogue:
    with POWERS_FILE.open("rb") as f:
        raw = tomllib.load(f)
    powers: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for p in raw.get("powers", []):
        powers[p["discipline"]].append(p)
    entries = [*raw.get("disciplines", []), *raw.get("powers", []), *raw.get("others", [])]
    return Catalogue(
        disciplines={d["name"]: d for d in raw.get("disciplines", [])},
        powers={k: sorted(v, key=lambda p: p["level"]) for k, v in powers.items()},
        attacks={a["skill"]: a for a in raw.get("attacks", [])},
        others={(o["category"], o["name"]): o for o in raw.get("others", [])},
        switch_keys=frozenset(a["key"] for e in entries for a in actives(e)),
    )


@dataclass
class Effect:
    pool: str
    source: str
    amount: int = 0
    when: str | None = None
    note: str | None = None
    attribute: str | None = None
    willpower_floor: int = 0
    instead_of: tuple[str, ...] = ()
    # The focus it needs, for working out what a switch's focus gives.
    focus: str | None = None


@dataclass
class DamageEffect:
    """A power's change to the damage of some attacks."""

    attacks: tuple[str, ...]
    source: str
    amount: int = 0
    exceptional: int = 0
    type: Literal["normal", "aggravated"] = "normal"
    when: str | None = None
    note: str | None = None
    focus: str | None = None


@dataclass
class Sheet:
    """What the pools are made of, read from the character's sheet rows."""

    ratings: dict[tuple[str, str], int] = field(default_factory=dict)
    focuses: set[str] = field(default_factory=set)
    disciplines: dict[str, int] = field(default_factory=dict)
    # Techniques, elder and luminary powers: (category name, name).
    others: list[tuple[str, str, str]] = field(default_factory=list)
    traits: list[tuple[str, str, Mapping[str, Any]]] = field(default_factory=list)
    # What was chosen when buying powers, by discipline and power (horatio.api.power_choices).
    choices: dict[str, Mapping[str, Mapping[str, str]]] = field(default_factory=dict)

    def rating(self, category: str, name: str) -> int:
        return self.ratings.get((category, name), 0)

    def held(self, category: str, name: str) -> bool:
        return (category, name) in self.ratings

    def chosen(self, discipline: str, power: Mapping[str, Any] | None) -> dict[str, str]:
        """A power's purchase choices, each its default until chosen."""
        if power is None:
            return {}
        made = self.choices.get(discipline, {}).get(power["name"], {})
        return {
            c["key"]: made.get(c["key"]) or c.get("default", "") for c in power.get("choices", [])
        }

    @property
    def switch_keys(self) -> frozenset[str]:
        """Every switch's key: the powers file's, and the house merits' this sheet has."""
        return catalogue().switch_keys | {a["key"] for e in house_entries(self) for a in actives(e)}

    def with_focus(self, focus: str) -> "Sheet":
        return Sheet(
            ratings=self.ratings,
            focuses=self.focuses | {focus},
            disciplines=self.disciplines,
            others=self.others,
            traits=self.traits,
            choices=self.choices,
        )

    @classmethod
    def read(cls, rows: Iterable[SheetRow], rule_set: RuleSetData) -> "Sheet":
        sheet = cls()
        for row in rows:
            sheet.add(
                row.category.key,
                row.category.name,
                row.definition.name,
                row.trait.rating,
                rule_set,
                row.trait.power_choices,
            )
        return sheet

    @classmethod
    def of(cls, traits: Iterable[SheetTrait], rule_set: RuleSetData) -> "Sheet":
        """The pools' makings from the rules' own view of a sheet, for trying one out
        (horatio.house_preview) where there are no rows."""
        sheet = cls()
        for t in traits:
            category = rule_set.categories.get(t.category)
            sheet.add(
                t.category, category.name if category else t.category, t.name, t.rating, rule_set
            )
        return sheet

    def add(
        self,
        category: str,
        category_name: str,
        name: str,
        rating: int | None,
        rule_set: RuleSetData,
        power_choices: Mapping[str, Mapping[str, str]] | None = None,
    ) -> None:
        rating = rating if rating is not None else 1
        if rating <= 0:
            return
        key = (category, name)
        self.ratings[key] = max(self.ratings.get(key, 0), rating)
        if category in FOCUS_CATEGORIES:
            self.focuses.add(name)
        elif category == "disciplines":
            self.disciplines[name] = max(self.disciplines.get(name, 0), rating)
            if power_choices:
                self.choices[name] = power_choices
        elif category in (*POWER_CATEGORIES, "techniques"):
            self.others.append((category, category_name, name))
        properties = rule_set.trait_properties(category, name)
        if properties:
            self.traits.append((category, name, properties))


def technique_bases(rule_set: RuleSetData) -> dict[str, set[str]]:
    """The disciplines each technique is built on, from its prerequisites."""
    bases: dict[str, set[str]] = defaultdict(set)
    for check in rule_set.checks:
        if check.category != "techniques" or check.name is None or check.requires is None:
            continue
        for need in _conditions(check.requires):
            if need.get("category") == "disciplines" and need.get("name"):
                bases[check.name].add(need["name"])
    return bases


def _conditions(condition: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(condition, Mapping):
        if "category" in condition:
            yield condition
        for value in condition.values():
            if isinstance(value, list | dict):
                yield from _conditions(value)
    elif isinstance(condition, list):
        for item in condition:
            yield from _conditions(item)


def power_count(sheet: Sheet, discipline: str, bases: Mapping[str, set[str]]) -> int:
    """Powers the character has of a discipline: its dots, its elder and
    luminary powers, and techniques built on it (Alacrity, p. 122)."""
    count = sheet.disciplines.get(discipline, 0)
    for category, _, name in sheet.others:
        elder = category in POWER_CATEGORIES and name.startswith(f"{discipline}:")
        technique = category == "techniques" and discipline in bases.get(name, set())
        if elder or technique:
            count += 1
    return count


def _amount(spec: Any, sheet: Sheet, bases: Mapping[str, set[str]]) -> int:
    if isinstance(spec, int):
        return spec
    if isinstance(spec, str) and spec.startswith("powers:"):
        return power_count(sheet, spec.removeprefix("powers:"), bases)
    if isinstance(spec, str) and spec.startswith("rating:"):
        category, name = spec.removeprefix("rating:").split("/", 1)
        return sheet.rating(category, name)
    return 0


def _holds(entry: Mapping[str, Any], sheet: Sheet, chosen: Mapping[str, str]) -> bool:
    """Whether an entry holds for this sheet: its focus, and the purchase choice it needs."""
    if "focus" in entry and entry["focus"] not in sheet.focuses:
        return False
    if "unless_focus" in entry and entry["unless_focus"] in sheet.focuses:
        return False
    return all(chosen.get(k) == v for k, v in entry.get("choice", {}).items())


def _needs(entry: Mapping[str, Any], sheet: Sheet) -> bool:
    need = entry.get("needs")
    return need is None or sheet.disciplines.get(need["discipline"], 0) >= need["level"]


@dataclass(frozen=True)
class Owner:
    """An entry of the powers file the character has, and what it is called."""

    entry: Mapping[str, Any]
    # The name a part of a pool shows: "Alacrity", "Celerity".
    source: str
    # Where it comes from, for a switch: "Protean 4", "Celerity", "Bullet Time".
    origin: str
    chosen: Mapping[str, str] = field(default_factory=dict[str, str])


def house_entries(sheet: Sheet) -> list[Mapping[str, Any]]:
    """The house merits and flaws on the sheet with a switch, as [[others]] entries."""
    return [
        {"category": category, "name": name, "active": properties["active"]}
        for category, name, properties in sheet.traits
        if category in ("merits", "flaws") and "active" in properties
    ]


def owners(sheet: Sheet) -> Iterable[Owner]:
    """Every entry the character has: its disciplines, the powers it has reached,
    its techniques, elder powers and merits from [[others]], and its house merits
    with a switch (their `pools` are read with the other merits')."""
    book = catalogue()
    for name, rating in sheet.disciplines.items():
        if name in book.disciplines:
            yield Owner(book.disciplines[name], name, name)
        for power in book.powers.get(name, []):
            if power["level"] <= rating:
                yield Owner(
                    power, power["name"], f"{name} {power['level']}", sheet.chosen(name, power)
                )
    for (category, name), other in book.others.items():
        if sheet.held(category, name) and _needs(other, sheet):
            short = name.split(": ", 1)[-1]
            yield Owner(other, short, name)
    for entry in house_entries(sheet):
        yield Owner(entry, entry["name"], entry["name"])


def effects(sheet: Sheet, bases: Mapping[str, set[str]]) -> list[Effect]:
    """Every pool change the character has, from its disciplines, powers,
    merits and flaws, resolved to numbers."""
    found: list[Effect] = []

    def add(entries: Iterable[Mapping[str, Any]], source: str, chosen: Mapping[str, str]) -> None:
        for e in entries:
            if not _holds(e, sheet, chosen):
                continue
            found.append(
                Effect(
                    pool=e["pool"],
                    source=source,
                    amount=_amount(e.get("amount", 0), sheet, bases),
                    when=e.get("when"),
                    note=e.get("note"),
                    attribute=e.get("attribute"),
                    willpower_floor=e.get("willpower_floor", 0),
                    instead_of=tuple(e.get("instead_of", ())),
                    focus=e.get("focus"),
                )
            )

    for owner in owners(sheet):
        add(owner.entry.get("pools", []), owner.source, owner.chosen)
    for category, name, properties in sheet.traits:
        if category in ("merits", "flaws"):
            add(properties.get("pools", []), name, {})
    return found


def damage_effects(sheet: Sheet) -> list[DamageEffect]:
    """Every change to attack damage the character has, from its disciplines, the
    powers it has reached and its other powers."""
    found: list[DamageEffect] = []
    for owner in owners(sheet):
        for e in owner.entry.get("damage", []):
            if not _holds(e, sheet, owner.chosen):
                continue
            found.append(
                DamageEffect(
                    attacks=tuple(e["attacks"]),
                    source=owner.source,
                    amount=e.get("amount", 0),
                    exceptional=e.get("exceptional", 0),
                    type=e.get("type", "normal"),
                    when=e.get("when"),
                    note=e.get("note"),
                    focus=e.get("focus"),
                )
            )
    return found


def damage(
    skill: str, found: Sequence[DamageEffect], keys: frozenset[str] | None = None
) -> Damage | None:
    """What a hit with the attack made on `skill` does: its base (core p. 279) plus
    each power that always adds to it. What a switch changes is kept apart, for
    the Play View to add while it is on; other powers that hold only some of the
    time (`when`) are notes."""
    base = catalogue().attacks.get(skill)
    if base is None:
        return None
    parts = [PoolPart(label=base["kind"], value=base["damage"])]
    exceptional = base.get("exceptional", 0)
    kind: Literal["normal", "aggravated"] = "normal"
    notes: list[str] = []
    switched: list[SwitchedDamage] = []
    keys = catalogue().switch_keys if keys is None else keys
    for e in found:
        if skill not in e.attacks:
            continue
        if e.when in keys:
            switched.append(
                SwitchedDamage(
                    switch=e.when,
                    label=e.source,
                    amount=e.amount,
                    exceptional=e.exceptional,
                    type=e.type,
                )
            )
            continue
        if e.when:
            notes.append(f"{e.note} ({e.source})" if e.note else f"{e.when} ({e.source})")
            continue
        if e.amount:
            parts.append(PoolPart(label=e.source, value=e.amount))
        exceptional += e.exceptional
        if e.type == "aggravated":
            kind = "aggravated"
    return Damage(
        kind=base["kind"],
        type=kind,
        parts=parts,
        total=sum(p.value for p in parts),
        exceptional=exceptional,
        notes=notes,
        switched=switched,
    )


def _applies(effect: Effect, key: str) -> bool:
    """Whether an effect's pool covers a pool: "attack" covers every attack,
    "discipline:Thaumaturgy" every Thaumaturgy path."""
    if effect.pool == key:
        return True
    family = key.split(":", 1)[0]
    if effect.pool == family:
        return True
    if effect.pool.startswith("discipline:") and key.startswith("discipline:"):
        return key.removeprefix("discipline:").startswith(effect.pool.removeprefix("discipline:"))
    return False


def _signed(n: int) -> str:
    return f"+{n}" if n >= 0 else str(n)


def _pool(
    key: str,
    name: str,
    group: str,
    base: list[PoolPart],
    found: Sequence[Effect],
    keys: frozenset[str],
    **extra: Any,
) -> TestPool:
    """A pool from its base parts and the effects that change it: those that
    always hold add to it, those a switch holds are kept for while it is on, and
    those with another `when` become its variants."""
    parts = list(base)
    variants: dict[str, list[PoolPart]] = defaultdict(list)
    switched: list[SwitchedPart] = []
    notes: list[str] = list(extra.pop("notes", []))
    for e in found:
        if e.pool == "all" or not _applies(e, key) or e.attribute or e.instead_of:
            continue
        if e.note:
            notes.append(f"{e.note} ({e.source})")
        elif e.when in keys:
            if e.amount:
                switched.append(SwitchedPart(switch=e.when, label=e.source, value=e.amount))
        elif e.when:
            variants[e.when].append(PoolPart(label=e.source, value=e.amount))
        elif e.amount:
            parts.append(PoolPart(label=e.source, value=e.amount))
    total = sum(p.value for p in parts)
    return TestPool(
        key=key,
        name=name,
        group=group,
        parts=parts,
        total=total,
        variants=[
            PoolVariant(when=when, total=total + sum(p.value for p in adds), parts=adds)
            for when, adds in variants.items()
        ],
        notes=notes,
        switched=switched,
        **extra,
    )


def _when_label(when: str) -> str:
    return when[:1].upper() + when[1:]


def _covers(which: str | None, key: str) -> bool:
    """Whether a switch's attribute change covers a pool: every pool made on the
    attribute, its attacks or its defences, or one pool."""
    if which is None:
        return True
    if which in ("attack", "defense"):
        return key.startswith(f"{which}:")
    return key == which


def pools(
    sheet: Sheet,
    found: Sequence[Effect],
    blood_per_turn: int,
    hurts: Sequence[DamageEffect] = (),
    switched: Sequence["Switch"] = (),
) -> list[TestPool]:
    attrs = {a: sheet.rating("attributes", a) for a in ATTRIBUTES}

    def skill(name: str) -> PoolPart:
        """A skill, or another the character may use in its place (Preternatural
        Awareness), whichever is higher."""
        best = PoolPart(label=name, value=sheet.rating("skills", name))
        for e in found:
            if name in e.instead_of:
                other = e.pool.removeprefix("skill:")
                value = sheet.rating("skills", other)
                if value > best.value:
                    best = PoolPart(label=f"{other} (for {name})", value=value)
        return best

    def attr(name: str) -> PoolPart:
        return PoolPart(label=name, value=attrs[name])

    keys = sheet.switch_keys
    out: list[TestPool] = []
    initiative_attr = next(
        (e.attribute for e in found if e.pool == "initiative" and e.attribute), None
    ) or ("Mental" if attrs["Mental"] > attrs["Physical"] else "Physical")
    out.append(_pool("initiative", "Initiative", "Combat", [attr(initiative_attr)], found, keys))
    blood = f"Spend Blood for +1 Physical each, up to {blood_per_turn} a turn."
    out.append(
        _pool(
            "dodge",
            "Dodge",
            "Combat",
            [attr("Physical"), skill("Dodge")],
            found,
            keys,
            notes=["Give up your standard action for +2 to one Dodge pool this round.", blood],
        )
    )
    for name, label in ATTACKS:
        part = skill(name)
        if part.value or name == "Brawl":
            out.append(
                _pool(
                    f"attack:{name}",
                    f"{label} attack" if label != name else f"{name} attack",
                    "Combat",
                    [attr("Physical"), part],
                    found,
                    keys,
                    versus="Physical + Dodge",
                    notes=[blood],
                    damage=damage(name, hurts, keys),
                )
            )
    floor = max((e.willpower_floor for e in found if e.pool == "defense"), default=0)
    for name in ("Mental", "Social", "Physical"):
        out.append(
            _pool(
                f"defense:{name}",
                f"Resisting {name} powers",
                "Defence",
                [attr(name)],
                found,
                keys,
                adds_willpower=True,
                willpower_floor=floor,
            )
        )
    book = catalogue()
    for discipline in sorted(sheet.disciplines):
        spec = book.disciplines.get(discipline, {})
        if not spec.get("pool"):
            continue
        attribute, skill_name = (s.strip() for s in spec["pool"].split("+", 1))
        out.append(
            _pool(
                f"discipline:{discipline}",
                discipline,
                "Disciplines",
                [attr(attribute), skill(skill_name)],
                found,
                keys,
                versus=spec.get("versus"),
            )
        )
    for pool in out:
        for variant in pool.variants:
            variant.when = _when_label(variant.when)
        for switch in switched:
            for change in switch.attributes:
                if pool.parts[0].label == change.attribute and _covers(change.pools, pool.key):
                    pool.switched.append(
                        SwitchedPart(
                            switch=switch.key,
                            label=f"{change.attribute} ({switch.key})",
                            value=change.amount,
                            attribute=change.attribute,
                            most=change.most,
                        )
                    )
    return out


def _page(entry: Mapping[str, Any]) -> str:
    """ "p. 155", "Vol. 2, p. 82", or a house switch's "House rule — Night Court"."""
    if "reference" in entry:
        return entry["reference"]
    book = entry.get("book", BOOK)
    return f"p. {entry['page']}" if book == BOOK else f"{book}, p. {entry['page']}"


def _pool_words(pool: str) -> str:
    """How a summary names a pool: "Brawl attacks", "Mental defence", "Dodge"."""
    family, _, which = pool.partition(":")
    if not which:
        return POOL_WORDS.get(family, family)
    if family == "attack":
        return f"{_attack_words((which,))} attacks"
    if family == "defense":
        return f"{which} defence"
    return which


def _attack_words(skills: Iterable[str]) -> str:
    """The attacks made on these skills: "Brawl and Melee", "thrown"."""
    return " and ".join("thrown" if s == "Athletics" else s for s in skills)


def _changes(switch: Switch, found: Sequence[Effect], hurts: Sequence[DamageEffect]) -> list[str]:
    """What a switch changes, in words, for its line on the Play View."""
    lines: list[str] = []
    for e in found:
        if e.when == switch.key and e.amount and not e.note:
            by = "" if switch.name.startswith(e.source) else f" ({e.source})"
            lines.append(f"{_signed(e.amount)} {_pool_words(e.pool)}{by}")
    for change in switch.attributes:
        to = {"attack": " for attacks", "defense": " for defences", None: ""}.get(
            change.pools, f" for {_pool_words(change.pools or '')}"
        )
        if change.amount:
            lines.append(f"{_signed(change.amount)} {change.attribute}{to}")
        if change.most is not None:
            lines.append(f"{change.attribute} counts as {change.most} at most{to}")
    levels: dict[str, int] = defaultdict(int)
    for level in switch.health:
        levels[level.level] += level.boxes
    lines += [f"+{boxes} {level}" for level, boxes in levels.items()]
    for d in hurts:
        if d.when != switch.key:
            continue
        words = _attack_words(d.attacks)
        upper = words[:1].upper() + words[1:]
        if d.type == "aggravated":
            lines.append(f"{upper} damage aggravated")
        if d.amount:
            lines.append(f"{_signed(d.amount)} {words} damage")
        if d.exceptional:
            lines.append(f"{upper} exceptional successes add {d.exceptional} more")
    lines += [f"The {focus} focus" for focus in switch.focuses]
    if switch.blood_per_turn:
        lines.append(f"{_signed(switch.blood_per_turn)} Blood a turn")
    if switch.blood_half:
        lines.append("Blood pool half again as big")
    return lines


def _switch(owner: Owner, active: Mapping[str, Any], sheet: Sheet) -> Switch:
    holds = lambda e: not isinstance(e, Mapping) or _holds(e, sheet, owner.chosen)  # noqa: E731
    name = active.get("name") or owner.entry["name"]
    chosen = [owner.chosen[k] for k in active.get("label", []) if owner.chosen.get(k)]
    blood = active.get("blood", {})
    return Switch(
        key=active["key"],
        name=f"{name} ({', '.join(chosen)})" if chosen else name,
        origin=owner.origin,
        form=active.get("form", False),
        combines=list(active.get("combines", [])),
        page=_page(active),
        notes=[n if isinstance(n, str) else n["note"] for n in active.get("notes", []) if holds(n)],
        health=[
            SwitchLevel(level=h["level"], boxes=h["boxes"])
            for h in active.get("health", [])
            if holds(h)
        ],
        attributes=[
            AttributeChange(
                attribute=a["attribute"],
                amount=a.get("amount", 0),
                most=a.get("most"),
                pools=a.get("pools"),
            )
            for a in active.get("attributes", [])
            if holds(a)
        ],
        focuses=list(active.get("focuses", [])),
        blood_per_turn=blood.get("per_turn", 0),
        blood_half=blood.get("most") == "half",
    )


def focus_effects(
    sheet: Sheet, bases: Mapping[str, set[str]], found: Sequence[Switch]
) -> tuple[list[Effect], list[DamageEffect]]:
    """What a switch's focus gives (Horrid Form's Strength focus: Potence's +2 to
    Brawl and Melee), as effects that hold while it is on."""
    pools: list[Effect] = []
    hurts: list[DamageEffect] = []
    for switch in found:
        for focus in switch.focuses:
            if focus in sheet.focuses:
                continue
            plus = sheet.with_focus(focus)
            label = f"{focus} focus"
            pools += [
                replace(e, when=switch.key, source=f"{e.source}, {label}")
                for e in effects(plus, bases)
                if e.focus == focus and e.when is None
            ]
            hurts += [
                replace(d, when=switch.key, source=f"{d.source}, {label}")
                for d in damage_effects(plus)
                if d.focus == focus and d.when is None
            ]
    return pools, hurts


@dataclass(frozen=True)
class Worked:
    """Everything that changes the character's pools, worked out from the sheet."""

    effects: list[Effect]
    hurts: list[DamageEffect]
    switches: list[Switch]


def work_out(sheet: Sheet, bases: Mapping[str, set[str]]) -> Worked:
    found = [_switch(o, a, sheet) for o in owners(sheet) for a in actives(o.entry)]
    pools, hurts = effects(sheet, bases), damage_effects(sheet)
    more_pools, more_hurts = focus_effects(sheet, bases, found)
    pools, hurts = pools + more_pools, hurts + more_hurts
    for switch in found:
        switch.changes = _changes(switch, pools, hurts)
    return Worked(pools, hurts, found)


def switches(rows: Sequence[SheetRow], rule_set: RuleSetData) -> list[Switch]:
    """The forms and powers on this sheet the Play View can switch on."""
    return work_out(Sheet.read(rows, rule_set), technique_bases(rule_set)).switches


def disciplines(sheet: Sheet) -> list[DisciplinePowers]:
    book = catalogue()
    found: list[DisciplinePowers] = []
    for name in sorted(sheet.disciplines):
        rating = sheet.disciplines[name]
        spec = book.disciplines.get(name, {})
        focuses = spec.get("focus", {}).items()
        focus = next((note for a, note in focuses if a in sheet.focuses), None)
        found.append(
            DisciplinePowers(
                name=name,
                rating=rating,
                pool=spec.get("pool"),
                versus=spec.get("versus"),
                note=spec.get("note"),
                focus=focus,
                powers=[
                    PowerNote(
                        level=p["level"],
                        name=p["name"],
                        note=p["note"],
                        focus=next(
                            (n for a, n in p.get("focus", {}).items() if a in sheet.focuses), None
                        ),
                    )
                    for p in book.powers.get(name, [])
                    if p["level"] <= rating
                ],
            )
        )
    return found


def other_notes(found: Sequence[Effect]) -> list[str]:
    """Modifiers for pools not shown (skills, frenzy), and those on every pool."""
    notes: list[str] = []
    for e in found:
        if e.pool.startswith("skill:") and not e.instead_of and e.amount:
            notes.append(f"{e.source}: {_signed(e.amount)} to {e.pool.removeprefix('skill:')}")
        elif e.pool.startswith("skill:") and e.instead_of:
            other = e.pool.removeprefix("skill:")
            notes.append(f"{e.source}: use {other} in place of {', '.join(e.instead_of)}")
        elif e.pool == "all":
            notes.append(f"{e.source}: {_signed(e.amount)} to every pool {e.when or ''}".strip())
        elif e.pool == "frenzy":
            notes.append(f"{e.source}: {e.note or _signed(e.amount) + ' to resist frenzy'}")
    return notes


def reference(rows: Sequence[SheetRow], rule_set: RuleSetData, blood_per_turn: int) -> Reference:
    sheet = Sheet.read(rows, rule_set)
    worked = work_out(sheet, technique_bases(rule_set))
    found = worked.effects
    return Reference(
        pools=pools(sheet, found, blood_per_turn, worked.hurts, worked.switches),
        disciplines=disciplines(sheet),
        other_powers=[
            OtherPower(
                category_name=category_name,
                name=name,
                note=rule_set.traits[(category, name)].description
                if (category, name) in rule_set.traits
                else None,
            )
            for category, category_name, name in sorted(sheet.others)
        ],
        notes=other_notes(found),
        blood_per_turn=blood_per_turn,
    )
