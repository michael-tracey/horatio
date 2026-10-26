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
"""

import tomllib
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from horatio.rules.model import RuleSetData
from horatio.sheets import SheetRow

POWERS_FILE = Path(__file__).parent / "rules" / "data" / "bns_met_vampire_powers.toml"
FOCUS_CATEGORIES = ("focus_physicals", "focus_socials", "focus_mentals")
ATTRIBUTES = ("Physical", "Social", "Mental")
# Attacks every character has a pool for, in order; Brawl even at 0.
ATTACKS = (
    ("Brawl", "Unarmed"),
    ("Melee", "Melee"),
    ("Firearms", "Firearms"),
    ("Athletics", "Thrown"),
)
# Categories whose traits are powers of a discipline, named "Discipline: Power".
POWER_CATEGORIES = ("elder_disciplines", "luminary_disciplines")


class PoolPart(BaseModel):
    label: str
    value: int


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


@lru_cache
def catalogue() -> Catalogue:
    with POWERS_FILE.open("rb") as f:
        raw = tomllib.load(f)
    powers: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for p in raw.get("powers", []):
        powers[p["discipline"]].append(p)
    return Catalogue(
        disciplines={d["name"]: d for d in raw.get("disciplines", [])},
        powers={k: sorted(v, key=lambda p: p["level"]) for k, v in powers.items()},
        attacks={a["skill"]: a for a in raw.get("attacks", [])},
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


@dataclass
class Sheet:
    """What the pools are made of, read from the character's sheet rows."""

    ratings: dict[tuple[str, str], int] = field(default_factory=dict)
    focuses: set[str] = field(default_factory=set)
    disciplines: dict[str, int] = field(default_factory=dict)
    # Techniques, elder and luminary powers: (category name, name).
    others: list[tuple[str, str, str]] = field(default_factory=list)
    traits: list[tuple[str, str, Mapping[str, Any]]] = field(default_factory=list)

    def rating(self, category: str, name: str) -> int:
        return self.ratings.get((category, name), 0)

    @classmethod
    def read(cls, rows: Iterable[SheetRow], rule_set: RuleSetData) -> "Sheet":
        sheet = cls()
        for row in rows:
            category, name = row.category.key, row.definition.name
            rating = row.trait.rating if row.trait.rating is not None else 1
            if rating <= 0:
                continue
            key = (category, name)
            sheet.ratings[key] = max(sheet.ratings.get(key, 0), rating)
            if category in FOCUS_CATEGORIES:
                sheet.focuses.add(name)
            elif category == "disciplines":
                sheet.disciplines[name] = max(sheet.disciplines.get(name, 0), rating)
            elif category in (*POWER_CATEGORIES, "techniques"):
                sheet.others.append((category, row.category.name, name))
            properties = rule_set.trait_properties(category, name)
            if properties:
                sheet.traits.append((category, name, properties))
        return sheet


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


def effects(sheet: Sheet, bases: Mapping[str, set[str]]) -> list[Effect]:
    """Every pool change the character has, from its disciplines, powers,
    merits and flaws, resolved to numbers."""
    found: list[Effect] = []

    def add(entries: Iterable[Mapping[str, Any]], source: str) -> None:
        for e in entries:
            if "focus" in e and e["focus"] not in sheet.focuses:
                continue
            if "unless_focus" in e and e["unless_focus"] in sheet.focuses:
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
                )
            )

    book = catalogue()
    for name, rating in sheet.disciplines.items():
        spec = book.disciplines.get(name, {})
        add(spec.get("pools", []), name)
        for power in book.powers.get(name, []):
            if power["level"] <= rating:
                add(power.get("pools", []), power["name"])
    for category, name, properties in sheet.traits:
        if category in ("merits", "flaws"):
            add(properties.get("pools", []), name)
    return found


def damage_effects(sheet: Sheet) -> list[DamageEffect]:
    """Every change to attack damage the character has, from its disciplines and
    the powers it has reached."""
    found: list[DamageEffect] = []

    def add(entries: Iterable[Mapping[str, Any]], source: str) -> None:
        for e in entries:
            found.append(
                DamageEffect(
                    attacks=tuple(e["attacks"]),
                    source=source,
                    amount=e.get("amount", 0),
                    exceptional=e.get("exceptional", 0),
                    type=e.get("type", "normal"),
                    when=e.get("when"),
                    note=e.get("note"),
                )
            )

    book = catalogue()
    for name, rating in sheet.disciplines.items():
        add(book.disciplines.get(name, {}).get("damage", []), name)
        for power in book.powers.get(name, []):
            if power["level"] <= rating:
                add(power.get("damage", []), power["name"])
    return found


def damage(skill: str, found: Sequence[DamageEffect]) -> Damage | None:
    """What a hit with the attack made on `skill` does: its base (core p. 279) plus
    each power that always adds to it. Powers that hold only some of the time
    (`when`) are notes."""
    base = catalogue().attacks.get(skill)
    if base is None:
        return None
    parts = [PoolPart(label=base["kind"], value=base["damage"])]
    exceptional = base.get("exceptional", 0)
    kind: Literal["normal", "aggravated"] = "normal"
    notes: list[str] = []
    for e in found:
        if skill not in e.attacks:
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
    **extra: Any,
) -> TestPool:
    """A pool from its base parts and the effects that change it: those that
    always hold add to it, those with `when` become its variants."""
    parts = list(base)
    variants: dict[str, list[PoolPart]] = defaultdict(list)
    notes: list[str] = list(extra.pop("notes", []))
    for e in found:
        if e.pool == "all" or not _applies(e, key) or e.attribute or e.instead_of:
            continue
        if e.note:
            notes.append(f"{e.note} ({e.source})")
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
        **extra,
    )


def _when_label(when: str) -> str:
    return "With Celerity active" if when == "Celerity" else when[:1].upper() + when[1:]


def pools(
    sheet: Sheet,
    found: Sequence[Effect],
    blood_per_turn: int,
    hurts: Sequence[DamageEffect] = (),
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

    out: list[TestPool] = []
    initiative_attr = next(
        (e.attribute for e in found if e.pool == "initiative" and e.attribute), None
    ) or ("Mental" if attrs["Mental"] > attrs["Physical"] else "Physical")
    out.append(_pool("initiative", "Initiative", "Combat", [attr(initiative_attr)], found))
    blood = f"Spend Blood for +1 Physical each, up to {blood_per_turn} a turn."
    out.append(
        _pool(
            "dodge",
            "Dodge",
            "Combat",
            [attr("Physical"), skill("Dodge")],
            found,
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
                    versus="Physical + Dodge",
                    notes=[blood],
                    damage=damage(name, hurts),
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
                versus=spec.get("versus"),
            )
        )
    for pool in out:
        for variant in pool.variants:
            variant.when = _when_label(variant.when)
    return out


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
    bases = technique_bases(rule_set)
    found = effects(sheet, bases)
    return Reference(
        pools=pools(sheet, found, blood_per_turn, damage_effects(sheet)),
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
