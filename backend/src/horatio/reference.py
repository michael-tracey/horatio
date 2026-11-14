"""The Play View's quick game reference (issue #83): a character's common test
pools, worked out from the sheet, and notes on what each of its powers does.

Pools follow MET: VTM (pp. 271-275): an attack or a static challenge is
attribute + skill; Physical defence is Physical + Dodge; Mental and Social
defence is the attribute + current Willpower, which the Play View's tracker
holds, so those pools are sent without it and the page adds it. Initiative is
the higher of Physical and Mental (p. 276).

Every other skill the character has is an "Other tests" pool (issue #371): a static
challenge is attribute + skill (p. 272), the attribute being the storyteller's call,
so each starts with the one the catalogue lists the skill under and carries what a
switch does to any attribute, for the Play View to change it. Resisting frenzy is
Mental + Willpower against 10 + Beast traits (p. 302): `frenzy` is its Mental side,
with what merits and flaws add or count as Beast traits.

Disciplines, focuses, merits and flaws change pools through `pools` entries in
the rules data: on a discipline or power in bns_met_vampire_powers.toml, and on
merits and flaws in the catalogue. See the top of that file for their shape. An
entry with `when` is a variant ("With Celerity active: 12"), not part of the
number shown, since it holds only some of the time. A variant can also be another
pool to use in its place (Rockheart's Physical + Survival), or add what the Play
View's trackers hold (Rampart of Faith's Morality minus Beast traits), which the
page counts (issue #602). One a switch holds only against someone (Killer
Instincts' hunted target, issue #613) is a variant the page shows while the switch
is on, with the equipment qualities it gives, rather than part of the total.

Each attack pool also carries the damage a hit does (issue #190): the base for its
type (core p. 279) plus what the sheet's powers add through `damage` entries in the
same file, with a note for the extra point of an exceptional success. Weapons are
not counted.

A power that deals damage through a test of its own rather than an attack (Psychic
Assault, Flame Bolt: issue #600) has a `test` entry: a pool in Combat, with what a
success does, that the Play View shows while the power's switch is on.

Forms and powers that hold only while they are active (issue #200) are switches,
from `active` in the same file: Shape of the Beast's forms, Celerity, Feral Claws
and the rest. Each pool says what each switch would change in it (`switched`), and
the Play View adds what is on, since being on is a tap in the game
(horatio.play). A switch can also add wound levels, change an attribute, give a
focus or more Blood; `switches` lists those the sheet has, with what they change.
Another power the character has can add notes to a switch (`notes` with a `when`,
issue #601), as Quickness does to Celerity's.

A troupe's house merits and flaws carry `pools` and `active` in their catalogue
properties, as the troupe's rules read them (horatio.rules.house_effects), and are
read here like a book merit's.
"""

import re
import tomllib
from collections import defaultdict
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
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
# Skills with pools of their own in Combat, left out of "Other tests".
COMBAT_SKILLS = ("Brawl", "Dodge", "Firearms", "Melee")
# Categories whose traits are powers of a discipline, named "Discipline: Power".
POWER_CATEGORIES = ("elder_disciplines", "luminary_disciplines")
BOOK = "core"
# How the summary of a switch names each pool family.
# Amounts the Play View's trackers hold, which it counts (TrackedPart): current
# Morality less current Beast traits, and current Derangement traits; or a power's
# counter, "charge:<key>" (issue #826: Reaper's Due's stack).
TRACKED = ("morality_less_beast", "derangements")
Tracked = str
# A power's charges, points or stack, tapped as "charge:<key>" (issue #826).
CHARGE = "charge:"


def tracked(amount: Any) -> str | None:
    """The tracker an amount counts, if the Play View's trackers hold it."""
    if amount in TRACKED or (isinstance(amount, str) and amount.startswith(CHARGE)):
        return amount
    return None


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
    # False for damage armour and Fortitude can't reduce (Psychic Assault, #600).
    reducible: bool = True


class TrackedPart(BaseModel):
    """A part of a variant the Play View's trackers hold, so the page counts it
    (issue #602): Rampart of Faith adds current Morality minus current Beast traits,
    Manic Episode current Derangement traits (#820), Reaper's Due its stack (#826:
    "charge:Reaper's Due")."""

    label: str
    tracks: Tracked


class VariantQuality(BaseModel):
    """An equipment quality a variant gives (issue #613): Killer Instincts' Brutal."""

    name: str
    # What it does at the table: "Win on the larger pool: exceptional success".
    play: str
    # Where its rules are: "p. 516".
    page: str


class PoolVariant(BaseModel):
    # When it applies: "With Celerity active", "In fight form".
    when: str
    total: int
    # What it adds to the pool: "+4 Alacrity".
    parts: list[PoolPart]
    # Its parts are the whole pool, in place of the pool's own and Willpower:
    # Rockheart's Physical + Survival for Mental and Social defence (issue #602).
    instead: bool = False
    # What it adds that the trackers hold, which `total` leaves out.
    tracked: list[TrackedPart] = []
    # The switch it holds for, shown only while that is on: Killer Instincts' line
    # "Against your hunted target" (issue #613), which the pool's total leaves out.
    switch: str | None = None
    # Equipment qualities it gives besides its parts, each with what it does.
    qualities: list[VariantQuality] = []


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
    # A power's own test (issue #600): the switch it shows while on, and the
    # challenge in words where it has no pool of its own (Scourge of Arikel).
    switch: str | None = None
    challenge: str | None = None


class Cost(BaseModel):
    """What using a power costs, for its Use button on the Pools tab (issue #370)."""

    tracker: Literal["blood", "willpower"]
    amount: int
    # The most the player may spend on one use, choosing how much from `amount` up
    # (issue #824: Promises Like Steel's 1 to 3 Blood, Vol. 2 pp. 217-218).
    most: int | None = None


class Heal(BaseModel):
    """Damage a use heals: of one kind, the worst first (aggravated, then normal),
    every box, or as much as the player says (issue #825)."""

    damage: Literal["normal", "aggravated", "worst", "all", "asked"]
    amount: int = 0


class ChargeChange(BaseModel):
    """What a use does to a power's counter (issue #826): gains or spends that many,
    fills it to its most, or empties it."""

    # The counter's tracker: "charge:Kineticism".
    counter: str
    gain: int = 0
    spend: int = 0
    # The player chooses how many to spend, from `spend` up to all held (Vengeful
    # Strike's charge a point of damage, Vol. 2 p. 75).
    more: bool = False
    # Filled to its most, whatever was left going (Rayzeel's Grace, Vol. 2 p. 219).
    fill: bool = False
    # Back to none (Reaper's Due on a new mark, Vol. 2 p. 118).
    reset: bool = False


class PowerUse(BaseModel):
    """A use of a power that changes the trackers besides spending its cost (issue
    #825): a button of its own on the Pools tab, made of ordinary taps with Undo."""

    label: str
    cost: Cost | None = None
    # The cost is half the tracker as it stands, rounded down, in place of its
    # amount (Indestructible, Vol. 2 p. 214); it needs at least 2.
    half: bool = False
    heal: Heal | None = None
    # Aggravated damage turned to normal; `convert_all` for every box of it.
    convert: int = 0
    convert_all: bool = False
    # Turn aggravated to normal, or where there is none heal normal (Cocoon).
    mend: int = 0
    # Blood or Willpower gained, never past the pool.
    gains: list[Cost] = []
    # Blood gained may go past the pool while a switch whose Blood may go over it
    # is on (issue #854: Mantle of Sutekh's tithes, Vol. 2 p. 240).
    over: bool = False
    # Beast traits taken (Feed the Blighted Wolf, Beast's Vigor).
    beast: int = 0
    # Damage moved onto one of the character's ghoul Retainers, up to this much a use.
    retainer: int = 0
    # Only onto an animal ghoul Retainer (issue #854: Beast's Vigor, Vol. 2 Issue 1 p. 58).
    animal: bool = False
    # The switch that must be on for it, by key.
    when: str | None = None
    # How often the book allows it ("Once a turn"), shown with it; the Play View
    # has no turns to count, so the player keeps to it.
    once: str | None = None
    note: str | None = None
    page: str | None = None
    # Who it is used on (issue #823): the character itself, or another character in
    # its home troupe, whose game it changes (horatio.play_on_others).
    target: Literal["self", "other"] = "self"
    # The ally it calls up, by its summon's key (issue #827): one more, or with
    # `summon_all` every one the character can have at once (Arms of the Abyss rise
    # together, core p. 149).
    summon: str | None = None
    summon_all: bool = False
    # What it does to a power's counter (issue #826).
    charges: ChargeChange | None = None
    # A switch it turns on, if off (Reaper's Due's mark).
    on: str | None = None
    # Its whole effect is what it spends (issue #876: reforming Bonecraft's broken
    # body weapon for 1 Blood, core p. 169).
    spends: bool = False


class Summon(BaseModel):
    """An ally a power calls up at a game (issue #827): Arms of the Abyss, a zombie, a
    bound wraith. Each has its own health levels (and Blood, where the book gives it),
    tapped as a Retainer's are, and is gone when dismissed or when the game ends. One
    with no health levels (Shadow Twin, immune to Physical harm) is only out or not."""

    key: str
    # One of them: "Arm of the Abyss".
    name: str
    # The power it comes from: "Obtenebration 3", "Guardian Lion".
    origin: str
    page: str
    # What it can do, and what ends it, in words.
    note: str = ""
    health: int = 0
    blood: int = 0
    # How many the character can have out at once, for this sheet.
    most: int = 1


class CounterFade(BaseModel):
    """A button that lets a counter's charges go (issue #826): the Play View has no
    fights or minutes to count, so the player says when."""

    label: str
    # How many it keeps: none when a fight ends, 1 going into one (Kineticism).
    keep: int = 0
    # A switch it also turns off (Reaper's Due's mark).
    off: str | None = None


class Counter(BaseModel):
    """Charges, points or a stack a power builds and spends (issue #826), tapped as
    its `key`, "charge:Kineticism": +n gains, -n spends, never below none or past
    its most. Every game starts it at none."""

    key: str
    name: str
    # What one is called, and more than one, on a use's button: "1 charge".
    unit: str
    units: str
    most: int
    note: str | None = None
    page: str | None = None
    fades: list[CounterFade] = []
    # Where the Pools tab shows it: with a discipline, under one of its powers, or
    # with a technique, elder or luminary power, by name.
    discipline: str | None = None
    power: str | None = None
    other: str | None = None


class PowerNote(BaseModel):
    level: int
    name: str
    note: str
    # What the character's focus adds, if they have the one the book names.
    focus: str | None = None
    # What using it costs, when that is plain; None for a power with no clear cost.
    cost: Cost | None = None
    # The keys of its switches (see `active`), which using it turns on.
    switches: list[str] = []
    # Uses that heal, convert damage or gain Blood or Willpower (issue #825).
    uses: list[PowerUse] = []


class DisciplinePowers(BaseModel):
    name: str
    rating: int
    pool: str | None
    versus: str | None
    note: str | None
    focus: str | None
    powers: list[PowerNote]
    # What activating the discipline itself costs (Celerity), and its switches.
    cost: Cost | None = None
    switches: list[str] = []


class OtherPower(BaseModel):
    """A technique, elder or luminary power: named, rated as held."""

    category_name: str
    name: str
    note: str | None
    # Where the note is from: "214", "Vol. 2, p. 198" (issue #587).
    page: str | None = None
    # What using it costs and the switches it turns on, from its [[others]] entry,
    # as for a numbered power (issue #588).
    cost: Cost | None = None
    switches: list[str] = []
    uses: list[PowerUse] = []


class SwitchLevel(BaseModel):
    """Wound levels a switch adds while it is on, or gives up (fewer than none: issue
    #824, Bonecraft's Extra Limbs, core p. 168): those come off the sheet's own in the
    category, and come back only when it ends (core p. 169)."""

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


class DisciplineRaise(BaseModel):
    """Dots a switch adds to a discipline the character has, never past 5 (issue #849:
    Mercurial Vitality's Potence and Fortitude, core p. 229). The powers gained hold
    while it is on: their pool and damage changes count as the switch's."""

    discipline: str
    amount: int
    # The dots it counts as while on, for this sheet: its own plus `amount`, at most 5.
    to: int = 0


class AddedNote(BaseModel):
    """What another power the character has adds to a switch, that can't be worked
    out (issue #601): Quickness's extra round on Celerity's."""

    # The power it comes from, and where its rules are: "Quickness", "p. 214".
    source: str
    page: str
    note: str


class SwitchQuality(BaseModel):
    """An equipment quality a switch gives while it is on (#820): Armor of Terra's
    Hardened and Ballistic. What it does to the pools counts as a picked quality's
    does (horatio.play)."""

    # The kind of equipment it is a quality of: "protective", "melee".
    kind: str
    name: str


class SwitchOption(BaseModel):
    """One of a power's own options, picked each time it is used (issue #821): Mantle
    of Atira's Bear Strength, Mythic Form's Tough. While its switch is on and it is
    picked, what it does counts as a switch's does: its `key` ("Mythic Form/Tough") is
    what a `when` in the powers file names, and it is on while it is picked."""

    name: str
    # "<switch key>/<name>": a switch of its own, on while picked.
    key: str
    page: str
    # What it does that can't be worked out, in words.
    note: str = ""
    health: list[SwitchLevel] = []
    attributes: list[AttributeChange] = []
    focuses: list[str] = []
    blood_per_turn: int = 0
    blood_half: bool = False
    # More Blood at most while picked (issue #824: Second Stomach's 2 for each level
    # given up, Vol. 2 Issue 1 p. 61).
    blood_extra: int = 0
    # Equipment qualities it gives while picked, counted as a picked quality's are.
    qualities: list[SwitchQuality] = []
    # Whether a form pauses it; None follows its switch's.
    normal_form_only: bool | None = None
    # For an option whose amount is chosen each use (issue #824: Tough's 1 to 3
    # Physical, core p. 168), one option per amount, named "Tough: 2": the option's
    # own name, the amount, and what the amount counts. Picking one drops another
    # amount of the same option, as it is one choice.
    base: str | None = None
    amount: int | None = None
    amount_label: str | None = None
    # Who it can be picked for, when its switch can be used on another (issue #813):
    # "self" only, "other" only (Bonecraft's Crippled, core p. 169), or "any". A trait
    # that rules it out (`hidden_by`: Tzimisce: Scar Tissue) rules it out on yourself
    # only, so it is left for others.
    target: Literal["self", "other", "any"] = "any"
    # Equipment qualities picked for it while it is picked (issue #876: Bonecraft's
    # Body Weaponry, a weapon built by the weapon rules, core p. 169): its switch's
    # own picks, which count as an equipped item's qualities do.
    picks: "Picks | None" = None


class Picks(BaseModel):
    """What the player picks each time a switch goes on: equipment qualities (issue
    #599: Flesh of Marble's two Protective Gear qualities, Vol. 2 p. 232), whose pool
    effects count as an equipped item's do (horatio.play), or the power's own options
    (issue #821: two of Mantle of Atira's qualities, Vol. 2 p. 82), each with what it
    does. `count` is how many at once, after the focus that raises it."""

    # The kind of equipment they are qualities of: "protective", "melee"; None for a
    # power whose options are its own.
    kind: str | None = None
    count: int
    # More kinds of equipment whose qualities can be picked (Perfect Stance: any weapon's).
    kinds: list[str] = []
    # Only these qualities of the kind (Mortician's Secret: four protective ones).
    only: list[str] = []
    # Qualities picked to be guarded against, not had (Perfect Stance, Vol. 2 p. 245):
    # they change no pool.
    immune: bool = False
    # The power's own options, those this sheet can pick.
    options: list[SwitchOption] = []
    # Who the power is used on: "self", or "any" for a power that can be used on
    # another character too, which the effects-on-others ticket (#823) follows.
    target: str = "self"


# An option's own picks name Picks, defined after it (issue #876).
SwitchOption.model_rebuild()


class Switch(BaseModel):
    """A form or power the Play View can switch on while the character has it
    (issue #200). Forms are transformative: only one is on at a time (core
    p. 114), but for those it combines with, or more with Ravenous
    Conglomeration (`forms_at_once`)."""

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
    # What other powers the character has add to it, that can't be worked out.
    added: list[AddedNote] = []
    # Wound levels it adds while on.
    health: list[SwitchLevel] = []
    attributes: list[AttributeChange] = []
    focuses: list[str] = []
    blood_per_turn: int = 0
    # The Blood pool is half again as big (rounded up) while it is on.
    blood_half: bool = False
    # More Blood at most while it is on (issue #824).
    blood_extra: int = 0
    # While it is on, Blood a use gains `over` may go past the pool; when it ends,
    # the Blood over the pool goes (issue #854: Mantle of Sutekh, Vol. 2 p. 240).
    blood_over: bool = False
    picks: Picks | None = None
    # Kept until undone, not until the game ends (issue #822): it lasts through Reset
    # until the player turns it off (horatio.play_effects). Using it again while it
    # is on replaces it, as a character carries one application at a time.
    kept: bool = False
    # It changes the character's normal form only (Malleable Visage, Bonecraft: core
    # pp. 168-169): while a form is on, what it does is paused, and comes back after.
    normal_form_only: bool = False
    # Kept while on, it takes one of the forms Ravenous Conglomeration allows at once
    # (Vol. 2 p. 249: kept Bonecraft alterations count as one).
    counts_as_form: bool = False
    # Qualities it gives every time, without picking.
    qualities: list[SwitchQuality] = []
    # For one of a power's own options (issue #821): the key of the switch it is
    # picked for. It is never shown as a switch of its own: it is on while picked.
    option_of: str | None = None
    # Who it can be used on (issue #823): the character itself ("self"), only another
    # character in its home troupe ("other": Fleshcraft reshaping a willing person),
    # or either ("any"). One used on another is an effect on them, kept until undone
    # (horatio.play_on_others).
    target: Literal["self", "other", "any"] = "self"
    # Dots it adds to disciplines while on (issue #849).
    disciplines: list[DisciplineRaise] = []
    # What using costs nothing while it is on, by the name of the discipline or power
    # its Use button is on (issue #849: Quickened Blood's Celerity, core p. 230).
    waives: list[str] = []


class Frenzy(BaseModel):
    """Resisting frenzy (core p. 302): Mental and what merits and flaws add, to
    which the Play View adds current Willpower, against 10 + Beast traits."""

    parts: list[PoolPart]
    # Beast traits the character counts as having more (or fewer) for it: Short Fuse.
    beast: list[PoolPart] = []
    # The same, while a switch is on: Heart of Darkness's removed heart, one fewer
    # (core p. 161). `value` is the Beast traits more, or fewer.
    switched_beast: list[SwitchedPart] = []


class Reference(BaseModel):
    pools: list[TestPool]
    frenzy: Frenzy
    disciplines: list[DisciplinePowers]
    other_powers: list[OtherPower]
    # Modifiers that change no pool shown here: "Hard of Hearing: -2 to Awareness".
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
    # The keys of switches kept until undone (issue #822).
    kept_keys: frozenset[str] = frozenset()
    # Powers' charges, points and stacks (issue #826), as the file has them.
    counters: Sequence[Mapping[str, Any]] = ()

    def power(self, discipline: str, name: str) -> Mapping[str, Any] | None:
        return next((p for p in self.powers.get(discipline, []) if p["name"] == name), None)


def actives(entry: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """An entry's switches: `active` is one table or a list of them."""
    found = entry.get("active", [])
    return [found] if isinstance(found, Mapping) else list(found)  # pyright: ignore[reportUnknownArgumentType]


def option_keys(active: Mapping[str, Any]) -> list[str]:
    """The keys of a switch's own options (issue #821): "Mythic Form/Tough"."""
    return [f"{active['key']}/{o['name']}" for o in active.get("picks", {}).get("options", [])]


def own_tests(entry: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """An entry's tests that deal damage (issue #600): `test` is one table or a list."""
    found = entry.get("test", [])
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
        switch_keys=frozenset(
            k for e in entries for a in actives(e) for k in (a["key"], *option_keys(a))
        ),
        kept_keys=frozenset(a["key"] for e in entries for a in actives(e) if a.get("kept")),
        counters=tuple(raw.get("counters", [])),
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
    # For frenzy: Beast traits it counts as more (or fewer, below 0).
    beast: int = 0
    # An amount the Play View's trackers hold, which it counts (TrackedPart).
    tracks: Tracked | None = None
    # Another pool to use in place of this one: Physical + Survival (Rockheart).
    alternative: tuple[PoolPart, ...] = ()
    # Whom it holds against, with a switch: a line of its own under the pool while
    # the switch is on, not part of its total (Killer Instincts, issue #613).
    against: str | None = None
    # What its part is called, if not its source: "Accurate".
    label: str | None = None
    qualities: tuple[VariantQuality, ...] = ()


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
    # Each skill held, by name and detail ("Crafts", "Painting"): its rating, and the
    # attribute the catalogue lists it under.
    skills: dict[tuple[str, str], tuple[int, str | None]] = field(default_factory=dict)

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
            skills=self.skills,
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
                row.trait.detail,
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
                t.category,
                category.name if category else t.category,
                t.name,
                t.rating,
                rule_set,
                detail=t.detail,
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
        detail: str = "",
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
        if category == "skills":
            held = self.skills.get((name, detail), (0, None))[0]
            self.skills[(name, detail)] = (max(held, rating), (properties or {}).get("attribute"))


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


def _alternative(spec: str | None, sheet: Sheet) -> tuple[PoolPart, ...]:
    """Another pool's parts, from its traits: "Physical + Survival"."""
    if not spec:
        return ()
    names = [s.strip() for s in spec.split("+")]
    return tuple(
        PoolPart(label=n, value=sheet.rating("attributes" if n in ATTRIBUTES else "skills", n))
        for n in names
    )


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


def _effects(
    entries: Iterable[Mapping[str, Any]],
    source: str,
    chosen: Mapping[str, str],
    sheet: Sheet,
    bases: Mapping[str, set[str]],
) -> list[Effect]:
    """The pool changes of some `pools` entries, resolved to numbers."""
    found: list[Effect] = []
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
                beast=e.get("beast", 0),
                tracks=tracked(e.get("amount")),
                alternative=_alternative(e.get("alternative"), sheet),
                against=e.get("against"),
                label=e.get("label"),
                qualities=tuple(
                    VariantQuality(name=q["name"], play=q["play"], page=_page(q))
                    for q in e.get("qualities", [])
                ),
            )
        )
    return found


def effects(sheet: Sheet, bases: Mapping[str, set[str]]) -> list[Effect]:
    """Every pool change the character has, from its disciplines, powers,
    merits and flaws, resolved to numbers."""
    found: list[Effect] = []
    for owner in owners(sheet):
        found += _effects(owner.entry.get("pools", []), owner.source, owner.chosen, sheet, bases)
    for category, name, properties in sheet.traits:
        if category in ("merits", "flaws"):
            found += _effects(properties.get("pools", []), name, {}, sheet, bases)
    return found


def _damage_effects(owner: Owner, sheet: Sheet) -> list[DamageEffect]:
    """The changes to attack damage of one entry the character has."""
    return [
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
        for e in owner.entry.get("damage", [])
        if _holds(e, sheet, owner.chosen)
    ]


def damage_effects(sheet: Sheet) -> list[DamageEffect]:
    """Every change to attack damage the character has, from its disciplines, the
    powers it has reached and its other powers."""
    return [d for owner in owners(sheet) for d in _damage_effects(owner, sheet)]


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


@dataclass(frozen=True)
class PowerTest:
    """A test of a power that deals damage (issue #600), as the sheet has it."""

    name: str
    entry: Mapping[str, Any]


def power_tests(sheet: Sheet) -> list[PowerTest]:
    """Each power the character has that deals damage through a test of its own,
    for its focus and purchase choices."""
    return [
        PowerTest(test.get("name") or owner.source, test)
        for owner in owners(sheet)
        for test in own_tests(owner.entry)
        if _holds(test, sheet, owner.chosen)
    ]


def tested_damage(test: PowerTest) -> Damage:
    """What a success with a power's test does: its damage, what an exceptional
    success adds, and whether anything can reduce it."""
    e = test.entry
    note = e.get("note")
    return Damage(
        kind="power",
        type=e.get("type", "normal"),
        parts=[PoolPart(label=test.name, value=e["damage"])],
        total=e["damage"],
        exceptional=e.get("exceptional", 0),
        notes=[note] if note else [],
        reducible=not e.get("unreducible", False),
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
    # A skill's covers each of its fields: "skill:Crafts" covers "skill:Crafts:Painting".
    if effect.pool.startswith("skill:"):
        return key.startswith(f"{effect.pool}:")
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
    those with another `when` become its variants, as does another pool to use
    in its place."""
    parts = list(base)
    variants: dict[str, list[PoolPart]] = defaultdict(list)
    tracked: dict[str, list[TrackedPart]] = defaultdict(list)
    instead: list[PoolVariant] = []
    # Variants a switch holds against someone, by switch and whom.
    against: dict[tuple[str, str], PoolVariant] = {}
    switched: list[SwitchedPart] = []
    notes: list[str] = list(extra.pop("notes", []))
    for e in found:
        if e.pool == "all" or not _applies(e, key) or e.attribute or e.instead_of:
            continue
        if e.alternative:
            instead.append(
                PoolVariant(
                    when=f"instead, with {e.source}",
                    total=sum(p.value for p in e.alternative),
                    parts=list(e.alternative),
                    instead=True,
                )
            )
        elif e.note:
            notes.append(f"{e.note} ({e.source})")
        elif e.when in keys and e.against:
            variant = against.setdefault(
                (e.when, e.against),
                PoolVariant(when=f"against {e.against}", total=0, parts=[], switch=e.when),
            )
            if e.tracks:
                # What the trackers hold, which the page counts (Reaper's Due, #826).
                variant.tracked.append(TrackedPart(label=e.label or e.source, tracks=e.tracks))
            elif e.amount:
                variant.parts.append(PoolPart(label=e.label or e.source, value=e.amount))
            variant.qualities += [q for q in e.qualities if q not in variant.qualities]
        elif e.when in keys:
            if e.amount:
                switched.append(SwitchedPart(switch=e.when, label=e.source, value=e.amount))
        elif e.when and e.tracks:
            # A variant of its own, though it adds no number here.
            variants.setdefault(e.when, [])
            tracked[e.when].append(TrackedPart(label=e.source, tracks=e.tracks))
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
            PoolVariant(
                when=when,
                total=total + sum(p.value for p in adds),
                parts=adds,
                tracked=tracked[when],
            )
            for when, adds in variants.items()
        ]
        + instead
        + [
            v.model_copy(update={"total": total + sum(p.value for p in v.parts)})
            for v in against.values()
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
    hurts: Sequence[DamageEffect] = (),
    switched: Sequence["Switch"] = (),
) -> list[TestPool]:
    attrs = {a: sheet.rating("attributes", a) for a in ATTRIBUTES}

    def skill(name: str, rating: int | None = None) -> PoolPart:
        """A skill, or another the character may use in its place (Preternatural
        Awareness), whichever is higher."""
        best = PoolPart(
            label=name, value=sheet.rating("skills", name) if rating is None else rating
        )
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
    # Spending Blood for Physical is said once, over the Combat pools (issue #371).
    out.append(
        _pool(
            "dodge",
            "Dodge",
            "Combat",
            [attr("Physical"), skill("Dodge")],
            found,
            keys,
            notes=["Give up your standard action for +2 to one Dodge pool this round."],
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
    # Powers that deal damage through a test of their own (issue #600): in Combat,
    # beside the attacks, made on their discipline's pool or the one they name.
    for test in power_tests(sheet):
        key = f"power:{test.name}"
        spec, versus = test.entry.get("pool", ""), test.entry.get("versus")
        # A discipline's pool counts what changes that discipline's pool.
        counts_as = key
        if spec.startswith("discipline:"):
            own = book.disciplines.get(spec.removeprefix("discipline:"), {})
            counts_as, spec, versus = spec, own.get("pool", ""), versus or own.get("versus")
        attribute, _, skill_name = (s.strip() for s in spec.partition("+"))
        made = _pool(
            counts_as,
            test.name,
            "Combat",
            [attr(attribute), skill(skill_name)] if spec else [],
            found,
            keys,
            versus=versus,
            damage=tested_damage(test),
            switch=test.entry["when"],
            challenge=test.entry.get("challenge"),
        )
        made.key = key
        out.append(made)
    for (name, detail), (rating, attribute) in sorted(sheet.skills.items()):
        if name in COMBAT_SKILLS:
            continue
        # A house skill with no attribute listed is the skill alone.
        base = [attr(attribute)] if attribute is not None and attribute in attrs else []
        out.append(
            _pool(
                f"skill:{name}:{detail}" if detail else f"skill:{name}",
                f"{name}: {detail}" if detail else name,
                "Other tests",
                [*base, skill(name, rating)],
                found,
                keys,
            )
        )
    for pool in out:
        for variant in pool.variants:
            variant.when = _when_label(variant.when)
        # Another test's attribute is the storyteller's call, so it carries what a
        # switch does to any of them, and the Play View counts the one in use.
        other = pool.group == "Other tests"
        for switch in switched:
            for change in switch.attributes:
                if (other and change.pools is None) or (
                    pool.parts[0].label == change.attribute and _covers(change.pools, pool.key)
                ):
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


def _changes(
    switch: Switch,
    found: Sequence[Effect],
    hurts: Sequence[DamageEffect],
    tested: Sequence[PowerTest] = (),
) -> list[str]:
    """What a switch changes, in words, for its line on the Play View."""
    lines: list[str] = []
    for e in found:
        if e.when == switch.key and e.against and not e.note:
            # "Against your hunted target: +2 attacks (Accurate), Brutal" (issue #613).
            gives = [q.name for q in e.qualities]
            if e.amount:
                gives.insert(
                    0, f"{_signed(e.amount)} {_pool_words(e.pool)} ({e.label or e.source})"
                )
            lines.append(f"Against {e.against}: {', '.join(gives)}")
            continue
        if e.when == switch.key and e.amount and not e.note:
            own = switch.option_of is not None or switch.name.startswith(e.source)
            by = "" if own else f" ({e.source})"
            lines.append(f"{_signed(e.amount)} {_pool_words(e.pool)}{by}")
        if e.when == switch.key and e.pool == "frenzy" and e.beast:
            fewer = "fewer" if e.beast < 0 else "more"
            traits = "trait" if abs(e.beast) == 1 else "traits"
            lines.append(f"Frenzy resisted as if with {abs(e.beast)} Beast {traits} {fewer}")
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
    # Levels given up read "-2 Healthy given up" (issue #824).
    lines += [
        f"{_signed(boxes)} {level}{' given up' if boxes < 0 else ''}"
        for level, boxes in levels.items()
        if boxes
    ]
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
    for t in tested:
        if t.entry["when"] != switch.key:
            continue
        hurt = tested_damage(t)
        kind = "aggravated damage" if hurt.type == "aggravated" else "damage"
        reduced = "" if hurt.reducible else " that nothing reduces"
        lines.append(f"{t.name} in Combat: {hurt.total} {kind}{reduced}")
    lines += [f"The {focus} focus" for focus in switch.focuses]
    if switch.qualities:
        lines.append(", ".join(q.name for q in switch.qualities))
    if switch.blood_per_turn:
        lines.append(f"{_signed(switch.blood_per_turn)} Blood a turn")
    if switch.blood_half:
        lines.append("Blood pool half again as big")
    if switch.blood_extra:
        lines.append(f"{_signed(switch.blood_extra)} most Blood")
    if switch.blood_over:
        lines.append("Blood past the pool until it ends")
    return lines


def _switch(owner: Owner, active: Mapping[str, Any], sheet: Sheet, every: bool = False) -> Switch:
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
        blood_extra=blood.get("extra", 0),
        blood_over=blood.get("over", False),
        picks=_picks(owner, active, sheet, every),
        kept=active.get("kept", False),
        normal_form_only=active.get("normal_form_only", False),
        counts_as_form=active.get("counts_as_form", False),
        qualities=[
            SwitchQuality(kind=q["kind"], name=q["name"])
            for q in active.get("qualities", [])
            if holds(q)
        ],
        disciplines=[
            DisciplineRaise(
                discipline=d["discipline"],
                amount=d["amount"],
                to=min(5, sheet.disciplines.get(d["discipline"], 0) + d["amount"]),
            )
            for d in active.get("disciplines", [])
            if sheet.disciplines.get(d["discipline"], 0) > 0
        ],
        waives=list(active.get("waives", [])),
        target=active.get("target") or active.get("picks", {}).get("target", "self"),
    )


def _has(sheet: Sheet, name: str) -> bool:
    """Whether the sheet holds a trait of this name, in any category."""
    return any(held == name for _, held in sheet.ratings)


def _names(spec: str | Sequence[str] | None) -> list[str]:
    if spec is None:
        return []
    return [spec] if isinstance(spec, str) else list(spec)


def _ruled_out(active: Mapping[str, Any], sheet: Sheet) -> bool:
    """Whether a trait the character has rules this switch out (`hidden_by`, #812:
    Tzimisce: Scar Tissue on Malleable Visage, Vol. 2 p. 278)."""
    return any(_has(sheet, n) for n in _names(active.get("hidden_by")))


def _option(
    active: Mapping[str, Any],
    o: Mapping[str, Any],
    holds: Callable[[Any], bool],
    amount: int | None = None,
) -> SwitchOption:
    """One of a power's own options, or for one whose amount is chosen each use
    (`amount = { least, most, label }`, issue #824) the option at that amount: what
    its entries marked `scale` give is that many times theirs (Tough's 2 Physical for
    2 Healthy levels), and it is named with the amount ("Tough: 2")."""
    times = 1 if amount is None else amount

    def scaled(entry: Mapping[str, Any], value: int) -> int:
        return value * times if entry.get("scale") else value

    blood = o.get("blood", {})
    spec = o.get("amount", {})
    return SwitchOption(
        name=f"{o['name']}: {amount}" if amount is not None else o["name"],
        key=f"{active['key']}/{o['name']}: {amount}"
        if amount is not None
        else f"{active['key']}/{o['name']}",
        page=_page({**({"book": active["book"]} if "book" in active else {}), **o})
        if "page" in o
        else _page(active),
        note=o.get("note", ""),
        health=[
            SwitchLevel(level=h["level"], boxes=scaled(h, h["boxes"]))
            for h in o.get("health", [])
            if holds(h)
        ],
        attributes=[
            AttributeChange(
                attribute=a["attribute"],
                amount=scaled(a, a.get("amount", 0)),
                most=a.get("most"),
                pools=a.get("pools"),
            )
            for a in o.get("attributes", [])
            if holds(a)
        ],
        focuses=list(o.get("focuses", [])),
        blood_per_turn=blood.get("per_turn", 0),
        blood_half=blood.get("most") == "half",
        blood_extra=scaled(blood, blood.get("extra", 0)),
        qualities=[
            SwitchQuality(kind=q["kind"], name=q["name"])
            for q in o.get("qualities", [])
            if holds(q)
        ],
        normal_form_only=o.get("normal_form_only"),
        picks=_quality_picks(o["picks"]) if "picks" in o else None,
        base=o["name"] if amount is not None else None,
        amount=amount,
        amount_label=spec.get("label") if amount is not None else None,
        target=o.get("target", "any"),
    )


def _quality_picks(spec: Mapping[str, Any]) -> Picks:
    """An option's own picks (issue #876): equipment qualities only, `count` of them,
    of its `kind` (and `kinds`), or `only` those named."""
    return Picks(
        kind=spec.get("kind"),
        count=spec.get("count", 1),
        kinds=list(spec.get("kinds", [])),
        only=list(spec.get("only", [])),
    )


def _options(
    active: Mapping[str, Any], o: Mapping[str, Any], holds: Callable[[Any], bool]
) -> list[SwitchOption]:
    """An option as it can be picked: itself, or one for each amount it allows."""
    spec = o.get("amount")
    if spec is None:
        return [_option(active, o, holds)]
    return [_option(active, o, holds, n) for n in range(spec.get("least", 1), spec["most"] + 1)]


def _picks(
    owner: Owner, active: Mapping[str, Any], sheet: Sheet, every: bool = False
) -> Picks | None:
    """What the player picks each time a switch goes on (issues #599, #821): how many,
    raised by a focus (`focus_count`: Bonecraft's two with Manipulation), and the
    power's own options this sheet can pick: those its focus and purchase choices
    allow, those another trait adds (`from`: Bonecraft Prodigy's), less those a trait
    it has rules out (`hidden_by`: Tzimisce: Scar Tissue, Vol. 2 p. 278).

    A trait that rules an option out does so on yourself: for a switch that can be
    used on another (issue #813), the option is left for others. With `every`, for an
    effect another's power left on this sheet (`switch_for`), every option counts
    whatever adds it, but those this sheet's traits rule out don't: its body can't
    take them (Scar Tissue on a Bonecraft alteration)."""
    spec = active.get("picks")
    if spec is None:
        return None
    holds = lambda e: not isinstance(e, Mapping) or _holds(e, sheet, owner.chosen)  # noqa: E731
    count = spec.get("count", 1)
    for focus, more in spec.get("focus_count", {}).items():
        if focus in sheet.focuses:
            count = max(count, more)
    on_others = (active.get("target") or spec.get("target", "self")) != "self"
    options: list[SwitchOption] = []
    for o in spec.get("options", []):
        if not every and not (holds(o) and all(_has(sheet, n) for n in _names(o.get("from")))):
            continue
        target = o.get("target", "any")
        if any(_has(sheet, n) for n in _names(o.get("hidden_by"))):
            if every or not on_others or target == "self":
                continue
            target = "other"
        options += [
            option.model_copy(update={"target": target})
            for option in _options(active, o, lambda e: every or holds(e))
        ]
    return Picks(
        kind=spec.get("kind"),
        count=count,
        kinds=list(spec.get("kinds", [])),
        only=list(spec.get("only", [])),
        immune=spec.get("immune", False),
        options=options,
        target=spec.get("target", "self"),
    )


def option_switches(switch: Switch) -> list[Switch]:
    """A switch's own options as switches of their own (issue #821), each on while it
    is picked, so what it does counts as any switch's does."""
    if switch.picks is None:
        return []
    return [
        Switch(
            key=o.key,
            name=f"{switch.name}: {o.name}",
            origin=switch.origin,
            page=o.page,
            notes=[o.note] if o.note else [],
            health=o.health,
            attributes=o.attributes,
            focuses=o.focuses,
            blood_per_turn=o.blood_per_turn,
            blood_half=o.blood_half,
            blood_extra=o.blood_extra,
            qualities=o.qualities,
            picks=o.picks,
            kept=switch.kept,
            normal_form_only=(
                switch.normal_form_only if o.normal_form_only is None else o.normal_form_only
            ),
            option_of=switch.key,
        )
        for o in switch.picks.options
    ]


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


def raised_effects(
    sheet: Sheet, bases: Mapping[str, set[str]], found: Sequence[Switch]
) -> tuple[list[Effect], list[DamageEffect]]:
    """What a switch's extra discipline dots give (issue #849: Mercurial Vitality's
    Potence and Fortitude, core p. 229): the powers gained by them, as effects that
    hold while it is on, and their notes added to the switch. A gained power's
    entries that hold only with another switch on, and its own switches, are left
    out: the Play View has no way to need two switches at once, and none of the
    powers raised so far has any."""
    pools: list[Effect] = []
    hurts: list[DamageEffect] = []
    book = catalogue()
    for switch in found:
        for raise_ in switch.disciplines:
            have = sheet.disciplines.get(raise_.discipline, 0)
            for power in book.powers.get(raise_.discipline, []):
                if not have < power["level"] <= raise_.to:
                    continue
                owner = Owner(
                    power,
                    power["name"],
                    f"{raise_.discipline} {power['level']}",
                    sheet.chosen(raise_.discipline, power),
                )
                pools += [
                    replace(e, when=switch.key)
                    for e in _effects(
                        power.get("pools", []), owner.source, owner.chosen, sheet, bases
                    )
                    if e.when is None
                ]
                hurts += [
                    replace(d, when=switch.key)
                    for d in _damage_effects(owner, sheet)
                    if d.when is None
                ]
                switch.notes.append(f"{owner.origin}, {power['name']}: {power['note']}")
    return pools, hurts


def _raised(switch: Switch, sheet: Sheet) -> list[str]:
    """A switch's extra discipline dots, in words: "Potence counts as 3"."""
    lines: list[str] = []
    for raise_ in switch.disciplines:
        have = sheet.disciplines.get(raise_.discipline, 0)
        if raise_.to > have:
            lines.append(f"{raise_.discipline} counts as {raise_.to}")
        else:
            lines.append(f"{raise_.discipline} is already at {have}, the most")
    return lines


def added_notes(sheet: Sheet, found: Sequence[Switch]) -> None:
    """Give each switch the `notes` other entries the character has add to it, by
    their `when` (issue #601): Quickness's on Celerity, Earth Control's on Earth Meld."""
    by_key = {switch.key: switch for switch in found}
    for owner in owners(sheet):
        for n in owner.entry.get("notes", []):
            switch = by_key.get(n["when"])
            if switch and _holds(n, sheet, owner.chosen):
                switch.added.append(AddedNote(source=owner.source, page=_page(n), note=n["note"]))


@dataclass(frozen=True)
class Worked:
    """Everything that changes the character's pools, worked out from the sheet."""

    effects: list[Effect]
    hurts: list[DamageEffect]
    switches: list[Switch]


def work_out(sheet: Sheet, bases: Mapping[str, set[str]]) -> Worked:
    found = [
        _switch(o, a, sheet)
        for o in owners(sheet)
        for a in actives(o.entry)
        if not _ruled_out(a, sheet)
    ]
    # A power's own options are switches too, on while picked (issue #821).
    found += [option for s in list(found) for option in option_switches(s)]
    pools, hurts = effects(sheet, bases), damage_effects(sheet)
    more_pools, more_hurts = focus_effects(sheet, bases, found)
    raised_pools, raised_hurts = raised_effects(sheet, bases, found)
    pools, hurts = pools + more_pools + raised_pools, hurts + more_hurts + raised_hurts
    tested = power_tests(sheet)
    for switch in found:
        switch.changes = _raised(switch, sheet) + _changes(switch, pools, hurts, tested)
    added_notes(sheet, found)
    return Worked(pools, hurts, found)


def switches(rows: Sequence[SheetRow], rule_set: RuleSetData) -> list[Switch]:
    """The forms and powers on this sheet the Play View can switch on."""
    return work_out(Sheet.read(rows, rule_set), technique_bases(rule_set)).switches


def switch_for(key: str, sheet: Sheet | None = None) -> list[Switch]:
    """A switch by its key, with its own options, as the powers file has it for any
    character (issue #823): what an effect another character's power left on this
    one does, though this one hasn't the power. No sheet's focus or purchase choice
    narrows it, so what a choice or focus gives is left out, and every option counts,
    whichever trait of the user's added it (Bonecraft Prodigy's, issue #813). With the
    sheet it is on, an option that sheet's traits rule out doesn't count: Tzimisce:
    Scar Tissue's body takes no beneficial Bonecraft alteration (Vol. 2 p. 278)."""
    for entry in [
        *catalogue().disciplines.values(),
        *(p for powers in catalogue().powers.values() for p in powers),
        *catalogue().others.values(),
    ]:
        for active in actives(entry):
            if active["key"] == key:
                owner = Owner(entry, entry["name"], entry["name"])
                found = _switch(owner, active, sheet or Sheet(), every=True)
                return [found, *option_switches(found)]
    return []


@dataclass(frozen=True)
class UseOnOther:
    """A use of a power the character has that changes another character's trackers
    (issue #823): Corpore Sano healing someone else."""

    power: str
    use: PowerUse


def uses_on_others(sheet: Sheet) -> list[UseOnOther]:
    """The uses this sheet's powers have for another character, by power name."""
    return [
        UseOnOther(power=o.source, use=u)
        for o in owners(sheet)
        for u in uses(o.entry, sheet)
        if u.target == "other"
    ]


def forms_at_once(sheet: Sheet) -> int:
    """How many forms the character can be in at once: one (core p. 114), or more
    with a power whose entry has `forms` (Ravenous Conglomeration's two, Vol. 2
    p. 249)."""
    return max((o.entry.get("forms", 1) for o in owners(sheet)), default=1)


# A note that starts with what the power costs: "1 Blood, standard action: …".
COST_NOTE = re.compile(r"^(\d+) (Blood|Willpower)\b")


def cost(entry: Mapping[str, Any], sheet: Sheet) -> Cost | None:
    """What using a discipline, power or [[others]] entry costs: its `cost`
    (`{ blood = 1 }` or `{ willpower = 1 }`, none with its `unless_focus`), or else
    the Blood or Willpower its note starts with. Costs that come part way through a
    note ("Grapple, then 1 Blood") are left to the player."""
    given = entry.get("cost")
    if given is not None:
        if given.get("unless_focus") in sheet.focuses:
            return None
        tracker = "willpower" if "willpower" in given else "blood"
        if given[tracker] == "half":
            return Cost(tracker=tracker, amount=0)
        return Cost(tracker=tracker, amount=given[tracker], most=given.get("most"))
    found = COST_NOTE.match(entry.get("note", ""))
    if not found:
        return None
    tracker = "blood" if found[2] == "Blood" else "willpower"
    return Cost(tracker=tracker, amount=int(found[1]))


TRACKER_COSTS: tuple[Literal["blood", "willpower"], ...] = ("blood", "willpower")


def uses(entry: Mapping[str, Any], sheet: Sheet) -> list[PowerUse]:
    """The uses of a discipline, power or [[others]] entry that change the
    trackers (`use`, issue #825), those its focus or the lack of one allows."""
    found: list[PowerUse] = []
    for u in entry.get("use", []):
        if "focus" in u and u["focus"] not in sheet.focuses:
            continue
        if u.get("unless_focus") in sheet.focuses:
            continue
        heal = u.get("heal")
        gain = u.get("gain", {})
        found.append(
            PowerUse(
                label=u["label"],
                cost=cost(u, sheet) if "cost" in u else None,
                half="half" in u.get("cost", {}).values(),
                heal=Heal(damage=heal["damage"], amount=heal.get("amount", 0)) if heal else None,
                convert=u.get("convert", 0) if u.get("convert") != "all" else 0,
                convert_all=u.get("convert") == "all",
                mend=u.get("mend", 0),
                gains=[Cost(tracker=t, amount=gain[t]) for t in TRACKER_COSTS if t in gain],
                over=gain.get("over", False),
                beast=u.get("beast", 0),
                retainer=u.get("retainer", 0),
                animal=u.get("animal", False),
                when=u.get("when"),
                once=u.get("once"),
                note=u.get("note"),
                page=_page(u) if "page" in u else None,
                target=u.get("target", "self"),
                summon=u.get("summon"),
                summon_all=u.get("summon_all", False),
                charges=_charges(u["charges"]) if "charges" in u else None,
                on=u.get("on"),
                spends=u.get("spends", False),
            )
        )
    return found


def _summon_holds(entry: Mapping[str, Any], sheet: Sheet, chosen: Mapping[str, str]) -> bool:
    """Whether a summon's variant holds for this sheet: its focus, a discipline it
    needs (`needs`), and a trait it needs (`has`: Spiritus: Primal Strength)."""
    return (
        _holds(entry, sheet, chosen)
        and _needs(entry, sheet)
        and ("has" not in entry or _has(sheet, entry["has"]))
    )


def summons(rows: Sequence[SheetRow], rule_set: RuleSetData) -> list[Summon]:
    """The allies this sheet's powers can call up (issue #827), from each entry's
    `summon`: one table or a list of them. Variants share a key, and the last that
    holds for the sheet is the one it has (Arms of the Abyss: 4 health levels, or 6
    with the Manipulation focus and a dot of Fortitude, core p. 149)."""
    return summons_of(Sheet.read(rows, rule_set), technique_bases(rule_set))


def summons_of(sheet: Sheet, bases: Mapping[str, set[str]]) -> list[Summon]:
    """The allies a sheet's powers can call up (see `summons`)."""
    found: dict[str, Summon] = {}
    for owner in owners(sheet):
        spec = owner.entry.get("summon", [])
        for entry in [spec] if isinstance(spec, Mapping) else spec:
            if not _summon_holds(entry, sheet, owner.chosen):
                continue
            most = _amount(entry.get("most", 1), sheet, bases)
            if "top" in entry:
                most = min(most, entry["top"])
            health = _amount(entry.get("health", 0), sheet, bases) + entry.get("health_add", 0)
            found[entry["key"]] = Summon(
                key=entry["key"],
                name=entry["name"],
                origin=owner.origin,
                page=_page(entry),
                note=entry.get("note", ""),
                health=max(0, health),
                blood=entry.get("blood", 0),
                most=max(0, most),
            )
    return [s for s in found.values() if s.most > 0]


def _charges(spec: Mapping[str, Any]) -> ChargeChange:
    return ChargeChange(
        counter=CHARGE + spec["counter"],
        gain=spec.get("gain", 0),
        spend=spec.get("spend", 0),
        more=spec.get("more", False),
        fill=spec.get("fill", False),
        reset=spec.get("reset", False),
    )


def _counter_held(spec: Mapping[str, Any], sheet: Sheet) -> bool:
    """Whether the character has what a counter belongs to: the discipline (and the
    power of it, if it names one), or the technique, elder or luminary power."""
    if "discipline" in spec:
        rating = sheet.disciplines.get(spec["discipline"], 0)
        power = catalogue().power(spec["discipline"], spec["power"]) if "power" in spec else None
        return rating > 0 and (
            "power" not in spec or (power is not None and power["level"] <= rating)
        )
    return any(name == spec.get("other") for _, _, name in sheet.others)


def counters_of(sheet: Sheet, bases: Mapping[str, set[str]]) -> list[Counter]:
    """The charges, points and stacks this character's powers keep (issue #826),
    each with its most for this sheet: Kineticism's one a power of it (Vol. 2 p. 72)."""
    return [
        Counter(
            key=CHARGE + c["key"],
            name=c["name"],
            unit=c.get("unit", "charge"),
            units=c.get("units", "charges"),
            most=max(0, _amount(c.get("most", 0), sheet, bases)),
            note=c.get("note"),
            page=_page(c) if "page" in c else None,
            fades=[
                CounterFade(label=f["label"], keep=f.get("keep", 0), off=f.get("off"))
                for f in c.get("fades", [])
            ],
            discipline=c.get("discipline"),
            power=c.get("power"),
            other=c.get("other"),
        )
        for c in catalogue().counters
        if _counter_held(c, sheet)
    ]


def counters(rows: Sequence[SheetRow], rule_set: RuleSetData) -> list[Counter]:
    """The counters the Play View keeps for this sheet."""
    return counters_of(Sheet.read(rows, rule_set), technique_bases(rule_set))


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
                cost=cost(spec, sheet),
                switches=[a["key"] for a in actives(spec) if not _ruled_out(a, sheet)],
                powers=[
                    PowerNote(
                        level=p["level"],
                        name=p["name"],
                        note=p["note"],
                        focus=next(
                            (n for a, n in p.get("focus", {}).items() if a in sheet.focuses), None
                        ),
                        cost=cost(p, sheet),
                        switches=[a["key"] for a in actives(p) if not _ruled_out(a, sheet)],
                        uses=uses(p, sheet),
                    )
                    for p in book.powers.get(name, [])
                    if p["level"] <= rating
                ],
            )
        )
    return found


def frenzy(sheet: Sheet, found: Sequence[Effect]) -> Frenzy:
    switched = sheet.switch_keys
    always = [e for e in found if e.pool == "frenzy" and e.when not in switched]
    return Frenzy(
        parts=[
            PoolPart(label="Mental", value=sheet.rating("attributes", "Mental")),
            *(PoolPart(label=e.source, value=e.amount) for e in always if e.amount),
        ],
        beast=[PoolPart(label=e.source, value=e.beast) for e in always if e.beast],
        switched_beast=[
            SwitchedPart(switch=e.when, label=e.source, value=e.beast)
            for e in found
            if e.pool == "frenzy" and e.beast and e.when is not None and e.when in switched
        ],
    )


def other_notes(found: Sequence[Effect], shown: Collection[str] = ()) -> list[str]:
    """Modifiers for pools not shown (skills, frenzy), and those on every pool. A
    skill's that a pool `shown` already counts is left out."""
    notes: list[str] = []
    for e in found:
        if e.pool in shown and not e.instead_of:
            continue
        if e.pool.startswith("skill:") and not e.instead_of and e.amount:
            when = f" {e.when}" if e.when else ""
            notes.append(
                f"{e.source}: {_signed(e.amount)} to {e.pool.removeprefix('skill:')}{when}"
            )
        elif e.pool.startswith("skill:") and e.instead_of:
            other = e.pool.removeprefix("skill:")
            notes.append(f"{e.source}: use {other} in place of {', '.join(e.instead_of)}")
        elif e.pool == "all":
            notes.append(f"{e.source}: {_signed(e.amount)} to every pool {e.when or ''}".strip())
        elif e.pool == "frenzy" and (e.note or e.amount):
            notes.append(f"{e.source}: {e.note or _signed(e.amount) + ' to resist frenzy'}")
    return notes


def other_powers(sheet: Sheet, rule_set: RuleSetData) -> list[OtherPower]:
    """Techniques, elder and luminary powers, each with its note from the catalogue
    and, from its [[others]] entry when it works for this sheet, its cost and switches."""
    book = catalogue()
    found: list[OtherPower] = []
    for category, category_name, name in sorted(sheet.others):
        trait = rule_set.traits.get((category, name))
        entry = book.others.get((category, name), {})
        if not _needs(entry, sheet):
            entry = {}
        found.append(
            OtherPower(
                category_name=category_name,
                name=name,
                note=trait.description if trait else None,
                page=trait.page_reference if trait else None,
                cost=cost(entry, sheet),
                switches=[a["key"] for a in actives(entry) if not _ruled_out(a, sheet)],
                uses=uses(entry, sheet),
            )
        )
    return found


def reference(
    rows: Sequence[SheetRow],
    rule_set: RuleSetData,
    blood_per_turn: int,
    foreign: Sequence[Switch] = (),
) -> Reference:
    """The Pools tab's reference. `foreign` are the switches of effects another
    character's power left on this one (issue #823): what they do to its attributes
    counts in its pools while on, though it hasn't the power."""
    sheet = Sheet.read(rows, rule_set)
    worked = work_out(sheet, technique_bases(rule_set))
    found = worked.effects
    made = pools(sheet, found, worked.hurts, [*worked.switches, *foreign])
    return Reference(
        pools=made,
        frenzy=frenzy(sheet, found),
        disciplines=disciplines(sheet),
        other_powers=other_powers(sheet, rule_set),
        notes=other_notes(found, {p.key for p in made}),
        blood_per_turn=blood_per_turn,
    )
