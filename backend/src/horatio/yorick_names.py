"""Yorick's names for traits, as its Print Characters page prints them, matched to
Horatio's catalogue (issue #482).

What it knows is kept in one table, `yorick_names.toml` beside this file, for the
troupe to review and extend; each troupe's own names (horatio.yorick_imports) are
added over it. Besides that
table, Horatio's own spelling fixes stand: the merits, flaws, powers and rituals
renamed to match the books (migrations 0106 and 0122, issue #410) are matched under
their old names too.

Each printed line becomes a trait in a category, with a name from the catalogue (or
the troupe's house merits and flaws), a detail where the trait is held once for each
of several (Retainers, Crafts, a Derangement, a path's Thaumaturgic Expertise), a
rating, and a note for anything else the line said. A line that matches nothing is
kept aside, with why, for the report.

Yorick prints no extra in-clan disciplines, only what a player wrote in the sheet's
notes (horatio.yorick_print). So a discipline an "In clan:" line names beyond the
clan's own, or that a merit such as Additional Common Discipline names in its detail,
is put under Extra In-Clan Disciplines (#565); the sheet's checks say if the rules
don't allow it.
"""

import ast
import re
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from horatio.rules.model import RuleSetData
from horatio.yorick_print import Line, PrintedCharacter

TABLE = Path(__file__).with_name("yorick_names.toml")
MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations" / "versions"
# The migrations that renamed traits to match the books, with their (category, old,
# new) lists.
SPELLING_MIGRATIONS = ("0106", "0122")
SPELLING_LISTS = ("RENAMES", "MERGES")

CUSTOM = "Custom"
EXTRA_IN_CLAN = "extra_in_clan_disciplines"
FOCUSES = {
    "Physical": "focus_physicals",
    "Social": "focus_socials",
    "Mental": "focus_mentals",
}


def plain(text: str) -> str:
    """For comparing names: no case, curly quotes, doubled spaces or trailing dots."""
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"')
    return " ".join(text.replace("”", '"').split()).strip(" .").casefold()


# --- the table ----------------------------------------------------------------------------


@dataclass
class Table:
    """What the mapping table says (see yorick_names.toml for each part)."""

    headings: dict[str, str]
    left_out: dict[str, str]
    identity: dict[str, str]
    # By category: Yorick's name, plain, to Horatio's.
    names: dict[str, dict[str, str]]
    # By category: a specialisation's value, plain, to Horatio's.
    values: dict[str, dict[str, str]]
    paths: dict[str, str]
    # Merits and flaws whose detail names a path, besides those the rules say.
    path_details: dict[str, list[str]]
    detail_names: dict[str, set[str]]
    # Merits whose detail names the discipline they make in-clan.
    in_clan_details: set[str]
    custom: set[str]
    split: set[str]

    def name_for(self, category: str, name: str) -> str | None:
        return self.names.get(category, {}).get(plain(name))

    def value_for(self, category: str, value: str) -> str | None:
        return self.values.get(category, {}).get(plain(value))


def spelling_renames(directory: Path = MIGRATIONS) -> list[tuple[str, str, str]]:
    """The (category, old, new) renames of the spelling migrations, read from their
    source rather than imported, so nothing in them runs."""
    found: list[tuple[str, str, str]] = []
    for number in SPELLING_MIGRATIONS:
        for path in sorted(directory.glob(f"{number}_*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in tree.body:
                if not isinstance(node, ast.Assign):
                    continue
                targets = {t.id for t in node.targets if isinstance(t, ast.Name)}
                if targets & set(SPELLING_LISTS):
                    found += [tuple(r) for r in ast.literal_eval(node.value)]
    return found


def read_table(
    paths: Sequence[Path] = (),
    *,
    renames: Iterable[tuple[str, str, str]] = (),
    more: Sequence[Mapping[str, Any]] = (),
) -> Table:
    """The bundled table, then each of `paths` over it, then each of `more` (a table
    already read, such as a troupe's own), with the spelling renames underneath."""
    raw: dict[str, Any] = {}
    for path in (TABLE, *paths):
        merge(raw, tomllib.loads(path.read_text(encoding="utf-8")))
    for table in more:
        merge(raw, table)
    names: dict[str, dict[str, str]] = {}
    for category, old, new in renames:
        names.setdefault(category, {})[plain(old)] = new
    for category, table in raw.get("names", {}).items():
        names.setdefault(category, {}).update({plain(k): v for k, v in table.items()})
    values = {
        category: {plain(k): v for k, v in table.items()}
        for category, table in raw.get("values", {}).items()
    }
    # One list of values can serve several categories (both Influences).
    for category, others in raw.get("same_values", {}).items():
        for other in others:
            values[other] = {**values.get(category, {}), **values.get(other, {})}
    return Table(
        headings=dict(raw.get("headings", {})),
        left_out=dict(raw.get("left_out", {})),
        identity=dict(raw.get("identity", {})),
        names=names,
        values=values,
        paths={plain(k): v for k, v in raw.get("paths", {}).items()},
        path_details={k: list(v) for k, v in raw.get("path_details", {}).items()},
        detail_names={k: set(v) for k, v in raw.get("detail_names", {}).items()},
        in_clan_details=set(raw.get("in_clan_details", [])),
        custom=set(raw.get("custom_allowed", [])),
        split=set(raw.get("split_on_commas", [])),
    )


def merge(into: dict[str, Any], more: Mapping[str, Any]) -> None:
    """A later table adds to an earlier one: its tables merge, its lists add."""
    for key, value in more.items():
        if isinstance(value, Mapping) and isinstance(into.get(key), dict):
            merge(into[key], value)
        elif isinstance(value, list) and isinstance(into.get(key), list):
            into[key] = [*into[key], *value]
        else:
            into[key] = value


# --- the catalogue ------------------------------------------------------------------------


@dataclass(frozen=True)
class Catalogue:
    """The traits a character in the troupe can hold, as the import needs them."""

    # By category, every name.
    names: Mapping[str, frozenset[str]]
    # The categories that are kinds of specialisation (horatio.specializations).
    kinds: frozenset[str] = frozenset()
    # (category, name) of the traits whose detail says which one, or what for: those
    # held once for each of several (Retainers, Crafts, a Derangement), and those
    # that give a trait the detail names (Angelic Visage's focus, Inept's discipline).
    detailed: frozenset[tuple[str, str]] = frozenset()
    # Those whose detail names a path (Thaumaturgic Expertise), with the disciplines
    # the path may be of.
    path_detailed: Mapping[tuple[str, str], tuple[str, ...]] = field(default_factory=dict)
    # The troupe's own lists of a kind of specialisation (horatio.specializations).
    lists: Mapping[str, Sequence[str]] = field(default_factory=dict)
    # Each clan's own in-clan disciplines, with those it leaves its player to choose
    # from.
    clans: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def find(self, category: str, name: str) -> str | None:
        """The catalogue's name for `name`, ignoring case and spacing."""
        names = self.names.get(category, frozenset())
        if name in names:
            return name
        wanted = plain(name)
        return next((n for n in sorted(names) if plain(n) == wanted), None)


def catalogue_of(
    rule_set: RuleSetData, lists: Mapping[str, Sequence[str]] | None = None
) -> Catalogue:
    """The catalogue of a rule set (as a troupe has it, with its house traits), and the
    troupe's specialisation lists."""
    names: dict[str, set[str]] = {}
    detailed: set[tuple[str, str]] = set()
    for (category, name), trait in rule_set.traits.items():
        names.setdefault(category, set()).add(name)
        if trait.properties.get("requires_specialization") or trait.properties.get("instance"):
            detailed.add((category, name))
    clans = {
        name: (*trait.properties.get("in_clan", []), *trait.properties.get("choices", []))
        for (category, name), trait in rule_set.traits.items()
        if category == "clan"
    }
    path_detailed: dict[tuple[str, str], tuple[str, ...]] = {}
    for grant in rule_set.grants:
        source = (grant.source.get("category", ""), grant.source.get("name", ""))
        prefix = grant.target.get("choose_prefix")
        if prefix:
            path_detailed[source] = (prefix.rstrip(": "),)
        elif grant.target.get("choose"):
            detailed.add(source)
    return Catalogue(
        names={category: frozenset(found) for category, found in names.items()},
        kinds=frozenset(c.key for c in rule_set.categories.values() if c.specializes),
        detailed=frozenset(detailed),
        path_detailed=path_detailed,
        lists=dict(lists or {}),
        clans=clans,
    )


# --- what a line becomes ------------------------------------------------------------------


@dataclass
class Trait:
    category: str
    name: str
    detail: str = ""
    # None for a trait with no rating, such as a clan.
    rating: int | None = None
    note: str = ""
    # Where on the printed sheet it came from: "Merits: Arcane (1)".
    source: str = ""


@dataclass
class Unmatched:
    heading: str
    text: str
    reason: str
    # The line in the table that would match it, where one would: its part ("names",
    # "values" or "paths"), category, and Yorick's name for it. A heading the table
    # has no category for has none: staff put that right by hand.
    table: str = ""
    category: str = ""
    key: str = ""

    @property
    def source(self) -> str:
        return f"{self.heading}: {self.text}"


@dataclass
class Mapped:
    """A printed character as Horatio's traits."""

    traits: list[Trait] = field(default_factory=list)
    unmatched: list[Unmatched] = field(default_factory=list)
    # What the printout says that the import leaves to staff, by design: its title,
    # its status, its antecedence.
    left_out: list[str] = field(default_factory=list)
    # Lines read as more than one trait ("Custom: French, Korean").
    split: list[str] = field(default_factory=list)


class Mapper:
    def __init__(self, table: Table, catalogue: Catalogue) -> None:
        self.table = table
        self.catalogue = catalogue

    # --- names ---

    def lookup(self, category: str, name: str) -> str | None:
        """Horatio's name for a trait Yorick calls `name`: the table's, else the
        catalogue's own, ignoring case and spacing."""
        named = self.table.name_for(category, name)
        if named is not None:
            return self.catalogue.find(category, named)
        return self.catalogue.find(category, name)

    def path(
        self, text: str, disciplines: Sequence[str] = ("Thaumaturgy", "Necromancy")
    ) -> str | None:
        """The Thaumaturgy or Necromancy path `text` names, written any of the ways
        Yorick's players wrote them: "Path of Conjuring", "The Path of Conjuring",
        "Conjuring", "Path of Ash", "Ash Path", "Thaumaturgy: Green Path"."""
        named = self.table.paths.get(plain(text))
        if named is not None:
            return self.catalogue.find("disciplines", named)
        wanted = path_words(text)
        if not wanted:
            return None
        found = [
            n
            for n in self.catalogue.names.get("disciplines", frozenset())
            if n.split(":")[0] in disciplines and ":" in n and path_words(n) == wanted
        ]
        return found[0] if len(found) == 1 else None

    def is_detailed(self, category: str, name: str) -> bool:
        return (category, name) in self.catalogue.detailed or name in self.table.detail_names.get(
            category, set()
        )

    # --- a character ---

    def character(self, printed: PrintedCharacter) -> Mapped:
        mapped = Mapped()
        self.identity(printed, mapped)
        self.attributes(printed, mapped)
        if printed.morality is not None:
            name, rating = printed.morality
            found = self.lookup("paths", name)
            if found is None:
                mapped.unmatched.append(
                    Unmatched("Morality", name, "no such Morality", "names", "paths", name)
                )
            else:
                mapped.traits.append(
                    Trait("paths", found, rating=rating, source=f"Morality: {name}")
                )
        for line in printed.skills:
            self.skill(line, mapped)
        for heading, lines in printed.sections.items():
            if heading in self.table.left_out:
                mapped.left_out += [f"{heading}: {line.text}" for line in lines]
                continue
            category = self.table.headings.get(heading)
            for line in lines:
                if category is None:
                    mapped.unmatched.append(Unmatched(heading, line.text, "no such heading"))
                elif category in self.catalogue.kinds:
                    self.specialization(heading, category, line, mapped)
                else:
                    self.trait(heading, category, line, mapped)
        self.in_clan(printed, mapped)
        mapped.traits = combined(mapped.traits)
        return mapped

    def starting(self, category: str, text: str) -> tuple[str, str] | None:
        """The longest trait name `text` starts with, as a whole word, and the rest."""
        text = " ".join(text.split())
        # (how it is written, Horatio's name, the rest of the text)
        best: tuple[str, str, str] | None = None
        candidates = [(n, n) for n in self.catalogue.names.get(category, frozenset())]
        candidates += [
            (n, self.table.name_for(category, n) or "") for n in self.table.names.get(category, {})
        ]
        for written, name in candidates:
            if not name or not text.casefold().startswith(written.casefold()):
                continue
            rest = text[len(written) :]
            if rest[:1].isalnum() or (best is not None and len(written) <= len(best[0])):
                continue
            found = self.catalogue.find(category, name)
            if found is not None:
                best = (written, found, rest)
        if best is None:
            return None
        return best[1], best[2].strip(" -:,;\u2013").removeprefix("(").removesuffix(")")

    def path_disciplines(self, category: str, name: str) -> tuple[str, ...] | None:
        """For a trait whose detail names a path, the disciplines the path may be of."""
        found = self.catalogue.path_detailed.get((category, name))
        if found is None and name in self.table.path_details:
            found = tuple(self.table.path_details[name])
        return found

    def identity(self, printed: PrintedCharacter, mapped: Mapped) -> None:
        for key, value in printed.identity.items():
            category = self.table.identity.get(key)
            if category is None:
                if key in self.table.left_out:
                    mapped.left_out.append(f"{key}: {value}")
                else:
                    mapped.unmatched.append(Unmatched(key, value, "no such heading"))
                continue
            found = self.lookup(category, value)
            if found is None:
                mapped.unmatched.append(
                    Unmatched(key, value, f"no such {key.lower()}", "names", category, value)
                )
            else:
                mapped.traits.append(Trait(category, found, source=f"{key}: {value}"))

    def attributes(self, printed: PrintedCharacter, mapped: Mapped) -> None:
        for name, attribute in printed.attributes.items():
            found = self.lookup("attributes", name)
            if found is None:
                mapped.unmatched.append(Unmatched(name, str(attribute.rating), "no such attribute"))
                continue
            mapped.traits.append(
                Trait(
                    "attributes",
                    found,
                    rating=attribute.rating,
                    source=f"{name}: {attribute.rating}",
                )
            )
            category = FOCUSES.get(found)
            if category is None or not attribute.focuses:
                continue
            words, _, note = attribute.focuses.partition(":")
            for word in words.split():
                focus = self.lookup(category, word)
                if focus is None:
                    mapped.unmatched.append(
                        Unmatched(f"{name} focus", word, "no such focus", "names", category, word)
                    )
                else:
                    mapped.traits.append(
                        Trait(
                            category,
                            focus,
                            rating=1,
                            note=note.strip(" ()"),
                            source=f"{name}: {attribute.focuses}",
                        )
                    )

    def skill(self, line: Line, mapped: Mapped) -> None:
        found = self.lookup("skills", line.name)
        if found is None:
            mapped.unmatched.append(
                Unmatched("Skills", line.text, "no such skill", "names", "skills", line.name)
            )
            return
        detailed = self.is_detailed("skills", found)
        mapped.traits.append(
            Trait(
                "skills",
                found,
                detail=line.detail if detailed else "",
                rating=line.rating or 1,
                note="" if detailed else line.detail,
                source=f"Skills: {line.text}",
            )
        )

    def trait(self, heading: str, category: str, line: Line, mapped: Mapped) -> None:
        """A background, discipline, technique, ritual, merit or flaw."""
        source = f"{heading}: {line.text}"
        name, detail = line.name, line.detail
        found: str | None = None
        # "Influences x4: The Elite", "Bloodline (2, Coyote)", "Gangrel (1, Rat in a
        # Cage)", "Thaumaturgy x3: Path of Blood": the detail is the rest of the name.
        if detail:
            found = self.lookup(category, f"{name}: {detail}")
            if found is not None:
                detail = ""
            else:
                # "Influences x3: The Underworld (Occult)", "Malkavian (1, Feeding
                # Fetish, Can only feed...)": the name, and a note after it.
                joined = self.starting(category, f"{name}: {detail}")
                if joined is not None:
                    found, detail = joined
        if found is None and category == "disciplines" and detail:
            found = self.path(f"{name}: {detail}", (name,))
            if found is not None:
                detail = ""
        if found is None:
            found = self.lookup(category, name)
        if found is None:
            # "Addiction (Hallucinogen)" where the catalogue has only "Addiction".
            bracketed = re.fullmatch(r"(.*?)\s*\((.*)\)", name)
            if bracketed is not None:
                found = self.lookup(category, bracketed[1])
                if found is not None:
                    detail = ", ".join(d for d in (bracketed[2], detail) if d)
        if found is None:
            # A discipline's path is named with it ("Thaumaturgy x3: Path of Blod"); else
            # the name alone is matched, its detail kept.
            key = f"{name}: {detail}" if category == "disciplines" and detail else name
            mapped.unmatched.append(
                Unmatched(
                    heading, line.text, f"no such {category_word(category)}", "names", category, key
                )
            )
            return
        note = ""
        disciplines = self.path_disciplines(category, found)
        if detail and disciplines is not None:
            path = self.path(detail, disciplines)
            if path is None:
                mapped.unmatched.append(
                    Unmatched(
                        heading,
                        line.text,
                        f"no such path: {detail}",
                        "paths",
                        "disciplines",
                        detail,
                    )
                )
                return
            detail = path
        elif detail and not self.is_detailed(category, found):
            note, detail = detail.lstrip("- ").strip(), ""
        # A line with no rating (a technique, a ritual) is held at its value, or 1.
        rating = abs(line.rating) if line.rating is not None else None
        mapped.traits.append(Trait(category, found, detail, rating, note, source))

    def in_clan(self, printed: PrintedCharacter, mapped: Mapped) -> None:
        """The disciplines in-clan beyond the clan's own, as Extra In-Clan Disciplines:
        those the notes' "In clan:" line names, and the one a merit that adds an
        in-clan discipline names in its detail ("Vestiges of Greatness (3,
        Vicissitude)"). A path the line names goes first to a Thaumaturgic or
        Necromantic Expertise printed without its path."""
        clan = next((t.name for t in mapped.traits if t.category == "clan"), "")
        own = set(self.catalogue.clans.get(clan, ()))
        # Paths a merit prices in-clan itself (Thaumaturgic Expertise, Necromantic
        # Insight): the merit says so already.
        by_merit = {
            t.detail for t in mapped.traits if (t.category, t.name) in self.catalogue.path_detailed
        }
        held = [t.name for t in mapped.traits if t.category == "disciplines"]
        extras = self.catalogue.names.get(EXTRA_IN_CLAN, frozenset())
        source = f"In clan: {', '.join(printed.in_clan)}"
        found: list[tuple[str, str]] = []
        for written in printed.in_clan:
            # "Thaumaturgy" alone: the clan's own path of it, or else the one path of it
            # the character holds.
            base = next(
                (b for b in ("Thaumaturgy", "Necromancy") if plain(b) == plain(written)), ""
            )
            if base and any(n.startswith(f"{base}: ") for n in own):
                continue
            name = self.lookup(EXTRA_IN_CLAN, written)
            if name is None and base:
                paths = [n for n in held if n.startswith(f"{base}: ") and n in extras]
                name = paths[0] if len(paths) == 1 else None
            elif name is None:
                path = self.path(written)
                name = path if path in extras else None
            reason = f"which path of {base}?" if base else "no such discipline"
            if name is None:
                mapped.unmatched.append(
                    Unmatched("In clan", written, reason, "names", EXTRA_IN_CLAN, written)
                )
            else:
                found.append((name, source))
        for t in mapped.traits:
            if t.category == "merits" and t.name in self.table.in_clan_details and t.note:
                name = self.lookup(EXTRA_IN_CLAN, t.note)
                if name is not None:
                    found.append((name, t.source))
        for name, where in found:
            if name in own or name in by_merit or self.give_path(name, mapped):
                continue
            by_merit.add(name)
            mapped.traits.append(Trait(EXTRA_IN_CLAN, name, rating=1, source=where))

    def give_path(self, path: str, mapped: Mapped) -> bool:
        """Name `path` in the detail of a merit that prices a path in-clan but was
        printed without one ("Thaumaturgical Expertise (1)"), if the character holds
        such a merit for the path's discipline: that is what makes it in-clan."""
        discipline = path.split(":")[0]
        blank = next(
            (
                t
                for t in mapped.traits
                if not t.detail
                and discipline in self.catalogue.path_detailed.get((t.category, t.name), ())
            ),
            None,
        )
        if blank is None or ":" not in path:
            return False
        blank.detail = path
        return True

    def specialization(self, heading: str, category: str, line: Line, mapped: Mapped) -> None:
        """A Haven quality, an Influence's area, a Contact, a Lore, a Language..."""
        source = f"{heading}: {line.text}"
        rating = line.rating if line.rating is not None else 1
        note = ""
        if line.rating is None:
            # "Custom: Fae", "Camarilla", "Cappadocians: Samedi", "Spanish: Native".
            value = line.text
            if plain(value).startswith("custom:"):
                value = value.split(":", 1)[1]
        elif plain(line.name) == "custom":
            value = line.detail
        elif line.detail and self.value(category, line.detail) is not None:
            # "Bureaucracy x1: Local Government": the area is the detail.
            value, note = line.detail, line.name
        else:
            value, note = line.name, line.detail
        value = value.strip().strip("[]").strip()
        parts = [p.strip() for p in value.split(",") if p.strip()]
        if len(parts) > 1 and category in self.table.split and self.value(category, value) is None:
            mapped.split.append(source)
        else:
            parts = [value]
        for part in parts:
            found = self.value(category, part)
            detail = ""
            if found is None:
                # "Spanish: Native", "Law Enforcement (Crooked Cops)": a value and a note.
                head = re.fullmatch(r"(.*?)\s*(?::\s*|\()(.*?)\)?", part)
                if head is not None and self.value(category, head[1]) is not None:
                    found = self.value(category, head[1])
                    note = ", ".join(n for n in (note, head[2]) if n)
            if found is None:
                if category not in self.table.custom or not self.catalogue.find(category, CUSTOM):
                    reason = (
                        "not on the troupe's list"
                        if category in self.catalogue.lists
                        else f"no such {category_word(category)}"
                    )
                    mapped.unmatched.append(
                        Unmatched(heading, line.text, f"{reason}: {part}", "values", category, part)
                    )
                    continue
                found, detail = CUSTOM, part
            mapped.traits.append(Trait(category, found, detail, rating, note, source))

    def value(self, category: str, value: str) -> str | None:
        """A specialisation's value as Horatio has it: on the troupe's list where it
        has one, else in the catalogue."""
        named = self.table.value_for(category, value) or value
        listed = self.catalogue.lists.get(category)
        if listed is not None:
            return next((n for n in listed if plain(n) == plain(named)), None)
        found = self.catalogue.find(category, named)
        return found if found != CUSTOM else None


def path_words(text: str) -> frozenset[str]:
    """The words that pick a path out: "Thaumaturgy: The Path of Elemental Mastery" and
    "Elemental Mastery" are both {elemental, mastery}."""
    text = text.split(":", 1)[1] if ":" in text else text
    words = re.findall(r"[a-z']+", plain(text))
    return frozenset(w for w in words if w not in {"the", "path", "of"})


def category_word(category: str) -> str:
    return {
        "backgrounds": "background",
        "disciplines": "discipline",
        "techniques": "technique",
        "elder_disciplines": "elder power",
        "luminary_disciplines": "luminary power",
        "rituals": "ritual",
        "sabbat_rituals": "Sabbat ritus",
        "merits": "merit",
        "flaws": "flaw",
        "haven_specializations": "Haven quality",
        "influence_elite_specializations": "Influence area",
        "influence_underworld_specializations": "Influence area",
        "lore_specializations": "Lore",
        "linguistics_specializations": "language",
        "academics_specializations": "Academics field",
        "drive_specializations": "kind of vehicle",
        "contacts_specializations": "Contact",
        "allies_specializations": "Ally",
    }.get(category, category.replace("_", " "))


def combined(traits: list[Trait]) -> list[Trait]:
    """One trait for each (category, name, detail): a line printed twice, or two
    lines that are one trait in Horatio, at the higher rating, notes together."""
    found: dict[tuple[str, str, str], Trait] = {}
    for trait in traits:
        key = (trait.category, trait.name, trait.detail)
        held = found.get(key)
        if held is None:
            found[key] = trait
            continue
        if (trait.rating or 0) > (held.rating or 0):
            held.rating = trait.rating
        held.note = "; ".join(n for n in dict.fromkeys((held.note, trait.note)) if n)
        held.source = f"{held.source}; {trait.source}"
    return list(found.values())
