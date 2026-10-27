"""NPC kinds (issue #215): what an NPC is, such as a werewolf, a mage or a mortal
hunter, for NPCs built on the Vampire rule set. Each kind is rules data, in
`data/bns_met_npc_kinds.toml` (MET: VTM ch. 12, pp. 489–505); see the top of that
file for its shape.

A kind is not a splat: every NPC kind plays by the Vampire rule set, as the book
has it ("a framework for using such creatures in a Vampire chronicle", p. 490).
"""

import tomllib
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field, replace
from functools import cache
from pathlib import Path
from typing import Any, Literal

from horatio.rules.files import DATA_DIR
from horatio.rules.splats import NO_VAMPIRE_PANELS, Panels

KINDS_FILE = DATA_DIR / "bns_met_npc_kinds.toml"
Nature = Literal["mortal", "partly_mortal", "supernatural"]
NATURES: tuple[Nature, ...] = ("mortal", "partly_mortal", "supernatural")
GROUPS = ("vampire", "mortal", "hunter", "supernatural", "bloodline", "custom")
# A Stock NPC's rating, unless its kind says otherwise (p. 489).
RATING_MAX = 5
# The most dots of a discipline anything gives a Stock NPC: no elder powers (p. 490).
MAX_DOTS = 5


@dataclass(frozen=True)
class Resource:
    """What an NPC spends on its powers, as a vampire spends Blood."""

    name: str
    size: int
    # The most it can spend in a turn; 0 for none at all (a mortal's Blood).
    per_turn: int
    # How it comes back, in words ("1 every five turns"); empty for not by itself.
    regains: str = ""


def stock_blood(nature: Nature) -> Resource:
    """A Stock NPC's Blood (p. 490): 5 for a mortal or partly mortal one, 10 for a
    supernatural one, spent 1 a turn. Only ghouls among mortals can spend theirs."""
    if nature == "supernatural":
        return Resource("Blood", 10, 1)
    return Resource("Blood", 5, 1 if nature == "partly_mortal" else 0)


@dataclass(frozen=True)
class Numina:
    """Powers of the kind's own that the Vampire rule set does not have, such as
    True Faith, taken as a specialization like a discipline."""

    name: str
    page: int
    # What each dot gives, from the first.
    levels: tuple[str, ...]


@dataclass(frozen=True)
class BuiltInPower:
    """What every NPC of a kind has: dots of a discipline, or one power or merit."""

    name: str
    # Dots of the discipline `name`: a number, or "rating" for the NPC's rating.
    # None for a single power or merit.
    dots: int | Literal["rating"] | None = None
    # The discipline a single power belongs to, or the category of a merit.
    discipline: str | None = None
    category: str | None = None
    # It comes only at this NPC rating or above.
    from_rating: int | None = None
    note: str = ""

    def dots_at(self, rating: int) -> int:
        """The dots it gives at `rating`; 0 for a single power."""
        if self.dots is None:
            return 0
        return min(rating if self.dots == "rating" else self.dots, MAX_DOTS)


@dataclass(frozen=True)
class NpcKind:
    key: str
    name: str
    group: str
    nature: Nature
    page: int
    to_page: int | None
    resource: Resource
    # Names a discipline specialization may take, or "any" discipline or path.
    # "Thaumaturgy: *" stands for any Thaumaturgy path.
    specializations: tuple[str, ...] | Literal["any"] = ()
    specialization_label: str = ""
    numina: tuple[Numina, ...] = ()
    powers: tuple[BuiltInPower, ...] = ()
    health_per_rating: int = 1
    rating_max: int = RATING_MAX
    notes: tuple[str, ...] = ()
    # The storyteller names it and sets its nature and resource, on each NPC.
    custom: bool = False
    # A custom kind's own name, as the storyteller gave it.
    custom_name: str = field(default="", compare=False)

    @property
    def mortal(self) -> bool:
        """Wholly mortal: not a ghoul, which is partly so."""
        return self.nature == "mortal"

    @property
    def label(self) -> str:
        return self.custom_name or self.name

    @property
    def vampiric(self) -> bool:
        """A vampire, a ghoul or one of the vampire bloodlines: those whose sheet is
        the Vampire sheet as it stands."""
        return self.group in ("vampire", "bloodline")

    @property
    def panels(self) -> Panels:
        """The sheet and Play View panels that apply to the kind. Any other kind
        has its own resource in Blood's place (Rage, Essence) and no Beast,
        Humanity or Generation."""
        if self.vampiric:
            return Panels(feed=self.resource.name == "Blood" and self.resource.per_turn > 0)
        return NO_VAMPIRE_PANELS

    def may_specialize(self, name: str, disciplines: Collection[str]) -> bool:
        """Whether a discipline specialization in `name` is open to this kind:
        one of its own numina, or a discipline or path in `disciplines` that its
        list allows."""
        if any(n.name == name for n in self.numina):
            return True
        if name not in disciplines:
            return False
        if self.specializations == "any":
            return True
        return any(matches(pattern, name) for pattern in self.specializations)


def matches(pattern: str, name: str) -> bool:
    """ "Thaumaturgy: *" matches any Thaumaturgy path; any other pattern, itself."""
    if pattern.endswith(": *"):
        return name.startswith(pattern[:-1])
    return pattern == name


def custom_kind(base: NpcKind, name: str, nature: Nature, resource: Resource) -> NpcKind:
    """The custom kind as a storyteller set it up for one NPC. A mortal one takes
    skill specializations only, as any mortal does (p. 489)."""
    return replace(
        base,
        custom_name=name,
        nature=nature,
        resource=resource,
        specializations=() if nature == "mortal" else "any",
    )


def _resource(source: str, raw: Any, nature: Nature) -> Resource:
    if raw is None:
        return stock_blood(nature)
    if not isinstance(raw, Mapping) or not raw.get("name"):
        raise ValueError(f"{source}: a resource needs a name")
    size, per_turn = raw.get("size"), raw.get("per_turn")
    if not isinstance(size, int) or size < 1 or not isinstance(per_turn, int) or per_turn < 0:
        raise ValueError(f"{source}: {raw['name']} needs a size and a per_turn")
    return Resource(str(raw["name"]), size, per_turn, str(raw.get("regains", "")))


def _power(source: str, raw: Mapping[str, Any]) -> BuiltInPower:
    dots = raw.get("dots")
    if dots is not None and dots != "rating" and not (isinstance(dots, int) and 1 <= dots <= 5):
        raise ValueError(f'{source}: {raw.get("name")!r} dots are 1 to 5 or "rating"')
    if not raw.get("name") or (
        dots is None and not raw.get("discipline") and not raw.get("category")
    ):
        raise ValueError(f"{source}: a power needs a name, and dots, a discipline or a category")
    return BuiltInPower(
        name=raw["name"],
        dots=dots,
        discipline=raw.get("discipline"),
        category=raw.get("category"),
        from_rating=raw.get("from_rating"),
        note=raw.get("note", ""),
    )


def load_npc_kinds(path: Path = KINDS_FILE) -> dict[str, NpcKind]:
    """Every kind in the file, by key, in its order there."""
    with path.open("rb") as f:
        data = tomllib.load(f)
    kinds: dict[str, NpcKind] = {}
    for raw in data.get("kinds", []):
        key = raw.get("key")
        source = f"{path.name}: {key!r}"
        if not key or not raw.get("name") or key in kinds:
            raise ValueError(f"{source}: each kind needs a key of its own and a name")
        nature = raw.get("nature")
        if nature not in NATURES:
            raise ValueError(f"{source}: nature is one of {', '.join(NATURES)}")
        if raw.get("group") not in GROUPS:
            raise ValueError(f"{source}: group is one of {', '.join(GROUPS)}")
        if not isinstance(raw.get("page"), int):
            raise ValueError(f"{source}: needs the page its rules are on")
        specializations = raw.get("specializations", [])
        if specializations != "any" and not (
            isinstance(specializations, list) and all(isinstance(s, str) for s in specializations)
        ):
            raise ValueError(f'{source}: specializations are "any" or a list of names')
        kinds[key] = NpcKind(
            key=key,
            name=raw["name"],
            group=raw["group"],
            nature=nature,
            page=raw["page"],
            to_page=raw.get("to_page"),
            resource=_resource(source, raw.get("resource"), nature),
            specializations="any" if specializations == "any" else tuple(specializations),
            specialization_label=raw.get("specialization_label", ""),
            numina=tuple(
                Numina(n["name"], n["page"], tuple(n["levels"])) for n in raw.get("numina", [])
            ),
            powers=tuple(_power(source, p) for p in raw.get("powers", [])),
            health_per_rating=raw.get("health_per_rating", 1),
            rating_max=raw.get("rating_max", RATING_MAX),
            notes=tuple(raw.get("notes", [])),
            custom=bool(raw.get("custom", False)),
        )
    return kinds


@cache
def npc_kinds() -> dict[str, NpcKind]:
    return load_npc_kinds()


def kind_name(key: str | None, custom: Mapping[str, Any] | None) -> str | None:
    """What an NPC's kind is called: a custom kind by the name staff gave it."""
    if key is None:
        return None
    if custom and custom.get("name"):
        return str(custom["name"])
    kind = npc_kinds().get(key)
    return kind.name if kind is not None else key
